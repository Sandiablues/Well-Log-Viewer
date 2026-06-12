"""Knowledge Repository seed implementation (KR-1).

This module owns the canonical product-group/subgroup/curve/display-rule
truth for WLV.  In KR-1 all data is seeded from Python constants that sit
behind this repository boundary.  A future KR management system can replace
or extend these seeds without requiring any frontend classification changes.

Alignment note:
  Open-hole subgroup keys are kept consistent with the vocabulary used by
  well_log_classifier.py (e.g. ``borehole_geometry_imaging``) so that
  products already classified and stored in the managed inventory continue
  to render under the correct subgroup.  The work-order's recommended
  expansion to ``caliper_borehole_geometry``, ``borehole_imaging``, and
  ``spectral_gamma_ray`` is deferred to KR-2 vocabulary alignment once a
  classifier migration can be done safely.
"""

from __future__ import annotations

from .models import (
    KR_VERSION,
    KrCurveDefinition,
    KrCurveDefinitionsResponse,
    KrDisplayRule,
    KrDisplayRulesResponse,
    KrHealthResponse,
    KrProductGroup,
    KrProductGroupsResponse,
    KrProductSubgroup,
    KrTemplatesResponse,
)
from .curve_knowledge import CURVE_DEFINITIONS


# ---------------------------------------------------------------------------
# Product-group / subgroup seed data
# ---------------------------------------------------------------------------

