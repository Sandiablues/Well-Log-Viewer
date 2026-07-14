"""Backend-owned projection from detailed curve classification to general family.

The detailed classification remains available for engineering semantics, scale policy,
provenance, and review. MWD and WDV categorization must use only the projected
general family identity from this module.
"""
from __future__ import annotations

from dataclasses import dataclass

from .family_registry import canonical_family_key

GENERAL_FAMILY_PROJECTION_VERSION = "general-curve-family-projection-v1"


@dataclass(frozen=True)
class GeneralCurveFamily:
    family_key: str
    family_label: str
    projection_version: str = GENERAL_FAMILY_PROJECTION_VERSION


# Explicit governed projection. Keys not listed remain their own general family.
# This is intentionally not heuristic or mnemonic-driven.
_GENERAL_FAMILY_ALIASES: dict[str, tuple[str, str]] = {
    "density": ("density", "Density"),
    "density_correction": ("density", "Density"),
    "sonic": ("sonic", "Sonic"),
    "sonic_compressional": ("sonic", "Sonic"),
    "sonic_shear": ("sonic", "Sonic"),
    "acoustic": ("sonic", "Sonic"),
    "array_acoustic": ("sonic", "Sonic"),
    "gamma_ray": ("gamma_ray", "Gamma Ray"),
    "computed_gamma_ray": ("gamma_ray", "Gamma Ray"),
    "spectral_gamma_ray": ("gamma_ray", "Gamma Ray"),
    "neutron_porosity": ("neutron_porosity", "Neutron Porosity"),
    "photoelectric_factor": ("photoelectric_factor", "Photoelectric Factor"),
    "spontaneous_potential": ("spontaneous_potential", "Spontaneous Potential"),
    "caliper": ("caliper", "Caliper"),
    "hole_diameter": ("caliper", "Caliper"),
    "resistivity": ("resistivity", "Resistivity"),
    "deep_resistivity": ("resistivity", "Resistivity"),
    "medium_resistivity": ("resistivity", "Resistivity"),
    "shallow_resistivity": ("resistivity", "Resistivity"),
    "micro_resistivity": ("resistivity", "Resistivity"),
    "flushed_zone_resistivity": ("resistivity", "Resistivity"),
    "induction_resistivity": ("resistivity", "Resistivity"),
    "laterolog_resistivity": ("resistivity", "Resistivity"),
    "array_resistivity": ("resistivity", "Resistivity"),
}


def project_general_curve_family(
    detailed_family_key: str | None,
    detailed_family_label: str | None,
) -> GeneralCurveFamily:
    key = canonical_family_key(detailed_family_key or detailed_family_label) or "unclassified"
    projected = _GENERAL_FAMILY_ALIASES.get(key)
    if projected is not None:
        return GeneralCurveFamily(*projected)

    raw_label = str(detailed_family_label or "").strip()
    label = raw_label or key.replace("_", " ").title()
    return GeneralCurveFamily(key, label)


# Explicit backend-owned mapping from accepted measurement domains to MWD
# product groups. This is presentation/routing projection only; it does not
# reclassify the curve or invent a family.
_MWD_PRODUCT_GROUP_BY_MEASUREMENT_DOMAIN: dict[str, str] = {
    "open_hole_log": "open_hole_logs",
    "petrophysical_log": "open_hole_logs",
    "cased_hole_log": "cased_hole_logs",
}


def project_mwd_product_group(
    *,
    current_product_category: str | None,
    measurement_domain_key: str | None,
    general_family_key: str | None,
    display_in_wdv: bool,
) -> str:
    """Project the MWD top-level product group from accepted backend contracts.

    MWD family presentation must match WDV for WDV-eligible curves. A curve
    already resolved to a general family and an explicit governed log domain
    must not remain in the legacy ``other_review_required`` bucket merely
    because the legacy product-category classifier failed earlier.

    This function is deliberately conservative:
      * it only changes a legacy review bucket;
      * it requires WDV eligibility;
      * it requires a resolved general family; and
      * it requires an explicit known measurement-domain mapping.
    """
    current = str(current_product_category or "").strip() or "other_review_required"
    if current != "other_review_required":
        return current
    if not display_in_wdv:
        return current
    family_key = canonical_family_key(general_family_key)
    if not family_key or family_key == "unclassified":
        return current
    domain_key = canonical_family_key(measurement_domain_key)
    return _MWD_PRODUCT_GROUP_BY_MEASUREMENT_DOMAIN.get(domain_key, current)
