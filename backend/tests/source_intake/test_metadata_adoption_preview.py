from app.source_intake.metadata_adoption import (
    adoption_summary,
    build_canonical_metadata_from_persisted_source,
)


def test_existing_canonical_metadata_is_preserved() -> None:
    source_metadata = {
        "canonical_source_metadata": {
            "schema_version": "source_metadata_v1",
            "source_format": "LAS",
            "parser_id": "las-parser",
            "fields": {
                "country": {
                    "canonical_field": "country",
                    "value": "Portugal",
                    "original_field": "CTRY",
                    "original_value": "Portugal",
                    "source_section": "LAS ~Well",
                    "parser_id": "las-parser",
                    "source_format": "LAS",
                    "normalization_rule": "trim_whitespace",
                    "review_required": False,
                }
            },
            "unmapped_header_values": {},
        }
    }

    result = build_canonical_metadata_from_persisted_source(source_metadata)

    assert result is not None
    assert result.fields["country"].value == "Portugal"


def test_legacy_las_adoption_uses_explicit_parsed_fields_only() -> None:
    source_metadata = {
        "parsed_metadata": {
            "parser_id": "las-parser",
            "source_format": "LAS",
            "well_header": {
                "well_name": "Well A",
                "operator": "Operator A",
                "country": None,
            },
            "log_header": {
                "service_company": "Service A",
            },
        },
        "original_path": "/Norway/Volve/Well-A.las",
    }

    result = build_canonical_metadata_from_persisted_source(source_metadata)

    assert result is not None
    assert result.fields["well_name"].value == "Well A"
    assert result.fields["operator"].value == "Operator A"
    assert result.fields["producer"].value == "Service A"
    assert "country" not in result.fields


def test_legacy_dlis_adoption_does_not_guess_country() -> None:
    source_metadata = {
        "parsed_metadata": {
            "parser_id": "dlis-parser",
            "source_format": "DLIS",
            "well_header": {
                "well_name": "15/9-F-5",
                "field": "Volve",
                "country": None,
            },
            "log_header": {
                "service_company": "CROCKER DATA PROCESSING",
            },
        },
        "file_name": "WLC_PETROPHYSICAL_COMPOSITE_1.DLIS",
    }

    result = build_canonical_metadata_from_persisted_source(source_metadata)

    assert result is not None
    assert result.fields["well_name"].value == "15/9-F-5"
    assert result.fields["field"].value == "Volve"
    assert result.fields["producer"].value == "CROCKER DATA PROCESSING"
    assert "country" not in result.fields


def test_adoption_summary_is_read_only_plan() -> None:
    source_metadata = {
        "parsed_metadata": {
            "parser_id": "las-parser",
            "source_format": "LAS",
            "well_header": {"well_name": "Well B"},
        }
    }

    before = repr(source_metadata)
    summary = adoption_summary(source_metadata)

    assert summary["proposal_available"] is True
    assert summary["fields"]["well_name"]["value"] == "Well B"
    assert repr(source_metadata) == before
