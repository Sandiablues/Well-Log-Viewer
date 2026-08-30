from app.knowledge.curve_knowledge import resolve_curve_definition
from app.knowledge.repository import KnowledgeRepository


EXPECTED = {
    "GRBM": ("gamma_ray", "gamma_ray", "Gamma Ray"),
    "GRDM": ("gamma_ray", "gamma_ray", "Gamma Ray"),
    "HCNL": ("neutron_porosity", "neutron_porosity", "Neutron Porosity"),
    "HDEN": ("bulk_density", "density", "Bulk Density"),
    "HRD": ("deep_resistivity", "resistivity", "Deep Resistivity"),
    "HRM": ("medium_resistivity", "resistivity", "Medium Resistivity"),
    "HRS": ("shallow_resistivity", "resistivity", "Shallow Resistivity"),
    "HRD1": ("density_auxiliary_count_rate", "density_auxiliary", "Density Auxiliary Count Rate"),
    "HRD2": ("density_auxiliary_count_rate", "density_auxiliary", "Density Auxiliary Count Rate"),
}


def test_lis_lti_mnemonics_resolve_to_governed_kr_definitions() -> None:
    for mnemonic, expected in EXPECTED.items():
        definition = resolve_curve_definition(mnemonic)
        assert definition is not None, mnemonic
        assert (
            definition.canonical_curve_id,
            definition.curve_family,
            definition.display_name,
        ) == expected


def test_lis_lti_mnemonics_are_exposed_by_kr_repository() -> None:
    response = KnowledgeRepository().get_curve_definitions()
    by_mnemonic = {}
    for definition in response.curve_definitions:
        for mnemonic in definition.all_known_mnemonics:
            by_mnemonic[mnemonic.upper()] = definition

    for mnemonic, expected in EXPECTED.items():
        definition = by_mnemonic[mnemonic]
        assert definition.canonical_curve_id == expected[0]
        assert definition.family == expected[1]
        assert definition.product_group == "open_hole_logs"
        assert definition.product_subgroup in {
            "gamma_ray",
            "resistivity",
            "density_neutron_porosity",
        }
