# KR1 Implementation Report
## WLV Knowledge Repository — Block KR-1

**Project:** MultiViewer / Well Log Viewer  
**Block:** KR-1 — Backend-Owned Read-Only Knowledge Repository Contract  
**Date:** 2026-06-12  
**Status:** Applied — external runtime validation required

---

## Summary

KR-1 establishes a backend-owned, read-only Knowledge Repository service for WLV. It centralises product groups, product subgroups, subgroup ordering, canonical curve definitions, display rules, and template seeds behind five new read-only API endpoints. The frontend now renders backend-provided contracts rather than owning classification truth locally.

---

## Files Changed

### New files

| File | Purpose |
|------|---------|
| `backend/app/knowledge/models.py` | Pydantic response models for all KR-1 contracts |
| `backend/app/knowledge/repository.py` | Seed repository — wraps vocabulary and curve_knowledge behind KR boundary |
| `backend/app/knowledge/api_knowledge.py` | FastAPI router for all 5 KR endpoints |
| `backend/tests/knowledge/test_kr1_knowledge_repository.py` | 26 unit + HTTP endpoint tests for KR-1 |
| `apply_kr1_patch.sh` | Backup and verify KR-1 is applied |
| `rollback_kr1_patch.sh` | Remove KR-1 files and restore pre-KR-1 state |
| `validate_kr1.sh` | Static validation (21 checks) + external testing instructions |
| `KR1_IMPLEMENTATION_REPORT.md` | This document |

### Modified files

| File | Change |
|------|--------|
| `backend/app/main.py` | +2 lines: import and register `knowledge_router` |
| `frontend/src/wells/prototype/TrackLayoutPrototype.tsx` | Replaced frontend-owned KR constants/functions with backend-fetched contracts |

---

## New Endpoints

All endpoints are under `/api/wlv/knowledge/` and are read-only (GET).

### `GET /api/wlv/knowledge/health`

```json
{
  "service": "wlv_knowledge_repository",
  "status": "ok",
  "mode": "read_only",
  "version": "kr-1",
  "product_group_count": 8,
  "curve_definition_count": 10,
  "display_rule_count": 10,
  "template_count": 0
}
```

### `GET /api/wlv/knowledge/product-groups`

Returns 8 ordered product groups, each with ordered subgroups. Example:

```json
{
  "version": "kr-1",
  "groups": [
    {
      "key": "open_hole_logs",
      "label": "Open-hole Logs",
      "order": 10,
      "subgroups": [
        { "key": "gamma_ray",   "label": "Gamma Ray",   "order": 10 },
        { "key": "resistivity", "label": "Resistivity", "order": 30 }
      ]
    }
  ]
}
```

### `GET /api/wlv/knowledge/curve-definitions`

Returns canonical curve definitions with aliases and product classification.

```json
{
  "version": "kr-1",
  "curve_definitions": [
    {
      "canonical_curve_id": "gamma_ray",
      "display_name": "Gamma Ray",
      "family": "Gamma Ray",
      "product_group": "open_hole_logs",
      "product_subgroup": "gamma_ray",
      "default_unit": "API",
      "aliases": ["GR", "GAM", "GRC", "ECGR", "HGR", "GR_EDTC"]
    }
  ]
}
```

### `GET /api/wlv/knowledge/display-rules`

Returns display rendering rules separate from curve identity.

```json
{
  "version": "kr-1",
  "display_rules": [
    {
      "canonical_curve_id": "gamma_ray",
      "preferred_track_family": "gamma_ray_sp",
      "scale_type": "linear",
      "display_min": 0.0,
      "display_max": 200.0,
      "default_unit": "API",
      "reverse_scale": false,
      "overlay_group": "Gamma Ray"
    }
  ]
}
```

### `GET /api/wlv/knowledge/templates`

```json
{ "version": "kr-1", "templates": [] }
```

---

## Architecture

### Backend ownership boundary

The `KnowledgeRepository` class in `repository.py` wraps the existing vocabulary (`well_log_vocabulary.py`) and curve knowledge (`curve_knowledge.py`) behind the KR service boundary. KR-1 seed data is Python constants but isolated from the API surface. A future KR management system can replace or extend the seed without any frontend changes.

### Frontend changes

Removed frontend-owned KR truth:

| Removed | Replaced with |
|---------|--------------|
| `OPEN_HOLE_SUBGROUP_ORDER` (constant) | Backend-provided `KrSubgroup.order` |
| `OPEN_HOLE_FALLBACK_SUBGROUP_LABELS` (constant) | Backend-provided `KrSubgroup.label` |
| `openHoleSubgroups()` (function) | `groupProductItemsByKrSubgroups()` using backend data |

Added:
- `KrSubgroup`, `KrProductGroup`, `KrProductGroupsPayload` types
- `groupProductItemsByKrSubgroups()` — renders backend-provided subgroups for **any** product group (not just open_hole)
- `krProductGroups` state — fetched on mount from `/api/wlv/knowledge/product-groups`
- KR fetch is **non-fatal**: if the endpoint is unavailable, subgrouping degrades gracefully to a flat item list

---

## Tests Run

### Static validation (in sandbox — 21 checks)

```
bash validate_kr1.sh
Passed: 21  Failed: 0
```

Checks:
- All 4 new backend files present
- All new Python files pass `ast.parse()` syntax check
- `main.py` has correct import and `include_router` call
- Frontend: `OPEN_HOLE_SUBGROUP_ORDER` absent
- Frontend: `OPEN_HOLE_FALLBACK_SUBGROUP_LABELS` absent
- Frontend: `openHoleSubgroups()` absent
- Frontend: KR types present (`KrProductGroup`, `KrSubgroup`, etc.)
- Frontend: `groupProductItemsByKrSubgroups` present
- Frontend: `krProductGroups` state present
- Frontend: `/api/wlv/knowledge/product-groups` fetch call present

