from pathlib import Path
import pytest
from types import SimpleNamespace

from app.wdv_quick_view.models import QuickViewCurve, QuickViewSample
from app.wdv_quick_view.service import (
    WdvQuickViewService,
    _adaptive_padding_fraction,
    _clean_scalar_samples,
    _curve_display_contract,
    _depth_transform_from_unit,
    _group,
    _unit_domain,
)

def _curve_display_contract_legacy6(*args, **kwargs):
    result = _curve_display_contract(*args, **kwargs)
    return result[:6]




def test_las_returns_self_contained_render_package_without_state(tmp_path):
    before = list(tmp_path.iterdir())
    result = WdvQuickViewService().parse(
        filename='sample.las',
        content=Path(__file__).with_name('fixture.las').read_bytes(),
    )
    assert result.source_format == 'LAS'
    assert result.depth_min < result.depth_max
    assert sum(len(t.curves) for t in result.tracks) == 4
    assert all(len(t.curves) == 1 for t in result.tracks)
    assert list(tmp_path.iterdir()) == before




def test_las_single_letter_f_depth_unit_resolves_to_feet():
    transform = _depth_transform_from_unit('F')
    assert transform.resolved is True
    assert transform.unit_label == 'ft'
    assert transform.apply(8660.0) == pytest.approx(8660.0)


def test_las_fixture_depth_unit_f_is_reported_as_feet_for_display_toggle():
    result = WdvQuickViewService().parse(
        filename='fixture.las',
        content=Path(__file__).with_name('fixture.las').read_bytes(),
    )
    assert result.depth_unit_label == 'ft'
    assert not any('index unit unresolved' in warning for warning in result.warnings)
    assert result.depth_min == pytest.approx(8660.0)
    assert result.depth_max == pytest.approx(8906.0)


def test_adaptive_padding_targets_controlled_visual_footprint():
    assert _adaptive_padding_fraction(0.30) == pytest.approx(1.1666666667)
    assert _adaptive_padding_fraction(0.35) == pytest.approx(0.9285714286)
    assert _adaptive_padding_fraction(0.55) == pytest.approx(0.4090909091)


def test_unknown_curve_uses_p10_p90_with_adaptive_footprint_padding():
    _, _, low, high, review, source = _curve_display_contract_legacy6(
        mnemonic='MYST', description='Unknown', unit='ZZZ', values=list(range(1, 101))
    )
    assert source == 'fallback_generic_linear_p10_p90'
    assert low == pytest.approx(-81.5)
    assert high == pytest.approx(182.5)
    assert review is True


def test_tpor_partial_bin_uses_p10_p90_with_adaptive_footprint_not_porosity_family_scale():
    _, direction, low, high, review, source = _curve_display_contract_legacy6(
        mnemonic='TPOR14',
        description='Partial Porosity Bin 14',
        unit='PU',
        values=[0.0, 0.2, 0.5, 1.0, 2.0, 3.0, 4.0, 5.0],
    )
    assert source == 'fallback_unit_domain_porosity_like_linear_p10_p90'
    assert direction == 'normal'
    assert low == pytest.approx(-4.7133333333)
    assert high == pytest.approx(9.1533333333)
    assert review is True


def test_exact_curve_rule_with_usable_units_is_applied(monkeypatch):
    resolved = SimpleNamespace(
        policy={
            'source': 'managed_knowledge_curve_rule',
            'type': 'linear',
            'direction': 'reversed',
        },
        unit_resolution=SimpleNamespace(
            resolved_bounds_usable=True,
            resolved_min=45.0,
            resolved_max=-15.0,
        ),
    )
    monkeypatch.setattr(
        'app.wdv_quick_view.service.ManagedKrFamilyDisplayPolicyResolver.resolve_with_unit_resolution',
        lambda item: resolved,
    )
    scale_type, direction, low, high, review, source = _curve_display_contract_legacy6(
        mnemonic='NPHI', description='Neutron Porosity', unit='PU', values=[8, 12, 18, 24, 31]
    )
    assert (scale_type, direction, low, high) == ('linear', 'reverse', 45.0, -15.0)
    assert source == 'managed_knowledge_curve_rule'
    assert review is False


def test_unusable_exact_unit_resolution_falls_back(monkeypatch):
    resolved = SimpleNamespace(
        policy={'source': 'managed_knowledge_curve_rule', 'type': 'linear', 'direction': 'reversed'},
        unit_resolution=SimpleNamespace(
            resolved_bounds_usable=False,
            resolved_min=None,
            resolved_max=None,
        ),
    )
    monkeypatch.setattr(
        'app.wdv_quick_view.service.ManagedKrFamilyDisplayPolicyResolver.resolve_with_unit_resolution',
        lambda item: resolved,
    )
    _, direction, low, high, review, source = _curve_display_contract_legacy6(
        mnemonic='NPHI', description='Neutron Porosity', unit='VENDOR', values=[8, 12, 18, 24, 31]
    )
    assert source == 'fallback_generic_linear_p10_p90'
    assert direction == 'normal'
    assert low < high
    assert review is True


