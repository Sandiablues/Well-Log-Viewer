from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.inventory.models import CanonicalUuid7

WbvLayoutTrackType = Literal[
    "curve",
    "depth",
    "formation_tops",
    "lithology",
    "core",
    "casing_hole",
    "completions",
    "borehole_imagery",
]
WbvTrackPosition = Literal["right", "left", "center"]
WbvTrackBackgroundMode = Literal["transparent", "solid"]
WbvTrackGridMode = Literal["off", "linear", "logarithmic"]
WbvDepthType = Literal["MD", "TVD", "TVDSS"]


class WbvLayoutTrack(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    track_uid: CanonicalUuid7
    display_name: str = Field(min_length=1, max_length=80)
    track_type: WbvLayoutTrackType = "curve"
    display_order: int = Field(ge=0)
    visible: bool = True
    position: WbvTrackPosition = "right"
    angular_position_deg: float = Field(default=0.0, ge=-360.0, le=360.0)
    distance_from_wellbore: float = Field(default=0.15, ge=0.0, le=20.0)
    previous_track_gap: float = Field(default=0.05, ge=0.0, le=20.0)
    width: float = Field(default=1.0, ge=0.1, le=20.0)
    opacity: float = Field(default=1.0, ge=0.0, le=1.0)
    background_mode: WbvTrackBackgroundMode = "transparent"
    background_color: str = "#000000"
    outline_visible: bool = True
    grid_mode: WbvTrackGridMode = "off"
    # WLV-WBV-DEPTH-TRACK-STAGE1
    depth_type: WbvDepthType = "MD"
    depth_increment: float = Field(default=100.0, gt=0.0)
    label_increment: float = Field(default=500.0, gt=0.0)
    label_size: float = Field(default=1.0, gt=0.0)
    show_depth_units: bool = True


class WbvTrackLayout(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    contract_version: Literal["wbv_track_layout_v1"] = "wbv_track_layout_v1"
    managed_well_uid: CanonicalUuid7
    revision: int = Field(default=1, ge=1)
    tracks: tuple[WbvLayoutTrack, ...] = ()

    @model_validator(mode="after")
    def validate_tracks(self):
        if len({track.track_uid for track in self.tracks}) != len(self.tracks):
            raise ValueError("Duplicate WBV layout track UID")
        if [track.display_order for track in self.tracks] != list(range(len(self.tracks))):
            raise ValueError("WBV layout track order must be contiguous")
        return self


class WbvLayoutCommandRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=1)
    command: Literal[
        "add_track",
        "update_track",
        "delete_track",
        "duplicate_track",
        "move_up",
        "move_down",
    ]
    track_uid: CanonicalUuid7 | None = None
    display_name: str | None = Field(default=None, min_length=1, max_length=80)
    track_type: WbvLayoutTrackType | None = None
    position: WbvTrackPosition | None = None
    distance_from_wellbore: float | None = Field(default=None, ge=0.0, le=20.0)
    previous_track_gap: float | None = Field(default=None, ge=0.0, le=20.0)
    width: float | None = Field(default=None, ge=0.1, le=20.0)
    opacity: float | None = Field(default=None, ge=0.0, le=1.0)
    background_mode: WbvTrackBackgroundMode | None = None
    background_color: str | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")
    outline_visible: bool | None = None
    grid_mode: WbvTrackGridMode | None = None
    visible: bool | None = None
    depth_type: WbvDepthType | None = None
    depth_increment: float | None = Field(default=None, gt=0.0)
    label_increment: float | None = Field(default=None, gt=0.0)
    label_size: float | None = Field(default=None, gt=0.0)
    show_depth_units: bool | None = None
