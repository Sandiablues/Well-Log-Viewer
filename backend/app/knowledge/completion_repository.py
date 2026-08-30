"""Durable governed KR repository for completion knowledge.

This module owns the persisted completion ontology and completion-standard
records used by KR Manager and downstream MultiViewer consumers.

It intentionally keeps the completion domain separate from the curve-specific
managed record dataclasses while using the same KR governance principles:
candidate -> approved/rejected, approved -> deprecated, production eligibility,
audit history, stable canonical IDs, and durable file-backed storage.
"""
from __future__ import annotations

import copy
import json
import os
import shutil
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


_DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "knowledge" / "completions"
_CATALOGUE = _DATA_DIR / "completion-knowledge.json"
_BACKUP_DIR = _DATA_DIR / "backups"
_AUDIT_LOG = _DATA_DIR / "completion-knowledge-audit.jsonl"
_LOCK = threading.RLock()

_ALLOWED_STATUSES = {"candidate", "approved", "rejected", "deprecated"}
_ALLOWED_RECORD_TYPES = {"component", "standard"}


_GEOMETRY_BY_CANONICAL = {
    "completion.tubing": "interval",
    "completion.casing": "interval",
    "completion.liner": "interval",
    "completion.screen": "interval",
    "completion.open_hole": "interval",
    "completion.perforations": "interval",
    "completion.packer": "point_or_short_interval",
    "completion.safety_valve": "point_or_short_interval",
    "completion.downhole_valve": "point_or_short_interval",
    "completion.sliding_sleeve": "point_or_short_interval",
    "completion.gas_lift": "point_or_short_interval",
    "completion.icd_aicd": "point_or_interval_association",
    "completion.bridge_plug": "point_or_short_interval",
    "completion.retainer": "point_or_short_interval",
    "completion.cement_barrier": "point_or_interval",
}

