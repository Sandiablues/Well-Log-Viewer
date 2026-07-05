"""Canonical backend-owned WDV viewer-package assembly."""

from __future__ import annotations

from app.identity import LegacyIdentityAlias, parse_uuid7
from app.depth_reference import well_depth_contract_from_record
from app.identity.wdv_contract_v2 import WdvCanonicalCurveReference
from app.identity.wdv_viewer_package_v21 import (
    WdvCanonicalCurveDisplayPolicy,
    WdvCanonicalDepthRange,
    WdvCanonicalViewerCurve,
    WdvCanonicalViewerPackage,
)
from app.inventory.canonical_identity_resolver import (
    CanonicalIdentityResolutionError,
    CanonicalInventoryIdentityResolver,
)
from app.inventory.models import ManagedProductGroupItem, ManagedSourceReference
from app.wdv_session.canonical_service import CanonicalWdvSessionService
from app.wdv_display.policy_service import WdvCurveDisplayPolicyService


class CanonicalViewerPackageService:
    def __init__(
        self,
        resolver: CanonicalInventoryIdentityResolver | None = None,
        session_service: CanonicalWdvSessionService | None = None,
    ) -> None:
        self.resolver = resolver or CanonicalInventoryIdentityResolver()
        self.session_service = session_service or CanonicalWdvSessionService()

    def generate(self, managed_well_uid: str) -> WdvCanonicalViewerPackage:
        well = self.resolver.resolve_well(managed_well_uid)
        well_uid = str(parse_uuid7(str(well.managed_well_uid)))
        wellbore_uid = (
            str(parse_uuid7(str(well.managed_wellbore_uid)))
            if well.managed_wellbore_uid is not None
            else None
        )

        source_by_uid = self._source_index(well.source_references)
        curves: list[WdvCanonicalViewerCurve] = []

        for group in well.product_groups:
            for product in group.items:
                if not product.selectable:
                    continue
                curves.append(
                    self._curve_reference(
                        well_uid=well_uid,
                        wellbore_uid=wellbore_uid,
                        product=product,
                        source_by_uid=source_by_uid,
                    )
                )

        curves.sort(
            key=lambda curve: (
                curve.curve_family or "",
                curve.observed_mnemonic,
                curve.managed_curve_uid,
            )
        )

        depth_contract = self._well_depth_contract(well)
        session = self.session_service.get_session(well_uid)
        return WdvCanonicalViewerPackage(
            managed_well_uid=well_uid,
            managed_wellbore_uid=wellbore_uid,
            well_name=well.well_name,
            wellbore_name=well.wellbore_name,
            depth_range=WdvCanonicalDepthRange(
                minimum=depth_contract["minimum"],
                maximum=depth_contract["maximum"],
                unit=depth_contract["unit"],
            ),
            curves=tuple(curves),
            session=session,
            warnings=(),
        )

    @staticmethod
    def _well_depth_contract(well: object) -> dict[str, object]:
        return well_depth_contract_from_record(well)

    @staticmethod
    def _source_index(
        sources: list[ManagedSourceReference],
    ) -> dict[str, ManagedSourceReference]:
        output: dict[str, ManagedSourceReference] = {}
        for source in sources:
            if source.managed_source_uid is None:
                raise CanonicalIdentityResolutionError(
                    f"Source {source.source_id} has no managed_source_uid"
                )
            uid = str(parse_uuid7(str(source.managed_source_uid)))
            if uid in output:
                raise CanonicalIdentityResolutionError(
                    f"Duplicate managed_source_uid: {uid}"
                )
            output[uid] = source
        return output

    @staticmethod
    def _curve_reference(
        *,
        well_uid: str,
        wellbore_uid: str | None,
        product: ManagedProductGroupItem,
        source_by_uid: dict[str, ManagedSourceReference],
    ) -> WdvCanonicalViewerCurve:
        if product.managed_curve_uid is None:
            raise CanonicalIdentityResolutionError(
                f"Product {product.product_id} has no managed_curve_uid"
            )
        if product.managed_product_uid is None:
            raise CanonicalIdentityResolutionError(
                f"Product {product.product_id} has no managed_product_uid"
            )
        if product.managed_source_uid is None:
            raise CanonicalIdentityResolutionError(
                f"Product {product.product_id} has no managed_source_uid"
            )

        curve_uid = str(parse_uuid7(str(product.managed_curve_uid)))
        product_uid = str(parse_uuid7(str(product.managed_product_uid)))
        source_uid = str(parse_uuid7(str(product.managed_source_uid)))
        if source_uid not in source_by_uid:
            raise CanonicalIdentityResolutionError(
                f"managed_source_uid {source_uid} is absent from the well"
            )

        product_wellbore_uid = (
            str(parse_uuid7(str(product.managed_wellbore_uid)))
            if product.managed_wellbore_uid is not None
            else wellbore_uid
        )

        aliases = list(product.legacy_ids)
        aliases.extend(
            [
                LegacyIdentityAlias(scheme="product_id", value=product.product_id),
                LegacyIdentityAlias(
                    scheme="curve_id",
                    value=product.curve_name or product.display_name,
                ),
            ]
        )

        display_policy = WdvCurveDisplayPolicyService.resolve(product, {})
        return WdvCanonicalViewerCurve(
            managed_curve_uid=curve_uid,
            managed_product_uid=product_uid,
            managed_well_uid=well_uid,
            managed_wellbore_uid=product_wellbore_uid,
            managed_source_uid=source_uid,
            kr_curve_type_id=product.kr_curve_type_id,
            observed_mnemonic=(
                product.observed_mnemonic
                or product.curve_name
                or product.display_name
            ),
            normalized_mnemonic=product.normalized_mnemonic,
            display_name=product.display_name,
            unit=product.curve_unit,
            curve_family=product.curve_family,
            description=product.curve_description,
            legacy_ids=tuple(aliases),
            display_policy=WdvCanonicalCurveDisplayPolicy(
                curve_class=display_policy["curve_class"],
                lattice=display_policy["lattice"],
                scale_type=display_policy["type"],
                display_min=display_policy.get("min"),
                display_max=display_policy.get("max"),
                review_required=bool(display_policy.get("review_required", False)),
                scale_direction=display_policy["direction"],
                default_color=display_policy["default_color"],
                source=display_policy["source"],
                warnings=tuple(display_policy.get("warnings") or ()),
            ),
        )
