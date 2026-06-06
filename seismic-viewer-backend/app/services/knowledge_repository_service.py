"""
Persistent Knowledge Repository service.

This is the durable storage layer for geophysical dictionary terms and aliases.

It is intentionally separate from:
- scanner records
- repository/package records
- load-sheet records
- viewer datasets

The knowledge repository stores reusable reference knowledge that the application
can later use for lookup, classification support, metadata evidence matching, and
QAQC assistance.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional
from datetime import datetime, timezone
import csv
import io
import json
import re
import sqlite3
import uuid


_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_KNOWLEDGE_DIR = _BACKEND_ROOT / "data" / "knowledge"
_DB_PATH = _KNOWLEDGE_DIR / "knowledge.db"


_NON_WORD_RE = re.compile(r"[^a-z0-9]+")


def normalize_term(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).lower().strip()
    text = text.replace("_", " ").replace("-", " ")
    text = _NON_WORD_RE.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_list(value: Any) -> str:
    if value is None:
        return "[]"
    if isinstance(value, str):
        if not value.strip():
            return "[]"
        # Allow semicolon/comma-separated aliases from CSV/simple forms.
        if ";" in value:
            items = [x.strip() for x in value.split(";") if x.strip()]
        elif "," in value:
            items = [x.strip() for x in value.split(",") if x.strip()]
        else:
            items = [value.strip()]
        return json.dumps(items, ensure_ascii=False)
    if isinstance(value, list):
        return json.dumps([str(x).strip() for x in value if str(x).strip()], ensure_ascii=False)
    return json.dumps([str(value).strip()], ensure_ascii=False)


def _from_json_list(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, list):
        return value
    try:
        parsed = json.loads(value)
        if isinstance(parsed, list):
            return parsed
    except Exception:
        pass
    return []


def _connect() -> sqlite3.Connection:
    _KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_knowledge_db() -> dict[str, Any]:
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS knowledge_terms (
                id TEXT PRIMARY KEY,
                term TEXT NOT NULL,
                normalized_term TEXT NOT NULL UNIQUE,
                definition TEXT DEFAULT '',
                category TEXT DEFAULT 'uncategorized',
                aliases_json TEXT DEFAULT '[]',
                related_terms_json TEXT DEFAULT '[]',
                source TEXT DEFAULT 'manual',
                authority TEXT DEFAULT 'reference',
                active INTEGER DEFAULT 1,
                metadata_json TEXT DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)

        # F3I.7: first-class classification fields.
        # Keep category for import/backward compatibility, but use these for the
        # long-term KM classification model.
        existing_term_columns = {
            row[1] for row in conn.execute("PRAGMA table_info(knowledge_terms)").fetchall()
        }

        if "knowledge_domain" not in existing_term_columns:
            conn.execute("ALTER TABLE knowledge_terms ADD COLUMN knowledge_domain TEXT DEFAULT ''")

        if "knowledge_subtype" not in existing_term_columns:
            conn.execute("ALTER TABLE knowledge_terms ADD COLUMN knowledge_subtype TEXT DEFAULT ''")

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_knowledge_terms_category
            ON knowledge_terms(category)
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_knowledge_terms_domain
            ON knowledge_terms(knowledge_domain)
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_knowledge_terms_subtype
            ON knowledge_terms(knowledge_subtype)
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_knowledge_terms_active
            ON knowledge_terms(active)
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS knowledge_imports (
                id TEXT PRIMARY KEY,
                filename TEXT,
                source TEXT,
                imported_count INTEGER DEFAULT 0,
                rejected_count INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                notes_json TEXT DEFAULT '[]'
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS knowledge_candidates (
                id TEXT PRIMARY KEY,
                candidate_type TEXT NOT NULL,
                candidate_value TEXT NOT NULL,
                normalized_candidate_value TEXT NOT NULL,
                suggested_canonical_term TEXT DEFAULT '',
                normalized_suggested_canonical_term TEXT DEFAULT '',
                category TEXT DEFAULT 'uncategorized',
                source_type TEXT DEFAULT 'usage_observation',
                source_reference TEXT DEFAULT '',
                evidence_count INTEGER DEFAULT 1,
                confidence TEXT DEFAULT 'low',
                review_status TEXT DEFAULT 'candidate',
                notes TEXT DEFAULT '',
                metadata_json TEXT DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_knowledge_candidates_status
            ON knowledge_candidates(review_status)
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_knowledge_candidates_type
            ON knowledge_candidates(candidate_type)
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_knowledge_candidates_category
            ON knowledge_candidates(category)
        """)

        conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_knowledge_candidates_unique_open
            ON knowledge_candidates(
                candidate_type,
                normalized_candidate_value,
                normalized_suggested_canonical_term,
                source_type,
                source_reference
            )
        """)

        conn.commit()

    return {
        "status": "ok",
        "db_path": str(_DB_PATH),
    }


def _row_to_term(row: sqlite3.Row) -> dict[str, Any]:
    keys = set(row.keys())
    metadata = json.loads(row["metadata_json"] or "{}")

    knowledge_domain = row["knowledge_domain"] if "knowledge_domain" in keys else ""
    knowledge_subtype = row["knowledge_subtype"] if "knowledge_subtype" in keys else ""

    return {
        "id": row["id"],
        "term": row["term"],
        "normalized_term": row["normalized_term"],
        "definition": row["definition"] or "",
        "category": row["category"] or "uncategorized",
        "knowledge_domain": knowledge_domain or metadata.get("knowledge_domain") or metadata.get("family") or "",
        "knowledge_subtype": knowledge_subtype or metadata.get("knowledge_subtype") or metadata.get("specific") or "",
        "aliases": _from_json_list(row["aliases_json"]),
        "related_terms": _from_json_list(row["related_terms_json"]),
        "source": row["source"] or "manual",
        "authority": row["authority"] or "reference",
        "active": bool(row["active"]),
        "metadata": metadata,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def upsert_knowledge_term(payload: dict[str, Any]) -> dict[str, Any]:
    init_knowledge_db()

    term = str(payload.get("term") or "").strip()
    if not term:
        raise ValueError("term is required")

    normalized = normalize_term(payload.get("normalized_term") or term)
    if not normalized:
        raise ValueError("normalized term is required")

    now = _utc_now()
    aliases_json = _json_list(payload.get("aliases"))
    related_terms_json = _json_list(payload.get("related_terms"))

    metadata = payload.get("metadata") or {}

    knowledge_domain = (
        payload.get("knowledge_domain")
        or payload.get("family")
        or metadata.get("knowledge_domain")
        or metadata.get("family")
        or ""
    )

    knowledge_subtype = (
        payload.get("knowledge_subtype")
        or payload.get("specific")
        or metadata.get("knowledge_subtype")
        or metadata.get("specific")
        or ""
    )

    category_value = str(payload.get("category") or "uncategorized")
    if category_value.lower() in {"", "uncategorized", "none"} and knowledge_domain:
        category_value = str(knowledge_domain)

    metadata["knowledge_domain"] = knowledge_domain
    metadata["knowledge_subtype"] = knowledge_subtype
    metadata_json = json.dumps(metadata, ensure_ascii=False)

    with _connect() as conn:
        existing_columns = {
            row[1] for row in conn.execute("PRAGMA table_info(knowledge_terms)").fetchall()
        }

        if "knowledge_domain" not in existing_columns:
            conn.execute("ALTER TABLE knowledge_terms ADD COLUMN knowledge_domain TEXT DEFAULT ''")

        if "knowledge_subtype" not in existing_columns:
            conn.execute("ALTER TABLE knowledge_terms ADD COLUMN knowledge_subtype TEXT DEFAULT ''")

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_knowledge_terms_domain
            ON knowledge_terms(knowledge_domain)
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_knowledge_terms_subtype
            ON knowledge_terms(knowledge_subtype)
        """)

        existing = conn.execute(
            "SELECT * FROM knowledge_terms WHERE normalized_term = ?",
            (normalized,),
        ).fetchone()

        if existing:
            term_id = existing["id"]
            created_at = existing["created_at"]
        else:
            term_id = str(payload.get("id") or uuid.uuid4())
            created_at = now

        conn.execute("""
            INSERT INTO knowledge_terms (
                id,
                term,
                normalized_term,
                definition,
                category,
                aliases_json,
                related_terms_json,
                source,
                authority,
                active,
                metadata_json,
                knowledge_domain,
                knowledge_subtype,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(normalized_term) DO UPDATE SET
                term = excluded.term,
                definition = excluded.definition,
                category = excluded.category,
                aliases_json = excluded.aliases_json,
                related_terms_json = excluded.related_terms_json,
                source = excluded.source,
                authority = excluded.authority,
                active = excluded.active,
                metadata_json = excluded.metadata_json,
                knowledge_domain = excluded.knowledge_domain,
                knowledge_subtype = excluded.knowledge_subtype,
                updated_at = excluded.updated_at
        """, (
            term_id,
            term,
            normalized,
            str(payload.get("definition") or ""),
            category_value,
            aliases_json,
            related_terms_json,
            str(payload.get("source") or "manual"),
            str(payload.get("authority") or "reference"),
            1 if payload.get("active", True) else 0,
            metadata_json,
            str(knowledge_domain or ""),
            str(knowledge_subtype or ""),
            created_at,
            now,
        ))

        conn.commit()

        row = conn.execute(
            "SELECT * FROM knowledge_terms WHERE normalized_term = ?",
            (normalized,),
        ).fetchone()

    return _row_to_term(row)