### Runtime tests

**Not run by Claude.** The project venv is a macOS `.venv` that cannot be invoked in the sandbox environment. All runtime, endpoint, and browser tests must be executed externally. See **External Testing Required** section.

---

## Known Limitations

### Subgroup key alignment (deferred to KR-2)

The work order recommends these open-hole subgroup keys for KR-1:
- `caliper_borehole_geometry`, `borehole_imaging` (split from current `borehole_geometry_imaging`)
- `spectral_gamma_ray` (currently folded into `gamma_ray`)

**KR-1 uses `borehole_geometry_imaging`** (the key already produced by `well_log_classifier.py`) to preserve existing data integrity. Renaming it would cause previously classified products with `product_subgroup_key = "borehole_geometry_imaging"` to fall to the "other/review" bucket.

The full recommended vocabulary alignment is deferred to KR-2, which should update `well_log_vocabulary.py` and migrate stored product_subgroup_key values together in a single coordinated step.

### All curve definitions are `product_group = "open_hole_logs"`

`curve_knowledge.py` defines 10 curves that are all open-hole. No cased-hole, lithology, or pressure curves are in the KR-1 curve_definitions seed. The `/api/wlv/knowledge/curve-definitions` endpoint only returns what `CURVE_DEFINITIONS` in `curve_knowledge.py` covers. Extending this to other product groups is deferred.

### Template seeding deferred

`/api/wlv/knowledge/templates` returns `[]`. Template seeding is explicitly out of scope for KR-1 per work order §9.

---

## Intentionally Deferred Items

Per work order §9 (Out of Scope):

- KR edit UI
- KR management page
- Review queue / candidate alias approval
- Import/export
- Audit log UI
- Auto-build / build from selected
- Template application
- AI/ML inference
- Broad UI redesign

None of these were implemented.

---

## Confirmations

- **No KR management UI was built.** Only 5 read-only GET endpoints.
- **No auto-build or template application was built.** Templates endpoint returns empty list.
- **WDV Loaded Curves behavior was not modified.** No changes to `wdvPackageState.ts`, `backendViewerPackageAdapter.ts`, or any viewer rendering files.
- **MDP well rows, expand/collapse, and load behavior are preserved.** The rendering logic was changed only in the product-subgroup expansion block; all other MDP behavior (search, sort, pagination, bulk actions, load/unload) is untouched.
- **No CSS was modified.**
- **No package dependencies were added.**
- **No database migration was required.** The KR is seeded from Python constants.

---

## External Testing Required

> **All runtime, endpoint, and browser validation must be performed outside Claude and reviewed through ChatGPT.**

### Endpoint checks (backend must be running on :8000)

```bash
curl -s http://127.0.0.1:8000/api/wlv/knowledge/health | python3 -m json.tool
curl -s http://127.0.0.1:8000/api/wlv/knowledge/product-groups | python3 -m json.tool
curl -s http://127.0.0.1:8000/api/wlv/knowledge/curve-definitions | python3 -m json.tool
curl -s http://127.0.0.1:8000/api/wlv/knowledge/display-rules | python3 -m json.tool
curl -s http://127.0.0.1:8000/api/wlv/knowledge/templates | python3 -m json.tool
```

**Expected:** All return HTTP 200 with `"version": "kr-1"`. `/health` returns `product_group_count: 8, template_count: 0`.

### Frontend typecheck / build

```bash
cd frontend && npm run typecheck
cd frontend && npm run build
```

**Expected:** Exits 0. If failures appear, confirm they are pre-existing (not introduced by KR-1) and document them.

### Backend tests

```bash
cd backend && .venv/bin/pytest tests/knowledge/ -v
cd backend && .venv/bin/pytest -v
```

**Expected:** All KR-1 tests pass. Any failures in pre-existing tests should be pre-existing.

### Manual MDP acceptance checks

1. Open the app and navigate to the **Data** tab (MDP)
2. Expand a well that has **open-hole logs**
3. Confirm subgroups render with backend-provided labels (e.g. "Gamma Ray", "Resistivity", "Caliper / Borehole Geometry")
4. Confirm subgroups appear in backend-provided order
5. Confirm items under each subgroup are correct
6. Check the browser console for any JavaScript errors

### Manual WDV acceptance checks

1. Select a product from MDP and click **Load**
2. Confirm the WDV opens
3. Confirm loaded curves appear in the **Loaded Curves** panel
4. Confirm curves do **not** auto-populate tracks
5. Confirm the WDV renders normally

### Expected pass criteria

| Check | Expected |
|-------|----------|
| `/api/wlv/knowledge/health` | 200, `status: ok`, `product_group_count: 8` |
| `/api/wlv/knowledge/product-groups` | 200, 8 groups, open_hole has ≥10 subgroups |
| `/api/wlv/knowledge/curve-definitions` | 200, ≥10 definitions |
| `/api/wlv/knowledge/display-rules` | 200, ≥10 rules |
| `/api/wlv/knowledge/templates` | 200, `templates: []` |
| `npm run typecheck` | Exit 0 (or pre-existing failures only) |
| `pytest tests/knowledge/` | All 26 tests pass |
| MDP subgroup rendering | Backend labels/order used |
| WDV Loaded Curves | Unchanged behaviour |
