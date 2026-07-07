from datetime import datetime, timezone
from pathlib import Path
from app.identity import new_uuid7_str
from app.identity.wdv_contract_v2 import WdvCanonicalAssignment, WdvCanonicalSession, WdvCanonicalTrack, WdvCurveSampleProvenance, WdvCurveSampleResponse
from app.wbv_publication.adapter import WbvPublishedPackageRenderAdapter
from app.wbv_publication.models import WbvOverlayPackage, WbvPublicationProvenance
from app.wbv_publication.repository import WbvOverlayPackageRepository

def _fixture():
    well, track, assignment, curve, product, source, session_uid, package_uid, command_uid = [new_uuid7_str() for _ in range(9)]
    a = WdvCanonicalAssignment(assignment_uid=assignment, managed_curve_uid=curve, managed_product_uid=product,
        managed_well_uid=well, managed_source_uid=source, track_uid=track, observed_mnemonic="GR",
        display_name="Gamma Ray", unit="gAPI", scale_min=0, scale_max=100, scale_type="linear",
        scale_direction="normal", color="#00ff00", line_width=2, line_opacity=80)
    s = WdvCanonicalSession(session_uid=session_uid, managed_well_uid=well, revision=7, state_status="active",
        tracks=(WdvCanonicalTrack(track_uid=track, managed_well_uid=well, track_name="Track 1", assignments=(a,)),),
        updated_at=datetime.now(timezone.utc).isoformat())
    now = datetime.now(timezone.utc).isoformat()
    p = WbvOverlayPackage(package_uid=package_uid, managed_well_uid=well, package_name="Published",
        source_wdv_session_uid=session_uid, source_wdv_revision=7, published_snapshot=s,
        provenance=WbvPublicationProvenance(published_at=now, published_by="test", publication_command_uid=command_uid,
            source_session_uid=session_uid, source_revision=7), created_at=now, updated_at=now)
    def samples(_):
        return WdvCurveSampleResponse(managed_well_uid=well, managed_curve_uid=curve, managed_product_uid=product,
            managed_source_uid=source, observed_mnemonic="GR", display_name="Gamma Ray", depth_unit="ft",
            value_unit="gAPI", depth_min=1000, depth_max=1001, value_min=0, value_max=100,
            sample_count=2, returned_sample_count=2, provenance=WdvCurveSampleProvenance(sample_source="test"),
            samples=((1000.0, 0.0), (1001.0, 100.0)))
    return p, samples

def test_published_package_compiles_to_existing_wbv_render_contract():
    package, samples = _fixture(); rendered = WbvPublishedPackageRenderAdapter(samples).compile(package)
    assert rendered.managed_well_id == package.managed_well_uid
    assert len(rendered.tracks) == 1 and len(rendered.curves) == 1
    assert [x.normalized for x in rendered.curves[0].samples] == [0.0, 1.0]
    assert rendered.curves[0].provenance["source_wdv_revision"] == 7

def test_repository_reload_retains_snapshot_and_is_independent(tmp_path: Path):
    package, _ = _fixture(); path = tmp_path / "packages.json"
    WbvOverlayPackageRepository(path).save_new(package)
    reloaded = WbvOverlayPackageRepository(path).get(package.package_uid)
    assert reloaded.model_dump() == package.model_dump()
    changed_source = package.published_snapshot.model_copy(update={"revision": 8})
    assert reloaded.source_wdv_revision == 7 and changed_source.revision == 8
