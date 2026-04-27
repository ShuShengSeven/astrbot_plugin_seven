import asyncio
import random
from datetime import datetime

import aiohttp

from astrbot.api import logger, AstrBotConfig
from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register


@register("astrbot_plugin_seven", "Seven", "定时推送与手动触发的随机图插件", "1.0.0")
class SevenPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self.scheduled_tasks: list[asyncio.Task] = []
        self._active_umos: set[str] = set()

    async def initialize(self):
        mode = self.config.get("schedule_mode", "off")
        if mode == "interval":
            minutes = self.config.get("schedule_interval", 60)
            task = asyncio.create_task(self._interval_loop(minutes))
            self.scheduled_tasks.append(task)
            logger.info(f"随机图插件: 间隔模式已启动，每 {minutes} 分钟推送一次")
        elif mode == "fixed_time":
            task = asyncio.create_task(self._fixed_time_loop())
            self.scheduled_tasks.append(task)
            fixed_times = self.config.get("schedule_fixed_times", [])
            logger.info(f"随机图插件: 定点模式已启动，推送时间点: {fixed_times}")

    async def _interval_loop(self, minutes: int):
        while True:
            seconds = minutes * 60
            offset = self.config.get("schedule_random_offset", 0)
            if offset > 0:
                seconds += random.randint(0, offset)
            await asyncio.sleep(seconds)
            await self._do_scheduled_push()

    async def _fixed_time_loop(self):
        fixed_times = self.config.get("schedule_fixed_times", [])
        if not fixed_times:
            return
        while True:
            now = datetime.now()
            target_times = []
            for t_str in fixed_times:
                try:
                    h, m = map(int, t_str.strip().split(":"))
                    target = now.replace(hour=h, minute=m, second=0, microsecond=0)
                    if target <= now:
                        target = target.replace(day=target.day + 1)
                    target_times.append(target)
                except ValueError:
                    logger.error(f"随机图插件: 无效的时间格式: {t_str}")
            if not target_times:
                return
            next_run = min(target_times)
            wait_seconds = (next_run - now).total_seconds()
            offset = self.config.get("schedule_random_offset", 0)
            if offset > 0:
                wait_seconds += random.randint(0, offset)
            await asyncio.sleep(wait_seconds)
            await self._do_scheduled_push()

    async def _do_scheduled_push(self):
        logger.info("随机图插件: 定时任务触发")
        for umo in list(self._active_umos):
            group_id = umo.split(":")[-1] if ":" in umo else ""
            if not self._check_group_allowed(group_id):
                continue
            try:
                await self._fetch_and_send(umo, self.config.get("api_base_url", ""))
            except Exception:
                logger.error(f"随机图插件: 向 {umo} 推送图片失败", exc_info=True)

    def _check_group_allowed(self, group_id: str) -> bool:
        whitelist_enabled = self.config.get("group_whitelist_enabled", False)
        blacklist_enabled = self.config.get("group_blacklist_enabled", False)
        whitelist = self.config.get("group_whitelist", [])
        blacklist = self.config.get("group_blacklist", [])
        if blacklist_enabled and group_id in blacklist:
            return False
        if whitelist_enabled:
            return group_id in whitelist
        return True

    async def _request_image(self, url: str) -> str | None:
        timeout = self.config.get("request_timeout", 15)
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
                    if resp.status == 200:
                        content_type = resp.headers.get("Content-Type", "")
                        if "image" in content_type:
                            return url
                        text = await resp.text()
                        text = text.strip()
                        if text.startswith("http"):
                            return text
                        logger.warning(f"随机图插件: API 返回非图片内容: {text[:200]}")
                        return text
                    logger.warning(f"随机图插件: API 返回状态码 {resp.status}")
        except asyncio.TimeoutError:
            logger.error(f"随机图插件: API 请求超时 ({timeout}s)")
        except Exception:
            logger.error("随机图插件: API 请求异常", exc_info=True)
        return None

    async def _fetch_and_send(self, umo: str, url: str) -> bool:
        image_url = await self._request_image(url)
        if image_url:
            from astrbot.api.message_components import Image
            chain = [Image.fromURL(image_url)]
            await self.context.send_message(umo, chain)
            return True
        return False

    @filter.command("img")
    async def cmd_img(self, event: AstrMessageEvent, sub_command: str = ""):
        umo = event.unified_msg_origin
        if umo:
            self._active_umos.add(umo)
        url = self._resolve_img_command(sub_command)
        if not url:
            return
        result = await self._send_result(event, url)
        if result:
            yield result
        event.stop_event()

    @filter.command("来张图")
    async def cmd_laizhangtu(self, event: AstrMessageEvent, sub_command: str = ""):
        umo = event.unified_msg_origin
        if umo:
            self._active_umos.add(umo)
        url = self._resolve_img_command(sub_command)
        if not url:
            return
        result = await self._send_result(event, url)
        if result:
            yield result
        event.stop_event()

    def _resolve_img_command(self, sub_command: str) -> str:
        if sub_command:
            mapped = self._match_img_sub(sub_command)
            if mapped:
                return mapped
        return self.config.get("api_base_url", "")

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_all_message(self, event: AstrMessageEvent):
        group_id = event.message_obj.group_id or "private"
        if not self._check_group_allowed(str(group_id)):
            return

        umo = event.unified_msg_origin
        if umo:
            self._active_umos.add(umo)

        msg = event.message_str
        url = self._match_keyword(msg)
        if url:
            result = await self._send_result(event, url)
            if result:
                yield result
            event.stop_event()

    async def _send_result(self, event: AstrMessageEvent, url: str) -> MessageEventResult | None:
        image_url = await self._request_image(url)
        if image_url is None:
            return event.plain_result("获取图片失败，请稍后重试")
        return event.image_result(image_url)

    def _match_img_sub(self, sub_command: str) -> str:
        for item in self.config.get("custom_img_sub_commands", []):
            parts = item.split(None, 1)
            if len(parts) == 2:
                trigger, url = parts
                if trigger == sub_command:
                    logger.info(f"随机图插件: 匹配 /img {trigger} -> {url}")
                    return url
        return ""

    def _match_keyword(self, message: str) -> str:
        for item in self.config.get("custom_commands_keyword", []):
            parts = item.split(None, 1)
            if len(parts) == 2:
                keyword, url = parts
                if keyword in message:
                    logger.info(f"随机图插件: 匹配关键词 {keyword} -> {url}")
                    return url
        return ""

    async def terminate(self):
        for task in self.scheduled_tasks:
            task.cancel()
        self.scheduled_tasks.clear()
        logger.info("随机图插件: 定时任务已全部取消")