_PRODUCT_GROUPS_SEED: list[KrProductGroup] = [
    KrProductGroup(
        key="open_hole_logs",
        label="Open-hole Logs",
        order=10,
        subgroups=[
            KrProductSubgroup(key="gamma_ray",                    label="Gamma Ray",                         order=10),
            KrProductSubgroup(key="sp_electrochemical",           label="SP / Electrochemical",              order=20),
            KrProductSubgroup(key="resistivity",                  label="Resistivity",                       order=30),
            KrProductSubgroup(key="density_neutron_porosity",     label="Density / Neutron / Porosity",      order=40),
            KrProductSubgroup(key="sonic_acoustic",               label="Sonic / Acoustic",                  order=50),
            KrProductSubgroup(key="borehole_geometry_imaging",    label="Caliper / Borehole Geometry",       order=60),
            KrProductSubgroup(key="nmr",                          label="NMR",                               order=70),
            KrProductSubgroup(key="dip_directional",              label="Dip / Directional",                 order=80),
            KrProductSubgroup(key="formation_pressure_sampling",  label="Formation Pressure / Sampling",     order=90),
            KrProductSubgroup(key="petrophysical_interpretation", label="Petrophysical Interpretation",      order=100),
            KrProductSubgroup(key="other_open_hole_review",       label="Other Open-hole / Review",          order=999),
        ],
    ),
    KrProductGroup(
        key="cased_hole_logs",
        label="Cased-hole Logs",
        order=20,
        subgroups=[
            KrProductSubgroup(key="cement_evaluation",              label="Cement Evaluation",                  order=10),
            KrProductSubgroup(key="production_logging",             label="Production Logging",                 order=20),
            KrProductSubgroup(key="pulsed_neutron_saturation",      label="Pulsed Neutron / Saturation",        order=30),
            KrProductSubgroup(key="casing_inspection",              label="Casing Inspection",                  order=40),
            KrProductSubgroup(key="depth_correlation",              label="Depth Correlation",                  order=50),
            KrProductSubgroup(key="completion_correlation",         label="Completion Correlation",             order=60),
            KrProductSubgroup(key="other_cased_hole_review",        label="Other Cased-hole / Review",          order=999),
        ],
    ),
    KrProductGroup(
        key="rasters_images",
        label="Rasters / Images",
        order=30,
        subgroups=[
            KrProductSubgroup(key="cgm",                  label="CGM",                     order=10),
            KrProductSubgroup(key="tiff",                 label="TIFF",                    order=20),
            KrProductSubgroup(key="scanned_log_image",    label="Scanned Log Image",       order=30),
            KrProductSubgroup(key="borehole_image",       label="Borehole Image",          order=40),
            KrProductSubgroup(key="other_raster_review",  label="Other Raster / Review",   order=999),
        ],
    ),
    KrProductGroup(
        key="lithology_core_markers",
        label="Lithology / Core / Markers",
        order=40,
        subgroups=[
            KrProductSubgroup(key="formation_tops",          label="Formation Tops",             order=10),
            KrProductSubgroup(key="lithology_intervals",     label="Lithology Intervals",        order=20),
            KrProductSubgroup(key="facies",                  label="Facies",                     order=30),
            KrProductSubgroup(key="core_data",               label="Core Data",                  order=40),
            KrProductSubgroup(key="other_geology_review",    label="Other Geology / Review",     order=999),
        ],
    ),
    KrProductGroup(
        key="pressure_production_fluid_data",
        label="Pressure / Production / Fluid Data",
        order=50,
        subgroups=[
            KrProductSubgroup(key="formation_pressure",              label="Formation Pressure",                 order=10),
            KrProductSubgroup(key="mobility_permeability_indicator", label="Mobility / Permeability Indicator",  order=20),
            KrProductSubgroup(key="fluid_sample",                    label="Fluid Sample",                       order=30),
            KrProductSubgroup(key="production_test",                 label="Production Test",                    order=40),
            KrProductSubgroup(key="other_pressure_fluid_review",     label="Other Pressure / Fluid / Review",    order=999),
        ],
    ),
    KrProductGroup(
        key="completion_integrity_data",
        label="Completion / Integrity Data",
        order=60,
        subgroups=[
            KrProductSubgroup(key="perforations",                label="Perforations",                order=10),
            KrProductSubgroup(key="casing",                      label="Casing",                      order=20),
            KrProductSubgroup(key="tubing",                      label="Tubing",                      order=30),
            KrProductSubgroup(key="packers",                     label="Packers",                     order=40),
            KrProductSubgroup(key="plugs",                       label="Plugs",                       order=50),
            KrProductSubgroup(key="well_integrity_inspection",   label="Well Integrity Inspection",   order=60),
            KrProductSubgroup(key="other_completion_review",     label="Other Completion / Review",   order=999),
        ],
    ),
    KrProductGroup(
        key="supporting_documents",
        label="Supporting Documents",
        order=70,
        subgroups=[
            KrProductSubgroup(key="well_report",           label="Well Report",            order=10),
            KrProductSubgroup(key="las_header_metadata",   label="LAS Header / Metadata",  order=20),
            KrProductSubgroup(key="completion_report",     label="Completion Report",      order=30),
            KrProductSubgroup(key="core_report",           label="Core Report",            order=40),
            KrProductSubgroup(key="image_log_report",      label="Image Log Report",       order=50),
            KrProductSubgroup(key="other_document_review", label="Other Document / Review",order=999),
        ],
    ),
    KrProductGroup(
        key="other_review_required",
        label="Other / Review Required",
        order=80,
        subgroups=[
            KrProductSubgroup(key="unknown_mnemonic",         label="Unknown Mnemonic",         order=10),
            KrProductSubgroup(key="ambiguous_context",        label="Ambiguous Context",        order=20),
            KrProductSubgroup(key="missing_units",            label="Missing Units",            order=30),
            KrProductSubgroup(key="conflicting_evidence",     label="Conflicting Evidence",     order=40),
            KrProductSubgroup(key="unsupported_format",       label="Unsupported Format",       order=50),
            KrProductSubgroup(key="other_review_required",    label="Other Review Required",    order=999),
        ],
    ),
]


# ---------------------------------------------------------------------------
# Curve definition seed data — derived from curve_knowledge.py
# ---------------------------------------------------------------------------

