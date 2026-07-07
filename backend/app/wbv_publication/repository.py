"""Atomic repository for independently retained WBV overlay packages."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from threading import RLock

from .models import WbvOverlayPackage


class WbvOverlayPackageNotFound(KeyError):
    pass


class WbvOverlayPackageRepository:
    _lock = RLock()

    def __init__(self, storage_path: Path | None = None) -> None:
        self.storage_path = storage_path or self.default_storage_path()

    @staticmethod
    def default_storage_path() -> Path:
        override = os.environ.get("WLV_WBV_OVERLAY_PACKAGE_STORE")
        if override:
            return Path(override).expanduser().resolve()
        return Path(__file__).resolve().parents[3] / "data" / "wbv" / "overlay_packages_v1.json"

    def list_for_well(self, managed_well_uid: str) -> tuple[WbvOverlayPackage, ...]:
        with self._lock:
            store = self._read_store()
            packages = [
                WbvOverlayPackage.model_validate(raw)
                for raw in store["packages"].values()
                if raw.get("managed_well_uid") == managed_well_uid
            ]
        return tuple(sorted(packages, key=lambda item: (item.created_at, item.package_uid)))

    def get(self, package_uid: str) -> WbvOverlayPackage:
        with self._lock:
            raw = self._read_store()["packages"].get(package_uid)
        if raw is None:
            raise WbvOverlayPackageNotFound(package_uid)
        return WbvOverlayPackage.model_validate(raw)

    def find_by_command_uid(self, command_uid: str) -> WbvOverlayPackage | None:
        with self._lock:
            values = self._read_store()["packages"].values()
            raw = next((item for item in values if self._raw_uses_command_uid(item, command_uid)), None)
        return WbvOverlayPackage.model_validate(raw) if raw is not None else None

    @staticmethod
    def _raw_uses_command_uid(raw: dict, command_uid: str) -> bool:
        if raw.get("provenance", {}).get("publication_command_uid") == command_uid:
            return True
        return any(
            item.get("provenance", {}).get("publication_command_uid") == command_uid
            for item in raw.get("revision_history", [])
        )

    def save_new(self, package: WbvOverlayPackage) -> WbvOverlayPackage:
        with self._lock:
            store = self._read_store()
            if package.package_uid in store["packages"]:
                raise ValueError(f"WBV overlay package already exists: {package.package_uid}")
            command_uid = package.provenance.publication_command_uid
            for raw in store["packages"].values():
                if raw.get("provenance", {}).get("publication_command_uid") == command_uid:
                    return WbvOverlayPackage.model_validate(raw)
            if package.status == "active":
                self._deactivate_well_packages(store, package.managed_well_uid)
            store["packages"][package.package_uid] = package.model_dump(mode="json")
            self._write_store(store)
        return package


    def replace_existing(
        self,
        package: WbvOverlayPackage,
        *,
        expected_package_revision: int,
    ) -> WbvOverlayPackage:
        with self._lock:
            store = self._read_store()
            raw = store["packages"].get(package.package_uid)
            if raw is None:
                raise WbvOverlayPackageNotFound(package.package_uid)
            current = WbvOverlayPackage.model_validate(raw)
            if current.managed_well_uid != package.managed_well_uid:
                raise ValueError("Package managed well cannot change")
            if current.package_revision != expected_package_revision:
                raise ValueError(
                    f"Stale package revision: expected {expected_package_revision}, "
                    f"current {current.package_revision}"
                )
            command_uid = package.provenance.publication_command_uid
            for uid, other in store["packages"].items():
                if uid != package.package_uid and self._raw_uses_command_uid(other, command_uid):
                    raise ValueError("Publication command UID was already used for another package")
            if package.status == "active":
                self._deactivate_well_packages(store, package.managed_well_uid)
            store["packages"][package.package_uid] = package.model_dump(mode="json")
            self._write_store(store)
        return package

    def delete_existing(
        self,
        managed_well_uid: str,
        package_uid: str,
        *,
        expected_package_revision: int,
    ) -> None:
        with self._lock:
            store = self._read_store()
            raw = store["packages"].get(package_uid)
            if raw is None:
                return
            package = WbvOverlayPackage.model_validate(raw)
            if package.managed_well_uid != managed_well_uid:
                raise ValueError("Package does not belong to the requested managed well")
            if package.package_revision != expected_package_revision:
                raise ValueError(
                    f"Stale package revision: expected {expected_package_revision}, "
                    f"current {package.package_revision}"
                )
            del store["packages"][package_uid]
            self._write_store(store)

    def set_active(self, managed_well_uid: str, package_uid: str, *, active: bool) -> WbvOverlayPackage:
        with self._lock:
            store = self._read_store()
            raw = store["packages"].get(package_uid)
            if raw is None:
                raise WbvOverlayPackageNotFound(package_uid)
            package = WbvOverlayPackage.model_validate(raw)
            if package.managed_well_uid != managed_well_uid:
                raise ValueError("Package does not belong to the requested managed well")
            if package.status == "archived":
                raise ValueError("Archived packages cannot be activated")
            if active:
                self._deactivate_well_packages(store, managed_well_uid)
            package = package.model_copy(update={"status": "active" if active else "inactive"})
            store["packages"][package_uid] = package.model_dump(mode="json")
            self._write_store(store)
        return package

    @staticmethod
    def _deactivate_well_packages(store: dict, managed_well_uid: str) -> None:
        for uid, raw in list(store["packages"].items()):
            if raw.get("managed_well_uid") == managed_well_uid and raw.get("status") == "active":
                updated = dict(raw)
                updated["status"] = "inactive"
                store["packages"][uid] = updated

    def _read_store(self) -> dict:
        if not self.storage_path.exists():
            return {"contract_version": "wbv_overlay_package_store_v1", "packages": {}}
        try:
            raw = json.loads(self.storage_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Cannot read WBV overlay package store: {exc}") from exc
        if not isinstance(raw, dict) or not isinstance(raw.get("packages"), dict):
            raise RuntimeError("Invalid WBV overlay package store")
        return raw

    def _write_store(self, store: dict) -> None:
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix=self.storage_path.name + ".", suffix=".tmp", dir=self.storage_path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(store, handle, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, self.storage_path)
        except Exception:
            try:
                os.unlink(temp_name)
            except OSError:
                pass
            raise
