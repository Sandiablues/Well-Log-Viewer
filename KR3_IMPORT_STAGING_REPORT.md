# KR3_IMPORT_STAGING_REPORT.md
## WLV-KR-3: Definition Import and Staging Contract

---

## Summary

KR-3 delivers the backend-owned import/staging layer for the Knowledge Repository.
Structured JSON payloads can now be validated (preview) and converted into candidate
managed KR records (stage) without affecting production behaviour.

All KR-3 work is backend-only.  No frontend changes, no UI, no approval endpoints,
no WDV/Auto-build changes.

---

## Files Changed

### New files

| File | Purpose |
|---|---|
| `backend/app/knowledge/import_models.py` | Pydantic import payload schema (JSON contract) |
| `backend/app/knowledge/import_validation_service.py` | Stateless validation service |
| `backend/app/knowledge/import_staging_service.py` | Candidate record creation service |
| `backend/tests/knowledge/test_kr3_import_staging.py` | KR-3 test suite (60+ tests) |

### Modified files

| File | Change |
|---|---|
| `backend/app/knowledge/api_managed_knowledge.py` | Added two POST import endpoints; converted GET endpoints to use FastAPI DI |
| `backend/app/knowledge/managed_models.py` | Added `KR3_VERSION = "kr-3"` constant |

### Patch / validate scripts (project root)

| File | Purpose |
|---|---|
| `apply_kr3_import_staging_patch.sh` | Verify presence of KR-3 files and `git add` them |
| `rollback_kr3_import_staging_patch.sh` | Remove KR-3 files and restore KR-2 originals |
| `validate_kr3_import_staging.sh` | Run test suite + frontend checks + curl examples |

---

## Import Payload Schema

```json
{
  "source": {
    "source_type": "manual_import",
    "source_label": "User KR Definition Set 001",
    "source_reference": "internal_wlv_kr_seed_extension",
    "source_file": null,
    "notes": "Optional import note"
  },
  "curve_definitions": [
    {
      "canonical_curve_id": "spectral_gamma_ray",
      "display_name": "Spectral Gamma Ray",
      "family": "spectral_gamma_ray",
      "product_group": "open_hole_logs",
      "product_subgroup": "gamma_ray",
      "default_unit": "API",
      "description": "Spectral gamma ray measurement.",
      "aliases": ["SGR", "THOR", "URAN", "POTA"]
    }
  ],
  "display_rules": [
    {
      "canonical_curve_id": "spectral_gamma_ray",
      "preferred_track_family": "gamma_ray_sp",
      "scale_type": "linear",
      "display_min": 0.0,
      "display_max": 300.0,
      "default_unit": "API",
      "reverse_scale": false,
      "overlay_group": "gamma_ray"
    }
  ],
  "classification_rules": [
    {
      "rule_key": "alias_sgr_to_spectral_gamma_ray",
      "match_type": "mnemonic_exact",
      "match_value": "SGR",
      "product_group": "open_hole_logs",
      "product_subgroup": "gamma_ray",
      "curve_family": "spectral_gamma_ray",
      "confidence": 0.95,
      "context_requirements": []
    }
  ],
  "template_rules": []
}
```

- All sections except `source` are optional.  Missing sections are treated as empty lists.
- `source_type` and `source_label` are required in the `source` block.

---

## Validation Rules

The import validation service (`import_validation_service.py`) checks:

| Code | Severity | Description |
|---|---|---|
| `missing_required_field` | error | `source.source_type`, `source.source_label`, `canonical_curve_id`, `display_name`, `family`, `product_group` empty |
| `duplicate_canonical_curve_id` | error | Same `canonical_curve_id` appears more than once in `curve_definitions` |
| `duplicate_alias_in_curve_definition` | error | Same alias (case-insensitive) appears twice within one `curve_definitions` entry |
| `alias_mapped_to_multiple_canonical_ids` | error | Same alias (case-insensitive) appears across two different `curve_definitions` entries |
| `alias_conflicts_with_existing_record` | error | Alias already exists in the managed KR mapped to a different `canonical_curve_id` |
| `alias_already_exists_for_same_curve` | warning | Alias exists in managed KR for the same `canonical_curve_id` (dup candidate will be created) |
| `display_rule_unknown_canonical_curve_id` | error | Display rule references a curve not in this payload and not in the existing managed KR |
| `invalid_scale_type` | error | `scale_type` is not `"linear"` or `"log"` |
| `unknown_product_group` | error | `product_group` in a classification rule is not a known KR product group |
| `unknown_product_subgroup` | error | `product_subgroup` in a classification rule is not a known subgroup of the given product group |
| `invalid_confidence_value` | error | `confidence` outside `[0.0, 1.0]` |

Validation is stateless and does NOT mutate the repository.

---

## Candidate Staging Behaviour

When `POST /import/stage` is called with a valid payload:

