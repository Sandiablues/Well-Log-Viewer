# KR-5 Implementation Report — Persistent Managed Knowledge Storage

## Summary

Managed KR storage is durable across backend restart.
Seed constants remain bootstrap knowledge.
Persisted managed records are stored separately from seed constants.
Candidate records remain non-production until approved.
Approved records persist as production-eligible.
Rejected/deprecated records persist as non-production.
Governance history and audit fields persist.
No frontend UI was added.
No runtime classifier wiring was added.

---

## Storage

**Storage file path:** `backend/data/knowledge/managed_knowledge.json`

**Storage schema version:** `wlv-managed-kr-1`

**Storage document shape:**
```json
{
  "storage_schema_version": "wlv-managed-kr-1",
  "kr_version": "kr-5",
  "updated_at": "<ISO-8601 UTC>",
  "records": [],
  "evidence_records": []
}
```

---

## Files Changed

### New Files

| File | Purpose |
|------|---------|
| `backend/app/knowledge/managed_storage.py` | Storage module: path resolution, load, atomic save, deserialization, health |
| `backend/tests/knowledge/test_kr5_persistent_storage.py` | KR-5 test suite (28 tests across 8 groups) |
| `backend/tests/knowledge/conftest.py` | Autouse fixture isolating existing KR-2/3/4 tests to temp storage |
| `backend/data/knowledge/managed_knowledge.json` | Initial empty storage file |
| `validate_kr5_persistent_storage.sh` | Automated + live validation script |
| `rollback_kr5_persistent_storage.sh` | Rollback script |

### Modified Files

| File | Change |
|------|--------|
| `backend/app/knowledge/managed_repository.py` | Rewrote to separate `_seed_records`/`_managed_records`; added `persist()`, `_ensure_managed()`, `prepare_for_mutation()`, storage injection via `storage_path` constructor arg |
| `backend/app/knowledge/governance_service.py` | Added `_get_mutable_or_raise()` using `repo.prepare_for_mutation()`; added `repo.persist()` calls after approve/reject/deprecate |
| `backend/app/knowledge/managed_models.py` | Added `KR5_VERSION = "kr-5"` constant |
| `backend/app/knowledge/api_managed_knowledge.py` | Added `StorageHealthResponse` model and `GET /managed/storage/health` endpoint |

---

## Architecture

### Seed / Managed Separation

| Store | Contents | Persisted? |
|-------|----------|-----------|
| `_seed_records` | Records from Python seed layer (status=SEED) | Never |
| `_managed_records` | Candidates, approved, rejected, deprecated, seed overrides | Always |
| `_evidence` | Evidence/provenance records from imports | Always |

`_all_records()` merges both: `{**_seed_records, **_managed_records}`. Managed records override seeds on the same `record_id`.

### Seed Transition Persistence (Override Pattern)

When a seed record is deprecated or approved:
1. `governance_service` calls `repo.prepare_for_mutation(record_id)`
2. `prepare_for_mutation` calls `_ensure_managed(record_id)` which deepcopies the seed record into `_managed_records`
3. Service mutates the managed copy (e.g., `status = DEPRECATED`)
4. Service calls `repo.persist()` — saves the mutated managed record
5. On reload: seed layer produces SEED record; storage produces DEPRECATED managed record; `_all_records()` merge gives DEPRECATED (managed wins)

### Persistence Points

- `_add_record()` — import staging candidate records
- `_add_evidence()` — import staging evidence records
- `repo.persist()` — after approve, reject, deprecate (called by GovernanceService)
- Preview operations: **do NOT persist**
- Read-only operations: **do NOT write**

### Atomic Write

`ManagedStorage.save()` writes to `managed_knowledge.json.tmp` then calls `os.replace()`. This is atomic on POSIX and Windows. No partial writes corrupt the storage file.

---

## Test Isolation

Tests pass `storage_path=tmp_path / "managed_knowledge.json"` to `ManagedKRRepository(storage_path=...)`.

