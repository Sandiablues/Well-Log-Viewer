# KR-4 Governance Review — Implementation Report

## Status

Implementation complete. All static checks pass. Run the validation script to execute tests.

---

## Contract Assertions

| Assertion | Status |
|-----------|--------|
| Candidate records remain non-production until approved | ✓ Enforced — candidates are excluded from `list_production_eligible()` |
| Approved records become production-eligible | ✓ Enforced — `PRODUCTION_STATUSES = {seed, approved}` |
| Rejected/deprecated records remain non-production | ✓ Enforced — terminal statuses, excluded from production-eligible listing |
| KR-1 endpoints remain unchanged | ✓ No changes to `api_knowledge.py`, `repository.py`, or `models.py` |
| KR-3 import/staging remains unchanged | ✓ No logic changes to import services; test updated for KR-4 compatibility |
| No UI added in KR-4 | ✓ Backend contract only |
| No runtime classifier wiring added in KR-4 | ✓ Approved records are production-eligible but not wired into classifier |

---

## Files Changed

### New files
| File | Description |
|------|-------------|
| `backend/app/knowledge/governance_service.py` | KR-4 governance service: `GovernanceService`, `GovernanceTransitionError`, `RecordNotFoundError`, `_serialize_record` |
| `backend/tests/knowledge/test_kr4_governance_review.py` | 28+ tests across 11 test groups |
| `apply_kr4_governance_review_patch.sh` | Apply script |
| `rollback_kr4_governance_review_patch.sh` | Rollback script |
| `validate_kr4_governance_review.sh` | Full validation script |
| `KR4_GOVERNANCE_REVIEW_REPORT.md` | This report |

### Edited files
| File | Change |
|------|--------|
| `backend/app/knowledge/managed_models.py` | Added `KR4_VERSION = "kr-4"`; added `governance_history: list[dict]` field to all 5 governed record types |
| `backend/app/knowledge/api_managed_knowledge.py` | Added KR-4 imports, `get_governance_service` dependency, 6 new endpoints, 3 new Pydantic response models |
| `backend/tests/knowledge/test_kr3_import_staging.py` | Updated `TestNoApprovalEndpoint.test_no_approve_endpoint_exists` to allow the `/records/{id}/approve` path added by KR-4 |

---

## New API Endpoints

All endpoints are under `/api/wlv/knowledge/managed`:

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/records` | List all governed records; filter by `?status=` and/or `?record_type=` |
| `GET` | `/records/{record_id}` | Fetch a single record by ID; 404 if not found |
| `POST` | `/records/{record_id}/approve` | Approve a candidate or seed record |
| `POST` | `/records/{record_id}/reject` | Reject a candidate record |
| `POST` | `/records/{record_id}/deprecate` | Deprecate a seed or approved record |
| `GET` | `/production-eligible` | List all production-eligible records (seed + approved); filter by `?record_type=` |

### Action request body
```json
{
  "actor": "manual_review",
  "reason": "Reviewed and accepted",
  "notes": "Optional reviewer notes"
}
```

### Action response body
```json
{
  "ok": true,
  "kr_version": "kr-4",
  "record_id": "...",
  "previous_status": "candidate",
  "new_status": "approved",
  "production_eligible": true,
  "record": { ... }
}
```

### Error responses
| Condition | HTTP Status |
|-----------|-------------|
| Unknown record ID | 404 |
| Invalid governance transition | 400 with `error: "invalid_transition"`, `from_status`, `to_status` |
| Missing required `actor` field | 422 |
| Unknown `status` query param value | 422 |

---

## Governance Service

`backend/app/knowledge/governance_service.py`

```python
class GovernanceService:
    list_records(status=None, record_type=None)
    get_record(record_id)                    # raises RecordNotFoundError
    approve_record(record_id, actor, reason, notes)
    reject_record(record_id, actor, reason, notes)
    deprecate_record(record_id, actor, reason, notes)
    list_production_eligible_records(record_type=None)
