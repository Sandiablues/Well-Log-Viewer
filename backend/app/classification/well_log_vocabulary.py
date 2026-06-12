"""Canonical well-log classification vocabulary.

This module is deliberately backend-owned and frontend-agnostic.  The WMDP
renders groups supplied by the inventory service; it must not infer these
categories from mnemonics locally.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProductGroupDefinition:
    group_key: str
    group_label: str



@dataclass(frozen=True)
class ProductSubgroupDefinition:
    subgroup_key: str
    subgroup_label: str


OPEN_HOLE_SUBGROUP_ORDER: tuple[ProductSubgroupDefinition, ...] = (
    ProductSubgroupDefinition("gamma_ray", "Gamma Ray"),
    ProductSubgroupDefinition("resistivity", "Resistivity"),
    ProductSubgroupDefinition("sonic_acoustic", "Sonic / Acoustic"),
    ProductSubgroupDefinition("density_neutron_porosity", "Density / Neutron / Porosity"),
    ProductSubgroupDefinition("nmr", "NMR"),
    ProductSubgroupDefinition("borehole_geometry_imaging", "Borehole Geometry / Imaging"),
    ProductSubgroupDefinition("sp_electrochemical", "SP / Electrochemical"),
    ProductSubgroupDefinition("dip_directional", "Dip / Directional"),
    ProductSubgroupDefinition("formation_pressure_sampling", "Formation Pressure / Sampling"),
    ProductSubgroupDefinition("petrophysical_interpretation", "Petrophysical Interpretation"),
    ProductSubgroupDefinition("other_open_hole_review", "Other Open-hole / Review"),
)

OPEN_HOLE_SUBGROUP_LABELS: dict[str, str] = {
    definition.subgroup_key: definition.subgroup_label
    for definition in OPEN_HOLE_SUBGROUP_ORDER
}

OPEN_HOLE_FAMILY_TO_SUBGROUP: dict[str, str] = {
    "gamma ray": "gamma_ray",
    "computed gamma ray": "gamma_ray",
    "spectral gamma ray": "gamma_ray",
    "resistivity": "resistivity",
    "density": "density_neutron_porosity",
    "density correction": "density_neutron_porosity",
    "neutron porosity": "density_neutron_porosity",
    "photoelectric factor": "density_neutron_porosity",
    "sonic": "sonic_acoustic",
    "sonic compressional": "sonic_acoustic",
    "sonic shear": "sonic_acoustic",
    "acoustic": "sonic_acoustic",
    "array acoustic": "sonic_acoustic",
    "nmr": "nmr",
    "caliper": "borehole_geometry_imaging",
    "hole diameter": "borehole_geometry_imaging",
    "borehole image": "borehole_geometry_imaging",
    "spontaneous potential": "sp_electrochemical",
    "dipmeter": "dip_directional",
    "directional": "dip_directional",
    "formation pressure": "formation_pressure_sampling",
    "formation tester": "formation_pressure_sampling",
    "formation sampling": "formation_pressure_sampling",
    "petrophysical interpretation": "petrophysical_interpretation",
}


def open_hole_subgroup_for_family(curve_family: str | None) -> ProductSubgroupDefinition:
    family_key = (curve_family or "").strip().lower()
    subgroup_key = OPEN_HOLE_FAMILY_TO_SUBGROUP.get(family_key, "other_open_hole_review")
    return ProductSubgroupDefinition(
        subgroup_key=subgroup_key,
        subgroup_label=OPEN_HOLE_SUBGROUP_LABELS[subgroup_key],
    )

PRODUCT_GROUP_ORDER: tuple[ProductGroupDefinition, ...] = (
    ProductGroupDefinition("open_hole_logs", "Open hole logs"),
    ProductGroupDefinition("cased_hole_logs", "Cased hole logs"),
    ProductGroupDefinition("rasters_images", "Rasters / Images"),
    ProductGroupDefinition("lithology_core_markers", "Lithology / Core / Markers"),
    ProductGroupDefinition("pressure_production_fluid_data", "Pressure / Production / Fluid data"),
    ProductGroupDefinition("completion_integrity_data", "Completion / Integrity data"),
    ProductGroupDefinition("supporting_documents", "Supporting documents"),
    ProductGroupDefinition("other_review_required", "Other / Review required"),
)

PRODUCT_GROUP_KEYS: set[str] = {definition.group_key for definition in PRODUCT_GROUP_ORDER}

# Mnemonic aliases are intentionally deterministic and conservative.  Context
# terms can override ambiguous curves such as GR.
OPEN_HOLE_CURVE_FAMILIES: dict[str, tuple[str, str]] = {
    "GR": ("Gamma Ray", "Gamma Ray"),
    "CGR": ("Gamma Ray", "Computed Gamma Ray"),
    "SGR": ("Spectral Gamma Ray", "Spectral Gamma Ray"),
    "SP": ("Spontaneous Potential", "Spontaneous Potential"),
    "AF90": ("Resistivity", "Array Resistivity 90 in"),
    "AT90": ("Resistivity", "Array Resistivity 90 in"),
    "AT60": ("Resistivity", "Array Resistivity 60 in"),
    "AT30": ("Resistivity", "Array Resistivity 30 in"),
    "AT10": ("Resistivity", "Array Resistivity 10 in"),
    "ILD": ("Resistivity", "Deep Induction Resistivity"),
    "ILM": ("Resistivity", "Medium Induction Resistivity"),
    "LLD": ("Resistivity", "Deep Laterolog Resistivity"),
    "LLS": ("Resistivity", "Shallow Laterolog Resistivity"),
    "RT": ("Resistivity", "True Formation Resistivity"),
    "RXO": ("Resistivity", "Flushed-Zone Resistivity"),
    "RHOB": ("Density", "Bulk Density"),
    "RHOZ": ("Density", "Bulk Density"),
    "DEN": ("Density", "Density"),
    "DRHO": ("Density Correction", "Density Correction"),
    "NPHI": ("Neutron Porosity", "Neutron Porosity"),
    "TNPH": ("Neutron Porosity", "Thermal Neutron Porosity"),
    "NPOR": ("Neutron Porosity", "Neutron Porosity"),
    "DT": ("Sonic", "Compressional Slowness"),
    "DTC": ("Sonic Compressional", "Delta-T Compressional"),
    "DTCO": ("Sonic Compressional", "Delta-T Compressional"),
    "DTS": ("Sonic Shear", "Delta-T Shear"),
    "DTSM": ("Sonic Shear", "Delta-T Shear"),
    "CALI": ("Caliper", "Caliper"),
    "CAL": ("Caliper", "Caliper"),
    "HCAL": ("Caliper", "Hole Caliper"),
    "PEF": ("Photoelectric Factor", "Photoelectric Factor"),
    "PE": ("Photoelectric Factor", "Photoelectric Factor"),
    "TCMR": ("NMR", "NMR Total Porosity"),
    "BVI": ("NMR", "Bound Volume Irreducible"),
    "FFI": ("NMR", "Free Fluid Index"),
}

CASED_HOLE_CURVE_FAMILIES: dict[str, tuple[str, str]] = {
    "CCL": ("Completion / Depth Correlation", "Casing Collar Locator"),
    "CBL": ("Cement Evaluation", "Cement Bond Log"),
    "VDL": ("Cement Evaluation", "Variable Density Log"),
    "SBT": ("Cement Evaluation", "Segmented Bond Tool"),
    "RBT": ("Cement Evaluation", "Radial Bond Tool"),
    "USIT": ("Cement Evaluation", "Ultrasonic Imager Tool"),
    "SIGMA": ("Pulsed Neutron", "Neutron Capture Sigma"),
    "C/O": ("Pulsed Neutron", "Carbon Oxygen Ratio"),
    "RST": ("Pulsed Neutron", "Reservoir Saturation Tool"),
    "TEMP": ("Production Logging", "Temperature"),
    "PRES": ("Production Logging", "Pressure"),
    "PRESS": ("Production Logging", "Pressure"),
    "FLOW": ("Production Logging", "Flow Rate"),
    "SPIN": ("Production Logging", "Spinner Flowmeter"),
    "RPM": ("Production Logging", "Spinner Speed"),
    "CWH": ("Production Logging", "Capacitance Water Holdup"),
    "FDEN": ("Production Logging", "Fluid Density"),
    "MIT": ("Casing Inspection", "Multi-Finger Imaging Tool"),
    "MFC": ("Casing Inspection", "Multi-Finger Caliper"),
    "MTT": ("Casing Inspection", "Magnetic Thickness Tool"),
    "EMIT": ("Casing Inspection", "Electromagnetic Inspection Tool"),
}

LITHOLOGY_CORE_MARKER_FAMILIES: dict[str, tuple[str, str]] = {
    "TOP": ("Formation Marker", "Formation Top"),
    "TOPS": ("Formation Marker", "Formation Tops"),
    "MARKER": ("Formation Marker", "Marker"),
    "LITH": ("Lithology", "Lithology"),
    "FACIES": ("Lithology", "Facies"),
    "CORE": ("Core", "Core Data"),
}

PRESSURE_PRODUCTION_FLUID_FAMILIES: dict[str, tuple[str, str]] = {
    "MDT_P": ("Formation Pressure", "Formation Pressure"),
    "RFT_P": ("Formation Pressure", "Formation Pressure"),
    "FPRESS": ("Formation Pressure", "Formation Pressure"),
    "MOB": ("Formation Tester", "Mobility"),
    "GOR": ("Fluid Analysis", "Gas Oil Ratio"),
    "OIL": ("Fluid Analysis", "Oil Indicator"),
    "GAS": ("Fluid Analysis", "Gas Indicator"),
    "WATER": ("Fluid Analysis", "Water Indicator"),
}

COMPLETION_INTEGRITY_FAMILIES: dict[str, tuple[str, str]] = {
    "PERF": ("Completion", "Perforation"),
    "PACKER": ("Completion", "Packer"),
    "PKR": ("Completion", "Packer"),
    "PLUG": ("Completion", "Plug"),
    "CASING": ("Completion", "Casing"),
    "TUBING": ("Completion", "Tubing"),
}

OPEN_HOLE_CONTEXT_TERMS: tuple[str, ...] = (
    "open hole",
    "openhole",
    "oh log",
    "formation evaluation",
    "wireline openhole",
)

CASED_HOLE_CONTEXT_TERMS: tuple[str, ...] = (
    "cased hole",
    "cased-hole",
    "production log",
    "plt",
    "cement",
    "casing",
    "tubing",
    "completion",
    "perforation",
)
