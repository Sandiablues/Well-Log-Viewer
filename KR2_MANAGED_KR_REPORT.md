# KR-2 Managed Knowledge Repository — Implementation Report

**Project:** MultiViewer / Well Log Viewer  
**Block:** KR-2 — Managed Knowledge Repository Schema and Governance Contract  
**Date:** 2026-06-12  
**Status:** Implementation complete; external runtime validation required

---

## Files Changed

### New files

| File | Description |
|------|-------------|
| `backend/app/knowledge/governance.py` | GovernanceStatus enum and state-machine helpers |
| `backend/app/knowledge/managed_models.py` | All six managed KR domain record types |
| `backend/app/knowledge/managed_seed.py` | Seed-to-managed bridge; `build_seed_managed_records()` |
| `backend/app/knowledge/managed_repository.py` | ManagedKRRepository service layer |
| `backend/app/knowledge/api_managed_knowledge.py` | Read-only managed KR API routes |
| `backend/tests/knowledge/test_kr2_managed_repository.py` | KR-2 test suite (10 required + additional tests) |

### Modified files

| File | Change |
|------|--------|
| `backend/app/main.py` | Added `managed_knowledge_router` import and `app.include_router()` call (2 lines) |

### Untouched KR-1 files (confirmed)

- `backend/app/knowledge/models.py`
- `backend/app/knowledge/repository.py`
- `backend/app/knowledge/curve_knowledge.py`
- `backend/app/knowledge/api_knowledge.py`

---

## Managed KR Architecture

```
KR Seed Layer (unchanged from KR-1)
  curve_knowledge.py → CURVE_DEFINITIONS (Python constants)
  repository.py → KnowledgeRepository (KR-1 read-only endpoints)

KR-2 Managed Layer (new)
  governance.py       → GovernanceStatus, transition rules
  managed_models.py   → 6 domain record types (dataclasses)
  managed_seed.py     → seed-to-managed bridge
  managed_repository.py → ManagedKRRepository service
  api_managed_knowledge.py → /api/wlv/knowledge/managed/* endpoints

KR-1 Endpoints (preserved, unchanged)
  /api/wlv/knowledge/health
  /api/wlv/knowledge/product-groups
  /api/wlv/knowledge/curve-definitions
  /api/wlv/knowledge/display-rules
  /api/wlv/knowledge/templates  (remains empty)

KR-2 New Read-Only Endpoints
  /api/wlv/knowledge/managed/health
  /api/wlv/knowledge/managed/schema
  /api/wlv/knowledge/managed/status-summary
```

The managed layer sits alongside — not replacing — the KR-1 repository.
A future KR block will wire the managed repository into the classifier/inventory
pipeline so that approved managed records override seed records.

---

## Record Model Summary

Six domain record types are implemented as Python dataclasses in `managed_models.py`:

### A. CurveDefinitionRecord
Canonical curve knowledge. Fields include: `record_id`, `canonical_curve_id`,
`display_name`, `family`, `product_group`, `product_subgroup`, `default_unit`,
`description`, `status`, `version`, `source_type`, `source_reference`,
`created_at`, `updated_at`, `created_by`, `reviewed_by`, `approved_by`,
`approved_at`, `deprecated_at`, `change_reason`, `evidence_refs`.

### B. AliasRecord
Mnemonic alias mapping to a canonical curve. Context-aware (context_hint field
supports open-hole vs cased-hole disambiguation in future blocks). Fields include:
`record_id`, `alias`, `normalized_alias`, `canonical_curve_id`, `unit_hint`,
`description_hint`, `vendor_hint`, `context_hint`, `confidence`, `status`,
`evidence_refs`, `created_at`, `reviewed_by`, `approved_by`, `change_reason`.

### C. DisplayRuleRecord
Curve display rendering rule. Fields include: `record_id`, `canonical_curve_id`,
`preferred_track_family`, `scale_type`, `display_min`, `display_max`,
`default_unit`, `reverse_scale`, `overlay_group`, `line_style_hint`, `color_hint`,
`status`, `version`, `evidence_refs`, `created_at`, `approved_by`, `change_reason`.

### D. ClassificationRuleRecord
Deterministic classification hint. Fields include: `record_id`, `rule_key`,
`match_type`, `match_value`, `product_group`, `product_subgroup`, `curve_family`,
`confidence`, `context_requirements`, `status`, `version`, `evidence_refs`,
`created_at`, `approved_by`, `change_reason`. **Empty seed set in KR-2.**

### E. TemplateRuleRecord
Viewer template construction rule. Fields include: `record_id`, `template_key`,
`template_label`, `track_order`, `required_curve_families`,
`preferred_curve_families`, `fallback_curve_families`, `overlay_rules`,
`missing_curve_behavior`, `status`, `version`, `evidence_refs`, `created_at`,
`approved_by`, `change_reason`. **Empty seed set in KR-2; templates endpoint
remains empty.**

