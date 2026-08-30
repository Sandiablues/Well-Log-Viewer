from app.inventory.models import (
    DeviationSurveyMetadataPublishRecord,
    DeviationSurveyStationPublishRecord,
    ManagedWellRecord,
    PublishDeviationSurveyRequest,
)
from app.inventory.repository import ManagedWellInventoryRepository
from app.inventory.service import ManagedWellInventoryService


def test_dsm_publication_preserves_source_values_and_builds_wbv_trajectory(tmp_path):
    source = tmp_path / "managed_wells.json"
    repository = ManagedWellInventoryRepository(storage_path=source)
    service = ManagedWellInventoryService(repository=repository)

    seed = ManagedWellRecord(
        managed_well_id="managed-well:dsm-regression",
        well_id="dsm-regression",
        well_name="DSM Regression",
        wellbore_id="dsm-regression",
        wellbore_name="DSM Regression",
        depth_unit="m",
        top_depth=0.0,
        base_depth=100.0,
    )
    repository.upsert_record(seed)

    request = PublishDeviationSurveyRequest(
        managed_well_id=seed.managed_well_id,
        survey_metadata=DeviationSurveyMetadataPublishRecord(
            survey_name="DSM regression",
            survey_type="Definitive",
            datum="RKB",
            calculation_method="minimum_curvature",
        ),
        stations=[
            DeviationSurveyStationPublishRecord(
                measured_depth=0.0,
                inclination=0.0,
                azimuth=0.0,
                true_vertical_depth=0.0,
                north_south=0.0,
                east_west=0.0,
                depth_unit="m",
                source_document="fixture.pdf",
                source_page="121",
            ),
            DeviationSurveyStationPublishRecord(
                measured_depth=100.0,
                inclination=10.0,
                azimuth=90.0,
                true_vertical_depth=99.5,
                north_south=0.0,
                east_west=8.7,
                depth_unit="m",
                source_document="fixture.pdf",
                source_page="121",
            ),
        ],
    )

    result = service.publish_deviation_survey(seed.managed_well_id, request)
    assert result.published_count == 2

    saved = repository.get_record(seed.managed_well_id)
    assert saved.metadata["deviation_survey_dataset"]["stations"][1]["true_vertical_depth"] == 99.5
    assert saved.metadata["wbv_trajectory_package"]["render_points"]
    assert saved.metadata["wbv_trajectory_package"]["source_values_preserved"] is True
    assert any(
        item.product_subgroup_key == "deviation_survey"
        for group in saved.product_groups
        for item in group.items
    )
