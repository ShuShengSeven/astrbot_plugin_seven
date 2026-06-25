from __future__ import annotations

import asyncio
import time
from typing import Any

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, MessageChain, filter
from astrbot.api.star import Context, Star

from .channel_client import TencentChannelCliClient
from .plugin_config import PluginConfigModel
from .review_service import ReviewService
from .storage import PluginStorage


class ChannelInspectPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.raw_config = config
        self.config_model = PluginConfigModel.from_dict(dict(config))
        self.storage = PluginStorage("astrbot_plugin_channel_inspect")
        self.cli = TencentChannelCliClient(
            cli_path=self.config_model.cli.cli_path,
            timeout_seconds=self.config_model.cli.timeout_seconds,
            detail_timeout_seconds=self.config_model.cli.detail_timeout_seconds,
            rate_limit_retry_seconds=self.config_model.cli.rate_limit_retry_seconds,
            dev_mode=self.config_model.dev_mode,
        )
        self.review_service = ReviewService(self.context, self.config_model, self.storage, self.cli)
        self._task: asyncio.Task | None = None
        self._lock = asyncio.Lock()
        self._stop_event = asyncio.Event()

    def _debug(self, message: str, **kwargs: Any) -> None:
        if not self.config_model.dev_mode:
            return
        if kwargs:
            logger.debug("[channel_inspect][debug] %s | %s", message, kwargs)
            return
        logger.debug("[channel_inspect][debug] %s", message)

    @filter.on_astrbot_loaded()
    async def on_astrbot_loaded(self):
        self._debug(
            "plugin.loaded",
            enabled=self.config_model.enabled,
            dev_mode=self.config_model.dev_mode,
            guild_id=self.config_model.channel.guild_id,
            scan_strategy=self.config_model.channel.scan_strategy,
            feed_source_mode=self.config_model.channel.feed_source_mode,
            dry_run=self.config_model.auto_review.dry_run,
            image_review_mode=self.config_model.review.image_review_mode,
            suspect_channel_id=self.config_model.channel.suspect_channel_id,
        )
        errors = self.config_model.validate()
        if errors:
            self.storage.patch_state(task_status="config_error", config_errors=errors)
            logger.error("频道巡检插件配置错误: %s", " | ".join(errors))
            return

        startup_result = await self.review_service.run_startup_check()
        self._debug("plugin.startup_check", result=startup_result)
        self.storage.patch_state(startup_check=startup_result, task_status="idle")
        if not startup_result.get("ok", True) and self.config_model.cli.startup_check_mode == "strict":
            logger.error("频道巡检插件自检失败，自动巡检未启动: %s", startup_result.get("error"))
            await self._notify_startup_failure(startup_result)
            self.storage.patch_state(task_status="startup_check_failed")
            return
        if not startup_result.get("ok", True):
            logger.warning("频道巡检插件自检失败，但根据配置继续运行: %s", startup_result.get("error"))
            await self._notify_startup_failure(startup_result)

        if self.config_model.enabled and self.config_model.auto_review.enabled:
            self._debug("plugin.start_poll_loop")
            self._task = asyncio.create_task(self._poll_loop())

    async def terminate(self):
        self._stop_event.set()
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _poll_loop(self):
        await asyncio.sleep(self.config_model.auto_review.startup_delay_seconds)
        while not self._stop_event.is_set():
            interval = self.config_model.auto_review.poll_interval_seconds
            self._debug("poll_loop.tick", interval=interval)
            if not self.config_model.enabled or not self.config_model.auto_review.enabled:
                await asyncio.sleep(interval)
                continue
            async with self._lock:
                try:
                    self.storage.patch_state(task_status="running", last_run_at=int(time.time()))
                    report = await self.review_service.scan_once(trigger="auto")
                    self.storage.patch_state(
                        task_status="idle",
                        last_success_at=int(time.time()),
                        last_report_summary={
                            "scanned": report.get("scanned", 0),
                            "flagged": report.get("flagged", 0),
                            "moved": report.get("moved", 0),
                            "move_failed": report.get("move_failed", 0),
                        },
                    )
                    self._debug("poll_loop.report", report=report)
                    await self._notify_report(report)
                except Exception as exc:
                    logger.exception("频道巡检任务执行失败")
                    self.storage.patch_state(
                        task_status="error",
                        last_error=str(exc),
                        last_error_at=int(time.time()),
                    )
            await asyncio.sleep(interval)

    async def _run_manual_scan(self) -> dict[str, Any]:
        self._debug("manual_scan.begin")
        async with self._lock:
            report = await self.review_service.scan_once(trigger="manual")
            self.storage.patch_state(last_manual_run_at=int(time.time()), last_report_summary=report)
            self._debug("manual_scan.report", report=report)
            return report

    async def _notify_report(self, report: dict[str, Any]) -> None:
        if not self.config_model.notify.enabled:
            self._debug("notify_report.skip_disabled")
            return
        if self.config_model.notify.notify_only_when_flagged and report.get("flagged", 0) == 0:
            self._debug("notify_report.skip_no_flagged", report=report)
            return
        text = self._format_report(report)
        self._debug("notify_report.broadcast", text_preview=text[:1200])
        await self._broadcast_message(text)

    async def _notify_startup_failure(self, startup_result: dict[str, Any]) -> None:
        if not self.config_model.notify.enabled or not self.config_model.notify.notify_on_startup_failure:
            return
        text = "频道巡检插件启动自检失败\n" + str(startup_result.get("error") or startup_result)
        await self._broadcast_message(text)

    async def _broadcast_message(self, text: str) -> None:
        targets = self.storage.load_notify_targets()
        manual = [
            {"unified_msg_origin": str(item)}
            for item in self.config_model.notify.manual_notify_targets
            if str(item).strip()
        ]
        merged: list[str] = []
        self._debug("broadcast.targets_loaded", stored_targets=targets, manual_targets=manual)
        for target in targets + manual:
            umo = str(target.get("unified_msg_origin") or "")
            if not umo or umo in merged:
                continue
            merged.append(umo)
            try:
                self._debug("broadcast.send", unified_msg_origin=umo)
                await self.context.send_message(umo, MessageChain().message(text))
            except Exception:
                logger.exception("频道巡检主动通知发送失败: %s", umo)

    def _format_report(self, report: dict[str, Any]) -> str:
        lines = [
            "频道巡检完成",
            f"扫描新帖：{report.get('scanned', 0)}",
            f"违规：{report.get('flagged', 0)}",
            f"成功移动：{report.get('moved', 0)}",
            f"移动失败：{report.get('move_failed', 0)}",
            f"已记录：{report.get('recorded', 0)}",
        ]
        if self.config_model.notify.notify_include_feed_detail:
            detail_limit = self.config_model.notify.notify_max_detail_count
            details = [item for item in report.get("details", []) if item.get("risk_level") != "none"][:detail_limit]
            if details:
                lines.append("")
                lines.append("违规明细：")
                for index, item in enumerate(details, start=1):
                    lines.append(f"{index}. {item.get('title') or item.get('feed_id')}")
                    if self.config_model.notify.notify_include_reason and item.get("reason"):
                        lines.append(f"原因：{item['reason']}")
                    lines.append(f"动作：{item.get('action', 'none')}")
                    if item.get("error"):
                        lines.append(f"错误：{item['error']}")
        return "\n".join(lines)

    @filter.command_group("频道巡检")
    def channel_inspect(self):
        pass

    @channel_inspect.command("状态")
    async def status(self, event: AstrMessageEvent):
        """查看巡检插件状态"""
        state = self.storage.load_state()
        summary = state.get("last_report_summary") or {}
        text = [
            "频道巡检状态",
            f"插件启用：{self.config_model.enabled}",
            f"自动巡检：{self.config_model.auto_review.enabled}",
            f"任务状态：{state.get('task_status', 'unknown')}",
            f"最近成功：{state.get('last_success_at', '-')}",
            f"最近错误：{state.get('last_error', '-')}",
            f"目标频道：{self.config_model.channel.guild_id or '-'}",
            f"通知目标数：{len(self.storage.load_notify_targets())}",
            f"最近摘要：扫描 {summary.get('scanned', 0)} / 违规 {summary.get('flagged', 0)} / 移动 {summary.get('moved', 0)}",
        ]
        yield event.plain_result("\n".join(text))

    @channel_inspect.command("立即执行")
    async def run_now(self, event: AstrMessageEvent):
        """手动立即执行一轮巡检"""
        self._debug("command.run_now", unified_msg_origin=event.unified_msg_origin)
        report = await self._run_manual_scan()
        yield event.plain_result(self._format_report(report))

    @channel_inspect.command("绑定通知")
    async def bind_notify(self, event: AstrMessageEvent):
        """绑定当前会话为巡检通知目标"""
        added = self.storage.add_notify_target(
            {
                "unified_msg_origin": event.unified_msg_origin,
                "platform_name": event.get_platform_name(),
                "group_id": event.get_group_id() if hasattr(event, "get_group_id") else "",
                "created_at": int(time.time()),
            }
        )
        if added:
            yield event.plain_result("已绑定当前会话为频道巡检通知目标。")
        else:
            yield event.plain_result("当前会话已经绑定过通知。")

    @channel_inspect.command("解绑通知")
    async def unbind_notify(self, event: AstrMessageEvent):
        """解绑当前会话的巡检通知"""
        removed = self.storage.remove_notify_target(event.unified_msg_origin)
        if removed:
            yield event.plain_result("已解绑当前会话的频道巡检通知。")
        else:
            yield event.plain_result("当前会话没有绑定巡检通知。")

    @channel_inspect.command("通知列表")
    async def list_notify(self, event: AstrMessageEvent):
        """查看已绑定的通知目标列表"""
        targets = self.storage.load_notify_targets()
        if not targets:
            yield event.plain_result("当前没有已绑定的通知目标。")
            return
        lines = ["已绑定通知目标："]
        for index, item in enumerate(targets, start=1):
            lines.append(f"{index}. {item.get('platform_name', '-')}: {item.get('unified_msg_origin', '-')}")
        yield event.plain_result("\n".join(lines))

    @channel_inspect.command("最近报告")
    async def last_report(self, event: AstrMessageEvent):
        """查看最近一次巡检报告"""
        report = self.storage.load_last_report()
        if not report:
            yield event.plain_result("当前没有保存的巡检报告。")
            return
        yield event.plain_result(self._format_report(report))

    @channel_inspect.command("自检")
    async def check_cli(self, event: AstrMessageEvent):
        """执行 tencent-channel-cli 自检"""
        result = await self.review_service.run_startup_check()
        self.storage.patch_state(startup_check=result)
        yield event.plain_result(f"自检结果：{result}")
