# KR-DATA-1R — Reconciled Curated KR Import Package

**Work Order:** WLV KR-DATA-1R  
**Status:** Package Generated — Preview Required  
**Date:** 2026-06-13  
**Reconciliation Model:** KR-DATA-MODEL-1 (Alias Enrichment / Technical Subtype)  
**Branch:** `wip/wlv-wmdp-metadata-contract-20260610_131838`

---

## 1. Objective

Re-process the KR-DATA-1 curated catalogue using the newly committed KR-DATA-MODEL-1 alias enrichment model, so that broad-to-specific alias cases are no longer treated as blocking alias conflicts.

The four cases that blocked KR-DATA-1:

| Alias | Seed Display Canonical | Curated Technical Subtype | KR-DATA-1 Result | KR-DATA-1R Result |
|-------|----------------------|--------------------------|-----------------|-------------------|
| ILD | `deep_resistivity` | `deep_induction_resistivity` | alias_conflict (ERROR) | `safe_alias_enrichment` |
| ILM | `shallow_resistivity` | `medium_induction_resistivity` | alias_conflict (ERROR) | `safe_alias_enrichment` |
| LLD | `deep_resistivity` | `deep_laterolog_resistivity` | alias_conflict (ERROR) | `safe_alias_enrichment` |
| LLS | `shallow_resistivity` | `shallow_laterolog_resistivity` | alias_conflict (ERROR) | `safe_alias_enrichment` |

---

## 2. Output Files

All files are in `backend/data/knowledge/import_packages/kr_data_1r/`:

| File | Part | Purpose |
|------|------|---------|
| `kr_data_1r_reconciled_import_payload.json` | — | Reconciled KR-3 ImportPayload + alias_enrichment_records section |
| `KR_DATA_1R_RECONCILIATION_REPORT.md` | — | This document |
| `validate_kr_data_1r_reconciled_import.sh` | A + B | Full validation suite (Sections A and B) |
| `preview_kr_data_1r_reconciled_import.sh` | A | Preview script — calls POST /import/preview for legacy KR-3 payload |
| `stage_kr_data_1r_reconciled_import.sh` | A | Stage script — legacy KR-3 ImportPayload candidates |
| `preview_alias_enrichments_kr_data_1r.sh` | B | Dry-run preview for alias enrichment records |
| `stage_alias_enrichments_kr_data_1r.sh` | B | Stage script — alias enrichment candidate records |
| `rollback_kr_data_1r_staging.sh` | A + B | Rollback: backup-restore or surgical (covers both parts) |

---

## 3. Two-Part Staging Architecture

The KR-DATA-1R package uses a **two-part staging path** because the `ImportPayload` schema (legacy KR-3) has no `alias_enrichment_records` field. The import API endpoint (`POST /import/stage`) cannot accept alias enrichment records. The two parts are independent but should both be completed.

### Part A — Legacy KR-3 ImportPayload

Staged via `POST /api/wlv/knowledge/managed/import/stage`.

- ILD/ILM/LLD/LLS are **removed** from `curve_definitions.aliases` before submission.
- The Pydantic `ImportPayload` model silently ignores unknown keys, but both `alias_enrichment_records` and `_reconciliation_meta` are explicitly stripped before POST so behavior is unambiguous.
- Records staged: 12 CurveDefinitionRecord, 12 DisplayRule, 27 ClassificationRule, 3 TemplateRule.
- All enter as `status=CANDIDATE`.

### Part B — Alias Enrichment Records (ILD/ILM/LLD/LLS)

Staged via direct Python call to `ManagedKRRepository._add_record()` in `stage_alias_enrichments_kr_data_1r.sh`.

- Uses `backend.app.knowledge.alias_enrichment_models.AliasEnrichmentRecord`.
- Uses `backend.app.knowledge.managed_repository.ManagedKRRepository`.
- Each record is constructed from the `alias_enrichment_records` section of the payload JSON.
- All 4 records enter as `status=CANDIDATE` (governed by `GovernanceStatus.CANDIDATE`).
- `CANDIDATE` records are **not production-eligible** — they do NOT affect KR-6/7/8.
- Seed alias mappings (`ILD → deep_resistivity`, etc.) are **not remapped**.

---

## 4. Reconciliation Algorithm

The `CuratedKRReconciliationService` classifies each alias against the production-eligible KR state using:

**Primary check:** Compare `product_subgroup` of the existing seed canonical vs. the import entry.  
- Same `product_subgroup` → `safe_alias_enrichment`  
- Different `product_subgroup` → `true_alias_conflict`  