def list_knowledge_terms(
    query: Optional[str] = None,
    category: Optional[str] = None,
    knowledge_domain: Optional[str] = None,
    knowledge_subtype: Optional[str] = None,
    active: Optional[bool] = True,
    limit: int = 500,
    offset: int = 0,
) -> dict[str, Any]:
    init_knowledge_db()

    where = []
    args: list[Any] = []

    if active is not None:
        where.append("active = ?")
        args.append(1 if active else 0)

    if category:
        where.append("category = ?")
        args.append(category)

    if knowledge_domain:
        where.append("knowledge_domain = ?")
        args.append(knowledge_domain)

    if knowledge_subtype:
        where.append("knowledge_subtype = ?")
        args.append(knowledge_subtype)

    if query:
        q = f"%{normalize_term(query)}%"
        raw = f"%{query.strip()}%"
        where.append("""
            (
                normalized_term LIKE ?
                OR lower(term) LIKE lower(?)
                OR lower(definition) LIKE lower(?)
                OR lower(aliases_json) LIKE lower(?)
                OR lower(related_terms_json) LIKE lower(?)
                OR lower(knowledge_domain) LIKE lower(?)
                OR lower(knowledge_subtype) LIKE lower(?)
            )
        """)
        args.extend([q, raw, raw, raw, raw, raw, raw])

    where_sql = "WHERE " + " AND ".join(where) if where else ""

    safe_limit = max(1, min(int(limit or 500), 5000))
    safe_offset = max(0, int(offset or 0))

    with _connect() as conn:
        total = conn.execute(
            f"SELECT COUNT(*) AS n FROM knowledge_terms {where_sql}",
            args,
        ).fetchone()["n"]

        rows = conn.execute(
            f"""
            SELECT *
            FROM knowledge_terms
            {where_sql}
            ORDER BY category ASC, normalized_term ASC
            LIMIT ? OFFSET ?
            """,
            args + [safe_limit, safe_offset],
        ).fetchall()

    return {
        "total": total,
        "limit": safe_limit,
        "offset": safe_offset,
        "terms": [_row_to_term(row) for row in rows],
    }


