from app.inventory.models import ManagedProductGroupItem
from app.inventory.service import ManagedWellInventoryService


def test_mwd_general_family_identity_is_separate_from_curve_subclass():
    items = [
        ManagedProductGroupItem(product_id="p1", display_name="DTCO", curve_name="DTCO", curve_type="Sonic Compressional", curve_family="Sonic", curve_family_key="sonic"),
        ManagedProductGroupItem(product_id="p2", display_name="DTSM", curve_name="DTSM", curve_type="Sonic Shear", curve_family="Sonic", curve_family_key="sonic"),
        ManagedProductGroupItem(product_id="p3", display_name="SPHI", curve_name="SPHI", curve_type="Sonic Porosity", curve_family="Sonic", curve_family_key="sonic"),
    ]
    assert {item.curve_family_key for item in items} == {"sonic"}
    assert len({item.curve_type for item in items}) == 3


def test_wdv_coalescing_groups_by_general_family_key_not_subclass():
    curves = [
        {"mnemonic": "DTCO", "curve_family": "Sonic", "curve_family_key": "sonic", "curve_type": "Sonic Compressional"},
        {"mnemonic": "DTSM", "curve_family": "Sonic", "curve_family_key": "sonic", "curve_type": "Sonic Shear"},
        {"mnemonic": "SPHI", "curve_family": "Sonic", "curve_family_key": "sonic", "curve_type": "Sonic Porosity"},
    ]
    result = ManagedWellInventoryService._coalesce_wdv_curve_family_contracts(curves)
    assert {row["curve_family_key"] for row in result} == {"sonic"}
    assert len({row["curve_family"] for row in result}) == 1
    assert len({row["curve_type"] for row in result}) == 3


def test_wdv_equivalent_family_labels_collapse_by_general_family_key():
    curves = [
        {"curve_family": "Resistivity", "curve_family_key": "resistivity", "curve_type": "Deep Resistivity"},
        {"curve_family": "resistivity", "curve_family_key": "resistivity", "curve_type": "Shallow Resistivity"},
        {"curve_family": "RESISTIVITY", "curve_family_key": "resistivity", "curve_type": "Micro Resistivity"},
    ]
    result = ManagedWellInventoryService._coalesce_wdv_curve_family_contracts(curves)
    assert {row["curve_family_key"] for row in result} == {"resistivity"}
    assert len({row["curve_family"] for row in result}) == 1
