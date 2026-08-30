from app.inventory.deviation_survey_rules import assess_deviation_survey, publication_state


def test_dsm_rules_block_duplicate_md_and_bad_angles():
    findings = assess_deviation_survey(
        [
            {"measured_depth": 100.0, "inclination": 0.0, "azimuth": 0.0, "depth_unit": "m", "dogleg_unit": "deg/30m", "station_type": "measured"},
            {"measured_depth": 100.0, "inclination": 181.0, "azimuth": 360.0, "depth_unit": "m", "dogleg_unit": "deg/30m", "station_type": "extrapolated"},
        ],
        survey_metadata={"datum": "RKB", "coordinate_origin": "Wellhead"},
    )
    ids = {finding.rule_id for finding in findings}
    assert {"DSM-MD-001", "DSM-MD-002", "DSM-INC-001", "DSM-AZI-001", "DSM-EXT-001"} <= ids
    assert publication_state(findings) == "blocked"


def test_dsm_rules_allow_clean_survey_with_information_only():
    findings = assess_deviation_survey(
        [
            {"measured_depth": 0.0, "inclination": 0.0, "azimuth": 0.0, "depth_unit": "m", "dogleg_unit": "deg/30m", "station_type": "measured"},
            {"measured_depth": 100.0, "inclination": 10.0, "azimuth": 90.0, "depth_unit": "m", "dogleg_unit": "deg/30m", "station_type": "extrapolated"},
        ],
        survey_metadata={"datum": "RKB", "coordinate_origin": "Wellhead"},
    )
    assert not any(finding.severity == "failure" for finding in findings)
    assert any(finding.rule_id == "DSM-EXT-001" for finding in findings)
    assert publication_state(findings) == "ready"
