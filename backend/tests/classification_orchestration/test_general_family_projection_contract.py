from app.classification_orchestration.general_family_projection import project_general_curve_family


def test_density_correction_projects_to_density():
    projected = project_general_curve_family("density_correction", "Density Correction")
    assert projected.family_key == "density"
    assert projected.family_label == "Density"


def test_sonic_subclasses_project_to_one_general_family():
    keys = {
        project_general_curve_family(key, label).family_key
        for key, label in (
            ("sonic", "Sonic"),
            ("sonic_compressional", "Sonic Compressional"),
            ("sonic_shear", "Sonic Shear"),
        )
    }
    assert keys == {"sonic"}


def test_distinct_general_families_remain_distinct():
    assert project_general_curve_family("density", "Density").family_key == "density"
    assert project_general_curve_family("neutron_porosity", "Neutron Porosity").family_key == "neutron_porosity"
    assert project_general_curve_family("photoelectric_factor", "Photoelectric Factor").family_key == "photoelectric_factor"
