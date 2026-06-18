"""Shared backend contracts for canonical WLV identity assignment."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .uuid7 import parse_uuid7

IDENTITY_SCHEMA_VERSION = "wlv_identity_v1"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ManagedEntityType(str, Enum):
    MANAGED_WELL = "managed_well"
    MANAGED_WELLBORE = "managed_wellbore"
    MANAGED_SOURCE = "managed_source"
    SOURCE_OCCURRENCE = "source_occurrence"
    MANAGED_PRODUCT = "managed_product"
    MANAGED_CURVE = "managed_curve"
    MANAGED_TRAJECTORY = "managed_trajectory"
    REPRESENTATION = "representation"
    VIEWER_PACKAGE = "viewer_package"
    ARTIFACT = "artifact"
    WDV_LAYOUT_SESSION = "wdv_layout_session"


class LegacyIdentityAlias(BaseModel):
    """A preserved identifier from a superseded identity scheme."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    scheme: str = Field(min_length=1)
    value: str = Field(min_length=1)


class IdentityAssignmentMetadata(BaseModel):
    """Audit metadata written when a repository assigns canonical identity."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = IDENTITY_SCHEMA_VERSION
    assigned_at: str = Field(default_factory=utc_now_iso)
    assignment_source: str = Field(min_length=1)


class CanonicalIdentity(BaseModel):
    """Canonical persisted identity contract.

    ``uid`` has no default factory by design. Domain models must receive an
    already assigned and persisted UUID from their owning repository/service;
    reading or serializing a model must never manufacture identity.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    entity_type: ManagedEntityType
    uid: str
    assignment: IdentityAssignmentMetadata
    legacy_ids: tuple[LegacyIdentityAlias, ...] = ()

    @field_validator("uid")
    @classmethod
    def validate_uid(cls, value: str) -> str:
        return str(parse_uuid7(value))