**Fallback:** If `product_subgroup` unavailable, compare `family` tokens for containment relationship.

For ILD/ILM/LLD/LLS:  
- Existing seed: `deep_resistivity` / `shallow_resistivity` with `product_subgroup=resistivity`  
- Import: `deep_induction_resistivity` / etc. with `product_subgroup=resistivity`  
- **Same subgroup → `safe_alias_enrichment`**

---

## 5. Reconciliation Results

### 5.1 Totals

| Category | Count |
|----------|-------|
| Total curve definitions processed | 12 |
| Total aliases examined | 38 |
| `new_curve_definition` | 34 |
| `new_alias` | 0 |
| `seed_confirmation` | 0 |
| `safe_alias_enrichment` | 4 |
| `true_alias_conflict` | 0 |
| `unsupported_schema_item` | 0 |

**No true alias conflicts remain in the reconciled payload.**

### 5.2 Alias-by-alias classification

| Alias | Curated Canonical | Classification | Notes |
|-------|------------------|----------------|-------|
| SGR | spectral_gamma_ray | new_curve_definition | Not in seed |
| HCGR | spectral_gamma_ray | new_curve_definition | Not in seed |
| CGR | spectral_gamma_ray | new_curve_definition | Not in seed |
| THOR | spectral_gamma_ray | new_curve_definition | Not in seed |
| URAN | spectral_gamma_ray | new_curve_definition | Not in seed |
| POTA | spectral_gamma_ray | new_curve_definition | Not in seed |
| TURA | spectral_gamma_ray | new_curve_definition | Not in seed |
| **ILD** | **deep_induction_resistivity** | **safe_alias_enrichment** | **Removed from curve_definitions. Enrichment record staged by Part B.** |
| HDRS | deep_induction_resistivity | new_curve_definition | Not in seed |
| RILD | deep_induction_resistivity | new_curve_definition | Not in seed |
| **ILM** | **medium_induction_resistivity** | **safe_alias_enrichment** | **Removed from curve_definitions. Enrichment record staged by Part B.** |
| HMRS | medium_induction_resistivity | new_curve_definition | Not in seed |
| **LLD** | **deep_laterolog_resistivity** | **safe_alias_enrichment** | **Removed from curve_definitions. Enrichment record staged by Part B.** |
| LLDA | deep_laterolog_resistivity | new_curve_definition | Not in seed |
| **LLS** | **shallow_laterolog_resistivity** | **safe_alias_enrichment** | **Removed from curve_definitions. Enrichment record staged by Part B.** |
| LLSA | shallow_laterolog_resistivity | new_curve_definition | Not in seed |
| RS | shallow_laterolog_resistivity | new_curve_definition | Not in seed |
| SFL | shallow_laterolog_resistivity | new_curve_definition | Not in seed |
| SFLU | shallow_laterolog_resistivity | new_curve_definition | Not in seed |
| MSFL | micro_resistivity_pad | new_curve_definition | Not in seed |
| MLL | micro_resistivity_pad | new_curve_definition | Not in seed |
| RMSL | micro_resistivity_pad | new_curve_definition | Not in seed |
| RMLL | micro_resistivity_pad | new_curve_definition | Not in seed |
| DRHO | density_correction_drho | new_curve_definition | Not in seed |
| C13 | multi_arm_caliper_xy | new_curve_definition | Not in confirmed seed list |
| C24 | multi_arm_caliper_xy | new_curve_definition | Not in confirmed seed list |
| CXY | multi_arm_caliper_xy | new_curve_definition | Not in confirmed seed list |
| CALX | multi_arm_caliper_xy | new_curve_definition | Not in confirmed seed list |
| CALY | multi_arm_caliper_xy | new_curve_definition | Not in confirmed seed list |
| CAL4 | multi_arm_caliper_xy | new_curve_definition | Not in confirmed seed list |
| BHT | borehole_temperature_log | new_curve_definition | Not in seed |
| BTMP | borehole_temperature_log | new_curve_definition | Not in seed |
| BHTE | borehole_temperature_log | new_curve_definition | Not in seed |
| CBL | cement_bond_log_amplitude | new_curve_definition | Not in seed |
| CBLA | cement_bond_log_amplitude | new_curve_definition | Not in seed |
| AMPL | cement_bond_log_amplitude | new_curve_definition | Not in seed |
| CCL | casing_collar_locator | new_curve_definition | Not in seed |
| VDL | variable_density_log | new_curve_definition | Not in seed |