def update_knowledge_term_by_id(term_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """
    Update an existing trusted knowledge term by id.

    This is used by the KM editor. It avoids accidental duplicate creation when
    a user edits the display term, normalized term, domain, subtype, aliases, or
    related terms.
    """
    init_knowledge_db()

    if not term_id:
        raise ValueError("term_id is required")

    with _connect() as conn:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(knowledge_terms)").fetchall()}
        if "knowledge_domain" not in cols:
            conn.execute("ALTER TABLE knowledge_terms ADD COLUMN knowledge_domain TEXT DEFAULT ''")
        if "knowledge_subtype" not in cols:
            conn.execute("ALTER TABLE knowledge_terms ADD COLUMN knowledge_subtype TEXT DEFAULT ''")

        existing = conn.execute(
            "SELECT * FROM knowledge_terms WHERE id = ?",
            (term_id,),
        ).fetchone()

        if not existing:
            raise ValueError(f"knowledge term not found: {term_id}")

        term = str(payload.get("term") if payload.get("term") is not None else existing["term"]).strip()
        if not term:
            raise ValueError("term is required")

        normalized = normalize_term(payload.get("normalized_term") or term)
        if not normalized:
            raise ValueError("normalized term is required")

        conflict = conn.execute(
            "SELECT id FROM knowledge_terms WHERE normalized_term = ? AND id != ?",
            (normalized, term_id),
        ).fetchone()

        if conflict:
            raise ValueError(f"another term already uses normalized_term: {normalized}")

        old_metadata = {}
        try:
            old_metadata = json.loads(existing["metadata_json"] or "{}")
        except Exception:
            old_metadata = {}

        incoming_metadata = payload.get("metadata")
        if isinstance(incoming_metadata, dict):
            metadata = {**old_metadata, **incoming_metadata}
        else:
            metadata = old_metadata

        knowledge_domain = (
            payload.get("knowledge_domain")
            or payload.get("family")
            or metadata.get("knowledge_domain")
            or metadata.get("family")
            or ""
        )

        knowledge_subtype = (
            payload.get("knowledge_subtype")
            or payload.get("specific")
            or metadata.get("knowledge_subtype")
            or metadata.get("specific")
            or ""
        )

        category_value = str(payload.get("category") or knowledge_domain or existing["category"] or "uncategorized")

        metadata["knowledge_domain"] = knowledge_domain
        metadata["knowledge_subtype"] = knowledge_subtype
        metadata["edited_by"] = "KM editor"

        aliases_json = _json_list(payload.get("aliases"))
        related_terms_json = _json_list(payload.get("related_terms"))

        conn.execute("""
            UPDATE knowledge_terms
            SET term = ?,
                normalized_term = ?,
                definition = ?,
                category = ?,
                knowledge_domain = ?,
                knowledge_subtype = ?,
                aliases_json = ?,
                related_terms_json = ?,
                source = ?,
                authority = ?,
                active = ?,
                metadata_json = ?,
                updated_at = ?
            WHERE id = ?
        """, (
            term,
            normalized,
            str(payload.get("definition") or ""),
            category_value,
            str(knowledge_domain or ""),
            str(knowledge_subtype or ""),
            aliases_json,
            related_terms_json,
            str(payload.get("source") or existing["source"] or "manual"),
            str(payload.get("authority") or existing["authority"] or "reference"),
            1 if payload.get("active", True) else 0,
            json.dumps(metadata, ensure_ascii=False),
            _utc_now(),
            term_id,
        ))

        conn.commit()

        updated = conn.execute(
            "SELECT * FROM knowledge_terms WHERE id = ?",
            (term_id,),
        ).fetchone()

    return _row_to_term(updated)

def get_categories() -> dict[str, Any]:
    init_knowledge_db()

    with _connect() as conn:
        rows = conn.execute("""
            SELECT category, COUNT(*) AS count
            FROM knowledge_terms
            WHERE active = 1
            GROUP BY category
            ORDER BY category ASC
        """).fetchall()

        domain_rows = conn.execute("""
            SELECT knowledge_domain, COUNT(*) AS count
            FROM knowledge_terms
            WHERE active = 1
              AND COALESCE(knowledge_domain, '') != ''
            GROUP BY knowledge_domain
            ORDER BY knowledge_domain ASC
        """).fetchall()

        subtype_rows = conn.execute("""
            SELECT knowledge_domain, knowledge_subtype, COUNT(*) AS count
            FROM knowledge_terms
            WHERE active = 1
              AND COALESCE(knowledge_subtype, '') != ''
            GROUP BY knowledge_domain, knowledge_subtype
            ORDER BY knowledge_domain ASC, knowledge_subtype ASC
        """).fetchall()

    return {
        "categories": [
            {"category": row["category"], "count": row["count"]}
            for row in rows
        ],
        "knowledge_domains": [
            {"knowledge_domain": row["knowledge_domain"], "count": row["count"]}
            for row in domain_rows
        ],
        "knowledge_subtypes": [
            {
                "knowledge_domain": row["knowledge_domain"],
                "knowledge_subtype": row["knowledge_subtype"],
                "count": row["count"],
            }
            for row in subtype_rows
        ],
    }


def export_knowledge_terms() -> dict[str, Any]:
    result = list_knowledge_terms(active=None, limit=5000, offset=0)
    return {
        "schema": "seismic-viewer-knowledge-terms-v1",
        "exported_at": _utc_now(),
        "terms": result["terms"],
    }


def _coerce_import_record(record: dict[str, Any], default_source: str) -> dict[str, Any]:
    term_value = (
        record.get("term")
        or record.get("Term")
        or record.get("name")
        or record.get("Name")
        or record.get("normalized_term")
        or record.get("Normalized Term")
        or record.get("normalized term")
    )

    normalized_value = (
        record.get("normalized_term")
        or record.get("Normalized Term")
        or record.get("normalized term")
        or term_value
    )

    return {
        "term": term_value,
        "normalized_term": normalized_value,
        "definition": record.get("definition") or record.get("Definition") or record.get("description") or record.get("Description") or "",
        "category": record.get("category") or record.get("Category") or record.get("knowledge_domain") or record.get("family") or "uncategorized",
        "knowledge_domain": record.get("knowledge_domain") or record.get("Knowledge Domain") or record.get("family") or record.get("Family") or "",
        "knowledge_subtype": record.get("knowledge_subtype") or record.get("Knowledge Subtype") or record.get("specific") or record.get("Specific") or "",
        "aliases": record.get("aliases") or record.get("Aliases") or record.get("alias") or record.get("Alias") or [],
        "related_terms": record.get("related_terms") or record.get("Related Terms") or record.get("related") or record.get("Related") or [],
        "source": record.get("source") or record.get("Source") or default_source,
        "authority": record.get("authority") or record.get("Authority") or "reference",
        "active": record.get("active", True),
        "metadata": record.get("metadata") or {},
    }


def import_knowledge_records(
    records: list[dict[str, Any]],
    filename: str = "",
    source: str = "import",
) -> dict[str, Any]:
    init_knowledge_db()

    imported = []
    rejected = []

    for idx, record in enumerate(records):
        try:
            payload = _coerce_import_record(record, default_source=source)
            if not payload.get("term"):
                raise ValueError("missing term")
            imported.append(upsert_knowledge_term(payload))
        except Exception as exc:
            rejected.append({
                "index": idx,
                "record": record,
                "error": str(exc),
            })

    import_id = str(uuid.uuid4())
    with _connect() as conn:
        conn.execute("""
            INSERT INTO knowledge_imports (
                id,
                filename,
                source,
                imported_count,
                rejected_count,
                created_at,
                notes_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            import_id,
            filename,
            source,
            len(imported),
            len(rejected),
            _utc_now(),
            json.dumps(rejected[:100], ensure_ascii=False),
        ))
        conn.commit()

    return {
        "import_id": import_id,
        "filename": filename,
        "source": source,
        "imported_count": len(imported),
        "rejected_count": len(rejected),
        "rejected": rejected[:100],
    }


def parse_json_or_csv_bytes(data: bytes, filename: str = "") -> list[dict[str, Any]]:
    name = (filename or "").lower()
    text = data.decode("utf-8-sig")

    if name.endswith(".json") or text.lstrip().startswith(("{", "[")):
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return [x for x in parsed if isinstance(x, dict)]
        if isinstance(parsed, dict):
            terms = parsed.get("terms") or parsed.get("records") or parsed.get("items")
            if isinstance(terms, list):
                return [x for x in terms if isinstance(x, dict)]
            return [parsed]
        raise ValueError("JSON import must be a list, object, or object with terms/records/items list")

    reader = csv.DictReader(io.StringIO(text))
    return [dict(row) for row in reader]


# ---------------------------------------------------------------------
# Candidate knowledge workflow
# ---------------------------------------------------------------------

_ALLOWED_CANDIDATE_TYPES = {
    "alias",
    "acronym",
    "synonym",
    "related_term",
    "product_variant",
    "document_type_hint",
    "processing_hint",
    "filename_pattern",
    "metadata_field_alias",
    "term",
}

_ALLOWED_REVIEW_STATUSES = {
    "candidate",
    "approved",
    "rejected",
    "promoted",
}


def _row_to_candidate(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "candidate_type": row["candidate_type"],
        "candidate_value": row["candidate_value"],
        "normalized_candidate_value": row["normalized_candidate_value"],
        "suggested_canonical_term": row["suggested_canonical_term"] or "",
        "normalized_suggested_canonical_term": row["normalized_suggested_canonical_term"] or "",
        "category": row["category"] or "uncategorized",
        "source_type": row["source_type"] or "usage_observation",
        "source_reference": row["source_reference"] or "",
        "evidence_count": int(row["evidence_count"] or 1),
        "confidence": row["confidence"] or "low",
        "review_status": row["review_status"] or "candidate",
        "notes": row["notes"] or "",
        "metadata": json.loads(row["metadata_json"] or "{}"),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def upsert_knowledge_candidate(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Store an observed candidate knowledge item.

    This does not modify trusted/approved knowledge_terms. It only creates or
    updates a reviewable candidate.
    """
    init_knowledge_db()

    candidate_type = str(payload.get("candidate_type") or "").strip()
    if not candidate_type:
        raise ValueError("candidate_type is required")

    if candidate_type not in _ALLOWED_CANDIDATE_TYPES:
        raise ValueError(f"unsupported candidate_type: {candidate_type}")

    candidate_value = str(payload.get("candidate_value") or "").strip()
    if not candidate_value:
        raise ValueError("candidate_value is required")

    suggested = str(payload.get("suggested_canonical_term") or "").strip()
    normalized_candidate = normalize_term(candidate_value)
    normalized_suggested = normalize_term(suggested)

    if not normalized_candidate:
        raise ValueError("normalized candidate value is required")

    review_status = str(payload.get("review_status") or "candidate").strip()
    if review_status not in _ALLOWED_REVIEW_STATUSES:
        raise ValueError(f"unsupported review_status: {review_status}")

    now = _utc_now()
    metadata_json = json.dumps(payload.get("metadata") or {}, ensure_ascii=False)

    source_type = str(payload.get("source_type") or "usage_observation")
    source_reference = str(payload.get("source_reference") or "")

    evidence_count = int(payload.get("evidence_count") or 1)
    evidence_count = max(1, evidence_count)

    with _connect() as conn:
        existing = conn.execute("""
            SELECT *
            FROM knowledge_candidates
            WHERE candidate_type = ?
              AND normalized_candidate_value = ?
              AND normalized_suggested_canonical_term = ?
              AND source_type = ?
              AND source_reference = ?
        """, (
            candidate_type,
            normalized_candidate,
            normalized_suggested,
            source_type,
            source_reference,
        )).fetchone()

        if existing:
            candidate_id = existing["id"]
            created_at = existing["created_at"]
            evidence_count = max(evidence_count, int(existing["evidence_count"] or 1) + 1)
        else:
            candidate_id = str(payload.get("id") or uuid.uuid4())
            created_at = now

        conn.execute("""
            INSERT INTO knowledge_candidates (
                id,
                candidate_type,
                candidate_value,
                normalized_candidate_value,
                suggested_canonical_term,
                normalized_suggested_canonical_term,
                category,
                source_type,
                source_reference,
                evidence_count,
                confidence,
                review_status,
                notes,
                metadata_json,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(
                candidate_type,
                normalized_candidate_value,
                normalized_suggested_canonical_term,
                source_type,
                source_reference
            ) DO UPDATE SET
                candidate_value = excluded.candidate_value,
                suggested_canonical_term = excluded.suggested_canonical_term,
                category = excluded.category,
                evidence_count = excluded.evidence_count,
                confidence = excluded.confidence,
                review_status = excluded.review_status,
                notes = excluded.notes,
                metadata_json = excluded.metadata_json,
                updated_at = excluded.updated_at
        """, (
            candidate_id,
            candidate_type,
            candidate_value,
            normalized_candidate,
            suggested,
            normalized_suggested,
            str(payload.get("category") or "uncategorized"),
            source_type,
            source_reference,
            evidence_count,
            str(payload.get("confidence") or "low"),
            review_status,
            str(payload.get("notes") or ""),
            metadata_json,
            created_at,
            now,
        ))

        conn.commit()

        row = conn.execute(
            "SELECT * FROM knowledge_candidates WHERE id = ?",
            (candidate_id,),
        ).fetchone()

    return _row_to_candidate(row)


def list_knowledge_candidates(
    candidate_type: Optional[str] = None,
    category: Optional[str] = None,
    review_status: Optional[str] = "candidate",
    query: Optional[str] = None,
    limit: int = 500,
    offset: int = 0,
) -> dict[str, Any]:
    init_knowledge_db()

    where = []
    args: list[Any] = []

    if candidate_type:
        where.append("candidate_type = ?")
        args.append(candidate_type)

    if category:
        where.append("category = ?")
        args.append(category)

    if review_status:
        where.append("review_status = ?")
        args.append(review_status)

    if query:
        q = f"%{normalize_term(query)}%"
        raw = f"%{query.strip()}%"
        where.append("""
            (
                normalized_candidate_value LIKE ?
                OR normalized_suggested_canonical_term LIKE ?
                OR lower(candidate_value) LIKE lower(?)
                OR lower(suggested_canonical_term) LIKE lower(?)
                OR lower(notes) LIKE lower(?)
                OR lower(source_reference) LIKE lower(?)
            )
        """)
        args.extend([q, q, raw, raw, raw, raw])

    where_sql = "WHERE " + " AND ".join(where) if where else ""

    safe_limit = max(1, min(int(limit or 500), 5000))
    safe_offset = max(0, int(offset or 0))

    with _connect() as conn:
        total = conn.execute(
            f"SELECT COUNT(*) AS n FROM knowledge_candidates {where_sql}",
            args,
        ).fetchone()["n"]

        rows = conn.execute(
            f"""
            SELECT *
            FROM knowledge_candidates
            {where_sql}
            ORDER BY evidence_count DESC, updated_at DESC
            LIMIT ? OFFSET ?
            """,
            args + [safe_limit, safe_offset],
        ).fetchall()

    return {
        "total": total,
        "limit": safe_limit,
        "offset": safe_offset,
        "candidates": [_row_to_candidate(row) for row in rows],
    }


def get_knowledge_candidate(candidate_id: str) -> Optional[dict[str, Any]]:
    init_knowledge_db()

    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM knowledge_candidates WHERE id = ?",
            (candidate_id,),
        ).fetchone()

    if not row:
        return None

    return _row_to_candidate(row)


def update_knowledge_candidate_status(
    candidate_id: str,
    review_status: str,
    notes: Optional[str] = None,
) -> dict[str, Any]:
    init_knowledge_db()

    if review_status not in _ALLOWED_REVIEW_STATUSES:
        raise ValueError(f"unsupported review_status: {review_status}")

    now = _utc_now()

    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM knowledge_candidates WHERE id = ?",
            (candidate_id,),
        ).fetchone()

        if not row:
            raise ValueError(f"candidate not found: {candidate_id}")

        existing_notes = row["notes"] or ""
        new_notes = existing_notes
        if notes:
            new_notes = (existing_notes + "\n" + notes).strip() if existing_notes else notes

        conn.execute("""
            UPDATE knowledge_candidates
            SET review_status = ?,
                notes = ?,
                updated_at = ?
            WHERE id = ?
        """, (
            review_status,
            new_notes,
            now,
            candidate_id,
        ))
        conn.commit()

        updated = conn.execute(
            "SELECT * FROM knowledge_candidates WHERE id = ?",
            (candidate_id,),
        ).fetchone()

    return _row_to_candidate(updated)


