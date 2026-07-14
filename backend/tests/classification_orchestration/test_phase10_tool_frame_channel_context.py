from app.classification_orchestration.context_resolver import ToolFrameChannelContextResolver
from app.classification_orchestration.contracts import CurveClassificationRequest
from app.classification_orchestration.family_registry import CanonicalCurveFamilyRegistry


def registry():
    r = CanonicalCurveFamilyRegistry()
    for family in ("Sonic", "NMR", "Neutron Porosity", "Drilling"):
        r.register_source_family(family)
    return r


def test_context_requires_two_independent_signals():
    resolver = ToolFrameChannelContextResolver(registry())
    req = CurveClassificationRequest(
        source_mnemonic="X",
        curve_id="x",
        description="Compressional wave travel time",
        source_uid="s",
        logical_file_id="l",
        frame_id="f",
    )
    assert resolver.resolve_batch([req], {}) == {}


def test_sonic_context_uses_description_plus_resolved_peer():
    resolver = ToolFrameChannelContextResolver(registry())
    peer = CurveClassificationRequest(
        source_mnemonic="PEER",
        curve_id="peer",
        description="Known acoustic curve",
        source_uid="s",
        logical_file_id="l",
        frame_id="f",
    )
    target = CurveClassificationRequest(
        source_mnemonic="X",
        curve_id="target",
        description="Compressional wave travel time post processed",
        source_uid="s",
        logical_file_id="l",
        frame_id="f",
    )
    out = resolver.resolve_batch([peer, target], {"peer": "sonic"})
    assert out["target"].family_key == "sonic"
    assert out["target"].signal_count >= 2


def test_nmr_context_uses_measurement_domain_plus_peer_context():
    resolver = ToolFrameChannelContextResolver(registry())
    peer = CurveClassificationRequest(
        source_mnemonic="PEER",
        curve_id="peer",
        source_uid="s",
        logical_file_id="run",
        frame_id="0",
    )
    target = CurveClassificationRequest(
        source_mnemonic="X",
        curve_id="target",
        description="MagTrak Mean T2",
        source_uid="s",
        logical_file_id="run",
        frame_id="0",
    )
    out = resolver.resolve_batch([peer, target], {"peer": "nmr"})
    assert out["target"].family_key == "nmr"


def test_neutron_thermal_count_context_is_not_mnemonic_specific():
    resolver = ToolFrameChannelContextResolver(registry())
    peer = CurveClassificationRequest(
        source_mnemonic="ANY",
        curve_id="peer",
        source_uid="las",
    )
    target = CurveClassificationRequest(
        source_mnemonic="COMPLETELY_UNKNOWN",
        curve_id="target",
        description="Corrected Far Thermal Count Rate",
        source_uid="las",
    )
    out = resolver.resolve_batch([peer, target], {"peer": "neutron_porosity"})
    assert out["target"].family_key == "neutron_porosity"


def test_context_does_not_force_ambiguous_crossplot_porosity():
    resolver = ToolFrameChannelContextResolver(registry())
    peer = CurveClassificationRequest(
        source_mnemonic="PEER",
        curve_id="peer",
        source_uid="las",
    )
    target = CurveClassificationRequest(
        source_mnemonic="X",
        curve_id="target",
        description="Crossplot Porosity from Lithology Computation",
        unit="CFCF",
        source_uid="las",
    )
    assert resolver.resolve_batch([peer, target], {"peer": "neutron_porosity"}) == {}


def test_context_is_scoped_by_source_logical_file_and_frame():
    resolver = ToolFrameChannelContextResolver(registry())
    peer = CurveClassificationRequest(
        source_mnemonic="PEER",
        curve_id="peer",
        source_uid="s",
        logical_file_id="other",
        frame_id="0",
    )
    target = CurveClassificationRequest(
        source_mnemonic="X",
        curve_id="target",
        description="Compressional wave travel time",
        source_uid="s",
        logical_file_id="target",
        frame_id="0",
    )
    assert resolver.resolve_batch([peer, target], {"peer": "sonic"}) == {}
