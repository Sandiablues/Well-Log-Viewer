#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import platform
from pathlib import Path
from typing import Any

from docling.datamodel.accelerator_options import AcceleratorDevice, AcceleratorOptions
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions, TableStructureOptions
from docling.document_converter import DocumentConverter, PdfFormatOption
from pypdfium2 import PdfDocument

from resolver import resolve_document


def arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--document-id", required=True)
    parser.add_argument("--source-sha256", required=True)
    parser.add_argument("--cache-key", required=True)
    return parser.parse_args()


def safe(value: Any):
    if value is None or isinstance(value, (str, int, float, bool)): return value
    if isinstance(value, dict): return {str(k): safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)): return [safe(v) for v in value]
    if hasattr(value, "model_dump"): return safe(value.model_dump())
    return str(value)


def walk(value: Any):
    if isinstance(value, dict):
        yield value
        for item in value.values(): yield from walk(item)
    elif isinstance(value, list):
        for item in value: yield from walk(item)


def raw_page_number(item: dict[str, Any]) -> int | None:
    provenance = item.get("prov") or item.get("provenance")
    entries = provenance if isinstance(provenance, list) else [provenance]
    for entry in entries:
        if isinstance(entry, dict):
            for key in ("page_no", "page", "page_number"):
                value = entry.get(key)
                if isinstance(value, int): return value
    return None


def bbox(item: dict[str, Any]):
    provenance = item.get("prov") or item.get("provenance")
    entries = provenance if isinstance(provenance, list) else [provenance]
    for entry in entries:
        if isinstance(entry, dict) and isinstance(entry.get("bbox"), dict): return entry["bbox"]
    return None


def main() -> int:
    args = arguments(); args.output_dir.mkdir(parents=True, exist_ok=True)
    source_page_count = len(PdfDocument(str(args.input)))

    options = PdfPipelineOptions(); options.do_ocr = True; options.do_table_structure = True
    options.table_structure_options = TableStructureOptions(do_cell_matching=True)
    options.accelerator_options = AcceleratorOptions(num_threads=4, device=AcceleratorDevice.AUTO)
    if platform.system() == "Darwin":
        try:
            from docling.datamodel.pipeline_options import OcrMacOptions
            options.ocr_options = OcrMacOptions()
        except Exception: pass

    document = DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)}).convert(args.input).document
    raw = safe(document.export_to_dict())
    raw_path = args.output_dir / "docling_document.json"
    raw_path.write_text(json.dumps(raw, indent=2, ensure_ascii=False), encoding="utf-8")

    provenance_numbers = [raw_page_number(item) for item in walk(raw)]
    provenance_numbers = [n for n in provenance_numbers if isinstance(n, int)]
    zero_based = bool(provenance_numbers) and min(provenance_numbers) == 0
    def normalize_page(number: int | None) -> int | None:
        if number is None: return None
        result = number + 1 if zero_based else number
        return result if 1 <= result <= source_page_count else None

    pages = {n: {"page_number": n, "text": [], "headings": [], "paragraphs": [], "table_ids": []} for n in range(1, source_page_count + 1)}
    seen = {n: set() for n in pages}
    for item in walk(raw):
        page_no = normalize_page(raw_page_number(item))
        if page_no is None: continue
        text = item.get("text") or item.get("orig") or ""
        label = str(item.get("label") or item.get("type") or "")
        if not isinstance(text, str) or not text.strip(): continue
        fingerprint = " ".join(text.split())
        if fingerprint in seen[page_no]: continue
        seen[page_no].add(fingerprint); pages[page_no]["text"].append(text.strip())
        evidence = {"page_number": page_no, "text": text.strip(), "bbox": bbox(item)}
        target = pages[page_no]["headings"] if any(t in label.casefold() for t in ("heading", "title", "section")) else pages[page_no]["paragraphs"]
        target.append(evidence)

    tables = []
    for index, table in enumerate(getattr(document, "tables", []) or [], start=1):
        rows = []; cells = []
        try:
            frame = table.export_to_dataframe(doc=document)
            rows = [[str(v) for v in frame.columns.tolist()]]
            rows.extend([[str(v) for v in row] for row in frame.fillna("").values.tolist()])
            for r, row in enumerate(rows):
                for c, value in enumerate(row): cells.append({"row": r, "column": c, "text": value, "bbox": None, "is_header": r == 0})
        except Exception: pass
        prov = safe(getattr(table, "prov", None)); raw_no = None
        if isinstance(prov, list) and prov and isinstance(prov[0], dict): raw_no = prov[0].get("page_no")
        page_no = normalize_page(raw_no if isinstance(raw_no, int) else None)
        table_id = f"table_{index:04d}"
        tables.append({"table_id": table_id, "page_number": page_no, "caption": None, "cells": cells, "rows": rows})
        if page_no: pages[page_no]["table_ids"].append(table_id)

    normalized_pages = []
    for n in range(1, source_page_count + 1):
        pages[n]["text"] = "\n".join(pages[n]["text"]); normalized_pages.append(pages[n])

    authority_tables = resolve_document(normalized_pages, tables, args.output_dir / "resolver_diagnostics.json")
    if authority_tables:
        authority_by_page: dict[int, list[dict[str, Any]]] = {}
        for table in authority_tables: authority_by_page.setdefault(int(table["page_number"]), []).append(table)
        public_pages = []
        for n in range(1, source_page_count + 1):
            selected = authority_by_page.get(n, [])
            rows = [row for table in selected for row in table.get("rows", [])]
            public_pages.append({"page_number": n, "text": "\n".join(" | ".join(map(str, row)) for row in rows), "headings": [], "paragraphs": [], "table_ids": [t["table_id"] for t in selected]})
        public_tables = authority_tables; authority_mode = True
    else:
        public_pages = normalized_pages; public_tables = tables; authority_mode = False

    try:
        import importlib.metadata as metadata
        version = metadata.version("docling")
    except Exception: version = None

    payload = {"document_id": args.document_id, "source_name": args.input.name, "source_sha256": args.source_sha256, "provider": "docling", "provider_version": version, "page_count": source_page_count, "pages": public_pages, "tables": public_tables, "raw_document_path": str(raw_path), "cache_key": args.cache_key}
    (args.output_dir / "worker_result.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0

if __name__ == "__main__": raise SystemExit(main())
