import pytest

from astrbot_plugin_channel_inspect.main import ChannelInspectPlugin
from astrbot_plugin_channel_inspect.plugin_config import PluginConfigModel


@pytest.fixture
def plugin(context, storage, cli):
    config_dict = {
        "enabled": True,
        "dev_mode": False,
        "auto_review": {"enabled": True, "poll_interval_seconds": 300, "fetch_count": 20, "dry_run": True, "startup_delay_seconds": 15},
        "cli": {"cli_path": "tencent-channel-cli", "timeout_seconds": 30, "detail_timeout_seconds": 60, "min_version": "1.0.6", "check_on_startup": False, "startup_check_mode": "disabled", "auto_doctor_on_error": False, "rate_limit_retry_seconds": 70},
        "channel": {"guild_id": "test_guild", "scan_strategy": "guild_home", "feed_source_mode": "guild_latest", "target_channel_ids": [], "exclude_channel_ids": [], "fallback_channel_id": "", "suspect_channel_id": "", "moderation_action": "notify_only", "skip_if_already_in_suspect_channel": True, "scan_all_when_target_empty": True},
        "review": {"provider_mode": "astrbot_provider", "provider_id": "test_provider", "model": "", "custom_base_url": "", "custom_api_key": "", "review_prompt": "test", "timeout_seconds": 90, "max_images_per_feed": 3, "image_review_mode": "all", "max_content_length": 500, "response_format": "feed_objects", "strict_mode": True, "require_reason": True, "move_risk_levels": ["high"]},
        "record": {"max_records": 2000, "record_safe_feeds": True, "record_failed_move_feeds": False, "retry_on_ai_failure": True, "store_last_report": True},
        "notify": {"enabled": True, "notify_only_when_flagged": True, "notify_include_feed_detail": True, "notify_include_reason": True, "notify_max_detail_count": 5, "notify_on_startup_failure": True, "manual_notify_targets": []},
    }
    plugin = ChannelInspectPlugin.__new__(ChannelInspectPlugin)
    plugin.config_model = PluginConfigModel.from_dict(config_dict)
    plugin.storage = storage
    return plugin


class TestFormatReport:
    def test_basic_report(self, plugin):
        report = {"scanned": 10, "flagged": 2, "moved": 1, "move_failed": 0, "recorded": 5, "details": []}
        text = plugin._format_report(report)
        assert "扫描新帖：10" in text
        assert "违规：2" in text
        assert "成功移动：1" in text
        assert "移动失败：0" in text
        assert "已记录：5" in text

    def test_with_details(self, plugin):
        report = {
            "scanned": 2,
            "flagged": 2,
            "moved": 1,
            "move_failed": 0,
            "recorded": 2,
            "details": [
                {"feed_id": "1", "title": "违规帖1", "risk_level": "high", "reason": "广告", "action": "move", "error": ""},
                {"feed_id": "2", "title": "违规帖2", "risk_level": "medium", "reason": "引流", "action": "notify_only", "error": ""},
            ],
        }
        text = plugin._format_report(report)
        assert "违规明细" in text
        assert "1. 违规帖1" in text
        assert "原因：广告" in text
        assert "动作：move" in text
        assert "2. 违规帖2" in text
        assert "原因：引流" in text

    def test_without_detail_when_disabled(self, plugin):
        plugin.config_model.notify.notify_include_feed_detail = False
        report = {
            "scanned": 2,
            "flagged": 2,
            "moved": 1,
            "move_failed": 0,
            "recorded": 2,
            "details": [
                {"feed_id": "1", "title": "违规帖1", "risk_level": "high", "reason": "广告", "action": "move", "error": ""},
            ],
        }
        text = plugin._format_report(report)
        assert "违规明细" not in text

    def test_without_reason_when_disabled(self, plugin):
        plugin.config_model.notify.notify_include_reason = False
        report = {
            "scanned": 1,
            "flagged": 1,
            "moved": 0,
            "move_failed": 0,
            "recorded": 1,
            "details": [
                {"feed_id": "1", "title": "违规帖1", "risk_level": "high", "reason": "广告", "action": "dry_run", "error": ""},
            ],
        }
        text = plugin._format_report(report)
        assert "违规明细" in text
        assert "1. 违规帖1" in text
        assert "原因：" not in text

    def test_with_error(self, plugin):
        report = {
            "scanned": 1,
            "flagged": 1,
            "moved": 0,
            "move_failed": 1,
            "recorded": 1,
            "details": [
                {"feed_id": "1", "title": "违规帖1", "risk_level": "high", "reason": "广告", "action": "move_failed", "error": "timeout"},
            ],
        }
        text = plugin._format_report(report)
        assert "错误：timeout" in text

    def test_empty_report(self, plugin):
        text = plugin._format_report({})
        assert "扫描新帖：0" in text
        assert "违规：0" in text