def test_near_flatline_uses_safe_padded_fallback(monkeypatch):
    monkeypatch.setattr(
        'app.wdv_quick_view.service.ManagedKrFamilyDisplayPolicyResolver.resolve_with_unit_resolution',
        lambda item: SimpleNamespace(
            policy={'source': 'managed_knowledge_curve_rule', 'type': 'linear', 'direction': 'normal'},
            unit_resolution=SimpleNamespace(
                resolved_bounds_usable=True, resolved_min=0.0, resolved_max=200.0
            ),
        ),
    )
    _, _, low, high, review, source = _curve_display_contract_legacy6(
        mnemonic='GR', description='Gamma Ray', unit='GAPI', values=[80.0] * 5
    )
    assert source == 'fallback_unit_domain_gamma_like_linear_p10_p90'
    assert low < 80.0 < high
    assert review is True


def test_unit_domain_resolver_is_unit_based_not_mnemonic_based():
    assert _unit_domain('OHMM') == 'resistivity'
    assert _unit_domain('OHM.M') == 'resistivity'
    assert _unit_domain('PU') == 'porosity_like'
    assert _unit_domain('GAPI') == 'gamma_like'
    assert _unit_domain('IN') == 'length_like'
    assert _unit_domain('mystery') == 'generic'


def test_resistivity_unit_fallback_uses_positive_log_p10_p90_not_negative_linear():
    scale_type, direction, low, high, review, source = _curve_display_contract_legacy6(
        mnemonic='AF10',
        description='Array resistivity channel',
        unit='OHMM',
        values=[0.18, 0.22, 0.35, 0.8, 1.5, 3.0, 8.0, 20.0, 60.0, 150.0],
    )
    assert scale_type == 'logarithmic'
    assert direction == 'normal'
    assert source == 'fallback_unit_domain_resistivity_log_p10_p90'
    assert low > 0
    assert high > low
    assert review is True


def test_resistivity_fallback_ignores_nonpositive_values_for_log_domain():
    scale_type, _, low, high, _, source = _curve_display_contract_legacy6(
        mnemonic='AO20',
        description='Unknown resistivity-like output',
        unit='OHM.M',
        values=[-999.25, 0.0, -1.0, 0.4, 0.7, 1.1, 2.5, 6.0, 12.0],
    )
    assert scale_type == 'logarithmic'
    assert source == 'fallback_unit_domain_resistivity_log_p10_p90'
    assert low > 0
    assert high > low


def test_known_unit_domains_keep_linear_fallback_when_not_exact_identity():
    scale_type, _, _, _, review, source = _curve_display_contract_legacy6(
        mnemonic='ABDC10M',
        description='Unknown diameter-style output',
        unit='IN',
        values=[2.0, 2.1, 2.3, 2.6, 2.8, 3.0],
    )
    assert scale_type == 'linear'
    assert source == 'fallback_unit_domain_length_like_linear_p10_p90'
    assert review is True

def test_common_null_values_are_removed_before_scaling():
    samples = _clean_scalar_samples([1000,1001,1002,1003], [-999,1.0,-999.25,3.0], set())
    assert [s.value for s in samples] == [1.0, 3.0]


def test_declared_fill_value_is_removed():
    samples = _clean_scalar_samples([1000,1001,1002], [12,-32768,15], {-32768})
    assert [s.value for s in samples] == [12.0, 15.0]


def test_fractional_inch_depth_units():
    for unit in ('0.1 in', '.1in', '1/10 in', 'in/10'):
        t = _depth_transform_from_unit(unit)
        assert t.resolved and t.unit_label == 'ft' and t.apply(1200) == 10.0


def test_metric_depth_subunits():
    assert _depth_transform_from_unit('mm').apply(183300) == 183.3
    assert _depth_transform_from_unit('cm').apply(183300) == 1833.0


def test_unresolved_depth_unit_stays_raw():
    t = _depth_transform_from_unit('vendor-depth-ticks')
    assert not t.resolved and t.unit_label is None and t.apply(183300) == 183300


def _curve(mnemonic):
    return QuickViewCurve(
        curve_id=f'curve-{mnemonic}', mnemonic=mnemonic, description=mnemonic,
        unit_label='PU', scale_type='linear', scale_direction='normal',
        scale_min=0.0, scale_max=1.0, review_required=True,
        scale_source='observed_p10_p90',
        samples=(QuickViewSample(depth=1000,value=.2), QuickViewSample(depth=1001,value=.8)),
    )


def test_one_curve_per_track():
    curves = [_curve('A'), _curve('B'), _curve('C')]
    tracks = _group(curves)
    assert len(tracks) == 3
    assert [t.curves[0].mnemonic for t in tracks] == ['A','B','C']


