from __future__ import annotations

# JOB_RETENTION_1_TEST

import json
import tempfile
import time
from pathlib import Path

from app.services.job_history_retention_service import prune_job_history, retention_policy


def write_job(path: Path, job_id: str, status: str, offset: int) -> None:
    payload = {
        "job_id": job_id,
        "status": status,
        "created_at": f"2026-01-01T00:00:{offset:02d}Z",
        "updated_at": f"2026-01-01T00:00:{offset:02d}Z",
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    ts = time.time() + offset
    path.touch()
    try:
        import os
        os.utime(path, (ts, ts))
    except Exception:
        pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    policy = retention_policy()
    require(policy["default_keep_latest"] == 100, "default keep_latest should be 100")

    with tempfile.TemporaryDirectory() as tmp:
        jobs_dir = Path(tmp) / "jobs"
        summary_dir = Path(tmp) / "summaries"
        jobs_dir.mkdir()

        for i in range(6):
            write_job(jobs_dir / f"completed_{i}.json", f"completed_{i}", "completed", i)

        write_job(jobs_dir / "running_1.json", "running_1", "running", 100)
        write_job(jobs_dir / "queued_1.json", "queued_1", "queued", 101)
        (jobs_dir / "invalid.json").write_text("{not-json", encoding="utf-8")

        dry = prune_job_history(keep_latest=5, dry_run=True, jobs_dir=jobs_dir, summary_dir=summary_dir)
        require(dry["dry_run"] is True, "dry run flag should be true")
        require(dry["jobs_seen"] == 9, f"expected 9 jobs, got {dry['jobs_seen']}")
        require(dry["would_prune"] == 4, f"expected 4 prune candidates, got {dry['would_prune']}")
        require(len(list(jobs_dir.glob("*.json"))) == 9, "dry run should not delete files")

        real = prune_job_history(keep_latest=5, dry_run=False, jobs_dir=jobs_dir, summary_dir=summary_dir)
        require(real["dry_run"] is False, "real prune flag should be false")
        require(real["pruned"] == 4, f"expected 4 pruned, got {real['pruned']}")
        require(len(list(jobs_dir.glob("*.json"))) == 5, "real prune should leave 5 files")
        require((jobs_dir / "running_1.json").exists(), "running job should be preserved")
        require((jobs_dir / "queued_1.json").exists(), "queued job should be preserved")
        require((jobs_dir / "invalid.json").exists(), "invalid JSON should be preserved")
        require(summary_dir.exists(), "summary dir should exist")
        require(list(summary_dir.glob("job_prune_summary_*.json")), "real prune should write summary")

    print("PASS JOB-RETENTION-1 retention policy test")


if __name__ == "__main__":
    main()
