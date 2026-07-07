from pathlib import Path

import pytest

from app.identity import new_uuid7_str
from app.identity.wdv_contract_v2 import WdvCanonicalSession
from app.wbv_publication.models import WbvPackageLifecycleRequest, WbvPublishAsNewRequest
from app.wbv_publication.repository import WbvOverlayPackageNotFound, WbvOverlayPackageRepository
from app.wbv_publication.service import WbvOverlayPublicationService

from test_publication_foundation import _session


class MutableSessionService:
    def __init__(self, session: WdvCanonicalSession):
        self.session = session

    def get_session(self, _well_uid: str) -> WdvCanonicalSession:
        return self.session


def _service(tmp_path: Path):
    session = _session()
    repository = WbvOverlayPackageRepository(tmp_path / "packages.json")
    service = WbvOverlayPublicationService(repository, MutableSessionService(session))
    return session.managed_well_uid, repository, service


def test_delete_available_package_directly(tmp_path: Path):
    well_uid, repository, service = _service(tmp_path)
    package = service.publish_as_new(
        well_uid,
        WbvPublishAsNewRequest(
            package_name="Published",
            command_uid=new_uuid7_str(),
            activate=False,
        ),
    )

    service.delete_package(
        well_uid,
        package.package_uid,
        expected_package_revision=package.package_revision,
    )

    with pytest.raises(WbvOverlayPackageNotFound):
        repository.get(package.package_uid)


def test_delete_active_package_directly(tmp_path: Path):
    well_uid, repository, service = _service(tmp_path)
    package = service.publish_as_new(
        well_uid,
        WbvPublishAsNewRequest(
            package_name="Published",
            command_uid=new_uuid7_str(),
            activate=True,
        ),
    )

    service.delete_package(
        well_uid,
        package.package_uid,
        expected_package_revision=package.package_revision,
    )

    with pytest.raises(WbvOverlayPackageNotFound):
        repository.get(package.package_uid)


def test_archive_then_delete_package(tmp_path: Path):
    well_uid, repository, service = _service(tmp_path)
    package = service.publish_as_new(
        well_uid,
        WbvPublishAsNewRequest(
            package_name="Published",
            command_uid=new_uuid7_str(),
            activate=True,
        ),
    )

    archived = service.change_lifecycle(
        well_uid,
        package.package_uid,
        WbvPackageLifecycleRequest(
            expected_package_revision=package.package_revision,
            action="archive",
        ),
    )
    service.delete_package(
        well_uid,
        archived.package_uid,
        expected_package_revision=archived.package_revision,
    )

    with pytest.raises(WbvOverlayPackageNotFound):
        repository.get(archived.package_uid)

def test_delete_missing_package_is_idempotent(tmp_path: Path):
    well_uid, _repository, service = _service(tmp_path)

    service.delete_package(
        well_uid,
        new_uuid7_str(),
        expected_package_revision=1,
    )

