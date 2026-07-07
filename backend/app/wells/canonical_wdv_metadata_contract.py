"""Backend-owned metadata contract for the Well Data Viewer."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from app.inventory.canonical_identity_resolver import CanonicalInventoryIdentityResolver


class WdvMetadataValue(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    key: str
    label: str
    value: str | float | int | None
    unit: str | None = None


class WdvMetadataSection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    key: str
    label: str
    values: tuple[WdvMetadataValue, ...]


class WdvMetadataContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    contract_kind: Literal["wdv_metadata"] = "wdv_metadata"
    contract_version: Literal["wdv_metadata_v1"] = "wdv_metadata_v1"
    managed_well_uid: str
    source_format: str | None
    sections: tuple[WdvMetadataSection, ...]


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, Enum):
        value = value.value
    rendered = str(value).strip()
    return rendered or None


def _upper_text(value: Any) -> str | None:
    rendered = _text(value)
    return rendered.upper() if rendered is not None else None


def _first_curve_provenance(well: Any, managed_source_uid: str | None) -> dict[str, Any]:
    for group in getattr(well, "product_groups", ()) or ():
        for item in getattr(group, "items", ()) or ():
            item_source_uid = _text(getattr(item, "managed_source_uid", None))
            if managed_source_uid is not None and item_source_uid != managed_source_uid:
                continue
            provenance = _dict(getattr(item, "provenance", None))
            if provenance:
                return provenance
    return {}


class CanonicalWdvMetadataService:
    def __init__(
        self,
        resolver: CanonicalInventoryIdentityResolver | None = None,
    ) -> None:
        self.resolver = resolver or CanonicalInventoryIdentityResolver()

    def get(self, managed_well_uid: str) -> WdvMetadataContract:
        well = self.resolver.resolve_well(managed_well_uid)

        sources = list(well.source_references)
        primary = sources[0] if sources else None

        well_metadata = _dict(getattr(well, "metadata", None))
        source_metadata = _dict(getattr(primary, "metadata", None))

        managed_source_uid = _text(
            getattr(primary, "managed_source_uid", None)
            if primary is not None
            else None
        )
        curve_provenance = _first_curve_provenance(well, managed_source_uid)

        parsed_metadata = _dict(source_metadata.get("parsed_metadata"))
        parsed_log_header = _dict(parsed_metadata.get("log_header"))

        source_format = None
        source_name = None
        checksum = None
        if primary is not None:
            source_format = _upper_text(
                getattr(primary, "file_format", None)
                or source_metadata.get("source_format")
                or getattr(primary, "source_kind", None)
            )
            source_name = _text(
                getattr(primary, "file_name", None)
                or getattr(primary, "display_name", None)
                or getattr(primary, "original_path", None)
            )
            checksum = _text(
                getattr(primary, "checksum", None)
                or source_metadata.get("checksum")
            )

        depth_normalization = _dict(source_metadata.get("depth_normalization"))

        logical_file_id = _text(
            curve_provenance.get("dlis_logical_file_id")
            or curve_provenance.get("logical_file_id")
        )
        frame_id = _text(
            curve_provenance.get("dlis_frame_id")
            or curve_provenance.get("frame_id")
        )
        index_channel = _text(
            curve_provenance.get("dlis_index_channel")
            or curve_provenance.get("index_channel")
        )

        producer = _text(
            parsed_log_header.get("service_company")
            or source_metadata.get("producer")
            or source_metadata.get("producer_name")
        )

        sections = (
            WdvMetadataSection(
                key="well",
                label="Well",
                values=(
                    WdvMetadataValue(
                        key="well_name",
                        label="Well",
                        value=well.well_name,
                    ),
                    WdvMetadataValue(
                        key="wellbore_name",
                        label="Wellbore",
                        value=well.wellbore_name,
                    ),
                    WdvMetadataValue(
                        key="field",
                        label="Field",
                        value=well.field,
                    ),
                    WdvMetadataValue(
                        key="operator",
                        label="Operator / company",
                        value=well.operator,
                    ),
                    WdvMetadataValue(
                        key="country",
                        label="Country",
                        value=getattr(well, "country", None),
                    ),
                    WdvMetadataValue(
                        key="block",
                        label="Block",
                        value=getattr(well, "block", None),
                    ),
                    WdvMetadataValue(
                        key="latitude",
                        label="Latitude",
                        value=well_metadata.get("latitude"),
                    ),
                    WdvMetadataValue(
                        key="longitude",
                        label="Longitude",
                        value=well_metadata.get("longitude"),
                    ),
                ),
            ),
            WdvMetadataSection(
                key="depth",
                label="Depth",
                values=(
                    WdvMetadataValue(
                        key="depth_basis",
                        label="Depth basis",
                        value="MD",
                    ),
                    WdvMetadataValue(
                        key="top_depth",
                        label="Top depth",
                        value=well.top_depth,
                        unit=well.depth_unit,
                    ),
                    WdvMetadataValue(
                        key="base_depth",
                        label="Base depth",
                        value=well.base_depth,
                        unit=well.depth_unit,
                    ),
                ),
            ),
            WdvMetadataSection(
                key="source",
                label="Source",
                values=(
                    WdvMetadataValue(
                        key="source_format",
                        label="Format",
                        value=source_format,
                    ),
                    WdvMetadataValue(
                        key="source_name",
                        label="Source file",
                        value=source_name,
                    ),
                    WdvMetadataValue(
                        key="checksum",
                        label="Fingerprint",
                        value=checksum,
                    ),
                    WdvMetadataValue(
                        key="logical_file_id",
                        label="Logical file",
                        value=logical_file_id,
                    ),
                    WdvMetadataValue(
                        key="frame_id",
                        label="Frame",
                        value=frame_id,
                    ),
                    WdvMetadataValue(
                        key="index_channel",
                        label="Index channel",
                        value=index_channel,
                    ),
                    WdvMetadataValue(
                        key="producer",
                        label="Producer",
                        value=producer,
                    ),
                    WdvMetadataValue(
                        key="product",
                        label="Product",
                        value=source_metadata.get("product"),
                    ),
                    WdvMetadataValue(
                        key="version",
                        label="Version",
                        value=source_metadata.get("version"),
                    ),
                    WdvMetadataValue(
                        key="created_at",
                        label="Creation date",
                        value=source_metadata.get("creation_time"),
                    ),
                ),
            ),
            WdvMetadataSection(
                key="registration",
                label="Registration and provenance",
                values=(
                    WdvMetadataValue(
                        key="source_candidate_id",
                        label="Source candidate",
                        value=source_metadata.get("source_intake_candidate_id")
                        or getattr(well, "source_intake_candidate_id", None),
                    ),
                    WdvMetadataValue(
                        key="parser_status",
                        label="Parser status",
                        value=source_metadata.get("parser_status"),
                    ),
                    WdvMetadataValue(
                        key="raw_depth_unit",
                        label="Raw depth unit",
                        value=depth_normalization.get("raw_unit"),
                    ),
                    WdvMetadataValue(
                        key="raw_start_depth",
                        label="Raw top depth",
                        value=depth_normalization.get("raw_start_depth"),
                        unit=depth_normalization.get("raw_unit"),
                    ),
                    WdvMetadataValue(
                        key="raw_stop_depth",
                        label="Raw base depth",
                        value=depth_normalization.get("raw_stop_depth"),
                        unit=depth_normalization.get("raw_unit"),
                    ),
                    WdvMetadataValue(
                        key="selected_depth_unit",
                        label="Registered depth unit",
                        value=depth_normalization.get("selected_target_unit"),
                    ),
                    WdvMetadataValue(
                        key="decision_actor",
                        label="Depth decision actor",
                        value=depth_normalization.get("decision_actor"),
                    ),
                    WdvMetadataValue(
                        key="decision_reason",
                        label="Depth decision reason",
                        value=depth_normalization.get("decision_reason"),
                    ),
                    WdvMetadataValue(
                        key="decision_timestamp",
                        label="Depth decision time",
                        value=depth_normalization.get("decision_timestamp"),
                    ),
                ),
            ),
        )

        return WdvMetadataContract(
            managed_well_uid=str(well.managed_well_uid),
            source_format=source_format,
            sections=sections,
        )
