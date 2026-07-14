from app.classification_orchestration.general_family_projection import project_general_curve_family
from app.inventory.models import ManagedProductGroupItem
from app.inventory.service import ManagedWellInventoryService


def _managed(mnemonic, detailed_label, detailed_key):
    general = project_general_curve_family(detailed_key, detailed_label)
    return ManagedProductGroupItem(
        product_id=f"p:{mnemonic}", display_name=mnemonic, curve_name=mnemonic,
        curve_type=detailed_label, curve_description=detailed_label,
        product_category="open_hole_logs",
        product_subgroup_key=general.family_key,
        product_subgroup_label=general.family_label,
        curve_family=detailed_label,
        curve_family_key=detailed_key,
        general_curve_family=general.family_label,
        general_curve_family_key=general.family_key,
        general_curve_family_projection_version=general.projection_version,
    )


def test_density_and_density_correction_share_mwd_and_wdv_family_category():
    density = _managed("RHOZ", "Density", "density")
    correction = _managed("HDRA", "Density Correction", "density_correction")

    # MWD category authority.
    assert {density.product_subgroup_key, correction.product_subgroup_key} == {"density"}
    assert {density.product_subgroup_label, correction.product_subgroup_label} == {"Density"}

    curves = [
        {
            "classification_curve_family": item.curve_family,
            "classification_curve_family_key": item.curve_family_key,
            "general_curve_family": item.general_curve_family,
            "general_curve_family_key": item.general_curve_family_key,
        }
        for item in (density, correction)
    ]
    result = ManagedWellInventoryService._coalesce_wdv_curve_family_contracts(curves)

    # WDV category authority is exactly the same persisted general family.
    assert {row["curve_family_key"] for row in result} == {"density"}
    assert {row["curve_family"] for row in result} == {"Density"}

    # Detailed classification remains available and distinct.
    assert {row["classification_curve_family_key"] for row in result} == {"density", "density_correction"}


def test_mwd_and_wdv_general_family_parity_for_sonic_subclasses():
    items = [
        _managed("DTCO", "Sonic Compressional", "sonic_compressional"),
        _managed("DTSM", "Sonic Shear", "sonic_shear"),
        _managed("SPHI", "Sonic", "sonic"),
    ]
    assert {item.product_subgroup_key for item in items} == {"sonic"}
    assert {item.product_subgroup_label for item in items} == {"Sonic"}
