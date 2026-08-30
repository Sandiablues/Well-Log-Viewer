from __future__ import annotations

from app.identity import new_uuid7_str, parse_uuid7

from .models import WbvLayoutCommandRequest, WbvLayoutTrack, WbvTrackLayout
from .repository import WbvTrackLayoutRepository

ANGLES = {"right": 0.0, "center": 90.0, "left": 180.0}


class WbvTrackLayoutService:
    def __init__(self, repository=None):
        self.repository = repository or WbvTrackLayoutRepository()

    def get_layout(self, well_uid: str):
        uid = str(parse_uuid7(well_uid))
        found = self.repository.get(uid)
        return found or self.repository.save(
            WbvTrackLayout(managed_well_uid=uid, revision=1, tracks=()),
            None,
        )

    def ensure_curve_capacity(self, well_uid: str, count: int):
        layout = self.get_layout(well_uid)
        tracks = list(layout.tracks)
        curves = [track for track in tracks if track.track_type == "curve"]
        while len(curves) < count:
            number = len(curves) + 1
            position = "right" if number % 2 == 1 else "left"
            track = WbvLayoutTrack(
                track_uid=new_uuid7_str(),
                display_name=f"Track {number}",
                track_type="curve",
                display_order=len(tracks),
                position=position,
                angular_position_deg=ANGLES[position],
            )
            tracks.append(track)
            curves.append(track)
        if tuple(tracks) == layout.tracks:
            return layout
        return self.repository.save(
            layout.model_copy(
                update={"revision": layout.revision + 1, "tracks": tuple(tracks)}
            ),
            layout.revision,
        )

    def command(self, well_uid: str, request: WbvLayoutCommandRequest):
        layout = self.get_layout(well_uid)
        if layout.revision != request.expected_revision:
            raise ValueError(
                f"Stale layout revision: expected {request.expected_revision}, current {layout.revision}"
            )
        tracks = list(layout.tracks)

        def selected_index():
            if not request.track_uid:
                raise ValueError("track_uid is required")
            for index, track in enumerate(tracks):
                if track.track_uid == request.track_uid:
                    return index
            raise ValueError("WBV layout track not found")

        if request.command == "add_track":
            track_type = request.track_type or "curve"
            position = request.position or "right"
            if track_type == "curve":
                curve_number = sum(track.track_type == "curve" for track in tracks) + 1
                default_name = f"Track {curve_number}"
            elif track_type == "depth":
                depth_number = sum(track.track_type == "depth" for track in tracks) + 1
                default_name = "Depth" if depth_number == 1 else f"Depth {depth_number}"
            else:
                default_name = track_type.replace("_", " ").title()
            tracks.append(
                WbvLayoutTrack(
                    track_uid=new_uuid7_str(),
                    display_name=request.display_name or default_name,
                    track_type=track_type,
                    display_order=len(tracks),
                    position=position,
                    angular_position_deg=ANGLES[position],
                )
            )
        elif request.command == "delete_track":
            tracks.pop(selected_index())
        elif request.command == "duplicate_track":
            source = tracks[selected_index()]
            tracks.append(
                source.model_copy(
                    update={
                        "track_uid": new_uuid7_str(),
                        "display_name": f"{source.display_name} Copy",
                        "display_order": len(tracks),
                    }
                )
            )
        elif request.command in ("move_up", "move_down"):
            index = selected_index()
            target = index + (-1 if request.command == "move_up" else 1)
            if 0 <= target < len(tracks):
                tracks[index], tracks[target] = tracks[target], tracks[index]
        elif request.command == "update_track":
            index = selected_index()
            source = tracks[index]
            patch = {
                key: value
                for key, value in {
                    "display_name": request.display_name,
                    "track_type": request.track_type,
                    "position": request.position,
                    "distance_from_wellbore": request.distance_from_wellbore,
                    "previous_track_gap": request.previous_track_gap,
                    "width": request.width,
                    "opacity": request.opacity,
                    "background_mode": request.background_mode,
                    "background_color": request.background_color,
                    "outline_visible": request.outline_visible,
                    "grid_mode": request.grid_mode,
                    "visible": request.visible,
                    "depth_type": request.depth_type,
                    "depth_increment": request.depth_increment,
                    "label_increment": request.label_increment,
                    "label_size": request.label_size,
                    "show_depth_units": request.show_depth_units,
                }.items()
                if value is not None
            }
            if request.position is not None:
                patch["angular_position_deg"] = ANGLES[request.position]
            tracks[index] = source.model_copy(update=patch)

        tracks = [
            track.model_copy(update={"display_order": index})
            for index, track in enumerate(tracks)
        ]
        return self.repository.save(
            layout.model_copy(
                update={"revision": layout.revision + 1, "tracks": tuple(tracks)}
            ),
            layout.revision,
        )
