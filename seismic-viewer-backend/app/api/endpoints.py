from __future__ import annotations

from fastapi import APIRouter

# Legacy compatibility module.
#
# Historical note:
# app.api.endpoints previously owned upload/jobs, slices, 2D section/survey,
# volume registry, and volume metadata/report routes.
#
# Those routes now live in bounded API modules:
# - app.api.ingestion
# - app.api.slices
# - app.api.sections2d
# - app.api.volumes
# - app.api.volume_metadata
#
# Keep an empty router so older imports of app.api.endpoints.router do not fail.
# Do not add new routes here.

router = APIRouter(tags=["legacy-endpoints-retired"])