def approve_knowledge_candidate(
    candidate_id: str,
    promote: bool = True,
    notes: Optional[str] = None,
) -> dict[str, Any]:
    """
    Approve a candidate.

    If promote=True:
    - alias/synonym/acronym/product_variant/etc. are promoted as aliases or related
      terms on the trusted canonical term.
    - candidate_type='term' is promoted as a trusted term.
    """
    candidate = get_knowledge_candidate(candidate_id)
    if not candidate:
        raise ValueError(f"candidate not found: {candidate_id}")

    promoted_term = None

    if promote:
        candidate_type = candidate["candidate_type"]
        candidate_value = candidate["candidate_value"]
        canonical = candidate["suggested_canonical_term"] or candidate_value
        category = candidate["category"] or "uncategorized"

        existing = list_knowledge_terms(query=canonical, active=None, limit=50, offset=0)
        exact_existing = None
        normalized_canonical = normalize_term(canonical)

        for term in existing.get("terms", []):
            if term.get("normalized_term") == normalized_canonical:
                exact_existing = term
                break

        if candidate_type == "term":
            payload = {
                "term": canonical,
                "normalized_term": canonical,
                "definition": candidate.get("notes") or "",
                "category": category,
                "aliases": [],
                "related_terms": [],
                "source": "candidate_promotion",
                "authority": "approved",
                "active": True,
                "metadata": {
                    "promoted_from_candidate_id": candidate_id,
                    "candidate_type": candidate_type,
                    "candidate_source_type": candidate.get("source_type"),
                    "candidate_source_reference": candidate.get("source_reference"),
                },
            }
            promoted_term = upsert_knowledge_term(payload)

        else:
            if exact_existing:
                aliases = list(exact_existing.get("aliases") or [])
                related_terms = list(exact_existing.get("related_terms") or [])

                if candidate_type in {"alias", "acronym", "synonym", "product_variant", "document_type_hint", "processing_hint", "metadata_field_alias", "filename_pattern"}:
                    if candidate_value not in aliases:
                        aliases.append(candidate_value)
                elif candidate_type == "related_term":
                    if candidate_value not in related_terms:
                        related_terms.append(candidate_value)

                payload = {
                    "id": exact_existing.get("id"),
                    "term": exact_existing.get("term") or canonical,
                    "normalized_term": exact_existing.get("normalized_term") or canonical,
                    "definition": exact_existing.get("definition") or "",
                    "category": exact_existing.get("category") or category,
                    "aliases": aliases,
                    "related_terms": related_terms,
                    "source": exact_existing.get("source") or "candidate_promotion",
                    "authority": exact_existing.get("authority") or "approved",
                    "active": exact_existing.get("active", True),
                    "metadata": {
                        **(exact_existing.get("metadata") or {}),
                        "last_promoted_candidate_id": candidate_id,
                    },
                }
                promoted_term = upsert_knowledge_term(payload)

            else:
                # If canonical term does not exist, create it and attach the candidate
                # value as an alias unless it is identical to the canonical term.
                aliases = []
                if normalize_term(candidate_value) != normalize_term(canonical):
                    aliases.append(candidate_value)

                payload = {
                    "term": canonical,
                    "normalized_term": canonical,
                    "definition": "",
                    "category": category,
                    "aliases": aliases,
                    "related_terms": [],
                    "source": "candidate_promotion",
                    "authority": "approved",
                    "active": True,
                    "metadata": {
                        "promoted_from_candidate_id": candidate_id,
                        "candidate_type": candidate_type,
                        "candidate_source_type": candidate.get("source_type"),
                        "candidate_source_reference": candidate.get("source_reference"),
                    },
                }
                promoted_term = upsert_knowledge_term(payload)

    updated = update_knowledge_candidate_status(
        candidate_id,
        "promoted" if promote else "approved",
        notes=notes,
    )

    return {
        "candidate": updated,
        "promoted_term": promoted_term,
    }


def reject_knowledge_candidate(candidate_id: str, notes: Optional[str] = None) -> dict[str, Any]:
    candidate = update_knowledge_candidate_status(candidate_id, "rejected", notes=notes)
    return {
        "candidate": candidate,
    }

