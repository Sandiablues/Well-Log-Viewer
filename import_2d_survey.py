#!/usr/bin/env python3

import argparse
import json
import shutil
import sys
import uuid
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
BACKEND_ROOT = PROJECT_ROOT / "seismic-viewer-backend"
APP_ROOT = BACKEND_ROOT / "app"

sys.path.insert(0, str(BACKEND_ROOT))

from app.services.seismic_service import SeismicService  # noqa: E402


def load_volumes(volumes_json: Path) -> dict:
    if volumes_json.exists():
        with open(volumes_json, "r") as f:
            return json.load(f)
    return {}


def save_volumes(volumes_json: Path, volumes: dict) -> None:
    volumes_json.parent.mkdir(parents=True, exist_ok=True)
    tmp = volumes_json.with_suffix(".json.tmp")
    with open(tmp, "w") as f:
        json.dump(volumes, f, indent=2)
    tmp.replace(volumes_json)


def unique_segy_files(source_folder: Path) -> list[Path]:
    files = []
    seen = set()

    for pattern in ("*.sgy", "*.SGY", "*.segy", "*.SEGY"):
        for path in source_folder.rglob(pattern):
            resolved = path.resolve()
            if resolved not in seen:
                seen.add(resolved)
                files.append(resolved)

    return sorted(files, key=lambda p: str(p).lower())


def make_line_display_name(source_folder: Path, segy_path: Path) -> str:
    rel = segy_path.relative_to(source_folder)
    folder = rel.parent.name
    stem = segy_path.stem
    if folder and folder != ".":
        return f"{folder} / {stem}"
    return stem


def convert_line(
    segy_path: Path,
    source_folder: Path,
    zarr_dir: Path,
    existing_volumes: dict,
) -> dict:
    file_id = str(uuid.uuid4())
    zarr_path = zarr_dir / f"{file_id}.zarr"

    if zarr_path.exists():
        shutil.rmtree(zarr_path)

    metadata = SeismicService.get_segy_metadata(str(segy_path))

    if metadata.get("is_3d") is True:
        raise ValueError(f"Refusing to import 3D SEG-Y as 2D survey line: {segy_path}")

    conversion_info = SeismicService.convert_to_zarr(str(segy_path), str(zarr_path))

    shape = metadata.get("shape") or conversion_info.get("shape")
    if not isinstance(shape, (list, tuple)) or len(shape) != 2:
        raise ValueError(f"Converted line is not 2D. shape={shape}, file={segy_path}")

    display_name = make_line_display_name(source_folder, segy_path)
    rel_path = str(segy_path.relative_to(source_folder))

    line_record = {
        "id": file_id,
        "filename": segy_path.name,
        "display_name": display_name,
        "dataset_type": "2d_line",
        "hidden": True,
        "metadata": {
            **metadata,
            "source_path": str(segy_path),
            "source_relative_path": rel_path,
            "survey_import_source": source_folder.name,
            "zarr": conversion_info,
        },
        "zarr_url": f"/data/zarr/{file_id}.zarr",
    }

    existing_volumes[file_id] = line_record

    return line_record


def make_line_summary(line_record: dict) -> dict:
    metadata = line_record.get("metadata") or {}
    zarr_meta = metadata.get("zarr") or {}
    shape = metadata.get("shape") or zarr_meta.get("shape") or []

    trace_count = metadata.get("trace_count") or zarr_meta.get("trace_count")
    sample_count = None

    if isinstance(shape, list) and len(shape) == 2:
        trace_count = trace_count or shape[0]
        sample_count = shape[1]

    return {
        "line_id": line_record["id"],
        "line_name": line_record.get("display_name") or line_record.get("filename"),
        "filename": line_record.get("filename"),
        "source_relative_path": metadata.get("source_relative_path"),
        "zarr_url": line_record.get("zarr_url"),
        "shape": shape,
        "trace_count": trace_count,
        "sample_count": sample_count,
        "sample_rate": metadata.get("sample_rate") or metadata.get("sample_interval_ms"),
        "axis_order": zarr_meta.get("axis_order") or ["trace", "sample"],
        "hidden": line_record.get("hidden", True),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Import a folder of 2D SEG-Y lines as one 2D survey.")
    parser.add_argument(
        "--source-folder",
        default="/Users/donarcher/Desktop/Seismic_Viewer/Test_Data/Rhode_Island_Sound_2D",
        help="Master folder containing 2D SEG-Y files.",
    )
    parser.add_argument(
        "--survey-name",
        default="Rhode_Island_Sound_2D",
        help="Survey display name.",
    )
    parser.add_argument(
        "--replace-existing-survey",
        action="store_true",
        help="Remove existing survey record with the same display name before creating the new one. Existing child line records are not deleted.",
    )

    args = parser.parse_args()

    source_folder = Path(args.source_folder).expanduser().resolve()
    survey_name = args.survey_name

    if not source_folder.exists():
        raise SystemExit(f"Source folder not found: {source_folder}")

    zarr_dir = BACKEND_ROOT / "data" / "zarr"
    volumes_json = BACKEND_ROOT / "data" / "volumes.json"

    zarr_dir.mkdir(parents=True, exist_ok=True)
    volumes = load_volumes(volumes_json)

    segy_files = unique_segy_files(source_folder)

    if not segy_files:
        raise SystemExit(f"No SEG-Y files found under: {source_folder}")

    print(f"Survey: {survey_name}")
    print(f"Source: {source_folder}")
    print(f"SEG-Y files found: {len(segy_files)}")
    print("")

    if args.replace_existing_survey:
        to_remove = [
            vid for vid, record in volumes.items()
            if record.get("dataset_type") == "2d_survey"
            and (record.get("display_name") == survey_name or record.get("filename") == survey_name)
        ]
        for vid in to_remove:
            print(f"Removing existing survey record: {vid}")
            volumes.pop(vid, None)

    line_records = []

    for idx, segy_path in enumerate(segy_files, start=1):
        print(f"[{idx}/{len(segy_files)}] Importing {segy_path.relative_to(source_folder)}")
        line_record = convert_line(segy_path, source_folder, zarr_dir, volumes)
        line_records.append(line_record)

    lines = [make_line_summary(record) for record in line_records]

    survey_id = f"survey_{uuid.uuid4()}"

    survey_record = {
        "id": survey_id,
        "filename": survey_name,
        "display_name": survey_name,
        "dataset_type": "2d_survey",
        "hidden": True,
        "zarr_url": None,
        "metadata": {
            "survey_name": survey_name,
            "source_folder": str(source_folder),
            "line_count": len(lines),
            "line_ids": [line["line_id"] for line in lines],
            "lines": lines,
            "source": "folder_import",
        },
        "lines": lines,
    }

    volumes[survey_id] = survey_record
    save_volumes(volumes_json, volumes)

    print("")
    print("Import complete.")
    print(f"Survey ID: {survey_id}")
    print(f"Lines imported: {len(lines)}")
    print(f"Registry: {volumes_json}")
    print(f"Zarr output: {zarr_dir}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
