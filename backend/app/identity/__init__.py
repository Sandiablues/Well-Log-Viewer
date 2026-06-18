"""Backend-owned identity foundation for WLV/MSI managed entities."""

from .models import (
    IDENTITY_SCHEMA_VERSION,
    CanonicalIdentity,
    IdentityAssignmentMetadata,
    LegacyIdentityAlias,
    ManagedEntityType,
)
from .uuid7 import (
    Uuid7Generator,
    is_uuid7,
    new_uuid7,
    new_uuid7_str,
    parse_uuid7,
    uuid7_timestamp_ms,
)

__all__ = [
    "IDENTITY_SCHEMA_VERSION",
    "CanonicalIdentity",
    "IdentityAssignmentMetadata",
    "LegacyIdentityAlias",
    "ManagedEntityType",
    "Uuid7Generator",
    "is_uuid7",
    "new_uuid7",
    "new_uuid7_str",
    "parse_uuid7",
    "uuid7_timestamp_ms",
]
