"""Canonical WDV workspace aggregate service."""

from __future__ import annotations

from app.identity import parse_uuid7
from app.identity.wdv_contract_v2 import WdvCanonicalSession
from app.wdv_session.canonical_service import CanonicalWdvSessionService
from app.wells.canonical_viewer_package_service import CanonicalViewerPackageService

from .models import WdvCanonicalWorkspace


class CanonicalWdvWorkspaceService:
    """Build and validate the complete backend-owned workspace for one well."""

    def __init__(
        self,
        viewer_package_service: CanonicalViewerPackageService | None = None,
        session_service: CanonicalWdvSessionService | None = None,
    ) -> None:
        self.session_service = session_service or CanonicalWdvSessionService()
        self.viewer_package_service = (
            viewer_package_service
            or CanonicalViewerPackageService(session_service=self.session_service)
        )

    def get_workspace(self, managed_well_uid: str) -> WdvCanonicalWorkspace:
        well_uid = str(parse_uuid7(managed_well_uid))
        package = self.viewer_package_service.generate(well_uid)
        return WdvCanonicalWorkspace(
            managed_well_uid=package.managed_well_uid,
            managed_wellbore_uid=package.managed_wellbore_uid,
            well_name=package.well_name,
            wellbore_name=package.wellbore_name,
            depth_range=package.depth_range,
            curve_registry=package.curves,
            session=package.session,
            warnings=package.warnings,
        )

    def validate_session(
        self,
        managed_well_uid: str,
        session: WdvCanonicalSession,
    ) -> WdvCanonicalWorkspace:
        """Validate a candidate session against the well's canonical registry.

        This method is used inside the atomic transaction lock before the
        candidate session is persisted.
        """
        well_uid = str(parse_uuid7(managed_well_uid))
        if session.managed_well_uid != well_uid:
            raise ValueError(
                "Candidate session managed_well_uid must match transaction well"
            )
        package = self.viewer_package_service.generate(well_uid)
        return WdvCanonicalWorkspace(
            managed_well_uid=package.managed_well_uid,
            managed_wellbore_uid=package.managed_wellbore_uid,
            well_name=package.well_name,
            wellbore_name=package.wellbore_name,
            depth_range=package.depth_range,
            curve_registry=package.curves,
            session=session,
            warnings=package.warnings,
        )
