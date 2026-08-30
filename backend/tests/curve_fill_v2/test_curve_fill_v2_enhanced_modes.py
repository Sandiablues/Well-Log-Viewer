from app.curve_fill_v2.models import CurveFillRule, CurveSeries, CurveTransform, FillStyle
from app.curve_fill_v2.service import CurveFillResolutionService


def series(uid, values):
    return CurveSeries(managed_well_uid='well', managed_curve_uid=uid, sample_revision='1', depth_unit='m', samples=tuple((1000.0+i, float(v)) for i,v in enumerate(values)))

def transform(uid, reverse=False):
    return CurveTransform(assignment_uid=f'a-{uid}', managed_curve_uid=uid, transform_revision='1', track_width_px=180, scale_min=100.0 if reverse else 0.0, scale_max=0.0 if reverse else 100.0)

STYLE=FillStyle(color='#112233', opacity=.5)


def test_value_band_resolves_fixed_band_and_reversal():
    a=series('a',[0,50,100])
    r=CurveFillRule(rule_uid='r',managed_well_uid='well',track_uid='t',order=0,rule_type='value_band',curve_a_uid='a',band_min_value=0,band_max_value=50,style=STYLE)
    g=CurveFillResolutionService().resolve(rule=r,series_a=a,transform_a=transform('a', True))
    assert len(g.polygons)==1
    assert all(v.x_a_px != v.x_b_px for v in g.polygons[0].vertices)


def test_curve_to_value_uses_reference_x():
    a=series('a',[0,50,100])
    r=CurveFillRule(rule_uid='r',managed_well_uid='well',track_uid='t',order=0,rule_type='curve_to_value',curve_a_uid='a',reference_value=50,style=STYLE)
    g=CurveFillResolutionService().resolve(rule=r,series_a=a,transform_a=transform('a'))
    assert len(g.polygons)==1


def test_threshold_only_fills_matching_side():
    a=series('a',[0,50,100])
    r=CurveFillRule(rule_uid='r',managed_well_uid='well',track_uid='t',order=0,rule_type='threshold',curve_a_uid='a',reference_value=50,comparison='greater_than',style=STYLE)
    g=CurveFillResolutionService().resolve(rule=r,series_a=a,transform_a=transform('a'))
    assert len(g.polygons)==1
    assert g.polygons[0].top_depth == 1001.0


def test_curve_envelope_uses_rendered_extremes():
    a,b=series('a',[0,50,100]),series('b',[100,50,0])
    r=CurveFillRule(rule_uid='r',managed_well_uid='well',track_uid='t',order=0,rule_type='curve_envelope',curve_a_uid='a',curve_operand_uids=('a','b'),style=STYLE)
    g=CurveFillResolutionService().resolve(rule=r,series_a=a,transform_a=transform('a'),envelope_series=(a,b),envelope_transforms=(transform('a'),transform('b')))
    assert len(g.polygons)==1
    assert all(v.x_a_px <= v.x_b_px for v in g.polygons[0].vertices)


def test_separation_uses_rendered_pixel_threshold():
    a,b=series('a',[0,50,100]),series('b',[100,50,0])
    r=CurveFillRule(rule_uid='r',managed_well_uid='well',track_uid='t',order=0,rule_type='separation',curve_a_uid='a',curve_b_uid='b',minimum_separation_px=20,separation_mode='absolute',style=STYLE)
    g=CurveFillResolutionService().resolve(rule=r,series_a=a,transform_a=transform('a'),series_b=b,transform_b=transform('b'))
    assert len(g.polygons)==2