1. One `EvidenceRecord` is created from the `source` block.
2. For each `curve_definition` entry: one `CurveDefinitionRecord` (status=`candidate`) plus one `AliasRecord` (status=`candidate`) per alias.
3. For each `display_rule` entry: one `DisplayRuleRecord` (status=`candidate`).
4. For each `classification_rule` entry: one `ClassificationRuleRecord` (status=`candidate`).
5. For each `template_rule` entry: one `TemplateRuleRecord` (status=`candidate`).

All staged records carry:
- `status = GovernanceStatus.CANDIDATE`
- `source_type` from `payload.source.source_type`
- `source_reference` from `payload.source.source_reference`
- `created_at` and `updated_at` set to UTC now
- `change_reason` describing the import batch ID
- `evidence_refs` containing the batch evidence record ID

Record IDs are deterministic given a batch ID:
- Curve definition: `import_{batch_id}_curve_def_{canonical_curve_id}`
- Alias: `import_{batch_id}_alias_{NORMALIZED_ALIAS}_{canonical_curve_id}`
- Display rule: `import_{batch_id}_display_{canonical_curve_id}`
- Classification rule: `import_{batch_id}_class_{rule_key}`
- Template rule: `import_{batch_id}_template_{template_key}`
- Evidence: `import_evidence_{batch_id}`

---

## Evidence / Source Behaviour

Each import batch creates exactly one `EvidenceRecord`:
- `evidence_id = "import_evidence_{batch_id}"`
- `source_type`, `source_label`, `source_reference`, `source_file`, `notes` from the import `source` block
- `created_at` set to UTC now

All staged candidate records link to this evidence record via their `evidence_refs` list.

---

## Storage Decision

**KR-3 uses the existing in-memory `ManagedKRRepository`.**

Staged candidate records survive for the lifetime of the running backend process only.
They are NOT persisted to disk, NOT committed to Git, and NOT file-backed.

Persistent candidate storage is deferred to a later block.

To enable file-backed persistence in a future block:
- Storage target: `backend/data/knowledge/` (gitignored)
- The `stage_import_payload` function and `ManagedKRRepository._add_record` interface
  are designed to accept a future file-backed or database-backed implementation.

---

## Endpoint Changes

### New endpoints (KR-3)

```
POST /api/wlv/knowledge/managed/import/preview
POST /api/wlv/knowledge/managed/import/stage
```

Both accept `application/json` with an `ImportPayload` body.

**Preview response (valid):**
```json
{
  "valid": true,
  "mode": "preview",
  "staged": false,
  "kr_version": "kr-3",
  "error_count": 0,
  "warning_count": 0,
  "candidate_record_count": 7,
  "evidence_record_count": 1,
  "record_type_counts": {
    "curve_definition": 1,
    "alias": 4,
    "display_rule": 1,
    "classification_rule": 1,
    "template_rule": 0,
    "evidence": 1
  },
  "errors": [],
  "warnings": []
}
```

**Stage response (valid):**
```json
{
  "valid": true,
  "mode": "stage",
  "staged": true,
  "kr_version": "kr-3",
  "import_batch_id": "kr_import_a3f1b2c9e04d",
  "error_count": 0,
  "warning_count": 0,
  "candidate_record_count": 7,
  "evidence_record_count": 1,
  "record_type_counts": {...},
  "record_ids": ["import_kr_import_a3f1b2c9e04d_curve_def_spectral_gamma_ray", "..."],
  "errors": [],
  "warnings": []
}
```

**Preview / stage response (invalid — semantic errors):**
```json
{
  "valid": false,
  "mode": "preview",
  "staged": false,
  "kr_version": "kr-3",
  "error_count": 1,
  "errors": [
    {
      "code": "missing_required_field",
      "path": "curve_definitions[0].canonical_curve_id",
      "message": "canonical_curve_id is required",
      "severity": "error"
    }
  ]
}
```

HTTP status codes:
- `200` for valid payloads and semantic validation failures
- `422` for malformed/unparseable JSON (Pydantic/FastAPI default)

### Modified endpoints (KR-2 GET routes — unchanged behaviour)

The three existing KR-2 GET routes now use FastAPI dependency injection for the
managed repository.  This does not change their behaviour; it enables test isolation
for KR-3 HTTP tests via `app.dependency_overrides`.

---

## Tests Run

Location: `backend/tests/knowledge/test_kr3_import_staging.py`

Test count: 60+ tests across 15 test classes.

**Tests cannot be run in the CI sandbox (Python 3.10 / missing venv).
Run on the host with:**

```bash
cd backend
.venv/bin/pytest tests/knowledge/test_kr3_import_staging.py -v
.venv/bin/pytest tests/knowledge/ -v
```

### Test classes and coverage

