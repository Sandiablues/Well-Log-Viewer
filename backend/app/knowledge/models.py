"""Pydantic response models for the WLV Knowledge Repository (KR-1).

These models define the backend-owned read-only contracts exposed by the
/api/wlv/knowledge/* endpoints.  The frontend renders these contracts; it must
not own or override the classification/category/subgroup truth they carry.
"""

from __future__ import annotations

from pydantic import BaseModel

KR_VERSION = "kr-1"


class KrProductSubgroup(BaseModel):
    """Ordered subgroup within a product group."""

    key: str
    label: str
    order: int


class KrProductGroup(BaseModel):
    """Top-level product group with ordered subgroups."""

    key: str
    label: str
    order: int
    subgroups: list[KrProductSubgroup] = []


class KrProductGroupsResponse(BaseModel):
    """Response contract for /api/wlv/knowledge/product-groups."""

    version: str = KR_VERSION
    groups: list[KrProductGroup] = []


class KrCurveDefinition(BaseModel):
    """Canonical curve definition with identity and classification fields."""

    canonical_curve_id: str
    display_name: str
    family: str
    product_group: str
    product_subgroup: str | None = None
    default_unit: str | None = None
    aliases: list[str] = []


class KrCurveDefinitionsResponse(BaseModel):
    """Response contract for /api/wlv/knowledge/curve-definitions."""

    version: str = KR_VERSION
    curve_definitions: list[KrCurveDefinition] = []


class KrDisplayRule(BaseModel):
    """Display rendering rule for one canonical curve."""

    canonical_curve_id: str
    preferred_track_family: str
    scale_type: str = "linear"
    display_min: float = 0.0
    display_max: float = 150.0
    default_unit: str | None = None
    reverse_scale: bool = False
    overlay_group: str | None = None


class KrDisplayRulesResponse(BaseModel):
    """Response contract for /api/wlv/knowledge/display-rules."""

    version: str = KR_VERSION
    display_rules: list[KrDisplayRule] = []


class KrTemplatesResponse(BaseModel):
    """Response contract for /api/wlv/knowledge/templates.

    KR-1: empty; template seeding deferred to a later block.
    """

    version: str = KR_VERSION
    templates: list[dict] = []  # type: ignore[type-arg]


class KrHealthResponse(BaseModel):
    """Response contract for /api/wlv/knowledge/health."""

    service: str = "wlv_knowledge_repository"
    status: str = "ok"
    mode: str = "read_only"
    version: str = KR_VERSION
    product_group_count: int = 0
    curve_definition_count: int = 0
    display_rule_count: int = 0
    template_count: int = 0
