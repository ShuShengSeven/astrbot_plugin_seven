from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any

from astrbot.api import logger


@dataclass
class CliError(Exception):
    message: str
    error_type: str = "cli_error"
    ret_code: int | None = None
    raw: Any = None

    def __str__(self) -> str:
        return self.message


class TencentChannelCliClient:
    def __init__(
        self,
        cli_path: str,
        timeout_seconds: int = 30,
        detail_timeout_seconds: int = 60,
        rate_limit_retry_seconds: int = 70,
        dev_mode: bool = False,
    ) -> None:
        self.cli_path = cli_path
        self.timeout_seconds = timeout_seconds
        self.detail_timeout_seconds = detail_timeout_seconds
        self.rate_limit_retry_seconds = rate_limit_retry_seconds
        self.dev_mode = dev_mode

    def _debug(self, message: str, **kwargs: Any) -> None:
        if not self.dev_mode:
            return
        if kwargs:
            logger.debug("[channel_inspect][debug] %s | %s", message, kwargs)
            return
        logger.debug("[channel_inspect][debug] %s", message)

    async def _execute(self, args: list[str], timeout: int | None = None) -> dict[str, Any]:
        command = [self.cli_path] + args + ["--json"]
        self._debug("cli.execute.start", args=args, timeout=timeout or self.timeout_seconds)
        proc = None
        try:
            proc = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout or self.timeout_seconds
            )
        except asyncio.TimeoutError as exc:
            if proc is not None and proc.returncode is None:
                try:
                    proc.kill()
                except ProcessLookupError:
                    pass
                try:
                    await proc.wait()
                except Exception:
                    pass
            raise CliError("CLI 执行超时", error_type="timeout") from exc
        except FileNotFoundError as exc:
            raise CliError("未找到 tencent-channel-cli，请检查 cli_path 配置", error_type="missing_cli") from exc

        stdout = self._decode_output(stdout_bytes).strip()
        stderr = self._decode_output(stderr_bytes).strip()
        self._debug(
            "cli.execute.done",
            return_stdout_preview=stdout[:500],
            return_stderr_preview=stderr[:500],
        )

        if not stdout and stderr:
            self._raise_from_text(stderr)
        if not stdout:
            raise CliError("CLI 无输出", error_type="empty_output")

        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise CliError(f"CLI 输出不是合法 JSON: {stdout[:300]}", error_type="invalid_json", raw=stdout) from exc

        self._debug("cli.execute.payload", payload=payload)
        self._raise_from_payload(payload)
        return payload

    @staticmethod
    def _decode_output(data: bytes) -> str:
        try:
            return data.decode("utf-8", errors="replace")
        except Exception:
            return data.decode("gbk", errors="replace")

    def _raise_from_text(self, text: str) -> None:
        lowered = text.lower()
        if "8011" in text or "未登录" in text:
            raise CliError(text, error_type="auth_required")
        if "153" in text or "频率上限" in text:
            raise CliError(text, error_type="rate_limit", ret_code=153)
        if "未找到" in lowered or "not recognized" in lowered:
            raise CliError(text, error_type="missing_cli")
        raise CliError(text)

    def _raise_from_payload(self, payload: dict[str, Any]) -> None:
        ret_code = payload.get("retCode")
        if ret_code in (0, None):
            return
        message = str(payload.get("msg") or payload.get("message") or payload)
        if ret_code == 8011 or "未登录" in message:
            raise CliError(message, error_type="auth_required", ret_code=ret_code, raw=payload)
        if ret_code == 153 or "频率上限" in message:
            raise CliError(message, error_type="rate_limit", ret_code=ret_code, raw=payload)
        raise CliError(message, ret_code=ret_code, raw=payload)

    async def _execute_with_retry(self, args: list[str], timeout: int | None = None) -> dict[str, Any]:
        try:
            return await self._execute(args, timeout=timeout)
        except CliError as exc:
            if exc.error_type != "rate_limit":
                raise
            self._debug("cli.execute.retry_rate_limit", args=args, wait_seconds=self.rate_limit_retry_seconds)
            await asyncio.sleep(self.rate_limit_retry_seconds)
            return await self._execute(args, timeout=timeout)

    async def get_version(self) -> str:
        payload = await self._execute_with_retry(["version"])
        data = payload.get("data")
        if isinstance(data, str):
            return data
        return str(data or payload.get("version") or "")

    async def login_status(self) -> dict[str, Any]:
        return await self._execute_with_retry(["login", "status"])

    async def doctor(self) -> dict[str, Any]:
        return await self._execute_with_retry(["doctor"])

    async def get_guild_feeds(self, guild_id: str, get_type: int, count: int) -> list[dict[str, Any]]:
        payload = await self._execute_with_retry(
            ["feed", "get-guild-feeds", "--guild-id", guild_id, "--get-type", str(get_type), "--count", str(count)]
        )
        return payload.get("data", {}).get("feeds", []) or []

    async def get_channel_timeline_feeds(self, guild_id: str, channel_id: str, count: int) -> list[dict[str, Any]]:
        payload = await self._execute_with_retry(
            [
                "feed",
                "get-channel-timeline-feeds",
                "--guild-id",
                guild_id,
                "--channel-id",
                channel_id,
                "--count",
                str(count),
            ]
        )
        return payload.get("data", {}).get("feeds", []) or []

    async def get_feed_detail(self, guild_id: str, feed_id: str) -> dict[str, Any]:
        payload = await self._execute_with_retry(
            ["feed", "get-feed-detail", "--guild-id", guild_id, "--feed-id", feed_id],
            timeout=self.detail_timeout_seconds,
        )
        return payload.get("data", {}).get("feed") or {}

    async def move_feed(
        self,
        guild_id: str,
        feed_id: str,
        original_channel_id: str,
        target_channel_id: str,
    ) -> dict[str, Any]:
        return await self._execute_with_retry(
            [
                "feed",
                "move-feed",
                "--guild-id",
                guild_id,
                "--channel-id",
                target_channel_id,
                "--original-channel-id",
                original_channel_id,
                "--feed-id",
                feed_id,
                "--yes",
            ]
        )
