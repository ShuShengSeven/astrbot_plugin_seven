from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AutoReviewConfig:
    enabled: bool = True
    poll_interval_seconds: int = 300
    fetch_count: int = 20
    dry_run: bool = True
    startup_delay_seconds: int = 15


@dataclass
class CliConfig:
    cli_path: str = ""
    timeout_seconds: int = 30
    detail_timeout_seconds: int = 60
    min_version: str = "1.0.6"
    check_on_startup: bool = True
    startup_check_mode: str = "strict"
    auto_doctor_on_error: bool = False
    rate_limit_retry_seconds: int = 70


@dataclass
class ChannelConfig:
    guild_id: str = ""
    scan_strategy: str = "guild_home"
    feed_source_mode: str = "guild_latest"
    target_channel_ids: list[str] = field(default_factory=list)
    exclude_channel_ids: list[str] = field(default_factory=list)
    fallback_channel_id: str = ""
    suspect_channel_id: str = ""
    moderation_action: str = "move_then_notify"
    skip_if_already_in_suspect_channel: bool = True
    scan_all_when_target_empty: bool = True


@dataclass
class ReviewConfig:
    provider_mode: str = "astrbot_provider"
    provider_id: str = ""
    model: str = ""
    custom_base_url: str = ""
    custom_api_key: str = ""
    review_prompt: str = "你是严谨的社区内容审核引擎。进行【意图审查】，不仅识别明显违规词，更要揪出使用谐音/拼音/变体伪装的违规交易与引流行为。输出 JSON 格式审核结果。"
    timeout_seconds: int = 90
    max_images_per_feed: int = 3
    image_review_mode: str = "all"
    max_content_length: int = 500
    response_format: str = "feed_objects"
    strict_mode: bool = True
    require_reason: bool = True
    move_risk_levels: list[str] = field(default_factory=lambda: ["high"])
    structured_output: bool = False


@dataclass
class ManualReviewConfig:
    fetch_count: int = 20


@dataclass
class RecordConfig:
    max_records: int = 2000
    record_safe_feeds: bool = True
    record_failed_move_feeds: bool = False
    retry_on_ai_failure: bool = True
    store_last_report: bool = True


@dataclass
class NotifyConfig:
    enabled: bool = True
    notify_only_when_flagged: bool = True
    notify_include_feed_detail: bool = True
    notify_include_reason: bool = True
    notify_max_detail_count: int = 5
    notify_on_startup_failure: bool = True
    manual_notify_targets: list[str] = field(default_factory=list)


@dataclass
class PluginConfigModel:
    enabled: bool = True
    dev_mode: bool = False
    auto_review: AutoReviewConfig = field(default_factory=AutoReviewConfig)
    cli: CliConfig = field(default_factory=CliConfig)
    channel: ChannelConfig = field(default_factory=ChannelConfig)
    review: ReviewConfig = field(default_factory=ReviewConfig)
    manual_review: ManualReviewConfig = field(default_factory=ManualReviewConfig)
    record: RecordConfig = field(default_factory=RecordConfig)
    notify: NotifyConfig = field(default_factory=NotifyConfig)

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> "PluginConfigModel":
        raw = raw or {}
        return cls(
            enabled=bool(raw.get("enabled", True)),
            dev_mode=bool(raw.get("dev_mode", False)),
            auto_review=AutoReviewConfig(**(raw.get("auto_review") or {})),
            cli=CliConfig(**(raw.get("cli") or {})),
            channel=ChannelConfig(**(raw.get("channel") or {})),
            review=ReviewConfig(**(raw.get("review") or {})),
            manual_review=ManualReviewConfig(**(raw.get("manual_review") or {})),
            record=RecordConfig(**(raw.get("record") or {})),
            notify=NotifyConfig(**(raw.get("notify") or {})),
        )

    def validate(self) -> list[str]:
        errors: list[str] = []

        if self.enabled and self.auto_review.enabled and not self.channel.guild_id:
            errors.append("启用自动巡检时必须配置 channel.guild_id。")
        if not self.auto_review.dry_run and not self.channel.suspect_channel_id:
            errors.append("关闭 dry_run 后必须配置 channel.suspect_channel_id。")
        if self.review.provider_mode == "astrbot_provider" and not self.review.provider_id:
            errors.append("review.provider_mode 为 astrbot_provider 时必须配置 review.provider_id。")
        if self.review.provider_mode == "custom_openai_compatible":
            if not self.review.custom_base_url:
                errors.append("自定义模型模式下必须配置 review.custom_base_url。")
            if not self.review.custom_api_key:
                errors.append("自定义模型模式下必须配置 review.custom_api_key。")
        if self.channel.scan_strategy == "per_channel" and not self.channel.target_channel_ids:
            errors.append("channel.scan_strategy 为 per_channel 时必须配置 target_channel_ids。")
        if self.channel.feed_source_mode == "channel_timeline" and not self.channel.target_channel_ids:
            errors.append("channel.feed_source_mode 为 channel_timeline 时必须配置 target_channel_ids。")
        if self.auto_review.poll_interval_seconds < 60:
            errors.append("auto_review.poll_interval_seconds 不能低于 60 秒。")
        if not 1 <= self.auto_review.fetch_count <= 20:
            errors.append("auto_review.fetch_count 必须在 1 到 20 之间。")
        if self.manual_review.fetch_count < 1:
            errors.append("manual_review.fetch_count 不能低于 1。")
        if not 0 <= self.review.max_images_per_feed <= 5:
            errors.append("review.max_images_per_feed 必须在 0 到 5 之间。")
        if self.review.image_review_mode not in {"all", "img"}:
            errors.append("review.image_review_mode 只允许 all 或 img。")
        if self.channel.moderation_action not in {"notify_only", "move", "move_then_notify"}:
            errors.append("channel.moderation_action 配置不合法。")

        return errors