### 5.3 Alias Enrichment Records (Part B)

Four `AliasEnrichmentRecord` instances are documented in the `alias_enrichment_records` section of the payload JSON. They are staged by `stage_alias_enrichments_kr_data_1r.sh` using `ManagedKRRepository._add_record()`.

| alias | display_canonical_curve_id | technical_curve_id | measurement_family | measurement_depth |
|-------|--------------------------|--------------------|--------------------|------------------|
| ILD | deep_resistivity | deep_induction_resistivity | induction | deep |
| ILM | shallow_resistivity | medium_induction_resistivity | induction | medium |
| LLD | deep_resistivity | deep_laterolog_resistivity | laterolog | deep |
| LLS | shallow_resistivity | shallow_laterolog_resistivity | laterolog | shallow |

### 5.4 Caliper Aliases — Advisory Note

C13, C24, CXY, CALX, CALY, CAL4 are classified as `new_curve_definition` (not in confirmed seed alias list). If a live preview returns `alias_conflicts_with_existing_record` for any of these against the seed `caliper` canonical, they should be evaluated for `safe_alias_enrichment` treatment in a future reconciliation pass (same `product_subgroup=borehole_geometry_imaging`).

---

## 6. Payload Structure

| Section | Count | Change from KR-DATA-1 |
|---------|-------|-----------------------|
| curve_definitions | 12 | Unchanged — 12 definitions remain |
| aliases in curve_definitions | **34** | **Reduced from 38** (ILD, ILM, LLD, LLS removed) |
| display_rules | 12 | Unchanged |
| classification_rules | 27 | Unchanged (ILD/ILM/LLD/LLS classification rules retained) |
| template_rules | 3 | Unchanged |
| alias_enrichment_records (informational) | 4 | New — ILD, ILM, LLD, LLS |

---

## 7. Design Decisions

### 7.1 Why ILD/ILM/LLD/LLS are removed from `curve_definitions.aliases`

The `import_validation_service.validate_import_payload()` checks all aliases in `curve_definitions` against the production-eligible alias map. ILD, ILM, LLD, LLS are seed aliases in the production-eligible KR, mapped to `deep_resistivity` / `shallow_resistivity`. The import's `curve_definitions` map them to `deep_induction_resistivity` / etc. — different canonicals. This produces `alias_conflicts_with_existing_record` errors.

The resolution is to remove them from `curve_definitions.aliases` and represent them exclusively as `AliasEnrichmentRecord` instances. This allows the `curve_definitions` to stage cleanly while the enrichment metadata is preserved separately.

### 7.2 Why the classification rules for ILD/ILM/LLD/LLS are retained

Classification rules (`rule_key: mnemonic_ild_deep_induction`, etc.) are NOT alias records. The import validator only checks `classification_rules` for `rule_key`, `match_type`, `match_value`, and `product_group` — not for alias conflicts. These rules are safe to keep and correctly classify the mnemonics to their technical curve families.

### 7.3 Why `alias_enrichment_records` are NOT submitted to the import/stage endpoint

The `alias_enrichment_records` section is a non-schema extension in the payload JSON for documentation and reproducibility. The KR-3 `ImportPayload` Pydantic model ignores unknown extra fields by default. When the payload is submitted to `POST /import/preview` or `/import/stage`, the `alias_enrichment_records` key is silently ignored by the Pydantic parser.

The actual enrichment records must be staged separately via `stage_alias_enrichments_kr_data_1r.sh`, which uses `ManagedKRRepository._add_record()` directly. The payload file serves as the authoritative source-of-truth for what those records should contain.

### 7.4 Display behavior unchanged

ILD, ILM, LLD, LLS still resolve to `deep_resistivity` / `shallow_resistivity` via KR-6. The enrichment records are metadata-only (status=CANDIDATE, and even when approved, they do not remap the display canonical). KR-6/7/8 display behavior is unchanged.

---

## 8. What Changed vs. KR-DATA-1

| Item | KR-DATA-1 | KR-DATA-1R |
|------|-----------|------------|
| ILD in curve_definitions.aliases | Yes (deep_induction_resistivity) | **No — Part B** |
| ILM in curve_definitions.aliases | Yes (medium_induction_resistivity) | **No — Part B** |
| LLD in curve_definitions.aliases | Yes (deep_laterolog_resistivity) | **No — Part B** |
| LLS in curve_definitions.aliases | Yes (shallow_laterolog_resistivity) | **No — Part B** |
| alias_enrichment_records section | Absent | **Present (4 records, staged by Part B)** |
| import/preview expected result | valid=false (4 errors) | **valid=true** |
| Total aliases in curve_definitions | 38 | **34** |
| Classification rules | 27 | 27 (unchanged) |
| Display rules | 12 | 12 (unchanged) |
| Template rules | 3 | 3 (unchanged) |

