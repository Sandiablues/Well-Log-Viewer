"""
MDE-1: Shared Metadata / Evidence / QAQC / Review contract package.

Package: app/services/metadata_evidence/

Schema version: mde.bundle.v1

This package is independent of SBLT and SSI.
SBLT and SSI consume this package via plain dict inputs.
This package does not import seismic_bulk_loader or source_intake modules.

Public surface:
    build_metadata_evidence_bundle  — build a complete MDE bundle
    detect_intake_mode              — classify intake richness
    validate_bundle_invariants      — assert contract invariants
    get_field_policy                — retrieve field policy
    SCHEMA_VERSION                  — "mde.bundle.v1"
"""

from .mde_builder import build_metadata_evidence_bundle, detect_intake_mode
from .mde_models import SCHEMA_VERSION
from .mde_policy import get_field_policy
from .mde_validation import MDEValidationError, validate_bundle_invariants

__all__ = [
    "SCHEMA_VERSION",
    "MDEValidationError",
    "build_metadata_evidence_bundle",
    "detect_intake_mode",
    "get_field_policy",
    "validate_bundle_invariants",
]
