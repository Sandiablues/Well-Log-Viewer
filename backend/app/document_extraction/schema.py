from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class FieldRule:
    key: str
    output_label: str
    aliases: tuple[str, ...]
    value_kind: str = "text"
    required_context: tuple[str, ...] = ()
    rejected_context: tuple[str, ...] = ()
    coordinate_context: str | None = None
    auto_accept: bool = True


FIELD_RULES: tuple[FieldRule, ...] = (
    FieldRule("well_name", "Well name", ("well name", "well", "well no", "well number", "well id"), "well_id"),
    FieldRule("wellbore_name", "Wellbore name", ("wellbore name", "wellbore", "well bore", "borehole", "borehole name"), "identifier"),
    FieldRule("uwi", "UWI", ("uwi", "unique well identifier", "api number", "api no"), "identifier"),
    FieldRule("field", "Field name", ("field name", "field"), "text"),
    FieldRule("site", "Site name", ("site name", "site", "platform", "installation"), "text"),
    FieldRule("block", "Block", ("block", "license block", "licence block"), "text"),
    FieldRule("operator", "Operator name", ("operator name", "operator", "company", "operating company"), "organization"),
    FieldRule("country", "Country", ("country",), "country"),
    FieldRule("well_status", "Final well status", ("final well status", "well status", "status", "completion status", "abandonment status"), "status"),
    FieldRule("latitude", "Wellhead latitude", ("wellhead latitude", "surface latitude", "latitude"), "latitude", coordinate_context="wellhead"),
    FieldRule("longitude", "Wellhead longitude", ("wellhead longitude", "surface longitude", "longitude"), "longitude", coordinate_context="wellhead"),
    FieldRule("northing", "Wellhead northing", ("wellhead northing", "surface northing", "northing"), "northing", coordinate_context="wellhead"),
    FieldRule("easting", "Wellhead easting", ("wellhead easting", "surface easting", "easting"), "easting", coordinate_context="wellhead"),
    FieldRule("coordinate_system", "Map system", ("coordinate system", "map system", "projection", "projected coordinate system"), "text"),
    FieldRule("utm_zone", "UTM zone", ("utm zone", "map zone", "zone"), "utm_zone", required_context=("utm", "transverse mercator", "map zone")),
    FieldRule("geodetic_datum", "Geodetic datum", ("geodetic datum", "geo datum", "datum"), "text"),
    FieldRule("epsg_code", "EPSG code", ("epsg code", "epsg"), "epsg"),
    FieldRule("north_reference", "North reference", ("north reference", "north ref"), "north_reference"),
    FieldRule("grid_convergence", "Grid convergence", ("grid convergence", "grid convergance", "convergence"), "angle"),
    FieldRule("depth_unit", "Depth unit", ("depth unit", "depth units", "unit of depth"), "depth_unit"),
    FieldRule("data_start_md", "Data start MD", ("data start md", "log start md", "curve start md"), "depth"),
    FieldRule("data_end_md", "Data end MD", ("data end md", "log end md", "curve end md"), "depth"),
    FieldRule("depth_reference", "Depth reference", ("depth reference", "md reference", "tvd reference", "measured depth reference", "rotary table", "kelly bushing", "rkb"), "reference"),
    FieldRule("reference_elevation", "Reference elevation", ("reference elevation", "rt to msl", "kb to msl", "rkb to msl", "rotary table elevation", "kelly bushing elevation"), "elevation"),
    FieldRule("surface_seabed_elevation", "Surface/seabed elevation", ("surface elevation", "ground elevation", "seabed elevation", "mudline elevation", "msl to seabed"), "elevation"),
    FieldRule("water_depth", "Water depth", ("water depth", "sea depth"), "depth"),
    FieldRule("seabed_depth_below_reference", "Seabed depth below reference", ("rt to seabed", "kb to seabed", "reference to seabed"), "depth"),
    FieldRule("wellhead_depth_below_reference", "Wellhead depth below reference", ("wellhead depth", "top of wellhead", "rt to wellhead", "kb to wellhead"), "depth"),
    FieldRule("trajectory_source", "Trajectory source", ("trajectory source", "survey source", "directional survey source"), "text"),
    FieldRule("survey_status", "Survey status", ("survey status", "phase"), "status"),
    FieldRule("survey_type", "Survey type", ("survey type", "survey tool", "survey instrument"), "text"),
    FieldRule("calculation_method", "Survey calculation method", ("survey calculation method", "calculation method", "survey method"), "method"),
    FieldRule("station_count", "Station count", ("station count", "survey station count", "number of stations"), "integer"),
    FieldRule("survey_start_md", "Survey start MD", ("survey start md", "first survey md", "first md"), "depth"),
    FieldRule("survey_start_tvd", "Survey start TVD", ("survey start tvd", "first survey tvd"), "depth"),
    FieldRule("survey_end_md", "Survey end MD", ("survey end md", "final survey md"), "depth"),
    FieldRule("total_depth_md", "Total depth MD", ("total measured", "total measured depth", "total depth md", "td md"), "depth"),
    FieldRule("survey_end_tvd", "Survey end TVD", ("survey end tvd", "final survey tvd"), "depth"),
    FieldRule("total_depth_tvd", "Total depth TVD", ("total vertical depth", "total depth tvd", "td tvd"), "depth"),
    FieldRule("maximum_inclination", "Maximum inclination", ("maximum inclination", "max inclination", "maximum inc", "max inc"), "angle"),
    FieldRule("final_north_offset", "Final north offset", ("final north offset", "final northing offset", "final north south offset"), "offset"),
    FieldRule("final_east_offset", "Final east offset", ("final east offset", "final easting offset", "final east west offset"), "offset"),
)

RULE_BY_KEY = {rule.key: rule for rule in FIELD_RULES}