# KR-owned repeatable completion rendering contract. WDV and future completion
# viewers must map canonical identity through these governed semantic families.
#
# WDV Completion Glyph Standard V1:
# All 15 normal canonical completion families carry a governed `wdvGlyph`.
# `wdvGlyphStatus=visually_reviewed` identifies glyphs explicitly reviewed and
# accepted in WDV. `wdvGlyphStatus=baseline_locked` identifies the existing WDV
# glyph implementation captured as the V1 baseline pending future visual review.
# `labelIndependentIdentity=required` means the glyph must remain interpretable
# without relying on its text label. `completion.other` remains the canonical
# fallback and is not one of the 15 normal completion-family glyphs.
_RENDER_RECIPE_BY_CANONICAL: dict[str, dict[str, str]] = {
    "completion.tubing": {"geometryFamily": "tubular", "materialFamily": "metal_polished", "annotationPolicy": "interval_aligned_conditional_leader", "wdvGlyph": "wdv.completion.tubing.distinct_interval.v1", "wdvGlyphVersion": "1.0", "labelIndependentIdentity": "required", "wdvGlyphStatus": "visually_reviewed", "wbvGlyph": "wbv.completion.tubing.tubular_interval.v1", "wbvGlyphVersion": "1.0", "wbvGlyphStatus": "visually_reviewed"},
    "completion.casing": {"geometryFamily": "tubular", "materialFamily": "metal_brushed", "annotationPolicy": "interval_aligned_conditional_leader", "wdvGlyph": "wdv.completion.casing.brushed_tubular_interval.v1", "wdvGlyphVersion": "1.0", "labelIndependentIdentity": "required", "wdvGlyphStatus": "baseline_locked", "wbvGlyph": "wbv.completion.casing.tubular_interval.v1", "wbvGlyphVersion": "1.0", "wbvGlyphStatus": "baseline_locked"},
    "completion.liner": {"geometryFamily": "tubular", "materialFamily": "metal_brushed", "annotationPolicy": "interval_aligned_conditional_leader", "wdvGlyph": "wdv.completion.liner.brushed_tubular_interval.v1", "wdvGlyphVersion": "1.0", "labelIndependentIdentity": "required", "wdvGlyphStatus": "baseline_locked", "wbvGlyph": "wbv.completion.liner.tubular_interval.v1", "wbvGlyphVersion": "1.0", "wbvGlyphStatus": "baseline_locked"},
    "completion.screen": {"geometryFamily": "screen_interval", "materialFamily": "metal_mesh", "annotationPolicy": "interval_aligned_conditional_leader", "wdvGlyph": "wdv.completion.screen.ribbed_interval.v1", "wdvGlyphVersion": "1.0", "labelIndependentIdentity": "required", "wdvGlyphStatus": "visually_reviewed", "wbvGlyph": "wbv.completion.screen.mesh_interval.v1", "wbvGlyphVersion": "1.0", "wbvGlyphStatus": "visually_reviewed"},
    "completion.open_hole": {"geometryFamily": "open_hole_interval", "materialFamily": "formation_matte", "annotationPolicy": "interval_aligned_conditional_leader", "wdvGlyph": "wdv.completion.open_hole.formation_interval.v1", "wdvGlyphVersion": "1.0", "labelIndependentIdentity": "required", "wdvGlyphStatus": "baseline_locked", "wbvGlyph": "wbv.completion.open_hole.borehole_interval.v1", "wbvGlyphVersion": "1.0", "wbvGlyphStatus": "baseline_locked"},
    "completion.perforations": {"geometryFamily": "perforation_cluster", "materialFamily": "perforation_cut", "annotationPolicy": "interval_aligned_conditional_leader", "wdvGlyph": "wdv.completion.perforations.cluster_interval.v1", "wdvGlyphVersion": "1.0", "labelIndependentIdentity": "required", "wdvGlyphStatus": "baseline_locked", "wbvGlyph": "wbv.completion.perforations.trajectory_interval.v1", "wbvGlyphVersion": "1.0", "wbvGlyphStatus": "baseline_locked"},
    "completion.packer": {"geometryFamily": "toolbody_annular", "materialFamily": "metal_dark_tool", "annotationPolicy": "aligned_conditional_leader", "wdvGlyph": "wdv.completion.packer.annular_isolation.v1", "wdvGlyphVersion": "1.0", "labelIndependentIdentity": "required", "wdvGlyphStatus": "visually_reviewed", "wbvGlyph": "wbv.completion.packer.annular_toolbody.v1", "wbvGlyphVersion": "1.0", "wbvGlyphStatus": "visually_reviewed"},
    "completion.safety_valve": {"geometryFamily": "valve_body", "materialFamily": "metal_brushed", "annotationPolicy": "aligned_conditional_leader", "wdvGlyph": "wdv.completion.safety_valve.symmetric_inline.v1", "wdvGlyphVersion": "1.0", "labelIndependentIdentity": "required", "wdvGlyphStatus": "visually_reviewed", "wbvGlyph": "wbv.completion.safety_valve.mechanical_inline.v1", "wbvGlyphVersion": "1.0", "wbvGlyphStatus": "visually_reviewed"},
    "completion.downhole_valve": {"geometryFamily": "valve_body", "materialFamily": "metal_brushed", "annotationPolicy": "aligned_conditional_leader", "wdvGlyph": "wdv.completion.downhole_valve.faceted_inline.v1", "wdvGlyphVersion": "1.0", "labelIndependentIdentity": "required", "wdvGlyphStatus": "visually_reviewed", "wbvGlyph": "wbv.completion.downhole_valve.cross_body.v1", "wbvGlyphVersion": "1.0", "wbvGlyphStatus": "visually_reviewed"},
    "completion.sliding_sleeve": {"geometryFamily": "valve_body", "materialFamily": "metal_brushed", "annotationPolicy": "aligned_conditional_leader", "wdvGlyph": "wdv.completion.sliding_sleeve.ported_body.v1", "wdvGlyphVersion": "1.0", "labelIndependentIdentity": "required", "wdvGlyphStatus": "visually_reviewed", "wbvGlyph": "wbv.completion.sliding_sleeve.ported_sleeve.v1", "wbvGlyphVersion": "1.0", "wbvGlyphStatus": "visually_reviewed"},
    "completion.gas_lift": {"geometryFamily": "mandrel_body", "materialFamily": "metal_brushed", "annotationPolicy": "aligned_conditional_leader", "wdvGlyph": "wdv.completion.gas_lift.sidecar_mandrel.v1", "wdvGlyphVersion": "1.0", "labelIndependentIdentity": "required", "wdvGlyphStatus": "visually_reviewed", "wbvGlyph": "wbv.completion.gas_lift.side_pod.v1", "wbvGlyphVersion": "1.0", "wbvGlyphStatus": "visually_reviewed"},
    "completion.icd_aicd": {"geometryFamily": "toolbody_inline", "materialFamily": "metal_dark_tool", "annotationPolicy": "aligned_conditional_leader", "wdvGlyph": "wdv.completion.icd_aicd.radial_nozzle.v1", "wdvGlyphVersion": "1.0", "labelIndependentIdentity": "required", "wdvGlyphStatus": "visually_reviewed", "wbvGlyph": "wbv.completion.icd_aicd.banded_toolbody.v1", "wbvGlyphVersion": "1.0", "wbvGlyphStatus": "visually_reviewed"},
    "completion.bridge_plug": {"geometryFamily": "toolbody_annular", "materialFamily": "metal_dark_tool", "annotationPolicy": "aligned_conditional_leader", "wdvGlyph": "wdv.completion.bridge_plug.opposed_cone.v1", "wdvGlyphVersion": "1.0", "labelIndependentIdentity": "required", "wdvGlyphStatus": "visually_reviewed", "wbvGlyph": "wbv.completion.bridge_plug.annular_plug.v1", "wbvGlyphVersion": "1.0", "wbvGlyphStatus": "visually_reviewed"},
    "completion.retainer": {"geometryFamily": "toolbody_annular", "materialFamily": "metal_dark_tool", "annotationPolicy": "aligned_conditional_leader", "wdvGlyph": "wdv.completion.retainer.annular_toolbody.v1", "wdvGlyphVersion": "1.0", "labelIndependentIdentity": "required", "wdvGlyphStatus": "baseline_locked", "wbvGlyph": "wbv.completion.retainer.annular_toolbody.v1", "wbvGlyphVersion": "1.0", "wbvGlyphStatus": "baseline_locked"},
    "completion.cement_barrier": {"geometryFamily": "annular_barrier", "materialFamily": "cement_matte", "annotationPolicy": "aligned_conditional_leader", "wdvGlyph": "wdv.completion.cement_barrier.annular_barrier.v1", "wdvGlyphVersion": "1.0", "labelIndependentIdentity": "required", "wdvGlyphStatus": "baseline_locked", "wbvGlyph": "wbv.completion.cement_barrier.annular_barrier.v1", "wbvGlyphVersion": "1.0", "wbvGlyphStatus": "baseline_locked"},
}