# KR-owned deterministic mapping from curve_knowledge.py curve_family values
# to KR open-hole subgroup keys.  Maintained here so the KR is self-contained
# and does not depend on vocabulary key formats from the classifier layer.
_CURVE_FAMILY_TO_KR_SUBGROUP: dict[str, str] = {
    "gamma_ray":           "gamma_ray",
    "spontaneous_potential": "sp_electrochemical",
    "resistivity":         "resistivity",
    "density":             "density_neutron_porosity",
    "neutron_porosity":    "density_neutron_porosity",
    "photoelectric_factor": "density_neutron_porosity",
    "sonic":               "sonic_acoustic",
    "sonic_shear":         "sonic_acoustic",
    "caliper":             "borehole_geometry_imaging",
    "nmr":                 "nmr",
    "dip":                 "dip_directional",
    "formation_pressure":  "formation_pressure_sampling",
}


def _curve_subgroup_from_family(family: str) -> str | None:
    """Map a curve_knowledge curve_family to a KR open-hole subgroup key."""
    return _CURVE_FAMILY_TO_KR_SUBGROUP.get(family.strip().lower())


_CURVE_DEFINITIONS_SEED: list[KrCurveDefinition] = [
    KrCurveDefinition(
        canonical_curve_id=defn.canonical_curve_id,
        display_name=defn.display_name,
        family=defn.curve_family,
        product_group="open_hole_logs",
        product_subgroup=_curve_subgroup_from_family(defn.curve_family),
        default_unit=defn.default_unit,
        aliases=list(defn.aliases),
    )
    for defn in CURVE_DEFINITIONS
]


# ---------------------------------------------------------------------------
# Display rule seed data — derived from curve_knowledge.py
# ---------------------------------------------------------------------------

_DISPLAY_RULES_SEED: list[KrDisplayRule] = [
    KrDisplayRule(
        canonical_curve_id=defn.canonical_curve_id,
        preferred_track_family=defn.track_family,
        scale_type=defn.scale_type,
        display_min=defn.display_min,
        display_max=defn.display_max,
        default_unit=defn.default_unit,
        reverse_scale=defn.display_min > defn.display_max,
        overlay_group=defn.curve_family,
    )
    for defn in CURVE_DEFINITIONS
]


# ---------------------------------------------------------------------------
# Public repository
# ---------------------------------------------------------------------------

class KnowledgeRepository:
    """Read-only Knowledge Repository for KR-1.

    All data is seeded from Python constants.  The repository boundary ensures
    a future KR management system can replace the seed without requiring
    frontend classification changes.
    """

    def __init__(self) -> None:
        self._product_groups = _PRODUCT_GROUPS_SEED
        self._curve_definitions = _CURVE_DEFINITIONS_SEED
        self._display_rules = _DISPLAY_RULES_SEED

    # -- product groups -------------------------------------------------------

    def get_product_groups(self) -> KrProductGroupsResponse:
        return KrProductGroupsResponse(
            version=KR_VERSION,
            groups=sorted(self._product_groups, key=lambda g: g.order),
        )

    # -- curve definitions ----------------------------------------------------

    def get_curve_definitions(self) -> KrCurveDefinitionsResponse:
        return KrCurveDefinitionsResponse(
            version=KR_VERSION,
            curve_definitions=self._curve_definitions,
        )

    # -- display rules --------------------------------------------------------

    def get_display_rules(self) -> KrDisplayRulesResponse:
        return KrDisplayRulesResponse(
            version=KR_VERSION,
            display_rules=self._display_rules,
        )

    # -- templates ------------------------------------------------------------

    def get_templates(self) -> KrTemplatesResponse:
        return KrTemplatesResponse(version=KR_VERSION, templates=[])

    # -- health ---------------------------------------------------------------

    def get_health(self) -> KrHealthResponse:
        return KrHealthResponse(
            service="wlv_knowledge_repository",
            status="ok",
            mode="read_only",
            version=KR_VERSION,
            product_group_count=len(self._product_groups),
            curve_definition_count=len(self._curve_definitions),
            display_rule_count=len(self._display_rules),
            template_count=0,
        )
