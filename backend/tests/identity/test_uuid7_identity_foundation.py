from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError

from app.identity import (
    IDENTITY_SCHEMA_VERSION,
    CanonicalIdentity,
    IdentityAssignmentMetadata,
    LegacyIdentityAlias,
    ManagedEntityType,
    Uuid7Generator,
    is_uuid7,
    new_uuid7_str,
    parse_uuid7,
    uuid7_timestamp_ms,
)


def test_generated_value_is_canonical_rfc_uuid7():
    value = new_uuid7_str()

    parsed = uuid.UUID(value)
    assert value == str(parsed)
    assert parsed.version == 7
    assert parsed.variant == uuid.RFC_4122
    assert is_uuid7(value) is True


def test_generator_is_monotonic_within_same_millisecond():
    generator = Uuid7Generator(
        time_ms=lambda: 1_750_000_000_123,
        random_bits=lambda bits: 10,
    )

    values = [generator.new() for _ in range(4)]

    assert values == sorted(values)
    assert len(set(values)) == 4
    assert [uuid7_timestamp_ms(value) for value in values] == [1_750_000_000_123] * 4


def test_generator_contains_clock_rollback_without_reordering_identity():
    timestamps = iter([1_000, 999, 1_001])
    generator = Uuid7Generator(
        time_ms=lambda: next(timestamps),
        random_bits=lambda bits: 100,
    )

    first = generator.new()
    second = generator.new()
    third = generator.new()

    assert first < second < third
    assert uuid7_timestamp_ms(first) == 1_000
    assert uuid7_timestamp_ms(second) == 1_000
    assert uuid7_timestamp_ms(third) == 1_001


def test_parser_rejects_non_uuid7_values():
    with pytest.raises(ValueError, match="expected UUIDv7"):
        parse_uuid7(uuid.uuid4())

    assert is_uuid7("not-a-uuid") is False
    assert is_uuid7(None) is False


def test_canonical_identity_requires_repository_assigned_uid():
    assignment = IdentityAssignmentMetadata(assignment_source="managed_inventory_repository")

    with pytest.raises(ValidationError):
        CanonicalIdentity(
            entity_type=ManagedEntityType.MANAGED_CURVE,
            assignment=assignment,
        )


def test_canonical_identity_preserves_legacy_alias_and_normalizes_uuid():
    generator = Uuid7Generator(time_ms=lambda: 1_750_000_000_123, random_bits=lambda bits: 42)
    canonical_uuid = generator.new()

    identity = CanonicalIdentity(
        entity_type=ManagedEntityType.MANAGED_CURVE,
        uid=str(canonical_uuid).upper(),
        assignment=IdentityAssignmentMetadata(assignment_source="identity_migration_v1"),
        legacy_ids=(
            LegacyIdentityAlias(
                scheme="wlv_curve_sha1_v1",
                value="wlv_curve:4e4789a3b0ea5c01aee4",
            ),
        ),
    )

    assert identity.uid == str(canonical_uuid)
    assert identity.assignment.schema_version == IDENTITY_SCHEMA_VERSION
    assert identity.legacy_ids[0].value == "wlv_curve:4e4789a3b0ea5c01aee4"


def test_identity_contract_is_immutable_and_forbids_unknown_fields():
    identity = CanonicalIdentity(
        entity_type=ManagedEntityType.MANAGED_WELL,
        uid=new_uuid7_str(),
        assignment=IdentityAssignmentMetadata(assignment_source="managed_inventory_repository"),
    )

    with pytest.raises(ValidationError):
        identity.uid = new_uuid7_str()

    with pytest.raises(ValidationError):
        CanonicalIdentity.model_validate(
            {
                **identity.model_dump(),
                "unexpected": "field",
            }
        )
