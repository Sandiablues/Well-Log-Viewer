"""Seed-to-managed bridge for KR-2.

Converts current Python seed definitions (curve_knowledge.py constants) into
managed KR records with status=GovernanceStatus.SEED.

Architecture intent
-------------------
The seed layer is the bootstrap/default knowledge layer.  In a future KR block,
approved managed records will override or extend seed records through the
ManagedKRRepository abstraction.  Until then, seed records are the sole
production knowledge source.

  Seed record IDs are deterministic and stable:
    - CurveDefinitionRecord: "seed_curve_def_{canonical_curve_id}"
    - AliasRecord:           "seed_alias_{NORMALIZED}_{canonical_curve_id}"
    - DisplayRuleRecord:     "seed_display_{canonical_curve_id}"

No classification rule seeds or template rule seeds are created here;
those record types are structurally ready but seeded empty in KR-2.

This module does NOT import or depend on repository.py to avoid circular
imports — it builds directly from curve_knowledge.py constants.
"""

from __future__ import annotations

from .curve_knowledge import CURVE_DEFINITIONS
from .governance import GovernanceStatus
from .managed_models import (
    AliasRecord,
    CurveDefinitionRecord,
    DisplayRuleRecord,
)

# ---------------------------------------------------------------------------
# KR-owned family → subgroup mapping (mirrors repository.py; self-contained)
# ---------------------------------------------------------------------------

_FAMILY_TO_SUBGROUP: dict[str, str] = {
    "gamma_ray":              "gamma_ray",
    "spontaneous_potential":  "sp_electrochemical",
    "resistivity":            "resistivity",
    "density":                "density_neutron_porosity",
    "neutron_porosity":       "density_neutron_porosity",
    "photoelectric_factor":   "density_neutron_porosity",
    "sonic":                  "sonic_acoustic",
    "sonic_shear":            "sonic_acoustic",
    "caliper":                "borehole_geometry_imaging",
    "nmr":                    "nmr",
    "dip":                    "dip_directional",
    "formation_pressure":     "formation_pressure_sampling",
}


def _subgroup_for(family: str) -> str | None:
    return _FAMILY_TO_SUBGROUP.get(family.strip().lower())


# ---------------------------------------------------------------------------
# Individual builders
# ---------------------------------------------------------------------------

def build_seed_curve_definition_records() -> list[CurveDefinitionRecord]:
    """Convert CURVE_DEFINITIONS into seed-status CurveDefinitionRecords.

    One record per CurveDisplayDefinition entry.  The record_id is
    deterministic: "seed_curve_def_{canonical_curve_id}".
    """
    records: list[CurveDefinitionRecord] = []
    for defn in CURVE_DEFINITIONS:
        records.append(
            CurveDefinitionRecord(
                record_id=f"seed_curve_def_{defn.canonical_curve_id}",
                canonical_curve_id=defn.canonical_curve_id,
                display_name=defn.display_name,
                family=defn.curve_family,
                product_group="open_hole_logs",
                product_subgroup=_subgroup_for(defn.curve_family),
                default_unit=defn.default_unit,
                description=None,
                status=GovernanceStatus.SEED,
                version=1,
                source_type="seed",
                source_reference="backend.app.knowledge.curve_knowledge.CURVE_DEFINITIONS",
                created_by="system",
            )
        )
    return records


def build_seed_alias_records() -> list[AliasRecord]:
    """Convert alias tuples from CURVE_DEFINITIONS into seed-status AliasRecords.

    One record per (alias, canonical_curve_id) pair.  The record_id is
    deterministic: "seed_alias_{NORMALIZED_ALIAS}_{canonical_curve_id}".

    Aliases are currently treated as globally applicable (context_hint=None).
    Context-dependent alias resolution is a future KR concern.
    """
    records: list[AliasRecord] = []
    for defn in CURVE_DEFINITIONS:
        for alias in defn.aliases:
            normalized = alias.strip().upper()
            records.append(
                AliasRecord(
                    record_id=f"seed_alias_{normalized}_{defn.canonical_curve_id}",
                    alias=alias,
                    normalized_alias=normalized,
                    canonical_curve_id=defn.canonical_curve_id,
                    unit_hint=defn.default_unit,
                    description_hint=defn.display_name,
                    confidence=1.0,
                    status=GovernanceStatus.SEED,
                )
            )
    return records


def build_seed_display_rule_records() -> list[DisplayRuleRecord]:
    """Convert CURVE_DEFINITIONS display fields into seed-status DisplayRuleRecords.

    One record per CurveDisplayDefinition entry.  The record_id is
    deterministic: "seed_display_{canonical_curve_id}".

    reverse_scale is inferred from display_min > display_max (e.g. neutron
    porosity reads right-to-left).
    """
    records: list[DisplayRuleRecord] = []
    for defn in CURVE_DEFINITIONS:
        records.append(
            DisplayRuleRecord(
                record_id=f"seed_display_{defn.canonical_curve_id}",
                canonical_curve_id=defn.canonical_curve_id,
                preferred_track_family=defn.track_family,
                scale_type=defn.scale_type,
                display_min=defn.display_min,
                display_max=defn.display_max,
                default_unit=defn.default_unit,
                reverse_scale=defn.display_min > defn.display_max,
                overlay_group=defn.curve_family,
                status=GovernanceStatus.SEED,
                version=1,
            )
        )
    return records


# ---------------------------------------------------------------------------
# Combined entry point
# ---------------------------------------------------------------------------

def build_seed_managed_records() -> (
    list[CurveDefinitionRecord | AliasRecord | DisplayRuleRecord]
):
    """Return all seed-status managed records from the Python seed layer.

    Called once by ManagedKRRepository on initialisation.  Returns records
    in a stable order: curve definitions → aliases → display rules.

    Classification rule seeds and template rule seeds are intentionally
    empty in KR-2; those record types exist structurally but are not seeded
    from Python constants.
    """
    records: list[CurveDefinitionRecord | AliasRecord | DisplayRuleRecord] = []
    records.extend(build_seed_curve_definition_records())
    records.extend(build_seed_alias_records())
    records.extend(build_seed_display_rule_records())
    return records
