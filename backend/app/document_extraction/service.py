from __future__ import annotations
import shutil, threading, time, uuid
from pathlib import Path
from .cache import ExtractionCache
from .docling_provider import DoclingExtractionProvider
from .models import ExtractionJobStatus, ParsedDocumentSummary

class ExtractionService:
    def __init__(self, project_root: Path):
        self.project_root=project_root; self.runtime_root=project_root/"backend"/"runtime"/"wme_extraction"; self.upload_root=self.runtime_root/"uploads"; self.cache=ExtractionCache(self.runtime_root/"cache"); self.provider=DoclingExtractionProvider(project_root); self.jobs={}; self.results={}; self.started={}; self.upload_root.mkdir(parents=True,exist_ok=True)
    def health(self): return self.provider.available()
    def save_upload(self, filename: str, content: bytes):
        doc=f"doc_{uuid.uuid4().hex}"; d=self.upload_root/doc; d.mkdir(parents=True,exist_ok=True); p=d/Path(filename).name; p.write_bytes(content); return p
    def submit(self, source_path: Path):
        source_sha=self.cache.sha256_file(source_path); version=self.provider.provider_version(); key=self.cache.cache_key(source_sha,version); cached=self.cache.load(key); doc=source_path.parent.name; job=f"job_{uuid.uuid4().hex}"
        if cached:
            summary=ParsedDocumentSummary(document_id=cached.document_id,source_name=cached.source_name,source_sha256=cached.source_sha256,provider=cached.provider,provider_version=cached.provider_version,page_count=cached.page_count,table_count=len(cached.tables),cache_key=cached.cache_key,cache_hit=True,output_path=str(self.cache.parsed_path(key)))
            status=ExtractionJobStatus(job_id=job,document_id=doc,source_name=source_path.name,state="completed",stage="cached structured document ready",cached=True,page_count=summary.page_count,table_count=summary.table_count); self.jobs[job]=status; self.results[job]=summary; return status
        status=ExtractionJobStatus(job_id=job,document_id=doc,source_name=source_path.name,state="queued",stage="queued",cached=False); self.jobs[job]=status; self.started[job]=time.monotonic(); threading.Thread(target=self._run,args=(job,source_path,source_sha,key),daemon=True).start(); return status
    def _run(self, job, source_path, source_sha, key):
        s=self.jobs[job]
        try:
            s.state="converting"; s.stage="interpreting document structure"; document=self.provider.parse_document(source_path,self.cache.entry_dir(key),s.document_id,source_sha,key); s.state="normalizing"; s.stage="normalizing structured document"; parsed=self.cache.save(document); summary=ParsedDocumentSummary(document_id=document.document_id,source_name=document.source_name,source_sha256=document.source_sha256,provider=document.provider,provider_version=document.provider_version,page_count=document.page_count,table_count=len(document.tables),cache_key=document.cache_key,cache_hit=False,output_path=str(parsed)); self.results[job]=summary; s.page_count=summary.page_count; s.table_count=summary.table_count; s.state="completed"; s.stage="structured document ready"
        except Exception as exc: s.state="failed"; s.stage="document extraction failed"; s.error=str(exc)
        finally: s.elapsed_seconds=round(time.monotonic()-self.started.get(job,time.monotonic()),3)
    def status(self, job):
        s=self.jobs.get(job)
        if s and s.state not in ("completed","failed"): s.elapsed_seconds=round(time.monotonic()-self.started.get(job,time.monotonic()),3)
        return s
    def result(self, job): return self.results.get(job)
    def document(self, job):
        summary=self.results.get(job)
        if not summary: return None
        return self.cache.load(summary.cache_key)
    def clear(self):
        self.cache.clear(); shutil.rmtree(self.upload_root,ignore_errors=True); self.upload_root.mkdir(parents=True,exist_ok=True); self.jobs.clear(); self.results.clear(); self.started.clear()
