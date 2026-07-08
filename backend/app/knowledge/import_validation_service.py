"""KR-3 import payload validation service.

Validates a structured ImportPayload against:
1. Internal required-field rules.
2. Duplicate canonical_curve_id within the payload.
3. Duplicate alias within the same curve definition.
4. Alias mapped to multiple canonical_curve_ids within the payload.
5. Alias conflicts against existing seed/managed alias records.
6. Display rule referencing an unknown canonical_curve_id.
7. Classification rule referencing an unknown product_group / product_subgroup.
8. Invalid scale_type for display rules.
9. Invalid confidence value for classification rules.

This service is PURE (no side effects) and does NOT mutate the repository.
Call it before staging to get a full ValidationResult.

Returns a structured ImportValidationResult suitable for both:
  - /import/preview  (validate only, no staging)
  - /import/stage    (validate then stage if valid)
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .import_models import ImportPayload
from .managed_models import AliasRecord, StandardMnemonicRecord
from .managed_repository import ManagedKRRepository


# ---------------------------------------------------------------------------
# Known KR taxonomy constants (sourced from repository.py seed data)
# ---------------------------------------------------------------------------

_KNOWN_PRODUCT_GROUPS: frozenset[str] = frozenset(
    {
        "open_hole_logs",
        "cased_hole_logs",
        "rasters_images",
        "lithology_core_markers",
        "pressure_production_fluid_data",
        "completion_integrity_data",
        "supporting_documents",
        "other_review_required",
    }
)

_KNOWN_SUBGROUPS_BY_GROUP: dict[str, frozenset[str]] = {
    "open_hole_logs": frozenset(
        {
            "gamma_ray",
            "sp_electrochemical",
            "resistivity",
            "density_neutron_porosity",
            "sonic_acoustic",
            "borehole_geometry_imaging",
            "nmr",
            "dip_directional",
            "formation_pressure_sampling",
            "petrophysical_interpretation",
            "other_open_hole_review",
        }
    ),
    "cased_hole_logs": frozenset(
        {
            "cement_evaluation",
            "production_logging",
            "pulsed_neutron_saturation",
            "casing_inspection",
            "depth_correlation",
            "completion_correlation",
            "other_cased_hole_review",
        }
    ),
    "rasters_images": frozenset(
        {
            "cgm",
            "tiff",
            "scanned_log_image",
            "borehole_image",
            "other_raster_review",
        }
    ),
    "lithology_core_markers": frozenset(
        {
            "formation_tops",
            "lithology_intervals",
            "facies",
            "core_data",
            "other_geology_review",
        }
    ),
    "pressure_production_fluid_data": frozenset(
        {
            "formation_pressure",
            "mobility_permeability_indicator",
            "fluid_sample",
            "production_test",
            "other_pressure_fluid_review",
        }
    ),
    "completion_integrity_data": frozenset(
        {
            "perforations",
            "casing",
            "tubing",
            "packers",
            "plugs",
            "well_integrity_inspection",
            "other_completion_review",
        }
    ),
    "supporting_documents": frozenset(
        {
            "well_report",
            "las_header_metadata",
            "completion_report",
            "core_report",
            "image_log_report",
            "other_document_review",
        }
    ),
    "other_review_required": frozenset(
        {
            "unknown_mnemonic",
            "ambiguous_context",
            "missing_units",
            "conflicting_evidence",
            "unsupported_format",
            "other_review_required",
        }
    ),
}


# ---------------------------------------------------------------------------
# Validation result types
# ---------------------------------------------------------------------------


@dataclass
class ValidationIssue:
    """A single validation error or warning with location context."""

    code: str
    message: str
    path: str
    severity: str  # "error" or "warning"


@dataclass
class ImportValidationResult:
    """Structured result of validating an ImportPayload.

    ``valid`` is True only when error_count == 0.
    Warnings do not block staging; errors do.
    """

    valid: bool
    error_count: int
    warning_count: int
    errors: list[ValidationIssue] = field(default_factory=list)
    warnings: list[ValidationIssue] = field(default_factory=list)
    candidate_record_count: int = 0
    evidence_record_count: int = 0
    record_type_counts: dict[str, int] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------


def validate_import_payload(
    payload: ImportPayload,
    repository: ManagedKRRepository,
) -> ImportValidationResult:
    """Validate ``payload`` against internal rules and ``repository`` state.

    Does NOT mutate ``repository``.  Safe to call as many times as needed.

    Args:
        payload: The import payload to validate.
        repository: The current ManagedKRRepository used to check alias
                    conflicts and existing canonical curve IDs.

    Returns:
        ImportValidationResult describing all errors, warnings, and the
        projected record counts if the import were staged.
    """
    errors: list[ValidationIssue] = []
    warnings: list[ValidationIssue] = []

    # -------------------------------------------------------------------
    # 1. Source block — belt-and-suspenders check (Pydantic ensures
    #    the block is present, but check string emptiness explicitly)
    # -------------------------------------------------------------------
    if not payload.source.source_type.strip():
        errors.append(
            ValidationIssue(
                code="missing_required_field",
                message="source.source_type is required and must be non-empty",
                path="source.source_type",
                severity="error",
            )
        )

    if not payload.source.source_label.strip():
        errors.append(
            ValidationIssue(
                code="missing_required_field",
                message="source.source_label is required and must be non-empty",
                path="source.source_label",
                severity="error",
            )
        )

    # -------------------------------------------------------------------
    # 2. Curve definition required fields + duplicate canonical_curve_id
    # -------------------------------------------------------------------

    # Maps canonical_curve_id → first-seen payload index (for dup detection)
    seen_canonical_ids: dict[str, int] = {}

    for idx, cd in enumerate(payload.curve_definitions):
        prefix = f"curve_definitions[{idx}]"

        if not cd.canonical_curve_id or not cd.canonical_curve_id.strip():
            errors.append(
                ValidationIssue(
                    code="missing_required_field",
                    message="canonical_curve_id is required",
                    path=f"{prefix}.canonical_curve_id",
                    severity="error",
                )
            )

        if not cd.display_name or not cd.display_name.strip():
            errors.append(
                ValidationIssue(
                    code="missing_required_field",
                    message="display_name is required",
                    path=f"{prefix}.display_name",
                    severity="error",
                )
            )

        if not cd.family or not cd.family.strip():
            errors.append(
                ValidationIssue(
                    code="missing_required_field",
                    message="family is required",
                    path=f"{prefix}.family",
                    severity="error",
                )
            )

        if not cd.product_group or not cd.product_group.strip():
            errors.append(
                ValidationIssue(
                    code="missing_required_field",
                    message="product_group is required",
                    path=f"{prefix}.product_group",
                    severity="error",
                )
            )

        # Duplicate canonical_curve_id within payload
        if cd.canonical_curve_id and cd.canonical_curve_id.strip():
            cid = cd.canonical_curve_id.strip()
            if cid in seen_canonical_ids:
                errors.append(
                    ValidationIssue(
                        code="duplicate_canonical_curve_id",
                        message=(
                            f"canonical_curve_id '{cid}' is already defined at "
                            f"curve_definitions[{seen_canonical_ids[cid]}]"
                        ),
                        path=f"{prefix}.canonical_curve_id",
                        severity="error",
                    )
                )
            else:
                seen_canonical_ids[cid] = idx

    # -------------------------------------------------------------------
    # 3. Standard mnemonic / alias duplicate and multi-mapping within payload
    # -------------------------------------------------------------------

    # normalized mnemonic → (cd_idx, field_name, item_idx) of first occurrence
    seen_mnemonic_global: dict[str, tuple[int, str, int]] = {}

    for idx, cd in enumerate(payload.curve_definitions):
        seen_mnemonic_in_cd: set[str] = set()
        mnemonic_entries = [
            ("standard_mnemonics", m_idx, mnemonic)
            for m_idx, mnemonic in enumerate(cd.standard_mnemonics)
        ] + [
            ("aliases", a_idx, alias)
            for a_idx, alias in enumerate(cd.aliases)
        ]

        for field_name, item_idx, mnemonic in mnemonic_entries:
            normalized = mnemonic.strip().upper()
            mnemonic_path = f"curve_definitions[{idx}].{field_name}[{item_idx}]"

            if normalized in seen_mnemonic_in_cd:
                if field_name == "aliases":
                    code = "duplicate_alias_in_curve_definition"
                    message = (
                        f"Alias '{mnemonic}' (normalized: '{normalized}') appears more than "
                        f"once within curve_definitions[{idx}]"
                    )
                elif field_name == "standard_mnemonics":
                    code = "duplicate_standard_mnemonic_in_curve_definition"
                    message = (
                        f"Standard mnemonic '{mnemonic}' (normalized: '{normalized}') appears more than "
                        f"once within curve_definitions[{idx}]"
                    )
                else:
                    code = "duplicate_mnemonic_in_curve_definition"
                    message = (
                        f"Mnemonic '{mnemonic}' (normalized: '{normalized}') appears more than "
                        f"once within curve_definitions[{idx}]"
                    )
                errors.append(
                    ValidationIssue(
                        code=code,
                        message=message,
                        path=mnemonic_path,
                        severity="error",
                    )
                )
                continue

            seen_mnemonic_in_cd.add(normalized)

            if normalized in seen_mnemonic_global:
                first_cd_idx, first_field, first_item_idx = seen_mnemonic_global[normalized]
                if first_cd_idx != idx:
                    if field_name == "aliases" and first_field == "aliases":
                        code = "alias_mapped_to_multiple_canonical_ids"
                        label = "Alias"
                    elif field_name == "standard_mnemonics" and first_field == "standard_mnemonics":
                        code = "standard_mnemonic_mapped_to_multiple_canonical_ids"
                        label = "Standard mnemonic"
                    else:
                        code = "mnemonic_mapped_to_multiple_canonical_ids"
                        label = "Mnemonic"
                    errors.append(
                        ValidationIssue(
                            code=code,
                            message=(
                                f"{label} '{mnemonic}' (normalized: '{normalized}') is assigned to "
                                f"multiple canonical_curve_ids in this payload "
                                f"(first seen at curve_definitions[{first_cd_idx}].{first_field}[{first_item_idx}])"
                            ),
                            path=mnemonic_path,
                            severity="error",
                        )
                    )
            else:
                seen_mnemonic_global[normalized] = (idx, field_name, item_idx)

    # -------------------------------------------------------------------
    # 4. Mnemonic conflict with existing seed / managed records
    # -------------------------------------------------------------------

    existing_mnemonic_map: dict[str, str] = {
        r.normalized_mnemonic: r.canonical_curve_id
        for r in repository.list_records("standard_mnemonic")
        if isinstance(r, StandardMnemonicRecord)
    }
    existing_mnemonic_map.update({
        r.normalized_alias: r.canonical_curve_id
        for r in repository.list_records("alias")
        if isinstance(r, AliasRecord)
    })

    for idx, cd in enumerate(payload.curve_definitions):
        seen_in_cd_normalized: set[str] = set()
        mnemonic_entries = [
            ("standard_mnemonics", m_idx, mnemonic)
            for m_idx, mnemonic in enumerate(cd.standard_mnemonics)
        ] + [
            ("aliases", a_idx, alias)
            for a_idx, alias in enumerate(cd.aliases)
        ]
        for field_name, item_idx, mnemonic in mnemonic_entries:
            normalized = mnemonic.strip().upper()
            if normalized in seen_in_cd_normalized:
                continue
            seen_in_cd_normalized.add(normalized)

            mnemonic_path = f"curve_definitions[{idx}].{field_name}[{item_idx}]"

            if normalized in existing_mnemonic_map:
                existing_canonical = existing_mnemonic_map[normalized]
                import_canonical = cd.canonical_curve_id.strip() if cd.canonical_curve_id else ""

                if existing_canonical != import_canonical:
                    errors.append(
                        ValidationIssue(
                            code="mnemonic_conflicts_with_existing_record",
                            message=(
                                f"Mnemonic '{mnemonic}' (normalized: '{normalized}') already exists in "
                                f"the managed KR mapped to canonical_curve_id '{existing_canonical}', "
                                f"but this import assigns it to '{import_canonical}'"
                            ),
                            path=mnemonic_path,
                            severity="error",
                        )
                    )
                else:
                    warnings.append(
                        ValidationIssue(
                            code="mnemonic_already_exists_for_same_curve",
                            message=(
                                f"Mnemonic '{mnemonic}' (normalized: '{normalized}') already exists in "
                                f"the managed KR for canonical_curve_id '{existing_canonical}'. "
                                f"A duplicate candidate mnemonic record will be created."
                            ),
                            path=mnemonic_path,
                            severity="warning",
                        )
                    )

    # -------------------------------------------------------------------
    # 5. Display rule validation
    # -------------------------------------------------------------------

    # Valid canonical IDs = payload curve defs (valid ones) + existing managed defs
    existing_curve_def_ids: set[str] = {
        r.canonical_curve_id  # type: ignore[union-attr]
        for r in repository.list_records("curve_definition")
        if hasattr(r, "canonical_curve_id")
    }
    payload_curve_def_ids: set[str] = set(seen_canonical_ids.keys())
    all_known_curve_ids = existing_curve_def_ids | payload_curve_def_ids

    for idx, dr in enumerate(payload.display_rules):
        prefix = f"display_rules[{idx}]"

        if not dr.canonical_curve_id or not dr.canonical_curve_id.strip():
            errors.append(
                ValidationIssue(
                    code="missing_required_field",
                    message="canonical_curve_id is required for a display rule",
                    path=f"{prefix}.canonical_curve_id",
                    severity="error",
                )
            )
        elif dr.canonical_curve_id.strip() not in all_known_curve_ids:
            errors.append(
                ValidationIssue(
                    code="display_rule_unknown_canonical_curve_id",
                    message=(
                        f"display_rule references canonical_curve_id "
                        f"'{dr.canonical_curve_id}' which is not defined in this "
                        f"payload or in the existing managed KR"
                    ),
                    path=f"{prefix}.canonical_curve_id",
                    severity="error",
                )
            )

        if dr.scale_type not in {"linear", "log"}:
            errors.append(
                ValidationIssue(
                    code="invalid_scale_type",
                    message=f"scale_type '{dr.scale_type}' must be 'linear' or 'log'",
                    path=f"{prefix}.scale_type",
                    severity="error",
                )
            )

    # -------------------------------------------------------------------
    # 6. Classification rule validation
    # -------------------------------------------------------------------

    for idx, cr in enumerate(payload.classification_rules):
        prefix = f"classification_rules[{idx}]"

        if not cr.rule_key or not cr.rule_key.strip():
            errors.append(
                ValidationIssue(
                    code="missing_required_field",
                    message="rule_key is required",
                    path=f"{prefix}.rule_key",
                    severity="error",
                )
            )

        if not cr.match_type or not cr.match_type.strip():
            errors.append(
                ValidationIssue(
                    code="missing_required_field",
                    message="match_type is required",
                    path=f"{prefix}.match_type",
                    severity="error",
                )
            )

        if not cr.match_value or not cr.match_value.strip():
            errors.append(
                ValidationIssue(
                    code="missing_required_field",
                    message="match_value is required",
                    path=f"{prefix}.match_value",
                    severity="error",
                )
            )

        if not cr.product_group or not cr.product_group.strip():
            errors.append(
                ValidationIssue(
                    code="missing_required_field",
                    message="product_group is required",
                    path=f"{prefix}.product_group",
                    severity="error",
                )
            )
        elif cr.product_group not in _KNOWN_PRODUCT_GROUPS:
            errors.append(
                ValidationIssue(
                    code="unknown_product_group",
                    message=(
                        f"product_group '{cr.product_group}' is not a known KR product "
                        f"group. Known groups: {sorted(_KNOWN_PRODUCT_GROUPS)}"
                    ),
                    path=f"{prefix}.product_group",
                    severity="error",
                )
            )
        elif cr.product_subgroup is not None:
            known_subgroups = _KNOWN_SUBGROUPS_BY_GROUP.get(cr.product_group)
            if known_subgroups is not None and cr.product_subgroup not in known_subgroups:
                errors.append(
                    ValidationIssue(
                        code="unknown_product_subgroup",
                        message=(
                            f"product_subgroup '{cr.product_subgroup}' is not a known "
                            f"subgroup of product_group '{cr.product_group}'"
                        ),
                        path=f"{prefix}.product_subgroup",
                        severity="error",
                    )
                )

        if not (0.0 <= cr.confidence <= 1.0):
            errors.append(
                ValidationIssue(
                    code="invalid_confidence_value",
                    message=(
                        f"confidence must be between 0.0 and 1.0, got {cr.confidence}"
                    ),
                    path=f"{prefix}.confidence",
                    severity="error",
                )
            )

    # -------------------------------------------------------------------
    # 7. Compute projected candidate record counts
    # -------------------------------------------------------------------

    curve_def_count = len(payload.curve_definitions)
    standard_mnemonic_count = sum(len(cd.standard_mnemonics) for cd in payload.curve_definitions)
    alias_count = sum(len(cd.aliases) for cd in payload.curve_definitions)
    display_rule_count = len(payload.display_rules)
    class_rule_count = len(payload.classification_rules)
    template_rule_count = len(payload.template_rules)
    evidence_count = 1  # always one evidence record per import batch

    candidate_record_count = (
        curve_def_count
        + standard_mnemonic_count
        + alias_count
        + display_rule_count
        + class_rule_count
        + template_rule_count
    )

    record_type_counts: dict[str, int] = {
        "curve_definition": curve_def_count,
        "standard_mnemonic": standard_mnemonic_count,
        "alias": alias_count,
        "display_rule": display_rule_count,
        "classification_rule": class_rule_count,
        "template_rule": template_rule_count,
        "evidence": evidence_count,
    }

    return ImportValidationResult(
        valid=len(errors) == 0,
        error_count=len(errors),
        warning_count=len(warnings),
        errors=errors,
        warnings=warnings,
        candidate_record_count=candidate_record_count,
        evidence_record_count=evidence_count,
        record_type_counts=record_type_counts,
    )
