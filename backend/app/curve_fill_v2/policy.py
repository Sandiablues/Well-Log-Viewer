"""Backend-owned governed crossover policy registry.

The registry is deliberately bounded.  Production wiring may source these
records from the Managed Knowledge Repository, but no frontend policy input is
accepted.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class OverlayPolicy:
    uid: str
    revision: str
    primary_families: frozenset[str]
    comparison_families: frozenset[str]
    polarity: str


DENSITY_NEUTRON_V1 = OverlayPolicy(
    uid="density-neutron-overlay-v1",
    revision="approved-2026-07-01",
    primary_families=frozenset({"density", "bulk_density"}),
    comparison_families=frozenset({"neutron_porosity"}),
    polarity="a_right_of_b",
)

GENERIC_VISUAL_CROSSOVER_V1 = OverlayPolicy(
    uid="generic-visual-crossover-v1",
    revision="approved-2026-07-05",
    primary_families=frozenset(),
    comparison_families=frozenset(),
    polarity="a_right_of_b",
)


class CurveFillPolicyError(ValueError):
    pass


class CurveFillPolicyRegistry:
    _policies = {
        (DENSITY_NEUTRON_V1.uid, DENSITY_NEUTRON_V1.revision): DENSITY_NEUTRON_V1,
        (GENERIC_VISUAL_CROSSOVER_V1.uid, GENERIC_VISUAL_CROSSOVER_V1.revision): GENERIC_VISUAL_CROSSOVER_V1,
    }

    @classmethod
    def require(cls, uid: str, revision: str) -> OverlayPolicy:
        try:
            return cls._policies[(uid, revision)]
        except KeyError as exc:
            raise CurveFillPolicyError(
                f"Unapproved or unknown crossover policy: {uid}@{revision}"
            ) from exc