def completion_render_recipe(canonical_id: str) -> dict[str, str]:
    # Return the governed repeatable render recipe for a canonical completion identity.
    recipe = _RENDER_RECIPE_BY_CANONICAL.get(canonical_id)
    if recipe is None:
        return {
            "geometryFamily": "toolbody_inline",
            "materialFamily": "metal_dark_tool",
            "annotationPolicy": "aligned_conditional_leader",
        }
    return copy.deepcopy(recipe)


def completion_geometry_class(canonical_id: str) -> str:
    """Return KR-owned visualization geometry semantics for a completion identity."""
    return _GEOMETRY_BY_CANONICAL.get(canonical_id, "point_or_interval")


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _next_version(value: str) -> str:
    raw = value.strip().lower().lstrip("v")
    parts = raw.split(".")
    try:
        values = [int(part) for part in parts]
    except ValueError:
        return "v1.0"
    while len(values) < 2:
        values.append(0)
    values[-1] += 1
    return "v" + ".".join(str(v) for v in values)


class CompletionKnowledgeError(ValueError):
    pass


class CompletionKnowledgeNotFound(KeyError):
    pass


class CompletionKnowledgeConflict(RuntimeError):
    pass


class CompletionKnowledgeRepository:
    def __init__(self, path: Path | None = None) -> None:
        self._path = path or _CATALOGUE
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_document()

    def _ensure_document(self) -> None:
        if not self._path.is_file():
            raise RuntimeError(f"Completion KR catalogue is missing: {self._path}")
        self._load()

    def _load(self) -> dict[str, Any]:
        try:
            doc = json.loads(self._path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise RuntimeError(f"Completion KR catalogue cannot be read: {exc}") from exc
        if doc.get("schemaVersion") != "kr-completions-1.0":
            raise RuntimeError("Unsupported completion KR schemaVersion")
        records = doc.get("records")
        if not isinstance(records, list):
            raise RuntimeError("Completion KR records must be a list")
        self._validate_document(doc)
        return doc

    def _validate_document(self, doc: dict[str, Any]) -> None:
        ids: set[str] = set()
        for record in doc.get("records", []):
            self._validate_record(record)
            rid = record["instructionId"]
            if rid in ids:
                raise RuntimeError(f"Duplicate completion KR instructionId: {rid}")
            ids.add(rid)

    def _validate_record(self, record: dict[str, Any]) -> None:
        required = (
            "instructionId", "recordType", "componentKey", "componentLabel",
            "canonicalId", "category", "version", "description",
            "mustDo", "mustNotDo", "status", "productionEligible", "evidence",
        )
        for key in required:
            if key not in record:
                raise CompletionKnowledgeError(f"Missing completion KR field: {key}")
        if record["recordType"] not in _ALLOWED_RECORD_TYPES:
            raise CompletionKnowledgeError("recordType must be component or standard")
        if record["status"] not in _ALLOWED_STATUSES:
            raise CompletionKnowledgeError("invalid completion KR status")
        if not isinstance(record["evidence"], list):
            raise CompletionKnowledgeError("evidence must be a list")
        if record["status"] != "approved" and record["productionEligible"]:
            raise CompletionKnowledgeError("Only approved records may be production eligible")

    def _persist(
        self,
        document: dict[str, Any],
        *,
        action: str,
        record_id: str,
        actor: str,
        before: dict[str, Any] | None,
        after: dict[str, Any] | None,
    ) -> None:
        self._validate_document(document)
        _BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        if self._path.is_file():
            shutil.copy2(self._path, _BACKUP_DIR / f"completion-knowledge-{stamp}.json")

        document["catalogueVersion"] = int(document.get("catalogueVersion") or 0) + 1
        document["updatedAt"] = _utcnow()

        fd, temp_name = tempfile.mkstemp(
            prefix="completion-knowledge-",
            suffix=".json",
            dir=str(self._path.parent),
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(document, handle, indent=2, ensure_ascii=False)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, self._path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)

        audit = {
            "timestamp": _utcnow(),
            "action": action,
            "recordId": record_id,
            "actor": actor,
            "catalogueVersion": document["catalogueVersion"],
            "before": before,
            "after": after,
        }
        with _AUDIT_LOG.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(audit, sort_keys=True, ensure_ascii=False) + "\n")

    def catalogue(
        self,
        *,
        status: str | None = None,
        production_only: bool = False,
    ) -> dict[str, Any]:
        with _LOCK:
            doc = self._load()
            records = copy.deepcopy(doc["records"])
            for record in records:
                if record.get("recordType") == "component":
                    canonical_id = str(record.get("canonicalId") or "")
                    record["geometryClass"] = completion_geometry_class(canonical_id)
                    record["renderRecipe"] = completion_render_recipe(canonical_id)
            if status is not None:
                if status not in _ALLOWED_STATUSES:
                    raise CompletionKnowledgeError("invalid status filter")
                records = [r for r in records if r["status"] == status]
            if production_only:
                records = [r for r in records if r["productionEligible"]]
            return {
                "schemaVersion": doc["schemaVersion"],
                "catalogueVersion": doc["catalogueVersion"],
                "updatedAt": doc["updatedAt"],
                "records": records,
            }

    def summary(self) -> dict[str, Any]:
        doc = self.catalogue()
        records = doc["records"]
        return {
            "schemaVersion": doc["schemaVersion"],
            "catalogueVersion": doc["catalogueVersion"],
            "totalRecordCount": len(records),
            "approvedCount": sum(r["status"] == "approved" for r in records),
            "candidateCount": sum(r["status"] == "candidate" for r in records),
            "rejectedCount": sum(r["status"] == "rejected" for r in records),
            "deprecatedCount": sum(r["status"] == "deprecated" for r in records),
            "productionEligibleCount": sum(bool(r["productionEligible"]) for r in records),
            "evidenceRecordCount": sum(len(r.get("evidence", [])) for r in records),
        }

    def get(self, instruction_id: str) -> dict[str, Any]:
        doc = self._load()
        for record in doc["records"]:
            if record["instructionId"] == instruction_id:
                return copy.deepcopy(record)
        raise CompletionKnowledgeNotFound(instruction_id)

    def create_candidate(self, payload: dict[str, Any], *, actor: str) -> dict[str, Any]:
        with _LOCK:
            doc = self._load()
            canonical_id = str(payload.get("canonicalId") or "").strip()
            if not canonical_id:
                raise CompletionKnowledgeError("canonicalId is required")
            for record in doc["records"]:
                if record["canonicalId"] == canonical_id and record["status"] == "candidate":
                    raise CompletionKnowledgeConflict(
                        f"Candidate already exists for canonicalId {canonical_id}"
                    )

            now = _utcnow()
            instruction_id = str(payload.get("instructionId") or "").strip()
            if not instruction_id:
                instruction_id = f"cmpl_candidate_{uuid4().hex[:12]}"

            candidate = {
                "instructionId": instruction_id,
                "recordType": payload["recordType"],
                "componentKey": str(payload["componentKey"]).strip(),
                "componentLabel": str(payload["componentLabel"]).strip(),
                "canonicalId": canonical_id,
                "category": payload["category"],
                "version": str(payload.get("version") or "v1.0"),
                "description": str(payload["description"]).strip(),
                "mustDo": str(payload["mustDo"]).strip(),
                "mustNotDo": str(payload["mustNotDo"]).strip(),
                "status": "candidate",
                "standardStatus": "Candidate",
                "productionEligible": False,
                "createdAt": now,
                "updatedAt": now,
                "createdBy": actor,
                "parentInstructionId": payload.get("parentInstructionId"),
                "evidence": copy.deepcopy(payload.get("evidence") or []),
                "governanceHistory": [{
                    "action": "candidate_created",
                    "actor": actor,
                    "timestamp": now,
                    "previousStatus": None,
                    "newStatus": "candidate",
                    "reason": payload.get("changeReason") or "Candidate created",
                }],
            }
            candidate["evidenceCount"] = len(candidate["evidence"])
            self._validate_record(candidate)
            doc["records"].append(candidate)
            self._persist(
                doc,
                action="candidate_created",
                record_id=instruction_id,
                actor=actor,
                before=None,
                after=candidate,
            )
            return copy.deepcopy(candidate)

    def clone_as_candidate(
        self,
        instruction_id: str,
        *,
        actor: str,
        updates: dict[str, Any] | None = None,
        change_reason: str | None = None,
    ) -> dict[str, Any]:
        source = self.get(instruction_id)
        if source["status"] not in {"approved", "deprecated"}:
            raise CompletionKnowledgeConflict(
                "Only approved or deprecated completion knowledge can be edited as candidate"
            )
        payload = copy.deepcopy(source)
        payload.update(updates or {})
        payload["instructionId"] = f"{instruction_id}_candidate_{uuid4().hex[:8]}"
        payload["parentInstructionId"] = instruction_id
        payload["version"] = _next_version(source["version"])
        payload["changeReason"] = change_reason or "Edit as candidate"
        for key in (
            "status", "standardStatus", "productionEligible", "createdAt", "updatedAt",
            "createdBy", "approvedBy", "approvedAt", "deprecatedAt", "rejectedAt",
            "governanceHistory", "evidenceCount",
        ):
            payload.pop(key, None)
        return self.create_candidate(payload, actor=actor)

    def approve(self, instruction_id: str, *, actor: str, reason: str | None = None) -> dict[str, Any]:
        with _LOCK:
            doc = self._load()
            target = next((r for r in doc["records"] if r["instructionId"] == instruction_id), None)
            if target is None:
                raise CompletionKnowledgeNotFound(instruction_id)
            if target["status"] != "candidate":
                raise CompletionKnowledgeConflict("Only candidate records may be approved")

            before = copy.deepcopy(target)
            now = _utcnow()

            # One live production truth per canonical ID.
            for record in doc["records"]:
                if (
                    record["instructionId"] != instruction_id
                    and record["canonicalId"] == target["canonicalId"]
                    and record["status"] == "approved"
                ):
                    previous = record["status"]
                    record["status"] = "deprecated"
                    record["standardStatus"] = "Deprecated"
                    record["productionEligible"] = False
                    record["updatedAt"] = now
                    record["deprecatedAt"] = now
                    record.setdefault("governanceHistory", []).append({
                        "action": "superseded",
                        "actor": actor,
                        "timestamp": now,
                        "previousStatus": previous,
                        "newStatus": "deprecated",
                        "reason": f"Superseded by {instruction_id}",
                    })

            target["status"] = "approved"
            target["standardStatus"] = "Live"
            target["productionEligible"] = True
            target["updatedAt"] = now
            target["approvedAt"] = now
            target["approvedBy"] = actor
            target.setdefault("governanceHistory", []).append({
                "action": "approved",
                "actor": actor,
                "timestamp": now,
                "previousStatus": "candidate",
                "newStatus": "approved",
                "reason": reason or "Approved",
            })
            self._persist(
                doc,
                action="approved",
                record_id=instruction_id,
                actor=actor,
                before=before,
                after=target,
            )
            return copy.deepcopy(target)

    def reject(self, instruction_id: str, *, actor: str, reason: str | None = None) -> dict[str, Any]:
        return self._transition_candidate(
            instruction_id,
            actor=actor,
            target_status="rejected",
            reason=reason or "Rejected",
        )

    def _transition_candidate(
        self,
        instruction_id: str,
        *,
        actor: str,
        target_status: str,
        reason: str,
    ) -> dict[str, Any]:
        with _LOCK:
            doc = self._load()
            target = next((r for r in doc["records"] if r["instructionId"] == instruction_id), None)
            if target is None:
                raise CompletionKnowledgeNotFound(instruction_id)
            if target["status"] != "candidate":
                raise CompletionKnowledgeConflict("Only candidate records may be rejected")
            before = copy.deepcopy(target)
            now = _utcnow()
            target["status"] = target_status
            target["standardStatus"] = target_status.capitalize()
            target["productionEligible"] = False
            target["updatedAt"] = now
            target[f"{target_status}At"] = now
            target.setdefault("governanceHistory", []).append({
                "action": target_status,
                "actor": actor,
                "timestamp": now,
                "previousStatus": "candidate",
                "newStatus": target_status,
                "reason": reason,
            })
            self._persist(
                doc,
                action=target_status,
                record_id=instruction_id,
                actor=actor,
                before=before,
                after=target,
            )
            return copy.deepcopy(target)

    def deprecate(self, instruction_id: str, *, actor: str, reason: str | None = None) -> dict[str, Any]:
        with _LOCK:
            doc = self._load()
            target = next((r for r in doc["records"] if r["instructionId"] == instruction_id), None)
            if target is None:
                raise CompletionKnowledgeNotFound(instruction_id)
            if target["status"] != "approved":
                raise CompletionKnowledgeConflict("Only approved records may be deprecated")
            before = copy.deepcopy(target)
            now = _utcnow()
            target["status"] = "deprecated"
            target["standardStatus"] = "Deprecated"
            target["productionEligible"] = False
            target["updatedAt"] = now
            target["deprecatedAt"] = now
            target.setdefault("governanceHistory", []).append({
                "action": "deprecated",
                "actor": actor,
                "timestamp": now,
                "previousStatus": "approved",
                "newStatus": "deprecated",
                "reason": reason or "Deprecated",
            })
            self._persist(
                doc,
                action="deprecated",
                record_id=instruction_id,
                actor=actor,
                before=before,
                after=target,
            )
            return copy.deepcopy(target)
