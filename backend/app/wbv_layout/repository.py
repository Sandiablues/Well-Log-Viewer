from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from threading import RLock

from .models import WbvTrackLayout


class WbvTrackLayoutRepository:
    _lock = RLock()

    def __init__(self, storage_path: Path | None = None):
        self.storage_path = storage_path or self.default_storage_path()

    @staticmethod
    def default_storage_path():
        override = os.environ.get("WLV_WBV_TRACK_LAYOUT_STORE")
        return (
            Path(override).expanduser().resolve()
            if override
            else Path(__file__).resolve().parents[3] / "data" / "wbv" / "track_layouts_v1.json"
        )

    def get(self, well_uid: str) -> WbvTrackLayout | None:
        with self._lock:
            raw = self._read()["layouts"].get(well_uid)
        if not raw:
            return None
        return WbvTrackLayout.model_validate(self._migrate_layout(raw))

    def save(self, layout: WbvTrackLayout, expected_revision: int | None) -> WbvTrackLayout:
        with self._lock:
            store = self._read()
            raw = store["layouts"].get(layout.managed_well_uid)
            if raw is not None and int(raw.get("revision", 0)) != expected_revision:
                raise ValueError(
                    f"Stale layout revision: expected {expected_revision}, current {raw.get('revision')}"
                )
            if raw is None and expected_revision not in (None, 1):
                raise ValueError("Stale layout revision")
            store["layouts"][layout.managed_well_uid] = layout.model_dump(mode="json")
            self._write(store)
        return layout

    @staticmethod
    def _migrate_layout(raw: dict) -> dict:
        migrated = dict(raw)
        migrated_tracks = []
        for source in raw.get("tracks", []):
            track = dict(source)
            prior_position = track.get("position", "right")
            if prior_position not in {"right", "left", "center"}:
                track["position"] = "center"
            track.setdefault("previous_track_gap", 0.05)
            track.setdefault("background_mode", "transparent")
            track.setdefault("background_color", "#000000")
            track.setdefault("outline_visible", True)
            track.setdefault("grid_mode", "off")
            migrated_tracks.append(track)
        migrated["tracks"] = migrated_tracks
        return migrated

    def _read(self):
        if not self.storage_path.exists():
            return {"contract_version": "wbv_track_layout_store_v1", "layouts": {}}
        raw = json.loads(self.storage_path.read_text())
        if not isinstance(raw, dict) or not isinstance(raw.get("layouts"), dict):
            raise RuntimeError("Invalid WBV track layout store")
        return raw

    def _write(self, store):
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(
            prefix=self.storage_path.name + ".",
            suffix=".tmp",
            dir=self.storage_path.parent,
        )
        try:
            with os.fdopen(fd, "w") as handle:
                json.dump(store, handle, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, self.storage_path)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
