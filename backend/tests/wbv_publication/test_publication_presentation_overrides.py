from pathlib import Path

from app.identity import new_uuid7_str
from app.wbv_publication.models import (
    WbvPresentationOverrides,
    WbvPresentationOverridesUpdateRequest,
    WbvPublishAsNewRequest,
)
from app.wbv_publication.repository import WbvOverlayPackageRepository
from app.wbv_publication.service import WbvOverlayPublicationService
from tests.wbv_publication.test_publication_foundation import _session


class StaticSessionService:
    def __init__(self, session):
        self.session = session

    def get_session(self, managed_well_uid: str):
        assert managed_well_uid == self.session.managed_well_uid
        return self.session


def test_presentation_overrides_persist_and_increment_revision(tmp_path: Path) -> None:
    session = _session()
    repository = WbvOverlayPackageRepository(tmp_path / "packages.json")
    service = WbvOverlayPublicationService(repository, StaticSessionService(session))
    package = service.publish_as_new(
        session.managed_well_uid,
        WbvPublishAsNewRequest(
            package_name="Presentation",
            command_uid=new_uuid7_str(),
            activate=True,
        ),
    )
    request = WbvPresentationOverridesUpdateRequest(
        expected_package_revision=package.package_revision,
        overrides=WbvPresentationOverrides(package_visible=False, track_spacing=0.25),
    )
    saved = service.update_presentation_overrides(
        session.managed_well_uid,
        package.package_uid,
        request,
    )
    assert saved.package_revision == package.package_revision + 1
    assert saved.wbv_overrides.package_visible is False
    assert saved.wbv_overrides.track_spacing == 0.25
    reloaded = WbvOverlayPackageRepository(repository.storage_path).get(package.package_uid)
    assert reloaded.wbv_overrides == saved.wbv_overrides
