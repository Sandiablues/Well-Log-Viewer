"""
WLV seed repository.

This repository provides a deterministic backend-owned seed contract for the
current Fallon Forge 21-31 prototype data. It is deliberately small and local:
future blocks can replace this with a JSON/SQLite/Postgres implementation while
keeping the API contract stable.
"""

from __future__ import annotations

from typing import Iterable

from .models import (
    Curve,
    CurveScale,
    DepthRange,
    DepthUnit,
    IntervalColumn,
    IntervalColumnType,
    IntervalRecord,
    ScaleType,
    Track,
    TrackType,
    WellDetail,
    WellMultitrackV1,
    WellSummary,
    LogFile,
)


class WellNotFoundError(KeyError):
    """Raised when a requested well id is not present in the repository."""


class SeedWellRepository:
    """
    Backend-owned seed repository for WLV-BE-001.

    The repository is intentionally deterministic and read-only. It gives the
    backend real API responses without turning frontend prototype constants into
    a permanent source of truth.
    """

    WELL_ID = "forge-21-31"
    WELLBORE_ID = "forge-21-31-main"
    DATASET_ID = "seed-dataset-forge-21-31"
    REPRESENTATION_ID = "seed-representation-forge-21-31-las"

    def list_wells(self) -> list[WellSummary]:
        detail = self.get_well(self.WELL_ID)
        return [
            WellSummary(
                well_id=detail.well_id,
                well_name=detail.well_name,
                field=detail.field,
                operator=detail.operator,
                country=detail.country,
                depth_range=detail.depth_range,
                depth_unit=detail.depth_unit,
                curve_count=len(self.list_curves(detail.well_id)),
                interval_column_count=len(self.list_interval_columns(detail.well_id)),
            )
        ]

    def get_well(self, well_id: str) -> WellDetail:
        self._require_seed_well(well_id)
        depth_range = DepthRange(min=300.5, max=6076.0)
        log_file = LogFile(
            log_file_id="forge-21-31-triple-combo-las",
            filename="DWM5-00038_Ormat Nevada_Forge 21-31_Pr_Composite1_Main_-GenericV12.las",
            file_type="LAS",
            service_company="Schlumberger",
            run_number="ONE",
            depth_range=depth_range,
            depth_unit=DepthUnit.FEET,
        )
        return WellDetail(
            well_id=self.WELL_ID,
            well_name="Forge 21-31",
            wellbore_id=self.WELLBORE_ID,
            wellbore_name="Main Bore",
            field="Carson Field",
            operator="Ormat Nevada, Inc.",
            country="USA",
            state="Nevada",
            county="Churchill",
            api_number="2700190539",
            latitude="39.386616 degrees",
            longitude="-118.66657 degrees",
            datum="GL",
            kb_elevation="3949.99976 ft",
            ground_elevation="3928.00000 ft",
            source_file=log_file.filename,
            depth_range=depth_range,
            depth_unit=DepthUnit.FEET,
            curve_count=len(self._seed_curve_specs()),
            interval_column_count=len(self.list_interval_columns(self.WELL_ID)),
            log_files=[log_file],
        )

    def list_curves(self, well_id: str) -> list[Curve]:
        self._require_seed_well(well_id)
        return [self._curve_from_spec(spec) for spec in self._seed_curve_specs()]

    def list_interval_columns(self, well_id: str) -> list[IntervalColumn]:
        self._require_seed_well(well_id)
        return [
            IntervalColumn(
                column_id="lithology-forge-21-31",
                name="Lithology",
                column_type=IntervalColumnType.LITHOLOGY,
                depth_unit=DepthUnit.FEET,
                intervals=[
                    IntervalRecord(interval_id="lith-5300-5480", top_md=5300.0, base_md=5480.0, code="VOLC", label="Volcanic / altered volcanic", color="#8b5cf6", pattern_id="crosshatch", source="FORGE_Well_Lith_Logs_2018 seed", confidence=0.8),
                    IntervalRecord(interval_id="lith-5480-5740", top_md=5480.0, base_md=5740.0, code="TUFF", label="Tuff / volcaniclastic", color="#f59e0b", pattern_id="dots", source="FORGE_Well_Lith_Logs_2018 seed", confidence=0.8),
                    IntervalRecord(interval_id="lith-5740-6076", top_md=5740.0, base_md=6076.0, code="GRAN", label="Granitoid / intrusive", color="#94a3b8", pattern_id="diagonal-hatch", source="FORGE_Well_Lith_Logs_2018 seed", confidence=0.8),
                ],
            ),
            IntervalColumn(column_id="biostrat-placeholder-forge-21-31", name="Biostratigraphy", column_type=IntervalColumnType.BIOSTRATIGRAPHY, depth_unit=DepthUnit.FEET, intervals=[]),
            IntervalColumn(column_id="formation-placeholder-forge-21-31", name="Formation / Stratigraphy", column_type=IntervalColumnType.FORMATION, depth_unit=DepthUnit.FEET, intervals=[]),
            IntervalColumn(column_id="facies-placeholder-forge-21-31", name="Facies", column_type=IntervalColumnType.FACIES, depth_unit=DepthUnit.FEET, intervals=[]),
        ]

    def get_viewer_package(self, well_id: str) -> WellMultitrackV1:
        detail = self.get_well(well_id)
        curves_by_track = self._tracks_for_seed_curves(self.list_curves(well_id))
        tracks = [Track(track_id="depth", track_type=TrackType.DEPTH, title="Depth", curves=[]), *curves_by_track]
        return WellMultitrackV1(
            viewer_package_version="well_multitrack_v1",
            dataset_id=self.DATASET_ID,
            representation_id=self.REPRESENTATION_ID,
            well_id=detail.well_id,
            wellbore_id=detail.wellbore_id,
            depth_unit=DepthUnit.FEET,
            depth_range=detail.depth_range,
            tracks=tracks,
            qaqc_findings=[],
        )

    def _require_seed_well(self, well_id: str) -> None:
        if well_id != self.WELL_ID:
            raise WellNotFoundError(well_id)

    def _curve_from_spec(self, spec: dict[str, object]) -> Curve:
        scale_type = ScaleType.LOG if spec["scale_type"] == "log" else ScaleType.LINEAR
        return Curve(
            curve_id=str(spec["curve_id"]),
            mnemonic=str(spec["mnemonic"]),
            normalized_name=str(spec.get("normalized_name") or spec["mnemonic"]),
            unit=str(spec.get("unit") or ""),
            samples_url=f"/api/wlv/wells/{self.WELL_ID}/curves/{spec['curve_id']}/samples",
            scale=CurveScale(type=scale_type, min=float(spec["min"]), max=float(spec["max"])),
        )

    def _tracks_for_seed_curves(self, curves: Iterable[Curve]) -> list[Track]:
        curves_by_id = {curve.curve_id: curve for curve in curves}
        return [
            Track(track_id="track-gr-sp", title="GR / SP", curves=[curves_by_id["GR"], curves_by_id["SP"]]),
            Track(track_id="track-resistivity", title="Resistivity", curves=[curves_by_id["AF90"], curves_by_id["AT90"]]),
            Track(track_id="track-density-neutron", title="Density / Neutron", curves=[curves_by_id["RHOB"], curves_by_id["NPHI"]]),
            Track(track_id="track-sonic", title="Sonic", curves=[curves_by_id["DTCO"], curves_by_id["DTSM"]]),
            Track(track_id="track-caliper", title="Caliper / PEF", curves=[curves_by_id["CALI"], curves_by_id["PEF"]]),
        ]

    def _seed_curve_specs(self) -> list[dict[str, object]]:
        return [
            {"curve_id": "GR", "mnemonic": "GR", "unit": "GAPI", "scale_type": "linear", "min": 0.0, "max": 150.0},
            {"curve_id": "SP", "mnemonic": "SP", "unit": "MV", "scale_type": "linear", "min": -120.0, "max": 80.0},
            {"curve_id": "AF90", "mnemonic": "AF90", "unit": "OHMM", "scale_type": "log", "min": 0.443, "max": 1950.0},
            {"curve_id": "AT90", "mnemonic": "AT90", "unit": "OHMM", "scale_type": "log", "min": 0.3638, "max": 1950.0},
            {"curve_id": "RHOB", "mnemonic": "RHOB", "unit": "G/C3", "scale_type": "linear", "min": 1.95, "max": 2.95},
            {"curve_id": "NPHI", "mnemonic": "NPHI", "unit": "V/V", "scale_type": "linear", "min": -0.15, "max": 0.45},
            {"curve_id": "DTCO", "mnemonic": "DTCO", "unit": "US/F", "scale_type": "linear", "min": 40.0, "max": 140.0},
            {"curve_id": "DTSM", "mnemonic": "DTSM", "unit": "US/F", "scale_type": "linear", "min": 80.0, "max": 240.0},
            {"curve_id": "CALI", "mnemonic": "CALI", "unit": "IN", "scale_type": "linear", "min": 6.0, "max": 16.0},
            {"curve_id": "PEF", "mnemonic": "PEF", "unit": "B/E", "scale_type": "linear", "min": 0.0, "max": 10.0},
        ]