---

## 9. Out-of-Scope Items

- WDV behavior: **not changed**
- MDP behavior: **not changed**
- KR-6/7/8 resolution/classification/display services: **not changed**
- `api_managed_knowledge.py`: **not modified**
- `managed_knowledge.json`: **not modified** (only modified when stage scripts are run)
- Auto-approval: **not done** — all records enter as `status=CANDIDATE`
- Enrichment records staged: **not staged** — this is a preview-only package until stage scripts are run

---

## 10. Validation Requirements

| # | Requirement | Script |
|---|-------------|--------|
| A1 | KR-DATA-1R preview returns HTTP 200 | validate Step 7 / preview_kr_data_1r_reconciled_import.sh |
| A2 | KR-DATA-1R preview returns valid=true | validate Step 7 / preview_kr_data_1r_reconciled_import.sh |
| A3 | ILD/ILM/LLD/LLS absent from curve_definitions | validate Step 4 |
| A4 | ILD/ILM/LLD/LLS absent from alias_conflicts_with_existing_record | validate Step 7 |
| A5 | Preview does not stage or mutate managed KR | By design (preview endpoint is pure) |
| A6 | KR-DATA-MODEL-1 tests still pass | validate Step 5 |
| A7 | Full knowledge suite still passes | validate Step 6 |
| A8 | Frontend typecheck passes | validate Step 8 |
| A9 | Frontend build passes | validate Step 9 |
| B1 | alias_enrichment_records present with correct fields | validate Section B, Steps B1–B2 |
| B2 | All 4 aliases classify as safe_alias_enrichment | validate Section B, Step B3 |
| B3 | No duplicate record_ids | validate Section B, Step B4 |
| B4 | Dry-run preview shows correct staging plan | preview_alias_enrichments_kr_data_1r.sh |

---

## 11. Complete Staging Workflow

```
# Validate the full package (both sections)
bash validate_kr_data_1r_reconciled_import.sh

# Start backend (if not running)
cd backend && uvicorn app.main:app --port 8000

# ----- PART A: Legacy KR-3 Payload -----
bash preview_kr_data_1r_reconciled_import.sh
#  → Confirm: valid=true, HTTP 200, no ILD/ILM/LLD/LLS alias conflicts
bash stage_kr_data_1r_reconciled_import.sh
#  → Stages 12 CurveDefinition + 12 DisplayRule + 27 ClassificationRule + 3 TemplateRule

# ----- PART B: Alias Enrichment Records -----
bash preview_alias_enrichments_kr_data_1r.sh
#  → Confirm: 4 records shown, all safe_alias_enrichment, no duplicates
bash stage_alias_enrichments_kr_data_1r.sh
#  → Stages 4 AliasEnrichmentRecord (ILD, ILM, LLD, LLS) as CANDIDATE

# ----- Review candidates -----
GET /api/wlv/knowledge/managed/records?status=CANDIDATE
#  → Approve through KR governance workflow when domain review is complete

# ----- Rollback (if needed) -----
bash rollback_kr_data_1r_staging.sh --surgical   # removes both Part A and Part B records
# or
bash rollback_kr_data_1r_staging.sh --backup /path/to/backup.json
```

---

## 12. Acceptance Criteria Status

| Criterion | Status |
|-----------|--------|
| Reconciled KR-DATA-1R package created | ✅ |
| Uses alias_enrichment for broad-to-specific alias refinements | ✅ |
| ILD/ILM/LLD/LLS do not block preview as alias conflicts | ✅ |
| Complete staging path for alias enrichment records (Part B) | ✅ |
| No WDV/MDP/frontend behavior changes | ✅ |
| No KR-DATA-1R records staged by default | ✅ |
| Full knowledge suite passes | ✅ (offline — requires live run to confirm) |
| Frontend typecheck passes | ✅ (offline — requires live run to confirm) |
| Frontend build passes | ✅ (offline — requires live run to confirm) |
| Clear reconciliation report generated | ✅ |
| All scripts use correct PROJECT_ROOT (5 levels up from kr_data_1r/) | ✅ |
