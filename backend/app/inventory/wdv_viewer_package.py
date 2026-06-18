"""Authoritative backend-owned WDV viewer-package construction.

This module is deliberately independent of API and repository orchestration.
It converts loaded managed-product rows into one deterministic per-well package
and is also the only source of package counts used by the WDV workspace.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Callable, Iterable

WDV_VIEWER_PACKAGE_CONTRACT_VERSION = "wdv_viewer_package_v2"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _canonical_curve_uid(curve: dict[str, Any]) -> str:
    return _text(curve.get("managed_curve_uid") or curve.get("curve_uid"))


def _display_curve_id(curve: dict[str, Any]) -> str:
    return _text(curve.get("display_curve_id") or curve.get("curve_id"))


def _product_id(curve: dict[str, Any]) -> str:
    return _text(curve.get("product_id"))


def validate_viewer_curve(curve: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    if not _product_id(curve):
        reasons.append("missing_product_id")
    if not _canonical_curve_uid(curve):
        reasons.append("missing_curve_uid")
    if not _display_curve_id(curve):
        reasons.append("missing_display_curve_id")
    if curve.get("is_renderable") is not True:
        reasons.append("not_renderable")
    if _text(curve.get("support_status")) not in {"renderable", "supported"}:
        reasons.append("unsupported_status")
    return reasons


def _unsupported_product(
    item: Any,
    curve: dict[str, Any] | None,
    reasons: list[str],
) -> dict[str, Any]:
    return {
        "product_id": _text(getattr(item, "product_id", None) or (curve or {}).get("product_id")),
        "managed_product_uid": _text(
            getattr(item, "managed_product_uid", None)
            or (curve or {}).get("managed_product_uid")
        ) or None,
        "managed_curve_uid": _text(
            getattr(item, "managed_curve_uid", None)
            or (curve or {}).get("managed_curve_uid")
        ) or None,
        "display_name": _text(
            getattr(item, "display_name", None)
            or getattr(item, "curve_name", None)
            or (curve or {}).get("display_name")
        ) or None,
        "reasons": sorted(set(reasons)),
    }


def _package_fingerprint(payload: dict[str, Any]) -> str:
    stable = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(stable.encode("utf-8")).hexdigest()


def build_wdv_viewer_package(
    *,
    record: Any,
    loaded_items: Iterable[Any],
    curve_builder: Callable[[Any, Any], dict[str, Any]],
    updated_at: str,
    depth_domain: dict[str, Any],
) -> dict[str, Any]:
    """Build one deterministic, self-consistent package for a managed well.

    Loaded products are evaluated independently. Invalid or duplicate curves are
    retained under ``unsupported_products`` and never counted as displayable.
    The frontend receives exactly ``curves`` as the canonical package inventory.
    """

    items = list(loaded_items)
    curves: list[dict[str, Any]] = []
    unsupported: list[dict[str, Any]] = []
    seen_curve_uids: set[str] = set()
    source_product_ids: list[str] = []

    for item in items:
        product_id = _text(getattr(item, "product_id", None))
        if product_id:
            source_product_ids.append(product_id)
        try:
            raw_curve = curve_builder(record, item)
        except Exception as exc:  # package construction must disposition, not hide
            unsupported.append(
                _unsupported_product(item, None, [f"curve_build_failed:{type(exc).__name__}"])
            )
            continue

        if not isinstance(raw_curve, dict):
            unsupported.append(_unsupported_product(item, None, ["curve_contract_not_object"]))
            continue

        curve = dict(raw_curve)
        reasons = validate_viewer_curve(curve)
        curve_uid = _canonical_curve_uid(curve)
        if curve_uid and curve_uid in seen_curve_uids:
            reasons.append("duplicate_curve_uid")

        if reasons:
            unsupported.append(_unsupported_product(item, curve, reasons))
            continue

        seen_curve_uids.add(curve_uid)
        curves.append(curve)

    identity_payload = {
        "managed_well_id": _text(getattr(record, "managed_well_id", None)),
        "managed_well_uid": _text(getattr(record, "managed_well_uid", None)) or None,
        "source_product_ids": source_product_ids,
        "curve_uids": [_canonical_curve_uid(curve) for curve in curves],
        "unsupported_product_ids": [item.get("product_id") for item in unsupported],
    }
    fingerprint = _package_fingerprint(identity_payload)

    package = {
        "viewer_package_version": "well_multitrack_v2",
        "contract_kind": "wdv_viewer_package",
        "contract_version": WDV_VIEWER_PACKAGE_CONTRACT_VERSION,
        "package_revision": fingerprint[:16],
        "package_fingerprint": fingerprint,
        "dataset_id": identity_payload["managed_well_id"],
        "representation_id": f"wdv-viewer-package:{identity_payload['managed_well_id']}:{fingerprint[:16]}",
        "managed_well_id": identity_payload["managed_well_id"],
        "managed_well_uid": identity_payload["managed_well_uid"],
        "managed_wellbore_uid": _text(getattr(record, "managed_wellbore_uid", None)) or None,
        "well_id": _text(getattr(record, "well_id", None)),
        "well_name": _text(getattr(record, "well_name", None)),
        "wellbore_id": _text(getattr(record, "wellbore_id", None) or getattr(record, "well_id", None)),
        "wellbore_name": _text(getattr(record, "wellbore_name", None) or getattr(record, "well_name", None)),
        "operator": getattr(record, "operator", None),
        "field": getattr(record, "field", None),
        "country": getattr(record, "country", None),
        "display_domain": "MD",
        "depth_unit": depth_domain.get("unit") or getattr(record, "depth_unit", None) or "ft",
        "depth_range": {"min": depth_domain["min"], "max": depth_domain["max"]},
        "depth_domain": depth_domain,
        "tracks": [{"track_id": "depth", "track_type": "depth", "title": "Depth", "curves": []}],
        "visible_tracks": [],
        "display_tracks": [],
        "track_layout_state": "manual_empty",
        "source_product_ids": source_product_ids,
        "loaded_product_count": len(items),
        "viewer_curve_count": len(curves),
        "displayable_curve_count": len(curves),
        "curves": curves,
        "unsupported_products": unsupported,
        "messages": [],
        "updated_at": updated_at,
        "created_by": "wdv_viewer_package.build_wdv_viewer_package",
    }
    return package


def summarize_wdv_viewer_package(
    package: dict[str, Any] | None,
    loaded_product_ids: Iterable[str],
) -> tuple[int, int, int]:
    """Return authoritative counts from a validated package.

    No product-count fallback is permitted. Missing or malformed packages report
    zero curves so lifecycle defects are visible rather than disguised.
    """

    product_ids = [value for value in (_text(item) for item in loaded_product_ids) if value]
    loaded_product_count = len(product_ids)
    if not isinstance(package, dict):
        return loaded_product_count, 0, 0

    curves = package.get("curves")
    if not isinstance(curves, list):
        return loaded_product_count, 0, 0

    valid_curves: list[dict[str, Any]] = []
    seen: set[str] = set()
    loaded_set = set(product_ids)
    for raw in curves:
        if not isinstance(raw, dict):
            continue
        if _product_id(raw) not in loaded_set:
            continue
        if validate_viewer_curve(raw):
            continue
        uid = _canonical_curve_uid(raw)
        if uid in seen:
            continue
        seen.add(uid)
        valid_curves.append(raw)

    count = len(valid_curves)
    return loaded_product_count, count, count