| Class | AC | Description |
|---|---|---|
| `TestImportPreview` | 1 | Preview returns valid, staged=False, mode=preview, counts correct |
| `TestImportStage` | 2 | Stage returns valid, staged=True, batch_id, creates candidate records |
| `TestCandidateNonProduction` | 3 | Staged candidates not in production-eligible, approved, or seeds |
| `TestCandidateVisibility` | 4 | Staged candidates appear in list_candidates and status-summary |
| `TestEvidenceRecord` | 5 | Evidence record created with correct source_type, source_label, source_reference |
| `TestEvidenceRefs` | 6 | All staged records include evidence_refs pointing to batch evidence |
| `TestMissingSourceBlock` | 7 | Missing source block → HTTP 422; empty source_type/source_label → validation error |
| `TestMissingCanonicalCurveId` | 8 | Missing canonical_curve_id, display_name, family, product_group → error |
| `TestDuplicateCanonicalCurveId` | 9 | Duplicate canonical_curve_id in payload → error |
| `TestDuplicateAlias` | 10 | Duplicate alias in same curve_definition → error |
| `TestAliasMultipleCanonicalIds` | 11 | Same alias across two different canonical_curve_ids → error |
| `TestAliasConflictWithSeedRecords` | 12 | Alias conflict with existing seed → error; same canonical_curve_id → warning |
| `TestDisplayRuleUnknownCanonicalId` | 13 | Unknown canonical_curve_id in display rule → error |
| `TestClassificationRuleValidation` | 14 | Invalid product_group → error; invalid product_subgroup → error |
| `TestMalformedPayload` | 15 | Non-JSON body and empty object → HTTP 422 |
| `TestKR1Compatibility` | 16 | All KR-1 endpoints return 200 with correct data |
| `TestKR2Compatibility` | 17 | All KR-2 managed endpoints return 200 with correct data |
| `TestTemplatesNonProduction` | 18 | Seed layer has no template rules; staged template is candidate, not production |
| `TestNoApprovalEndpoint` | 19 | No approve/promote route exists; HTTP 404 for attempted approval paths |
| `TestCandidatesDoNotAffectKR1` | 20 | Staging does not change KR-1 curve definitions count; production IDs have no import prefix |
| `TestServiceLevel` | extra | Minimal payload valid; deterministic batch_id; normalized aliases; kr_version in response |

---

## Known Limitations

1. **In-memory storage only.** Staged candidates are lost on process restart. File-backed persistence is deferred to a later block.
2. **No approval/promotion endpoint.** Candidate review, approval, and rejection are deferred to KR-4.
3. **No management UI.** A KR management UI is deferred to KR-5.
4. **No duplicate curve-definition detection across payload + existing records.** The validator detects duplicates within the payload; it does not reject a `canonical_curve_id` that already exists as a seed record. This is intentional — candidate imports may reference the same canonical curve as a seed.
5. **Template rule seeds remain empty.** Imported template rules are staged as candidates. No template seeds are created by this block.

---

## External Testing Required

The following checks must be performed outside Claude on the user's host system:

### Automated tests

```bash
cd backend
.venv/bin/pytest tests/knowledge/test_kr3_import_staging.py -v
.venv/bin/pytest tests/knowledge/ -v
```

KR-2 baseline expected: 111 passed.
KR-3 new tests: 60+ additional.

```bash
cd frontend
npm run typecheck
npm run build
```

### Known unrelated failure (pre-existing, not a KR-3 concern)

```
tests/wells/test_las_import_service.py::TestLasImportServiceScaffold::test_no_las_parsing_in_module
```

Cause: The test reads `backend/app/wells/las_import_service.py` from inside `backend/`,
resolving incorrectly as `backend/backend/app/wells/las_import_service.py`.
This is a pre-existing path issue. **Do not fix in KR-3.**

### Live endpoint smoke tests (via curl)

See `validate_kr3_import_staging.sh` for full curl command set.

### Manual UI checks

No UI changes were made in KR-3.  Existing UI checks from KR-2 apply:

1. Open Data / MDP.
2. Confirm existing subgroup display still works.
3. Load selected curves to WDV.
4. Confirm loaded curves appear in Loaded Curves.
5. Confirm no tracks auto-populate.

---

## Confirmations

| Requirement | Status |
|---|---|
| No KR management UI built | CONFIRMED |
| No approval/promotion HTTP endpoint added | CONFIRMED |
| Candidate records are non-production | CONFIRMED — `GovernanceStatus.CANDIDATE` excluded from `PRODUCTION_STATUSES` |
| No Auto-build / Build from Selected built | CONFIRMED |
| No WDV loaded-curves or auto-track behavior changed | CONFIRMED |
| KR-1 endpoints preserved unchanged | CONFIRMED |
| KR-2 managed endpoints preserved unchanged | CONFIRMED |
| Frontend not changed | CONFIRMED — no `.tsx`, `.ts`, `.css` files modified |
| No large hard-coded curve dictionary added | CONFIRMED |
| No database migration | CONFIRMED |
| Known LAS path failure not touched | CONFIRMED |
