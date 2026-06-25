import os
import sys
import types
from unittest.mock import MagicMock

import pytest

# Ensure the project root is importable as a package from parent dir
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if os.path.basename(_project_root) not in sys.modules:
    _parent = os.path.dirname(_project_root)
    if _parent not in sys.path:
        sys.path.insert(0, _parent)

# Build a proper mock module hierarchy for astrbot
astrbot_mod = types.ModuleType("astrbot")
astrbot_api_mod = types.ModuleType("astrbot.api")
astrbot_api_mod.event = types.ModuleType("astrbot.api.event")
astrbot_api_mod.star = types.ModuleType("astrbot.api.star")
astrbot_api_mod.logger = MagicMock()
astrbot_api_mod.AstrBotConfig = dict
astrbot_api_mod.event.filter = MagicMock()
astrbot_api_mod.event.AstrMessageEvent = MagicMock()
astrbot_api_mod.event.MessageChain = MagicMock()
astrbot_api_mod.star.Context = MagicMock
astrbot_api_mod.star.Star = type("Star", (), {"__init__": lambda self, context: None})
astrbot_mod.api = astrbot_api_mod
astrbot_mod.AstrBotConfig = dict

sys.modules["astrbot"] = astrbot_mod
sys.modules["astrbot.api"] = astrbot_api_mod
sys.modules["astrbot.api.event"] = astrbot_api_mod.event
sys.modules["astrbot.api.star"] = astrbot_api_mod.star
astrbot_core_mod = types.ModuleType("astrbot.core")
astrbot_core_utils_mod = types.ModuleType("astrbot.core.utils")
astrbot_core_utils_path_mod = types.ModuleType("astrbot.core.utils.astrbot_path")
astrbot_core_utils_path_mod.get_astrbot_data_path = MagicMock(return_value="/tmp/astrbot_data")
astrbot_core_utils_mod.astrbot_path = astrbot_core_utils_path_mod
astrbot_core_mod.utils = astrbot_core_utils_mod
sys.modules["astrbot.core"] = astrbot_core_mod
sys.modules["astrbot.core.utils"] = astrbot_core_utils_mod
sys.modules["astrbot.core.utils.astrbot_path"] = astrbot_core_utils_path_mod

from astrbot_plugin_channel_inspect.plugin_config import PluginConfigModel


def make_config(overrides: dict | None = None) -> PluginConfigModel:
    raw = {
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

    cfg = deepcopy(raw)
    if overrides:
        _deep_merge(cfg, overrides)
    return PluginConfigModel.from_dict(cfg)


def _deep_merge(base: dict, override: dict) -> None:
    for k, v in override.items():
        if k in base and isinstance(base[k], dict) and isinstance(v, dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v


@pytest.fixture
def config():
    return make_config()


@pytest.fixture
def context():
    return MagicMock()


@pytest.fixture
def storage():
    return MagicMock()


@pytest.fixture
def cli():
    return MagicMock()