```

All governance actions enforce the existing `VALID_TRANSITIONS` map from KR-2's `governance.py`. Invalid transitions raise `GovernanceTransitionError` deterministically before any mutation occurs.

---

## Audit Fields

KR-4 adds a `governance_history: list[dict]` field to all 5 governed record types. Each governance action appends one entry:

```json
{
  "action": "approved",
  "actor": "manual_review",
  "timestamp": "2026-06-12T10:30:00+00:00",
  "previous_status": "candidate",
  "new_status": "approved",
  "reason": "Verified against reference source",
  "notes": "Optional notes"
}
```

Answers all 4 required audit questions:
- **Who?** → `actor`
- **When?** → `timestamp`
- **What transition?** → `previous_status` + `new_status` + `action`
- **Why?** → `reason`

Legacy fields (`approved_by`, `approved_at`, `deprecated_at`, `change_reason`) are kept in sync where they exist on the model, preserving backward compatibility.

---

## Production Eligibility Rules

| Status | Production-eligible |
|--------|-------------------|
| `seed` | ✓ Yes |
| `approved` | ✓ Yes |
| `candidate` | ✗ No |
| `rejected` | ✗ No |
| `deprecated` | ✗ No |

---

## Blocked Transitions

| From | To | Blocked? |
|------|----|----------|
| `candidate` | `deprecated` | ✓ Blocked (HTTP 400) |
| `approved` | `rejected` | ✓ Blocked (HTTP 400) |
| `rejected` | `approved` | ✓ Blocked (HTTP 400) |
| `deprecated` | `approved` | ✓ Blocked (HTTP 400) |
| `rejected` | `deprecated` | ✓ Blocked (terminal) |
| `deprecated` | `rejected` | ✓ Blocked (terminal) |

---

## Tests

**Test file:** `backend/tests/knowledge/test_kr4_governance_review.py`

| Group | Tests |
|-------|-------|
| `TestManagedRecordListing` | 4 tests (seed listing, candidate filter, type filter, combined) |
| `TestManagedRecordLookup` | 4 tests (by ID, 404, kr_version, service raise) |
| `TestApproveCandidate` | 5 tests (HTTP 200, response shape, status change, production-eligible, approved_by field) |
| `TestRejectCandidate` | 4 tests (HTTP 200, status change, not in PE, response shape) |
| `TestDeprecateRecord` | 4 tests (approved→deprecated, not in PE, seed→deprecated, seed disappears from PE) |
| `TestInvalidTransitions` | 8 tests (candidate→deprecated, approved→rejected, rejected→approved, deprecated→approved, 404, 422, service raise, double-approve) |
| `TestProductionEligibleListing` | 5 tests (returns seed, no candidate before approval, yes after, deprecated disappears, type filter) |
| `TestGovernanceAuditFields` | 8 tests (actor, timestamp, reason, transition, notes, response includes history, multiple actions, reject actor) |
| `TestKR1Compatibility` | 7 tests (health, product-groups, curve-defs, display-rules, templates, candidates don't affect KR-1, PE count change) |
| `TestKR2Compatibility` | 3 tests (health, schema, status-summary) |
| `TestKR3Compatibility` | 5 tests (preview, stage, semantic-invalid, malformed 422, staged non-production) |

---

## Run Tests

```bash
cd ~/Applications/MultiViewer/Well-Log-Viewer/backend

# KR-4 tests only
.venv/bin/python -m pytest tests/knowledge/test_kr4_governance_review.py -v

# Full knowledge suite (regression)
.venv/bin/python -m pytest tests/knowledge/ -v

# Frontend checks
cd ../frontend
npm run typecheck && npm run build
```

Or use the validation script:
```bash
bash ~/Applications/MultiViewer/Well-Log-Viewer/validate_kr4_governance_review.sh
```

---

## Known Limitations

1. **In-memory storage only.** All records, including governance history, are held in the process's memory. Governance actions are lost on server restart. Persistent storage is intentionally deferred per the work order.

2. **No multi-user locking.** Concurrent governance actions on the same record are not protected by a lock. This is acceptable for the current single-process, in-memory architecture.

3. **No approval workflow steps.** There is no draft/pending-review state between candidate and approved. All transitions are atomic single-step.

4. **Approved records not wired into runtime classifier.** This is intentional per the KR-4 scope. Wiring approved records into the live curve classifier is deferred to a future KR block.

5. **`_serialize_record` is a module-level function in `governance_service.py`** and is imported by `api_managed_knowledge.py`. If the serialization logic needs to change (e.g. adding custom field renderers), it lives in one place.

---

## Deferred Persistence Note

KR-4 continues to use the same in-memory `ManagedKRRepository` established in KR-2 and KR-3. No stop conditions were triggered:
- No redesign of KR-2/KR-3 data ownership was required.
- No candidates were made production-eligible by default.
- No KR-1 read-only endpoints were altered.
- No classifier wiring was introduced.
- No durable persistence was required as a side-effect.

If durability is needed in a future KR block, the `GovernanceService` interface is stable; only the `ManagedKRRepository` backend would need to change.
