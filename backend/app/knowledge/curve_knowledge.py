"""Backend-owned curve knowledge and WDV viewer-package normalization.

This module is intentionally backend-owned and frontend-agnostic.  The WDV
renders packages produced by the backend; it must not own curve ontology,
mnemonic aliases, product eligibility, or display defaults.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

CURVE_KNOWLEDGE_VERSION = "wlv_curve_knowledge_v1"


@dataclass(frozen=True)
class CurveDisplayDefinition:
    canonical_curve_id: str
    curve_family: str
    display_name: str
    track_family: str
    render_curve_id: str
    render_kind: str = "curve"
    scale_type: str = "linear"
    display_min: float = 0.0
    display_max: float = 150.0
    default_unit: str | None = None
    aliases: tuple[str, ...] = field(default_factory=tuple)


CURVE_DEFINITIONS: tuple[CurveDisplayDefinition, ...] = (
    CurveDisplayDefinition(
        canonical_curve_id="gamma_ray",
        curve_family="gamma_ray",
        display_name="Gamma Ray",
        track_family="gamma_ray_sp",
        render_curve_id="GR",
        display_min=0.0,
        display_max=200.0,
        default_unit="API",
        aliases=("GR", "GAM", "GRC", "ECGR", "HGR", "GR_EDTC"),
    ),
    CurveDisplayDefinition(
        canonical_curve_id="spontaneous_potential",
        curve_family="spontaneous_potential",
        display_name="Spontaneous Potential",
        track_family="gamma_ray_sp",
        render_curve_id="SP",
        display_min=-700.0,
        display_max=-480.0,
        default_unit="MV",
        aliases=("SP", "SPAR"),
    ),
    CurveDisplayDefinition(
        canonical_curve_id="deep_resistivity",
        curve_family="resistivity",
        display_name="Deep Resistivity",
        track_family="resistivity",
        render_curve_id="AT90",
        scale_type="log",
        display_min=0.2,
        display_max=200.0,
        default_unit="OHMM",
        aliases=("AT90", "AF90", "RT", "ILD", "LLD", "AORX", "AORT"),
    ),
    CurveDisplayDefinition(
        canonical_curve_id="shallow_resistivity",
        curve_family="resistivity",
        display_name="Shallow Resistivity",
        track_family="resistivity",
        render_curve_id="AT10",
        scale_type="log",
        display_min=0.2,
        display_max=200.0,
        default_unit="OHMM",
        aliases=("AT10", "AF10", "LLS", "ILM", "RXO", "RXOZ", "RXO8"),
    ),
    CurveDisplayDefinition(
        canonical_curve_id="bulk_density",
        curve_family="density",
        display_name="Bulk Density",
        track_family="density_neutron",
        render_curve_id="RHOZ",
        display_min=1.95,
        display_max=2.95,
        default_unit="G/C3",
        aliases=("RHOB", "RHOZ", "DEN", "DENS", "ZDEN", "DPHZ"),
    ),
    CurveDisplayDefinition(
        canonical_curve_id="neutron_porosity",
        curve_family="neutron_porosity",
        display_name="Neutron Porosity",
        track_family="density_neutron",
        render_curve_id="TNPH",
        display_min=0.45,
        display_max=-0.15,
        default_unit="V/V",
        aliases=("NPHI", "NPOR", "TNPH", "DNPH", "HNPO", "HTNP"),
    ),
    CurveDisplayDefinition(
        canonical_curve_id="sonic_compressional",
        curve_family="sonic",
        display_name="Compressional Sonic",
        track_family="sonic",
        render_curve_id="DTCO",
        display_min=140.0,
        display_max=40.0,
        default_unit="US/F",
        aliases=("DT", "DTC", "DTCO"),
    ),
    CurveDisplayDefinition(
        canonical_curve_id="sonic_shear",
        curve_family="sonic_shear",
        display_name="Shear Sonic",
        track_family="sonic",
        render_curve_id="DTSM",
        display_min=300.0,
        display_max=80.0,
        default_unit="US/F",
        aliases=("DTS", "DTSM"),
    ),
    CurveDisplayDefinition(
        canonical_curve_id="caliper",
        curve_family="caliper",
        display_name="Caliper",
        track_family="borehole",
        render_curve_id="HCAL",
        display_min=6.0,
        display_max=16.0,
        default_unit="IN",
        aliases=("CALI", "CAL", "HCAL", "DCAL", "CALIPER"),
    ),
    CurveDisplayDefinition(
        canonical_curve_id="photoelectric_factor",
        curve_family="photoelectric_factor",
        display_name="Photoelectric Factor",
        track_family="lithology_density",
        render_curve_id="PEFZ",
        display_min=0.0,
        display_max=10.0,
        default_unit="B/E",
        aliases=("PEF", "PE", "PEFZ"),
    ),
)

_ALIAS_TO_DEFINITION = {
    alias.upper(): definition
    for definition in CURVE_DEFINITIONS
    for alias in definition.aliases
}


def mnemonic_key(value: Any) -> str:
    return str(value or "").strip().upper()


def resolve_curve_definition(mnemonic: str | None) -> CurveDisplayDefinition | None:
    return _ALIAS_TO_DEFINITION.get(mnemonic_key(mnemonic))


def _raw_curve_mnemonic(curve: dict[str, Any]) -> str:
    return mnemonic_key(curve.get("mnemonic") or curve.get("curve_id") or curve.get("original_mnemonic"))


def normalize_viewer_curve(curve: dict[str, Any]) -> dict[str, Any]:
    """Normalize one backend curve into a WDV-ready curve contract.

    The returned contract preserves source evidence while adding canonical
    backend knowledge fields.  Unknown curves are returned as non-renderable so
    the frontend can report/skip them safely instead of crashing.
    """

    original_mnemonic = _raw_curve_mnemonic(curve)
    definition = resolve_curve_definition(original_mnemonic)

    if definition is None:
        return {
            **curve,
            "original_curve_id": curve.get("curve_id") or original_mnemonic,
            "original_mnemonic": original_mnemonic,
            "canonical_curve_id": "unknown",
            "curve_family": "unknown",
            "display_name": str(curve.get("normalized_name") or curve.get("description") or original_mnemonic or "Unknown curve"),
            "track_family": "unknown",
            "render_kind": "unsupported_curve",
            "is_renderable": False,
            "support_status": "unsupported_curve",
            "messages": [f"Curve mnemonic {original_mnemonic or 'UNKNOWN'} is not mapped in backend curve knowledge."],
        }

    scale = curve.get("scale") if isinstance(curve.get("scale"), dict) else {}
    scale_type = str(scale.get("type") or definition.scale_type)
    if scale_type not in {"linear", "log"}:
        scale_type = definition.scale_type

    unit = str(curve.get("unit") or definition.default_unit or "")
    render_curve_id = definition.render_curve_id

    return {
        **curve,
        "original_curve_id": curve.get("curve_id") or original_mnemonic,
        "original_mnemonic": original_mnemonic,
        "curve_id": render_curve_id,
        "display_curve_id": render_curve_id,
        "canonical_curve_id": definition.canonical_curve_id,
        "curve_family": definition.curve_family,
        "display_name": definition.display_name,
        "normalized_name": definition.display_name,
        "track_family": definition.track_family,
        "render_kind": definition.render_kind,
        "unit": unit,
        "scale": {
            "type": scale_type,
            "min": float(scale.get("min", definition.display_min)),
            "max": float(scale.get("max", definition.display_max)),
        },
        "scale_type": scale_type,
        "display_min": float(scale.get("min", definition.display_min)),
        "display_max": float(scale.get("max", definition.display_max)),
        "is_renderable": True,
        "support_status": "renderable",
        "curve_knowledge_version": CURVE_KNOWLEDGE_VERSION,
    }


def normalize_viewer_package_for_wdv(contract: dict[str, Any]) -> dict[str, Any]:
    """Return a backend-normalized viewer package for WDV rendering."""

    normalized = dict(contract)
    normalized_tracks: list[dict[str, Any]] = []
    unsupported_products: list[dict[str, Any]] = []
    messages: list[str] = [str(message) for message in contract.get("messages", []) if str(message)]

    for raw_track in contract.get("tracks", []):
        if not isinstance(raw_track, dict):
            continue

        track_type = str(raw_track.get("track_type") or "curve")
        raw_curves = raw_track.get("curves")

        if track_type == "depth" or not isinstance(raw_curves, list):
            normalized_tracks.append(dict(raw_track))
            continue

        renderable_curves: list[dict[str, Any]] = []
        for raw_curve in raw_curves:
            if not isinstance(raw_curve, dict):
                continue
            normalized_curve = normalize_viewer_curve(raw_curve)
            if normalized_curve.get("is_renderable") is True:
                renderable_curves.append(normalized_curve)
            else:
                unsupported_products.append(normalized_curve)

        if renderable_curves:
            next_track = dict(raw_track)
            next_track["curves"] = renderable_curves
            families = {str(curve.get("track_family") or "") for curve in renderable_curves}
            if len(families) == 1:
                next_track["track_family"] = next(iter(families))
            next_track["curve_knowledge_version"] = CURVE_KNOWLEDGE_VERSION
            normalized_tracks.append(next_track)

    if unsupported_products:
        messages.append(f"{len(unsupported_products)} curve(s) were not renderable by backend curve knowledge.")

    normalized["tracks"] = normalized_tracks
    normalized["unsupported_products"] = unsupported_products
    normalized["messages"] = messages
    normalized["curve_knowledge_version"] = CURVE_KNOWLEDGE_VERSION
    return normalized
