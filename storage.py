from __future__ import annotations

import json
from pathlib import Path
from typing import Any


try:
    from astrbot.core.utils.astrbot_path import get_astrbot_data_path
except Exception:  # pragma: no cover - AstrBot runtime fallback
    get_astrbot_data_path = None


class PluginStorage:
    def __init__(self, plugin_name: str) -> None:
        self.plugin_name = plugin_name
        self.base_dir = self._resolve_base_dir()
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.processed_path = self.base_dir / "processed_feeds.json"
        self.state_path = self.base_dir / "runtime_state.json"
        self.notify_targets_path = self.base_dir / "notify_targets.json"
        self.last_report_path = self.base_dir / "last_report.json"

    def _resolve_base_dir(self) -> Path:
        if get_astrbot_data_path:
            try:
                return Path(get_astrbot_data_path()) / "plugin_data" / self.plugin_name
            except Exception:
                pass
        return Path(__file__).resolve().parent / "data" / self.plugin_name

    def _read_json(self, path: Path, default: Any) -> Any:
        if not path.exists():
            return default
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return default

    def _write_json(self, path: Path, data: Any) -> None:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def load_processed(self) -> list[dict[str, Any]]:
        data = self._read_json(self.processed_path, [])
        return data if isinstance(data, list) else []

    def save_processed(self, records: list[dict[str, Any]], max_records: int) -> None:
        self._write_json(self.processed_path, records[-max_records:])

    def get_processed_ids(self) -> set[str]:
        return {
            str(item.get("feed_id"))
            for item in self.load_processed()
            if isinstance(item, dict) and item.get("feed_id")
        }

    def append_processed(self, records: list[dict[str, Any]], max_records: int) -> None:
        existing = self.load_processed()
        seen = {str(item.get("feed_id")) for item in existing if isinstance(item, dict)}
        for record in records:
            feed_id = str(record.get("feed_id", ""))
            if not feed_id:
                continue
            if feed_id in seen:
                existing = [item for item in existing if str(item.get("feed_id")) != feed_id]
            existing.append(record)
            seen.add(feed_id)
        self.save_processed(existing, max_records)

    def load_state(self) -> dict[str, Any]:
        data = self._read_json(self.state_path, {})
        return data if isinstance(data, dict) else {}

    def save_state(self, state: dict[str, Any]) -> None:
        self._write_json(self.state_path, state)

    def patch_state(self, **kwargs: Any) -> dict[str, Any]:
        state = self.load_state()
        state.update(kwargs)
        self.save_state(state)
        return state

    def load_notify_targets(self) -> list[dict[str, Any]]:
        data = self._read_json(self.notify_targets_path, [])
        return data if isinstance(data, list) else []

    def save_notify_targets(self, targets: list[dict[str, Any]]) -> None:
        self._write_json(self.notify_targets_path, targets)

    def add_notify_target(self, target: dict[str, Any]) -> bool:
        targets = self.load_notify_targets()
        umo = str(target.get("unified_msg_origin", ""))
        if not umo:
            return False
        if any(str(item.get("unified_msg_origin")) == umo for item in targets):
            return False
        targets.append(target)
        self.save_notify_targets(targets)
        return True

    def remove_notify_target(self, unified_msg_origin: str) -> bool:
        targets = self.load_notify_targets()
        filtered = [item for item in targets if str(item.get("unified_msg_origin")) != unified_msg_origin]
        if len(filtered) == len(targets):
            return False
        self.save_notify_targets(filtered)
        return True

    def save_last_report(self, report: dict[str, Any]) -> None:
        self._write_json(self.last_report_path, report)

    def load_last_report(self) -> dict[str, Any]:
        data = self._read_json(self.last_report_path, {})
        return data if isinstance(data, dict) else {}
