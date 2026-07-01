"""Approved bootstrap Curve Fill policies owned by the Knowledge Repository.

These immutable seed policies provide production defaults until equivalent
managed records supersede them through the governed KR lifecycle.
"""
from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class CurveFillPolicySeed:
    preset_id: str
    revision: str
    label: str
    fill_mode: str
    operand_a_aliases: frozenset[str]
    operand_b_aliases: frozenset[str]
    default_condition: str | None
    overlay_policy_id: str | None
    default_fill: str
    default_opacity: float
    deadband: float | None = None
    minimum_interval: float | None = None

APPROVED_CURVE_FILL_POLICY_SEEDS = (
    CurveFillPolicySeed("deep-over-shallow-resistivity","1","Deep-over-Shallow Resistivity","conditional",frozenset({"RDEEP","RT","ILD","LLD","AT90","RLA5","RLA4"}),frozenset({"RSHALLOW","RXO","ILM","LLS","AT10","RLA1","RLA2"}),"a_greater_than_b",None,"#d8b85a",0.55),
    CurveFillPolicySeed("caliper-greater-than-bit-size","1","Caliper Greater Than Bit Size","conditional",frozenset({"CALI","HCAL","CAL","C1","C2"}),frozenset({"BIT","BS","BITSIZE","BIT_SIZE"}),"a_greater_than_b",None,"#c79a63",0.50),
    CurveFillPolicySeed("density-neutron-crossover","1","Density–Neutron Crossover","crossover",frozenset({"RHOB","RHOZ","DEN","ZDEN"}),frozenset({"NPHI","TNPH","NPOR","PHIN"}),None,"density-neutron-overlay-v1","#f0cf4c",0.55,0.005),
)