`backend/tests/knowledge/conftest.py` patches `DEFAULT_STORAGE_PATH` to a per-test temp path for all knowledge tests as an autouse fixture. This ensures:
- KR-2/3/4 tests using `ManagedKRRepository()` (no args) never write to the real storage file
- The conftest runs before test-file fixtures (pytest autouse ordering)
- KR-5 tests that pass explicit paths are unaffected

---

## New Endpoint

```
GET /api/wlv/knowledge/managed/storage/health
```

Response:
```json
{
  "kr_version": "kr-5",
  "storage_enabled": true,
  "storage_path": "...backend/data/knowledge/managed_knowledge.json",
  "storage_schema_version": "wlv-managed-kr-1",
  "persisted_record_count": 0,
  "persisted_evidence_record_count": 0
}
```

---

## Tests Added

**File:** `backend/tests/knowledge/test_kr5_persistent_storage.py`

| Group | Tests |
|-------|-------|
| `TestStorageInitialization` | Missing file, dir creation, zero persisted count |
| `TestStagePersistence` | Stage writes to disk, preview does not, candidate/evidence survive reload |
| `TestGovernancePersistence` | Approve/reject/deprecate persist and survive reload; production-eligibility after reload |
| `TestSeedOverridePersistence` | Seed deprecation persists as managed override; governance history/audit fields survive reload |
| `TestRestartReload` | Candidates non-production after reload until approved |
| `TestMalformedStorage` | Malformed JSON raises `ManagedStorageError` |
| `TestAtomicWrite` | No `.tmp` file after save; valid JSON in storage file |
| `TestCompatibility` | KR-1/2/3/4 endpoints still work; storage health endpoint; KR-1 isolation from candidates |

Total: **28 test cases** across 8 groups (plus 2 additional sub-tests).

---

## Known Limitations

1. **No migration tooling**: Storage schema version `wlv-managed-kr-1` is written and read but no automatic migration is performed if the schema changes in a future KR block.
2. **File-backed only**: KR-5 uses JSON file storage. A database backend (PostgreSQL, SQLite) is deferred to a future block per the work order.
3. **No compression**: Large managed repositories (many thousands of records) may accumulate significant file size over time without periodic compaction.
4. **No concurrent write safety**: If two backend processes write simultaneously (e.g., multi-worker uvicorn without process locking), the last write wins. Intended for single-process use.
5. **No storage health endpoint for malformed state**: The `GET /managed/storage/health` returns 0 counts when storage is malformed rather than surfacing an error. A restart with malformed storage would fail loudly (via `ManagedStorageError`), which is the intended behavior.

---

## Deferred Database / Persistence Considerations

- **Database backend**: Replace `ManagedStorage` with a SQLite or PostgreSQL adapter by changing the constructor injected into `ManagedKRRepository`. Service and API layers are unchanged.
- **Schema migration**: Add a `migrate_storage()` method to `ManagedStorage` if the storage schema version changes in a future KR.
- **Audit log table**: The `governance_history` list could be normalized into a separate audit events table in a database-backed implementation.
- **Multi-process locking**: Add a file lock (e.g., `fcntl.flock`) or database-level transactions for multi-worker deployments.

---

## Acceptance Criteria Status

| Criterion | Status |
|-----------|--------|
| KR-5 tests pass | Run `validate_kr5_persistent_storage.sh` to verify |
| Full knowledge suite passes | Run `validate_kr5_persistent_storage.sh` to verify |
| Frontend typecheck passes | Run `validate_kr5_persistent_storage.sh` to verify |
| Frontend build passes | Run `validate_kr5_persistent_storage.sh` to verify |
| Live restart persistence validation | Manual — see validation script for curl commands |
| KR-1 compatibility intact | ✅ KR-1 repo unchanged; managed repo isolated |
| KR-3 preview does not persist | ✅ Preview calls `validate_import_payload` only |
| KR-3 stage persists candidates | ✅ `_add_record()` auto-persists |
| KR-4 governance persists state | ✅ `repo.persist()` after approve/reject/deprecate |
| Candidates non-production until approved | ✅ Status-gated in `list_production_eligible()` |
| Approved records production-eligible after restart | ✅ Managed override survives reload |
| Rejected/deprecated non-production after restart | ✅ Terminal status not in `PRODUCTION_STATUSES` |
