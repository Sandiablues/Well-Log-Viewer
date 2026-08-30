from __future__ import annotations
import os
import subprocess
from pathlib import Path
from .models import ParsedDocument

class DoclingExtractionProvider:
    name = "docling"
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.venv_python = project_root / "runtime" / "wme_docling_venv" / "bin" / "python"
        self.worker_script = project_root / "backend" / "app" / "document_extraction" / "worker.py"
    def available(self) -> tuple[bool, str | None]:
        if not self.venv_python.is_file(): return False, "private document extraction environment is not installed"
        if not self.worker_script.is_file(): return False, "document extraction worker is missing"
        try:
            result = subprocess.run([str(self.venv_python), "-c", "import docling; print(getattr(docling, '__version__', 'unknown'))"], capture_output=True, text=True, timeout=20, check=False)
        except Exception as exc:
            return False, f"worker readiness check failed: {exc}"
        if result.returncode != 0: return False, result.stderr.strip() or "Docling import failed"
        return True, result.stdout.strip() or "ready"
    def provider_version(self) -> str:
        available, detail = self.available()
        return detail if available and detail else "unavailable"
    def parse_document(self, source_path: Path, output_dir: Path, document_id: str, source_sha256: str, cache_key: str) -> ParsedDocument:
        output_dir.mkdir(parents=True, exist_ok=True)
        result_path = output_dir / "worker_result.json"
        log_path = output_dir / "worker.log"
        command = [str(self.venv_python), str(self.worker_script), "--input", str(source_path), "--output-dir", str(output_dir), "--document-id", document_id, "--source-sha256", source_sha256, "--cache-key", cache_key]
        env = os.environ.copy()
        env.setdefault("HF_HOME", str(self.project_root / "runtime" / "models" / "docling"))
        with log_path.open("w", encoding="utf-8") as log_handle:
            result = subprocess.run(command, stdout=log_handle, stderr=subprocess.STDOUT, text=True, env=env, check=False)
        if result.returncode != 0:
            tail = log_path.read_text(encoding="utf-8", errors="replace")[-5000:]
            raise RuntimeError(f"document extraction failed: {tail}")
        if not result_path.is_file(): raise RuntimeError("document extraction completed without a result")
        return ParsedDocument.model_validate_json(result_path.read_text(encoding="utf-8"))
