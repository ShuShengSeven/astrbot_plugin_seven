from astrbot_plugin_channel_inspect.plugin_config import PluginConfigModel


def make(overrides: dict | None = None):
    default = {
        "enabled": True,
        "dev_mode": False,
        "auto_review": {"enabled": True, "poll_interval_seconds": 300, "fetch_count": 20, "dry_run": True, "startup_delay_seconds": 15},
        "cli": {"cli_path": "tencent-channel-cli", "timeout_seconds": 30, "detail_timeout_seconds": 60, "min_version": "1.0.6", "check_on_startup": False, "startup_check_mode": "disabled", "auto_doctor_on_error": False, "rate_limit_retry_seconds": 70},
        "channel": {"guild_id": "test_guild", "scan_strategy": "guild_home", "feed_source_mode": "guild_latest", "target_channel_ids": [], "exclude_channel_ids": [], "fallback_channel_id": "", "suspect_channel_id": "", "moderation_action": "notify_only", "skip_if_already_in_suspect_channel": True, "scan_all_when_target_empty": True},
        "review": {"provider_mode": "astrbot_provider", "provider_id": "test_provider", "model": "", "custom_base_url": "", "custom_api_key": "", "review_prompt": "test prompt", "timeout_seconds": 90, "max_images_per_feed": 3, "image_review_mode": "all", "max_content_length": 500, "response_format": "feed_objects", "strict_mode": True, "require_reason": True, "move_risk_levels": ["high"]},
        "record": {"max_records": 2000, "record_safe_feeds": True, "record_failed_move_feeds": False, "retry_on_ai_failure": True, "store_last_report": True},
        "notify": {"enabled": True, "notify_only_when_flagged": True, "notify_include_feed_detail": True, "notify_include_reason": True, "notify_max_detail_count": 5, "notify_on_startup_failure": True, "manual_notify_targets": []},
    }
    from copy import deepcopy
    cfg = deepcopy(default)
    if overrides:
        _deep_merge(cfg, overrides)
    return PluginConfigModel.from_dict(cfg)


def _deep_merge(base: dict, override: dict) -> None:
    for k, v in override.items():
        if k in base and isinstance(base[k], dict) and isinstance(v, dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v


class TestValidate:
    def test_valid_default(self):
        cfg = make()
        errors = cfg.validate()
        assert len(errors) == 0

    def test_guild_id_required_when_enabled(self):
        cfg = make({"enabled": True, "auto_review": {"enabled": True}, "channel": {"guild_id": ""}})
        errors = cfg.validate()
        assert any("guild_id" in e for e in errors)

    def test_guild_id_not_required_when_disabled(self):
        cfg = make({"enabled": False, "auto_review": {"enabled": False}, "channel": {"guild_id": ""}})
        errors = cfg.validate()
        assert all("guild_id" not in e for e in errors)

    def test_suspect_channel_required_when_not_dry_run(self):
        cfg = make({"auto_review": {"dry_run": False}, "channel": {"suspect_channel_id": ""}})
        errors = cfg.validate()
        assert any("suspect_channel_id" in e for e in errors)

    def test_suspect_channel_not_required_when_dry_run(self):
        cfg = make({"auto_review": {"dry_run": True}, "channel": {"suspect_channel_id": ""}})
        errors = cfg.validate()
        assert all("suspect_channel_id" not in e for e in errors)

    def test_provider_id_required_in_astrbot_mode(self):
        cfg = make({"review": {"provider_mode": "astrbot_provider", "provider_id": ""}})
        errors = cfg.validate()
        assert any("provider_id" in e for e in errors)

    def test_custom_url_and_key_required(self):
        cfg = make({"review": {"provider_mode": "custom_openai_compatible", "custom_base_url": "", "custom_api_key": ""}})
        errors = cfg.validate()
        assert any("custom_base_url" in e for e in errors)
        assert any("custom_api_key" in e for e in errors)

    def test_target_channel_ids_required_for_per_channel(self):
        cfg = make({"channel": {"scan_strategy": "per_channel", "target_channel_ids": []}})
        errors = cfg.validate()
        assert any("target_channel_ids" in e for e in errors)

    def test_target_channel_ids_required_for_channel_timeline(self):
        cfg = make({"channel": {"feed_source_mode": "channel_timeline", "target_channel_ids": []}})
        errors = cfg.validate()
        assert any("target_channel_ids" in e for e in errors)

    def test_poll_interval_minimum(self):
        cfg = make({"auto_review": {"poll_interval_seconds": 30}})
        errors = cfg.validate()
        assert any("poll_interval_seconds" in e for e in errors)

    def test_poll_interval_ok(self):
        cfg = make({"auto_review": {"poll_interval_seconds": 60}})
        errors = cfg.validate()
        assert all("poll_interval_seconds" not in e for e in errors)

    def test_fetch_count_range(self):
        cfg = make({"auto_review": {"fetch_count": 0}})
        errors = cfg.validate()
        assert any("fetch_count" in e for e in errors)

    def test_max_images_per_feed_range(self):
        cfg = make({"review": {"max_images_per_feed": 10}})
        errors = cfg.validate()
        assert any("max_images_per_feed" in e for e in errors)

    def test_invalid_image_review_mode(self):
        cfg = make({"review": {"image_review_mode": "video"}})
        errors = cfg.validate()
        assert any("image_review_mode" in e for e in errors)

    def test_invalid_moderation_action(self):
        cfg = make({"channel": {"moderation_action": "delete"}})
        errors = cfg.validate()
        assert any("moderation_action" in e for e in errors)
