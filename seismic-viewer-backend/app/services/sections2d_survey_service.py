from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List

from fastapi import HTTPException

from app.api import endpoints as volume_legacy


def import_2d_survey_folder(*, source_folder: str, survey_name: str, replace_existing_survey: bool = False) -> Dict[str, Any]:
    project_root = Path(__file__).resolve().parents[3]
    import_script = project_root / "import_2d_survey.py"

    source_path = Path(source_folder).expanduser()

    if not import_script.exists():
        return {"ok": False, "message": f"Import script not found: {import_script}"}

    if not source_path.exists() or not source_path.is_dir():
        return {"ok": False, "message": f"Source folder not found: {source_path}"}

    segy_files = []
    for pattern in ("*.sgy", "*.SGY", "*.segy", "*.SEGY"):
        segy_files.extend(source_path.rglob(pattern))

    if not segy_files:
        return {"ok": False, "message": f"No SEG-Y files found under: {source_path}"}

    cmd = [
        sys.executable,
        str(import_script),
        "--source-folder",
        str(source_path),
        "--survey-name",
        survey_name,
    ]

    if replace_existing_survey:
        cmd.append("--replace-existing-survey")

    try:
        completed = subprocess.run(
            cmd,
            cwd=str(project_root),
            capture_output=True,
            text=True,
            timeout=3600,
        )

        if completed.returncode != 0:
            return {
                "ok": False,
                "message": "2D survey import failed.",
                "returncode": completed.returncode,
                "stdout": completed.stdout[-4000:],
                "stderr": completed.stderr[-4000:],
            }

        return {
            "ok": True,
            "message": f"Imported 2D survey '{survey_name}' from {len(segy_files)} SEG-Y files.",
            "source_folder": str(source_path),
            "survey_name": survey_name,
            "file_count": len(segy_files),
            "stdout": completed.stdout[-4000:],
            "stderr": completed.stderr[-4000:],
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "message": "2D survey import timed out after 1 hour."}
    except Exception as exc:
        return {"ok": False, "message": f"2D survey import failed: {exc}"}


def get_2d_survey_lines(survey_id: str) -> List[Dict[str, Any]]:
    volumes = volume_legacy.load_volumes()

    if survey_id not in volumes:
        raise HTTPException(status_code=404, detail="2D survey not found.")

    survey = volume_legacy.normalize_volume_record(volumes[survey_id])

    if survey.get("dataset_type") != "2d_survey":
        raise HTTPException(status_code=400, detail=f"Dataset {survey_id} is not a 2D survey.")

    return survey.get("lines") or survey.get("metadata", {}).get("lines") or []


def get_2d_survey(survey_id: str) -> Dict[str, Any]:
    volumes = volume_legacy.load_volumes()

    if survey_id not in volumes:
        raise HTTPException(status_code=404, detail="2D survey not found.")

    survey = volume_legacy.normalize_volume_record(volumes[survey_id])

    if survey.get("dataset_type") != "2d_survey":
        raise HTTPException(status_code=400, detail=f"Dataset {survey_id} is not a 2D survey.")

    return survey