def test_curve_display_contract_returns_catalogue_and_scale_decision_fields(monkeypatch):
    monkeypatch.setattr(
        'app.wdv_quick_view.service.ManagedKrFamilyDisplayPolicyResolver.resolve_with_unit_resolution',
        lambda item: type('Resolved', (), {'policy': None, 'unit_resolution': None})(),
    )
    result = _curve_display_contract(
        mnemonic='UNKNOWN_VENDOR_RES',
        description='Vendor resistivity channel',
        unit='OHMM',
        values=[0.2, 0.5, 1.0, 2.0, 5.0],
    )
    assert len(result) == 8
    scale_type, _, low, high, review, source, catalogue_status, scale_decision = result
    assert scale_type == 'logarithmic'
    assert low > 0
    assert high > low
    assert review is True
    assert source == 'fallback_unit_domain_resistivity_log_p10_p90'
    assert catalogue_status == 'Unit domain'
    assert scale_decision == 'Unit-log fallback'


def test_quick_view_catalogue_exact_precedes_alias():
    from app.wdv_quick_view.service import _quick_view_catalogue_match

    for mnemonic in ('GR', 'SP', 'RHOZ', 'RHOB', 'DTCO', 'DTSM', 'PEFZ', 'AT10', 'AT90', 'NPHI', 'TNPH'):
        match = _quick_view_catalogue_match(mnemonic=mnemonic, description=mnemonic, unit='')
        assert match.status == 'KR exact', mnemonic
        assert match.canonical_curve_id


def test_quick_view_catalogue_alias_after_exact():
    from app.wdv_quick_view.service import _quick_view_catalogue_match

    for mnemonic in ('AF10', 'AF90', 'RXO8', 'NPOR', 'DNPH'):
        match = _quick_view_catalogue_match(mnemonic=mnemonic, description=mnemonic, unit='')
        assert match.status == 'KR alias', mnemonic
        assert match.canonical_curve_id


def test_known_alias_never_reports_generic_fallback(monkeypatch):
    monkeypatch.setattr(
        'app.wdv_quick_view.service.ManagedKrFamilyDisplayPolicyResolver.resolve_with_unit_resolution',
        lambda item: type('Resolved', (), {'policy': None, 'unit_resolution': None})(),
    )
    result = _curve_display_contract(
        mnemonic='NPHI',
        description='Thermal Neutron Porosity',
        unit='PU',
        values=[5.0, 10.0, 20.0, 30.0],
    )
    assert result[6] in {'KR exact', 'KR alias'}
    assert result[7] != 'Generic fallback'
    assert result[7] == 'KR-known fallback'


def test_unknown_non_domain_curve_reports_generic_fallback(monkeypatch):
    monkeypatch.setattr(
        'app.wdv_quick_view.service.ManagedKrFamilyDisplayPolicyResolver.resolve_with_unit_resolution',
        lambda item: type('Resolved', (), {'policy': None, 'unit_resolution': None})(),
    )
    result = _curve_display_contract(
        mnemonic='ZZZ_UNKNOWN',
        description='Vendor arbitrary channel',
        unit='ARB',
        values=[1.0, 2.0, 3.0],
    )
    assert result[6] == 'Unknown'
    assert result[7] == 'Generic fallback'


def test_exact_governed_contract_reports_catalogue_and_scale_decision(monkeypatch):
    from types import SimpleNamespace

    resolved = SimpleNamespace(
        policy={
            'source': 'managed_knowledge_curve_rule',
            'type': 'linear',
            'direction': 'normal',
            'mnemonic': 'GR',
        },
        unit_resolution=SimpleNamespace(
            resolved_bounds_usable=True,
            resolved_min=0.0,
            resolved_max=200.0,
        ),
    )
    monkeypatch.setattr(
        'app.wdv_quick_view.service.ManagedKrFamilyDisplayPolicyResolver.resolve_with_unit_resolution',
        lambda item: resolved,
    )
    result = _curve_display_contract(
        mnemonic='GR',
        description='Gamma Ray',
        unit='GAPI',
        values=[50.0, 80.0, 120.0],
    )
    assert result[5] == 'managed_knowledge_curve_rule'
    assert result[6] == 'KR exact'
    assert result[7] == 'Governed'


def test_quick_view_package_exposes_standardized_metadata_sections():
    result = WdvQuickViewService().parse(
        filename='sample.las',
        content=Path(__file__).with_name('fixture.las').read_bytes(),
    )
    metadata = result.quick_view_metadata
    assert metadata is not None
    assert metadata.file_info.file_type.value == 'LAS'
    assert metadata.well_info.well_name.value is not None
    assert metadata.curve_info.curve_counts.total_curves == 4
    assert metadata.curve_info.curve_counts.renderable_curves == 4
    assert metadata.curve_info.index.source_mnemonic.value is not None
    assert metadata.curve_info.index.start.value < metadata.curve_info.index.stop.value
    assert metadata.early_qaqc.severity in {'ok', 'info', 'warning', 'error'}


def test_las_wrap_mode_is_qaqc_flag_not_file_info():
    result = WdvQuickViewService().parse(
        filename='sample.las',
        content=Path(__file__).with_name('fixture.las').read_bytes(),
    )
    metadata = result.quick_view_metadata
    assert metadata is not None
    codes = {flag.code for flag in metadata.early_qaqc.flags}
    assert 'las_wrap_mode' in codes or 'las_wrap_mode_missing' in codes
    assert not hasattr(metadata.file_info, 'wrap')
