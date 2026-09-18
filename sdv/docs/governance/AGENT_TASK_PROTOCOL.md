# Agent Task Protocol

Every AI-assisted task must include:

- Block Name
- Objective
- Scope
- Explicit Exclusions
- Allowed Files
- Forbidden Files
- Architecture Owner
- Current Contract
- Implementation Steps
- Required Tests
- Manual Checks
- Stop Conditions
- Result Bundle Required

Standard instruction:

Follow docs/governance/AI_DEVELOPMENT_RULES.md.
Follow docs/governance/SEISMIC_VIEWER_CONTROL_PACK.md.
Work only within this block.
Do not make autonomous architecture changes.
Do not perform repeated micro-patching.
Do not touch files outside the allowed list.
Stop and produce a structural-fix report if ownership, lifecycle, contract, or component-structure problems appear.
Return a result bundle.
## Required Sprint Gate Section

Every agent task must include this gate section before implementation:

### Sprint Type

Diagnostic / Remediation / Feature

### Gate 0 — Preflight Architecture Review

- Target area:
- Architecture owner:
- Existing contract:
- Target files:
- Known brittle patterns:
- Test coverage:
- Fit for implementation: yes/no

If no, stop and produce a structural-fix report.

### Gate 1 — Contract / Model Validation

- Backend contract exists: yes/no
- Lifecycle/backend truth owner clear: yes/no
- Frontend render-only role clear: yes/no
- Error states defined: yes/no
- Testable behavior: yes/no

If no, stop and create a remediation sprint.

### Gate 2 — Implementation Validation

Implementation may proceed only if Gate 0 and Gate 1 pass.

One bounded implementation attempt only.

### Gate 3 — Integration / Test Validation

Run required tests/build/manual checks.

If failure is structural, stop. Do not keep patching.

## Updated Standard Agent Instruction

Follow docs/governance/AI_DEVELOPMENT_RULES.md.
Follow docs/governance/SEISMIC_VIEWER_CONTROL_PACK.md.
Follow docs/governance/SPRINT_GATE_PROTOCOL.md.
Work only within this sprint block.
Classify the sprint as Diagnostic, Remediation, or Feature.
Run Gate 0 and Gate 1 before implementation.
Do not build on deficient code.
Do not make autonomous architecture changes.
Do not perform repeated micro-patching.
Do not touch files outside the allowed list.
Stop and produce a structural-fix report if ownership, lifecycle, contract, or component-structure problems appear.
Return a gated result bundle.