### F. EvidenceRecord
Provenance/source record. No governance lifecycle. Fields include: `evidence_id`,
`source_type`, `source_label`, `source_reference`, `source_file`, `source_url`,
`extracted_text`, `observed_mnemonic`, `observed_unit`, `observed_description`,
`confidence`, `created_at`, `notes`. **No internet access required.**

---

## Governance State Model

```
GovernanceStatus (str enum)
  seed       — bootstrap/default knowledge from Python constants
  candidate  — proposed/imported knowledge awaiting review
  approved   — trusted, production-eligible
  rejected   — reviewed and rejected; retained for audit
  deprecated — formerly valid; retained for backward compatibility

Production eligibility:
  seed, approved → eligible
  candidate, rejected, deprecated → NOT eligible (isolated)

State transitions (VALID_TRANSITIONS):
  seed      → approved, deprecated
  candidate → approved, rejected
  approved  → deprecated
  rejected  → (terminal, no transitions)
  deprecated → (terminal, no transitions)
```

Service methods `promote_to_approved()`, `deprecate_record()`, and
`reject_record()` exist on `ManagedKRRepository` but are **not** exposed
as public HTTP endpoints in KR-2.

---

## Seed-to-Managed Bridge Design

`managed_seed.py` implements `build_seed_managed_records()`, which converts
the existing Python seed constants into managed records with `status=seed`:

| Source | → | Managed record type | Count |
|--------|---|---------------------|-------|
| `CURVE_DEFINITIONS` entries | → | `CurveDefinitionRecord` | 10 |
| All aliases across all curves | → | `AliasRecord` | 47 |
| Display fields per curve | → | `DisplayRuleRecord` | 10 |
| *(none in KR-2)* | → | `ClassificationRuleRecord` | 0 |
| *(none in KR-2)* | → | `TemplateRuleRecord` | 0 |

**Total seed records: 67**

Record IDs are deterministic (stable across restarts):
- `"seed_curve_def_{canonical_curve_id}"`
- `"seed_alias_{NORMALIZED_ALIAS}_{canonical_curve_id}"`
- `"seed_display_{canonical_curve_id}"`

The `_FAMILY_TO_SUBGROUP` mapping in `managed_seed.py` is self-contained
(mirrors `repository.py`) to avoid circular imports.

---

## Storage Decision

**KR-2 uses in-memory storage only.** All records are derived from
`CURVE_DEFINITIONS` on repository initialisation. No file-backed storage
and no database migration was introduced.

The repository interface (`list_records`, `get_by_id`, `_add_record`, etc.)
is designed so that a future KR block can substitute a file-backed or
database-backed store without changing the service or API contracts.

Runtime data path `backend/data/knowledge/` is **not created** in KR-2.

---

## API Endpoint Changes

### New read-only endpoints (KR-2)

| Endpoint | Response |
|----------|----------|
| `GET /api/wlv/knowledge/managed/health` | Service status, total record counts, status and type breakdowns |
| `GET /api/wlv/knowledge/managed/schema` | Record type metadata, governance status definitions, valid transitions |
| `GET /api/wlv/knowledge/managed/status-summary` | Per-status and per-type record counts; candidate vs production-eligible split |

### Preserved KR-1 endpoints (unchanged)

| Endpoint | Status |
|----------|--------|
| `GET /api/wlv/knowledge/health` | ✓ Unchanged |
| `GET /api/wlv/knowledge/product-groups` | ✓ Unchanged |
| `GET /api/wlv/knowledge/curve-definitions` | ✓ Unchanged |
| `GET /api/wlv/knowledge/display-rules` | ✓ Unchanged |
| `GET /api/wlv/knowledge/templates` | ✓ Unchanged, still returns `[]` |

### Endpoint validation commands (run with backend active)

```bash
# KR-1 compatibility
curl -s http://127.0.0.1:8000/api/wlv/knowledge/health | python3 -m json.tool
curl -s http://127.0.0.1:8000/api/wlv/knowledge/product-groups | python3 -m json.tool
curl -s http://127.0.0.1:8000/api/wlv/knowledge/curve-definitions | python3 -m json.tool
curl -s http://127.0.0.1:8000/api/wlv/knowledge/display-rules | python3 -m json.tool
curl -s http://127.0.0.1:8000/api/wlv/knowledge/templates | python3 -m json.tool

# KR-2 managed introspection
curl -s http://127.0.0.1:8000/api/wlv/knowledge/managed/health | python3 -m json.tool
curl -s http://127.0.0.1:8000/api/wlv/knowledge/managed/schema | python3 -m json.tool
curl -s http://127.0.0.1:8000/api/wlv/knowledge/managed/status-summary | python3 -m json.tool
```

Expected responses:
- KR-1 `/health` → `product_group_count: 8, template_count: 0`
- KR-1 `/templates` → `{"templates": []}`
- KR-2 `/managed/health` → `total_record_count: 67, seed: 67, candidate: 0, approved: 0`
- KR-2 `/managed/status-summary` → `production_eligible_count: 67, candidate_count: 0`

