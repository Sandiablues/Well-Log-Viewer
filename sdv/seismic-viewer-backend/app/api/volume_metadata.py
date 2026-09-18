from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, HTMLResponse

from app.reports.metadata_score_report import render_volume_metadata_score_report
from app.services.metadata_agent_service import build_normalized_metadata, get_normalized_metadata
from app.services.metadata_summary_service import build_metadata_summary

router = APIRouter(tags=["volume-metadata"])


@router.get("/report-assets/metadata_score_report.css", include_in_schema=False)
def metadata_score_report_css():
    css_path = Path(__file__).resolve().parents[1] / "reports" / "static" / "metadata_score_report.css"
    return FileResponse(css_path, media_type="text/css")


@router.get("/volumes/{volume_id}/metadata-summary")
async def get_volume_metadata_summary(volume_id: str):
    summary, error = build_metadata_summary(volume_id)
    if error:
        raise HTTPException(status_code=404, detail=error)
    return summary


@router.post("/volumes/{volume_id}/metadata/enrich")
async def enrich_volume_metadata(volume_id: str):
    try:
        normalized = build_normalized_metadata(volume_id)
        return {
            "status": "ok",
            "volume_id": volume_id,
            "normalized_metadata": normalized,
        }
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Metadata enrichment failed: {exc}")


@router.get("/volumes/{volume_id}/metadata-score-report", response_class=HTMLResponse)
async def get_volume_metadata_score_report(volume_id: str):
    return HTMLResponse(render_volume_metadata_score_report(volume_id))


@router.get("/volumes/{volume_id}/metadata/normalized")
async def get_volume_normalized_metadata(volume_id: str):
    try:
        normalized = get_normalized_metadata(volume_id)

        if normalized is None:
            normalized = build_normalized_metadata(volume_id)

        return {
            "volume_id": volume_id,
            "normalized_metadata": normalized,
        }

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get or build normalized metadata for volume_id={volume_id}: {exc}",
        )
