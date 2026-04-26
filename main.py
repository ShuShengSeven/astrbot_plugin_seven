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
        target_groups = self._get_scheduled_target_groups()
        for umo in target_groups:
            try:
                await self._fetch_and_send_image(umo)
            except Exception:
                logger.error(f"随机图插件: 向 {umo} 推送图片失败", exc_info=True)

    def _get_scheduled_target_groups(self) -> list:
        """获取定时推送的目标群聊列表（基于当前活跃会话）"""
        platforms = self.context.platform_manager.get_insts()
        target_umos = []
        for platform in platforms:
            platform_name = getattr(platform, "platform_name", None) or platform.__class__.__name__
            if platform_name:
                groups = getattr(platform, "get_groups", None)
                if callable(groups):
                    try:
                        group_list = groups()
                        for g in group_list:
                            group_id = str(g.get("group_id", ""))
                            if self._check_group_allowed(group_id):
                                umo = f"{platform_name}:GroupMessage:{group_id}"
                                target_umos.append(umo)
                    except Exception as e:
                        logger.warning(f"随机图插件: 获取 {platform_name} 群列表失败: {e}")
        logger.info(f"随机图插件: 定时推送目标群聊: {target_umos}")
        return target_umos

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

    async def _fetch_image_url(self, suffix: str = "") -> str | None:
        base_url = self.config.get("api_base_url", "").rstrip("/")
        if suffix:
            url = f"{base_url}?{suffix}" if "?" not in suffix else f"{base_url}{'&' if '?' in base_url else '?'}{suffix}" if suffix.startswith("&") else f"{base_url}?{suffix}"
        else:
            url = base_url
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
                        if text:
                            logger.warning(f"随机图插件: API 返回非图片内容: {text[:200]}")
                            return text
                    logger.warning(f"随机图插件: API 返回状态码 {resp.status}")
        except asyncio.TimeoutError:
            logger.error(f"随机图插件: API 请求超时 ({timeout}s)")
        except Exception:
            logger.error("随机图插件: API 请求异常", exc_info=True)
        return None

    async def _fetch_and_send_image(self, umo: str, suffix: str = "") -> bool:
        image_url = await self._fetch_image_url(suffix)
        if image_url:
            from astrbot.api.message_components import Image
            chain = [Image.fromURL(image_url)]
            await self.context.send_message(umo, chain)
            return True
        return False

    @filter.command("img")
    async def cmd_img(self, event: AstrMessageEvent):
        """手动触发随机图，默认不带任何后缀"""
        yield await self._handle_manual_trigger(event)

    @filter.command("来张图")
    async def cmd_laizhangtu(self, event: AstrMessageEvent):
        """手动触发随机图，默认不带任何后缀"""
        yield await self._handle_manual_trigger(event)

    async def _handle_manual_trigger(self, event: AstrMessageEvent) -> MessageEventResult:
        group_id = event.message_obj.group_id or "private"
        if not self._check_group_allowed(str(group_id)):
            return event.plain_result("该群不在允许范围内")
        suffix = await self._match_custom_command(event.message_str)
        image_url = await self._fetch_image_url(suffix)
        if image_url is None:
            return event.plain_result("获取图片失败，请稍后重试")
        return event.image_result(image_url)

    async def _match_custom_command(self, message: str) -> str:
        """匹配自定义命令并返回对应的 URL 后缀"""
        custom_commands = self.config.get("custom_commands", {})
        for cmd_name, suffix in custom_commands.items():
            if f"/{cmd_name}" in message:
                return suffix
        return ""

    async def terminate(self):
        for task in self.scheduled_tasks:
            task.cancel()
        self.scheduled_tasks.clear()
        logger.info("随机图插件: 定时任务已全部取消")