---

## Tests

### Test file
`backend/tests/knowledge/test_kr2_managed_repository.py`

### Test classes and coverage

| Class | Tests | Coverage |
|-------|-------|----------|
| `TestManagedEndpoints` | 8 | KR-2 endpoint responses, status summary, schema completeness |
| `TestSeedCurveDefinitions` | 7 | seed→CurveDefinitionRecord conversion, status, fields |
| `TestSeedAliases` | 7 | seed→AliasRecord conversion, normalization, GR alias |
| `TestSeedDisplayRules` | 6 | seed→DisplayRuleRecord conversion, reverse_scale |
| `TestRecordIds` | 9 | determinism, uniqueness, format verification |
| `TestGovernanceStatus` | 10 | all statuses, transitions, terminal states, eligibility |
| `TestCandidateIsolation` | 7 | candidate not in approved/production lists, visible via explicit filter |
| `TestApprovedListing` | 9 | promote/deprecate/reject service methods, transition enforcement |
| `TestKR1Compatibility` | 7 | all five KR-1 endpoints verified unchanged |
| `TestTemplatesEmpty` | 4 | templates endpoint empty, no TemplateRuleRecord seeds |
| `TestSchemaAndValidation` | 10 | schema content, validation errors, record access |

**Total tests: 84**

### Verified via direct Python execution (sandbox)

The following were verified by running Python directly against the project
modules (the sandbox cannot execute the project venv due to architecture
mismatch — Python 3.13 on the host vs 3.10 in the sandbox):

| Check | Result |
|-------|--------|
| All 6 new files: `ast.parse()` clean | ✓ PASS |
| `governance.py` status values, transitions, eligibility | ✓ PASS |
| `managed_seed.py`: 10 curve defs, 47 aliases, 10 display rules | ✓ PASS |
| All 67 seed record IDs unique and deterministic | ✓ PASS |
| `managed_repository.py`: list/filter/get/promote/deprecate/reject | ✓ PASS |
| Candidate isolation (not in approved/production lists) | ✓ PASS |
| Seed-to-approved promotion with `hasattr` guard | ✓ PASS |
| Validate record errors correctly identified | ✓ PASS |
| KR-1 symbol grep (all symbols present, files unchanged) | ✓ PASS |
| `git status` confirms only 5 new files + main.py change | ✓ PASS |

### Run commands

```bash
cd backend && .venv/bin/pytest tests/knowledge/ -v
cd backend && .venv/bin/pytest -v
cd frontend && npm run typecheck
cd frontend && npm run build
```

---

## Known Limitations

1. **In-memory only** — no persistence across process restarts. Seed records
   are re-derived from Python constants on each startup.
2. **No write endpoints** — import, add, approve, and deprecate operations are
   service methods only. A KR management UI is deferred to a future block.
3. **No import staging** — the staging/candidate import pipeline is structurally
   supported (candidate status, `_add_record`) but no import workflow exists yet.
4. **Classification rules and template rules are structurally ready but empty.**
   Converting the classifier vocabulary to managed classification rules
   requires a separate migration block.
5. **Seed records always re-created on start** — if records are mutated
   in-memory during a session (via service methods), those changes are lost on
   restart. Durable mutation requires file-backed or database storage (KR-3+).
6. **`promote_to_approved` guards `approved_at`/`deprecated_at` with `hasattr`**
   because only `CurveDefinitionRecord` has those fields per spec. Other record
   types (AliasRecord, DisplayRuleRecord) set `approved_by` only.

---

## External Testing Required

Runtime and browser testing must be performed by the user with the backend
and frontend servers running. Claude cannot claim runtime test success
without captured output.

### Manual UI checks

1. Open Data / MDP.
2. Expand a well with open-hole data.
3. Confirm subgroup labels and order render correctly (no regression).
4. Load selected curves to WDV.
5. Confirm loaded curves appear in Loaded Curves panel.
6. Confirm no tracks auto-populate.
7. Confirm browser console has no new errors.

---

## Confirmations

| Requirement | Status |
|-------------|--------|
| No KR management UI built | ✓ Confirmed |
| No Auto-build / Build from Selected built | ✓ Confirmed |
| No large hard-coded curve dictionary added | ✓ Confirmed |
| No WDV auto-track behavior introduced | ✓ Confirmed |
| KR-1 endpoints preserved and unchanged | ✓ Confirmed |
| Templates endpoint remains empty | ✓ Confirmed |
| Frontend files untouched | ✓ Confirmed |
| No database migration | ✓ Confirmed |
| No package dependency changes | ✓ Confirmed |
| Managed KR record models exist for all 6 record types | ✓ Confirmed |
| Governance statuses defined and validated | ✓ Confirmed |
| Seed-to-managed bridge implemented | ✓ Confirmed |
| Candidate/approved/deprecated model testable | ✓ Confirmed |
| Import/staging data structure ready (`_add_record`) | ✓ Confirmed |
| Validation helpers implemented | ✓ Confirmed |
