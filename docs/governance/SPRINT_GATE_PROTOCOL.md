# Sprint Gate Protocol

This protocol governs all Seismic Viewer development sprints/blocks.

A sprint is not a continuous coding run. A sprint is a sequence of gated stages.

If a gate fails, implementation must stop. The agent must not continue building on deficient code.

---

## Gate 0 — Preflight Architecture Review

Before any code change, inspect the target area.

The agent must identify:

- Target files/directories
- Correct architecture owner
- Existing service boundary
- Existing data contract
- Current frontend/backend responsibility split
- Known brittle patterns
- Test coverage status
- Whether the target area is fit for feature work

If the target area is structurally deficient, stop.

Do not implement the feature.

Produce a structural-fix report or recommend a remediation sprint.

---

## Gate 1 — Contract / Model Validation

Before implementation, validate that the required contract/model exists.

Check:

- Is the backend contract explicit?
- Is lifecycle state backend-owned?
- Are data shapes defined?
- Are allowed actions defined?
- Are error states defined?
- Can the behavior be tested?
- Does the frontend only render the contract?

If the contract is missing, weak, or ambiguous, stop.

Do not proceed to UI or feature code.

---

## Gate 2 — Implementation Validation

Implementation may proceed only after Gate 0 and Gate 1 pass.

Implementation must remain inside the allowed files.

The agent may make one bounded implementation attempt.

If the implementation exposes ownership, lifecycle, contract, or component-structure problems, stop.

Do not patch around the problem.

---

## Gate 3 — Integration / Test Validation

After implementation, run the required tests/build/manual checks.

If the failure is a simple local defect, one correction attempt is allowed.

If the failure indicates structural weakness, contract mismatch, lifecycle ambiguity, or brittle component behavior, stop.

Produce a structural-fix report.

---

## Sprint Types

Every sprint must be one of:

### 1. Diagnostic Sprint

Inspect only. No code changes.

Use when root cause, ownership, contract state, or risk is unclear.

### 2. Remediation Sprint

Repair structure, service boundaries, contracts, or test coverage.

No new product feature work.

### 3. Feature Sprint

Add functionality only after the affected area passes Gate 0 and Gate 1.

No feature sprint may begin until the target area is fit for modification.

---

## Foundation Gate Rule

Before implementing a sprint/block, the agent must validate that the target files, service ownership, data contracts, and component boundaries are fit for the proposed change.

If the target area is structurally deficient, the agent must not continue implementing the requested feature.

The sprint must stop and produce a structural-fix report or a remediation block.

---

## Mandatory Preflight Classification

Every sprint must begin with:

- Sprint type: Diagnostic / Remediation / Feature
- Target area:
- Architecture owner:
- Risk level:
- Existing contract:
- Target files:
- Is target area fit for implementation? yes/no
- If no, recommended remediation:

---

## Mandatory Gate Result

Every result bundle must include:

- Gate 0 result:
- Gate 1 result:
- Gate 2 result:
- Gate 3 result:
- Did any gate fail?
- If a gate failed, was implementation stopped?
- Structural-fix report required? yes/no
