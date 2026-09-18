from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from datetime import datetime, timezone
from uuid import uuid4
from typing import Any

from .schemas import ManagedDataset, ManagedRepresentation, ViewerLoadState


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class MSIRepository:
    """
    Thin SQLite-backed repository for MSI lifecycle state.

    This is intentionally small for Block 1A. Keep all persistence access behind
    this class so SQLite can later be replaced by Postgres without touching the
    viewer/frontend contract.
    """

    def __init__(self, db_path: Path | None = None) -> None:
        backend_dir = Path(__file__).resolve().parents[2]
        self.db_path = db_path or backend_dir / "data" / "msi" / "msi.sqlite"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_db()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS msi_datasets (
                    dataset_id TEXT PRIMARY KEY,
                    dataset_type TEXT NOT NULL DEFAULT 'unknown',
                    display_name TEXT NOT NULL,
                    survey_name TEXT,
                    line_name TEXT,
                    volume_name TEXT,
                    processing_stage TEXT,
                    processing_version TEXT,
                    source_reference_json TEXT NOT NULL DEFAULT '{}',
                    registration_state TEXT NOT NULL DEFAULT 'registered',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS msi_representations (
                    representation_id TEXT PRIMARY KEY,
                    dataset_id TEXT NOT NULL,
                    representation_type TEXT NOT NULL DEFAULT 'unknown',
                    viewer_mode TEXT NOT NULL DEFAULT 'none',
                    storage_uri TEXT,
                    lifecycle_state TEXT NOT NULL DEFAULT 'not_created',
                    viewer_ready INTEGER NOT NULL DEFAULT 0,
                    is_preferred INTEGER NOT NULL DEFAULT 0,
                    artifact_summary_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(dataset_id) REFERENCES msi_datasets(dataset_id)
                );

                CREATE TABLE IF NOT EXISTS msi_artifact_jobs (
                    job_id TEXT PRIMARY KEY,
                    job_type TEXT NOT NULL,
                    dataset_id TEXT,
                    representation_id TEXT,
                    status TEXT NOT NULL DEFAULT 'queued',
                    progress REAL,
                    message TEXT,
                    logs_uri TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS msi_viewer_loads (
                    load_id TEXT PRIMARY KEY,
                    dataset_id TEXT NOT NULL,
                    representation_id TEXT NOT NULL,
                    viewer_mode TEXT NOT NULL,
                    loaded INTEGER NOT NULL DEFAULT 1,
                    loaded_at TEXT,
                    unloaded_at TEXT,
                    UNIQUE(representation_id),
                    FOREIGN KEY(dataset_id) REFERENCES msi_datasets(dataset_id),
                    FOREIGN KEY(representation_id) REFERENCES msi_representations(representation_id)
                );

                CREATE INDEX IF NOT EXISTS idx_msi_repr_dataset
                    ON msi_representations(dataset_id);

                CREATE INDEX IF NOT EXISTS idx_msi_loads_loaded
                    ON msi_viewer_loads(loaded);
                """
            )

    @staticmethod
    def _json_loads(value: str | None) -> dict[str, Any]:
        if not value:
            return {}
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}

    def list_datasets(self) -> list[ManagedDataset]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM msi_datasets ORDER BY display_name COLLATE NOCASE"
            ).fetchall()
        return [self._dataset_from_row(row) for row in rows]

    def get_dataset(self, dataset_id: str) -> ManagedDataset | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM msi_datasets WHERE dataset_id = ?",
                (dataset_id,),
            ).fetchone()
        return self._dataset_from_row(row) if row else None

    def list_representations(self, dataset_id: str | None = None) -> list[ManagedRepresentation]:
        with self.connect() as conn:
            if dataset_id:
                rows = conn.execute(
                    """
                    SELECT * FROM msi_representations
                    WHERE dataset_id = ?
                    ORDER BY is_preferred DESC, viewer_ready DESC, representation_type
                    """,
                    (dataset_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM msi_representations
                    ORDER BY dataset_id, is_preferred DESC, viewer_ready DESC, representation_type
                    """
                ).fetchall()
        return [self._representation_from_row(row) for row in rows]

    def get_representation(self, representation_id: str) -> ManagedRepresentation | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM msi_representations WHERE representation_id = ?",
                (representation_id,),
            ).fetchone()
        return self._representation_from_row(row) if row else None

    def list_loaded_states(self, dataset_id: str | None = None) -> list[ViewerLoadState]:
        with self.connect() as conn:
            if dataset_id:
                rows = conn.execute(
                    """
                    SELECT * FROM msi_viewer_loads
                    WHERE dataset_id = ? AND loaded = 1
                    ORDER BY loaded_at DESC
                    """,
                    (dataset_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM msi_viewer_loads
                    WHERE loaded = 1
                    ORDER BY loaded_at DESC
                    """
                ).fetchall()
        return [self._load_from_row(row) for row in rows]

    def set_loaded(self, representation_id: str, loaded: bool) -> ViewerLoadState:
        representation = self.get_representation(representation_id)
        if not representation:
            raise ValueError(f"Representation not found: {representation_id}")

        if loaded and not representation.viewer_ready:
            raise ValueError(f"Representation is not viewer-ready: {representation_id}")

        now = utc_now()

        with self.connect() as conn:
            existing = conn.execute(
                "SELECT * FROM msi_viewer_loads WHERE representation_id = ?",
                (representation_id,),
            ).fetchone()

            if existing:
                conn.execute(
                    """
                    UPDATE msi_viewer_loads
                    SET loaded = ?, loaded_at = ?, unloaded_at = ?
                    WHERE representation_id = ?
                    """,
                    (
                        1 if loaded else 0,
                        now if loaded else existing["loaded_at"],
                        None if loaded else now,
                        representation_id,
                    ),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO msi_viewer_loads (
                        load_id, dataset_id, representation_id, viewer_mode,
                        loaded, loaded_at, unloaded_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        f"load_{uuid4().hex[:12]}",
                        representation.dataset_id,
                        representation.representation_id,
                        representation.viewer_mode,
                        1 if loaded else 0,
                        now if loaded else None,
                        None if loaded else now,
                    ),
                )

            row = conn.execute(
                "SELECT * FROM msi_viewer_loads WHERE representation_id = ?",
                (representation_id,),
            ).fetchone()

        return self._load_from_row(row)


    def upsert_test_seed_plan(
        self,
        datasets: list[dict[str, Any]],
        representations: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """
        Insert/update test-only MSI rows.

        This method is intentionally constrained:
        - accepts only rows with source_reference.test_content or artifact_summary.test_content
        - does not create viewer load state
        - is idempotent by primary key
        """
        now = utc_now()
        dataset_upserts = 0
        representation_upserts = 0

        with self.connect() as conn:
            for row in datasets:
                source_reference = row.get("source_reference") or {}
                if source_reference.get("test_content") is not True:
                    raise ValueError(f"Refusing to seed non-test dataset: {row.get('dataset_id')}")

                dataset_id = str(row.get("dataset_id") or "").strip()
                display_name = str(row.get("display_name") or dataset_id).strip()
                if not dataset_id:
                    raise ValueError("Dataset row missing dataset_id")

                existing = conn.execute(
                    "SELECT created_at, source_reference_json, registration_state FROM msi_datasets WHERE dataset_id = ?",
                    (dataset_id,),
                ).fetchone()

                if existing:
                    existing_source_reference = self._json_loads(existing["source_reference_json"])
                    existing_is_test = existing_source_reference.get("test_content") is True
                    existing_state = str(existing["registration_state"] or "")

                    # Test-seed must never downgrade or overwrite a production MSI row.
                    if not existing_is_test and existing_state != "test_seed_candidate":
                        continue

                created_at = existing["created_at"] if existing else now

                conn.execute(
                    """
                    INSERT INTO msi_datasets (
                        dataset_id, dataset_type, display_name,
                        survey_name, line_name, volume_name,
                        processing_stage, processing_version,
                        source_reference_json, registration_state,
                        created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(dataset_id) DO UPDATE SET
                        dataset_type = excluded.dataset_type,
                        display_name = excluded.display_name,
                        survey_name = excluded.survey_name,
                        line_name = excluded.line_name,
                        volume_name = excluded.volume_name,
                        processing_stage = excluded.processing_stage,
                        processing_version = excluded.processing_version,
                        source_reference_json = excluded.source_reference_json,
                        registration_state = excluded.registration_state,
                        updated_at = excluded.updated_at
                    """,
                    (
                        dataset_id,
                        row.get("dataset_type") or "unknown",
                        display_name,
                        row.get("survey_name"),
                        row.get("line_name"),
                        row.get("volume_name"),
                        row.get("processing_stage"),
                        row.get("processing_version"),
                        json.dumps(source_reference, sort_keys=True),
                        row.get("registration_state") or "test_seed_candidate",
                        created_at,
                        now,
                    ),
                )
                dataset_upserts += 1

            for row in representations:
                artifact_summary = row.get("artifact_summary") or {}
                if artifact_summary.get("test_content") is not True:
                    raise ValueError(f"Refusing to seed non-test representation: {row.get('representation_id')}")

                representation_id = str(row.get("representation_id") or "").strip()
                dataset_id = str(row.get("dataset_id") or "").strip()

                if not representation_id:
                    raise ValueError("Representation row missing representation_id")
                if not dataset_id:
                    raise ValueError(f"Representation row missing dataset_id: {representation_id}")

                existing = conn.execute(
                    "SELECT created_at, artifact_summary_json FROM msi_representations WHERE representation_id = ?",
                    (representation_id,),
                ).fetchone()

                if existing:
                    existing_artifact_summary = self._json_loads(existing["artifact_summary_json"])
                    existing_is_test = existing_artifact_summary.get("test_content") is True

                    # Test-seed must never overwrite a production MSI representation.
                    if not existing_is_test:
                        continue

                created_at = existing["created_at"] if existing else now

                conn.execute(
                    """
                    INSERT INTO msi_representations (
                        representation_id, dataset_id,
                        representation_type, viewer_mode, storage_uri,
                        lifecycle_state, viewer_ready, is_preferred,
                        artifact_summary_json, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(representation_id) DO UPDATE SET
                        dataset_id = excluded.dataset_id,
                        representation_type = excluded.representation_type,
                        viewer_mode = excluded.viewer_mode,
                        storage_uri = excluded.storage_uri,
                        lifecycle_state = excluded.lifecycle_state,
                        viewer_ready = excluded.viewer_ready,
                        is_preferred = excluded.is_preferred,
                        artifact_summary_json = excluded.artifact_summary_json,
                        updated_at = excluded.updated_at
                    """,
                    (
                        representation_id,
                        dataset_id,
                        row.get("representation_type") or "unknown",
                        row.get("viewer_mode") or "none",
                        row.get("storage_uri"),
                        row.get("lifecycle_state") or "not_created",
                        1 if row.get("viewer_ready") else 0,
                        1 if row.get("is_preferred") else 0,
                        json.dumps(artifact_summary, sort_keys=True),
                        created_at,
                        now,
                    ),
                )
                representation_upserts += 1

        return {
            "dataset_upserts": dataset_upserts,
            "representation_upserts": representation_upserts,
            "writes_performed": True,
            "test_seed": True,
        }


    def upsert_managed_inventory(
        self,
        datasets: list[dict[str, Any]],
        representations: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """
        Insert/update normal MSI managed inventory rows.

        This is the production-style counterpart to upsert_test_seed_plan().
        It is idempotent by dataset_id / representation_id and does not create
        viewer load state.
        """
        now = utc_now()
        dataset_upserts = 0
        representation_upserts = 0

        with self.connect() as conn:
            for row in datasets:
                dataset_id = str(row.get("dataset_id") or "").strip()
                display_name = str(row.get("display_name") or dataset_id).strip()
                source_reference = row.get("source_reference") or {}

                if not dataset_id:
                    raise ValueError("Dataset row missing dataset_id")
                if not display_name:
                    raise ValueError(f"Dataset row missing display_name: {dataset_id}")

                existing = conn.execute(
                    """
                    SELECT
                        created_at, display_name,
                        survey_name, line_name, volume_name,
                        processing_stage, processing_version,
                        source_reference_json
                    FROM msi_datasets
                    WHERE dataset_id = ?
                    """,
                    (dataset_id,),
                ).fetchone()

                created_at = existing["created_at"] if existing else now
                effective_display_name = display_name
                effective_source_reference = dict(source_reference)

                if existing:
                    existing_source_reference = self._json_loads(existing["source_reference_json"])
                    if existing_source_reference.get("display_name_override") is True:
                        effective_display_name = str(existing["display_name"] or display_name)
                        for key in (
                            "display_name_override",
                            "display_name_override_source",
                            "display_name_override_at",
                        ):
                            if key in existing_source_reference:
                                effective_source_reference[key] = existing_source_reference[key]

                    existing_admin_field_overrides = existing_source_reference.get("admin_field_overrides")
                    if isinstance(existing_admin_field_overrides, dict) and existing_admin_field_overrides:
                        effective_source_reference["admin_field_overrides"] = existing_admin_field_overrides

                    existing_metadata_overrides = existing_source_reference.get("dataset_metadata_overrides")
                    if isinstance(existing_metadata_overrides, dict) and existing_metadata_overrides:
                        effective_source_reference["dataset_metadata_overrides"] = existing_metadata_overrides

                        for field_name in (
                            "survey_name",
                            "line_name",
                            "volume_name",
                            "processing_stage",
                            "processing_version",
                        ):
                            if field_name in existing_metadata_overrides:
                                row[field_name] = existing[field_name]

                conn.execute(
                    """
                    INSERT INTO msi_datasets (
                        dataset_id, dataset_type, display_name,
                        survey_name, line_name, volume_name,
                        processing_stage, processing_version,
                        source_reference_json, registration_state,
                        created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(dataset_id) DO UPDATE SET
                        dataset_type = excluded.dataset_type,
                        display_name = excluded.display_name,
                        survey_name = excluded.survey_name,
                        line_name = excluded.line_name,
                        volume_name = excluded.volume_name,
                        processing_stage = excluded.processing_stage,
                        processing_version = excluded.processing_version,
                        source_reference_json = excluded.source_reference_json,
                        registration_state = excluded.registration_state,
                        updated_at = excluded.updated_at
                    """,
                    (
                        dataset_id,
                        row.get("dataset_type") or "unknown",
                        effective_display_name,
                        row.get("survey_name"),
                        row.get("line_name"),
                        row.get("volume_name"),
                        row.get("processing_stage"),
                        row.get("processing_version"),
                        json.dumps(effective_source_reference, sort_keys=True),
                        row.get("registration_state") or "registered",
                        created_at,
                        now,
                    ),
                )
                dataset_upserts += 1

            for row in representations:
                representation_id = str(row.get("representation_id") or "").strip()
                dataset_id = str(row.get("dataset_id") or "").strip()
                artifact_summary = row.get("artifact_summary") or {}

                if not representation_id:
                    raise ValueError("Representation row missing representation_id")
                if not dataset_id:
                    raise ValueError(f"Representation row missing dataset_id: {representation_id}")

                existing = conn.execute(
                    "SELECT created_at FROM msi_representations WHERE representation_id = ?",
                    (representation_id,),
                ).fetchone()

                created_at = existing["created_at"] if existing else now

                conn.execute(
                    """
                    INSERT INTO msi_representations (
                        representation_id, dataset_id,
                        representation_type, viewer_mode, storage_uri,
                        lifecycle_state, viewer_ready, is_preferred,
                        artifact_summary_json, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(representation_id) DO UPDATE SET
                        dataset_id = excluded.dataset_id,
                        representation_type = excluded.representation_type,
                        viewer_mode = excluded.viewer_mode,
                        storage_uri = excluded.storage_uri,
                        lifecycle_state = excluded.lifecycle_state,
                        viewer_ready = excluded.viewer_ready,
                        is_preferred = excluded.is_preferred,
                        artifact_summary_json = excluded.artifact_summary_json,
                        updated_at = excluded.updated_at
                    """,
                    (
                        representation_id,
                        dataset_id,
                        row.get("representation_type") or "unknown",
                        row.get("viewer_mode") or "none",
                        row.get("storage_uri"),
                        row.get("lifecycle_state") or "not_created",
                        1 if row.get("viewer_ready") else 0,
                        1 if row.get("is_preferred") else 0,
                        json.dumps(artifact_summary, sort_keys=True),
                        created_at,
                        now,
                    ),
                )
                representation_upserts += 1

        return {
            "dataset_upserts": dataset_upserts,
            "representation_upserts": representation_upserts,
            "writes_performed": True,
            "test_seed": False,
        }

    def update_dataset_display_name(self, dataset_id: str, display_name: str) -> ManagedDataset:
        clean_dataset_id = str(dataset_id or "").strip()
        clean_display_name = str(display_name or "").strip()

        if not clean_dataset_id:
            raise ValueError("dataset_id is required")

        if not clean_display_name:
            raise ValueError("display_name is required")

        now = utc_now()

        with self.connect() as conn:
            existing = conn.execute(
                "SELECT * FROM msi_datasets WHERE dataset_id = ?",
                (clean_dataset_id,),
            ).fetchone()

            if not existing:
                raise ValueError(f"Dataset not found: {clean_dataset_id}")

            source_reference = self._json_loads(existing["source_reference_json"])
            source_reference.update(
                {
                    "display_name_override": True,
                    "display_name_override_source": "manual_msi_admin",
                    "display_name_override_at": now,
                }
            )

            conn.execute(
                """
                UPDATE msi_datasets
                SET display_name = ?, source_reference_json = ?, updated_at = ?
                WHERE dataset_id = ?
                """,
                (
                    clean_display_name,
                    json.dumps(source_reference, sort_keys=True),
                    now,
                    clean_dataset_id,
                ),
            )

            row = conn.execute(
                "SELECT * FROM msi_datasets WHERE dataset_id = ?",
                (clean_dataset_id,),
            ).fetchone()

        return self._dataset_from_row(row)

    def update_dataset_descriptive_metadata(
        self,
        dataset_id: str,
        updates: dict[str, str | None],
    ) -> ManagedDataset:
        clean_dataset_id = str(dataset_id or "").strip()

        if not clean_dataset_id:
            raise ValueError("dataset_id is required")

        editable_fields = {
            "survey_name",
            "line_name",
            "volume_name",
            "processing_stage",
            "processing_version",
        }

        clean_updates = {key: updates[key] for key in updates if key in editable_fields}

        if not clean_updates:
            raise ValueError("At least one editable dataset metadata field is required")

        now = utc_now()

        with self.connect() as conn:
            existing = conn.execute(
                "SELECT * FROM msi_datasets WHERE dataset_id = ?",
                (clean_dataset_id,),
            ).fetchone()

            if not existing:
                raise ValueError(f"Dataset not found: {clean_dataset_id}")

            source_reference = self._json_loads(existing["source_reference_json"])
            metadata_overrides = source_reference.get("dataset_metadata_overrides")
            if not isinstance(metadata_overrides, dict):
                metadata_overrides = {}

            for field_name, value in clean_updates.items():
                if value is None:
                    metadata_overrides.pop(field_name, None)
                else:
                    metadata_overrides[field_name] = {
                        "source": "manual_msi_admin",
                        "at": now,
                    }

            if metadata_overrides:
                source_reference["dataset_metadata_overrides"] = metadata_overrides
            else:
                source_reference.pop("dataset_metadata_overrides", None)

            update_values = {
                "survey_name": existing["survey_name"],
                "line_name": existing["line_name"],
                "volume_name": existing["volume_name"],
                "processing_stage": existing["processing_stage"],
                "processing_version": existing["processing_version"],
            }
            update_values.update(clean_updates)

            conn.execute(
                """
                UPDATE msi_datasets
                SET
                    survey_name = ?,
                    line_name = ?,
                    volume_name = ?,
                    processing_stage = ?,
                    processing_version = ?,
                    source_reference_json = ?,
                    updated_at = ?
                WHERE dataset_id = ?
                """,
                (
                    update_values["survey_name"],
                    update_values["line_name"],
                    update_values["volume_name"],
                    update_values["processing_stage"],
                    update_values["processing_version"],
                    json.dumps(source_reference, sort_keys=True),
                    now,
                    clean_dataset_id,
                ),
            )

            row = conn.execute(
                "SELECT * FROM msi_datasets WHERE dataset_id = ?",
                (clean_dataset_id,),
            ).fetchone()

        return self._dataset_from_row(row)



    def admin_update_dataset_fields(
        self,
        dataset_id: str,
        updates: dict[str, str | None],
        *,
        reason: str,
        evidence_ref: str | None = None,
    ) -> ManagedDataset:
        clean_dataset_id = str(dataset_id or "").strip()
        clean_reason = str(reason or "").strip()
        clean_evidence_ref = str(evidence_ref or "").strip() or None

        if not clean_dataset_id:
            raise ValueError("dataset_id is required")

        if not clean_reason:
            raise ValueError("reason is required for MSI admin field updates")

        editable_fields = {
            "display_name",
            "survey_name",
            "line_name",
            "volume_name",
            "processing_stage",
            "processing_version",
        }

        clean_updates = {key: updates[key] for key in updates if key in editable_fields}

        if not clean_updates:
            raise ValueError("At least one admin-editable MSI dataset field is required")

        if "display_name" in clean_updates:
            display_name = str(clean_updates.get("display_name") or "").strip()
            if not display_name:
                raise ValueError("display_name cannot be cleared by generic admin field update")
            clean_updates["display_name"] = display_name

        now = utc_now()

        with self.connect() as conn:
            existing = conn.execute(
                "SELECT * FROM msi_datasets WHERE dataset_id = ?",
                (clean_dataset_id,),
            ).fetchone()

            if not existing:
                raise ValueError(f"Dataset not found: {clean_dataset_id}")

            source_reference = self._json_loads(existing["source_reference_json"])

            admin_field_overrides = source_reference.get("admin_field_overrides")
            if not isinstance(admin_field_overrides, dict):
                admin_field_overrides = {}

            for field_name, value in clean_updates.items():
                admin_field_overrides[field_name] = {
                    "source": "manual_msi_admin",
                    "reason": clean_reason,
                    "evidence_ref": clean_evidence_ref,
                    "at": now,
                }

            source_reference["admin_field_overrides"] = admin_field_overrides

            if "display_name" in clean_updates:
                source_reference.update(
                    {
                        "display_name_override": True,
                        "display_name_override_source": "manual_msi_admin",
                        "display_name_override_at": now,
                    }
                )

            metadata_fields = {
                "survey_name",
                "line_name",
                "volume_name",
                "processing_stage",
                "processing_version",
            }
            metadata_overrides = source_reference.get("dataset_metadata_overrides")
            if not isinstance(metadata_overrides, dict):
                metadata_overrides = {}

            for field_name in metadata_fields:
                if field_name in clean_updates:
                    value = clean_updates[field_name]
                    if value is None:
                        metadata_overrides.pop(field_name, None)
                    else:
                        metadata_overrides[field_name] = {
                            "source": "manual_msi_admin",
                            "at": now,
                            "reason": clean_reason,
                            "evidence_ref": clean_evidence_ref,
                        }

            if metadata_overrides:
                source_reference["dataset_metadata_overrides"] = metadata_overrides
            else:
                source_reference.pop("dataset_metadata_overrides", None)

            update_values = {
                "display_name": existing["display_name"],
                "survey_name": existing["survey_name"],
                "line_name": existing["line_name"],
                "volume_name": existing["volume_name"],
                "processing_stage": existing["processing_stage"],
                "processing_version": existing["processing_version"],
            }
            update_values.update(clean_updates)

            conn.execute(
                """
                UPDATE msi_datasets
                SET
                    display_name = ?,
                    survey_name = ?,
                    line_name = ?,
                    volume_name = ?,
                    processing_stage = ?,
                    processing_version = ?,
                    source_reference_json = ?,
                    updated_at = ?
                WHERE dataset_id = ?
                """,
                (
                    update_values["display_name"],
                    update_values["survey_name"],
                    update_values["line_name"],
                    update_values["volume_name"],
                    update_values["processing_stage"],
                    update_values["processing_version"],
                    json.dumps(source_reference, sort_keys=True),
                    now,
                    clean_dataset_id,
                ),
            )

            row = conn.execute(
                "SELECT * FROM msi_datasets WHERE dataset_id = ?",
                (clean_dataset_id,),
            ).fetchone()

        return self._dataset_from_row(row)




    def mark_representation_invalid(
        self,
        representation_id: str,
        *,
        lifecycle_state: str = "failed",
        reason: str = "backend_cleanup",
        clear_preferred: bool = True,
        viewer_ready: bool = False,
    ) -> ManagedRepresentation | None:
        """
        Backend-owned safety valve for failed cleanup/reconcile cases.

        This does not delete the dataset row and does not touch artifact files.
        It marks the MSI representation as not viewer-ready so Managed Data and
        viewer selection cannot expose a stale or contract-invalid artifact.
        """
        clean_representation_id = str(representation_id or "").strip()
        if not clean_representation_id:
            raise ValueError("representation_id is required")

        now = utc_now()
        with self.connect() as conn:
            existing = conn.execute(
                "SELECT * FROM msi_representations WHERE representation_id = ?",
                (clean_representation_id,),
            ).fetchone()

            if not existing:
                return None

            artifact_summary = self._json_loads(existing["artifact_summary_json"])
            artifact_summary.setdefault("invalidations", [])
            invalidations = artifact_summary.get("invalidations")
            if not isinstance(invalidations, list):
                invalidations = []
                artifact_summary["invalidations"] = invalidations

            invalidations.append(
                {
                    "at": now,
                    "reason": str(reason or "backend_cleanup"),
                    "previous_lifecycle_state": existing["lifecycle_state"],
                    "previous_viewer_ready": bool(existing["viewer_ready"]),
                    "previous_is_preferred": bool(existing["is_preferred"]),
                }
            )
            artifact_summary["failed"] = True
            artifact_summary["invalidated_at"] = now
            artifact_summary["invalidated_reason"] = str(reason or "backend_cleanup")

            conn.execute(
                """
                UPDATE msi_representations
                SET lifecycle_state = ?,
                    viewer_ready = ?,
                    is_preferred = ?,
                    artifact_summary_json = ?,
                    updated_at = ?
                WHERE representation_id = ?
                """,
                (
                    str(lifecycle_state or "failed"),
                    1 if viewer_ready else 0,
                    0 if clear_preferred else int(existing["is_preferred"]),
                    json.dumps(artifact_summary, sort_keys=True),
                    now,
                    clean_representation_id,
                ),
            )

            conn.execute(
                """
                UPDATE msi_viewer_loads
                SET loaded = 0, unloaded_at = ?
                WHERE representation_id = ? AND loaded = 1
                """,
                (now, clean_representation_id),
            )

            row = conn.execute(
                "SELECT * FROM msi_representations WHERE representation_id = ?",
                (clean_representation_id,),
            ).fetchone()

        return self._representation_from_row(row) if row else None


    def delete_managed_representation_full(self, representation_id: str) -> dict[str, Any] | None:
        """
        Fully delete an MSI managed representation and its MSI lifecycle rows.

        This is the current Managed Data delete contract: remove the viewer load
        state, representation row, dataset row when no representations remain,
        and return source/artifact identity so the caller can reset source-side
        conversion linkage and delete the managed artifact from storage.
        """
        clean_representation_id = str(representation_id or "").strip()
        if not clean_representation_id:
            raise ValueError("representation_id is required")

        now = utc_now()
        with self.connect() as conn:
            rep_row = conn.execute(
                "SELECT * FROM msi_representations WHERE representation_id = ?",
                (clean_representation_id,),
            ).fetchone()

            if not rep_row:
                return None

            dataset_id = rep_row["dataset_id"]
            dataset_row = conn.execute(
                "SELECT * FROM msi_datasets WHERE dataset_id = ?",
                (dataset_id,),
            ).fetchone()

            artifact_summary = self._json_loads(rep_row["artifact_summary_json"])
            source_reference = self._json_loads(dataset_row["source_reference_json"]) if dataset_row else {}

            conn.execute(
                "DELETE FROM msi_viewer_loads WHERE representation_id = ?",
                (clean_representation_id,),
            )
            conn.execute(
                "DELETE FROM msi_artifact_jobs WHERE representation_id = ?",
                (clean_representation_id,),
            )
            conn.execute(
                "DELETE FROM msi_representations WHERE representation_id = ?",
                (clean_representation_id,),
            )

            remaining = conn.execute(
                "SELECT COUNT(*) AS count FROM msi_representations WHERE dataset_id = ?",
                (dataset_id,),
            ).fetchone()
            remaining_count = int(remaining["count"] if remaining else 0)

            dataset_deleted = False
            if remaining_count == 0:
                conn.execute(
                    "DELETE FROM msi_artifact_jobs WHERE dataset_id = ?",
                    (dataset_id,),
                )
                conn.execute(
                    "DELETE FROM msi_datasets WHERE dataset_id = ?",
                    (dataset_id,),
                )
                dataset_deleted = True

        return {
            "status": "deleted",
            "delete_mode": "full_managed_lifecycle",
            "representation_id": clean_representation_id,
            "dataset_id": dataset_id,
            "dataset_deleted": dataset_deleted,
            "remaining_representations_for_dataset": remaining_count,
            "artifact_summary": artifact_summary,
            "source_reference": source_reference,
            "deleted_at": now,
        }

    def mark_representations_invalid_by_artifact_id(
        self,
        artifact_id: str,
        *,
        reason: str = "backend_cleanup",
    ) -> dict[str, Any]:
        """
        Mark all MSI representations whose artifact_summary.volume_id matches
        the supplied physical artifact id as not viewer-ready.
        """
        clean_artifact_id = str(artifact_id or "").strip()
        if not clean_artifact_id:
            raise ValueError("artifact_id is required")

        with self.connect() as conn:
            rows = conn.execute(
                "SELECT representation_id, artifact_summary_json FROM msi_representations"
            ).fetchall()

        matched: list[str] = []
        for row in rows:
            artifact_summary = self._json_loads(row["artifact_summary_json"])
            if str(artifact_summary.get("volume_id") or "").strip() == clean_artifact_id:
                matched.append(row["representation_id"])

        updated = 0
        for representation_id in matched:
            result = self.mark_representation_invalid(
                representation_id,
                lifecycle_state="failed",
                reason=reason,
                clear_preferred=True,
                viewer_ready=False,
            )
            if result is not None:
                updated += 1

        return {
            "artifact_id": clean_artifact_id,
            "matched": len(matched),
            "updated": updated,
            "representation_ids": matched,
        }

    def purge_test_seed(self) -> dict[str, Any]:
        """
        Remove only MSI rows explicitly marked as test content.

        This does not delete source registry records, Zarr folders, SEG-Y index
        folders, or any viewer/source data artifacts.
        """
        with self.connect() as conn:
            test_repr_rows = conn.execute(
                """
                SELECT representation_id FROM msi_representations
                WHERE json_extract(artifact_summary_json, '$.test_content') = 1
                """
            ).fetchall()

            test_dataset_rows = conn.execute(
                """
                SELECT dataset_id FROM msi_datasets
                WHERE json_extract(source_reference_json, '$.test_content') = 1
                """
            ).fetchall()

            representation_ids = [row["representation_id"] for row in test_repr_rows]
            dataset_ids = [row["dataset_id"] for row in test_dataset_rows]

            # Remove load state for test representations first, if any were created manually later.
            for representation_id in representation_ids:
                conn.execute(
                    "DELETE FROM msi_viewer_loads WHERE representation_id = ?",
                    (representation_id,),
                )

            for representation_id in representation_ids:
                conn.execute(
                    "DELETE FROM msi_representations WHERE representation_id = ?",
                    (representation_id,),
                )

            for dataset_id in dataset_ids:
                conn.execute(
                    "DELETE FROM msi_datasets WHERE dataset_id = ?",
                    (dataset_id,),
                )

        return {
            "datasets_deleted": len(dataset_ids),
            "representations_deleted": len(representation_ids),
            "writes_performed": True,
            "test_seed": True,
            "artifact_files_deleted": 0,
            "source_registry_records_deleted": 0,
        }

    def _dataset_from_row(self, row: sqlite3.Row) -> ManagedDataset:
        return ManagedDataset(
            dataset_id=row["dataset_id"],
            dataset_type=row["dataset_type"],
            display_name=row["display_name"],
            survey_name=row["survey_name"],
            line_name=row["line_name"],
            volume_name=row["volume_name"],
            processing_stage=row["processing_stage"],
            processing_version=row["processing_version"],
            source_reference=self._json_loads(row["source_reference_json"]),
            registration_state=row["registration_state"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def _representation_from_row(self, row: sqlite3.Row) -> ManagedRepresentation:
        return ManagedRepresentation(
            representation_id=row["representation_id"],
            dataset_id=row["dataset_id"],
            representation_type=row["representation_type"],
            viewer_mode=row["viewer_mode"],
            storage_uri=row["storage_uri"],
            lifecycle_state=row["lifecycle_state"],
            viewer_ready=bool(row["viewer_ready"]),
            is_preferred=bool(row["is_preferred"]),
            artifact_summary=self._json_loads(row["artifact_summary_json"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def _load_from_row(self, row: sqlite3.Row) -> ViewerLoadState:
        return ViewerLoadState(
            load_id=row["load_id"],
            dataset_id=row["dataset_id"],
            representation_id=row["representation_id"],
            viewer_mode=row["viewer_mode"],
            loaded=bool(row["loaded"]),
            loaded_at=row["loaded_at"],
            unloaded_at=row["unloaded_at"],
        )
