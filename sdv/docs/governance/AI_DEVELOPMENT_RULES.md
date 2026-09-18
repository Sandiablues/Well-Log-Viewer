# AI Development Rules — Immutable Project Governance

These rules govern all AI-assisted development on this project.

## Core Rules

1. Architecture first.
2. One bounded implementation attempt per block.
3. No brittle micro-patching.
4. Backend owns lifecycle, metadata, QAQC, source classification, and managed-state truth.
5. Frontend renders backend-owned contracts only.
6. Service boundaries are mandatory.
7. Large mixed-responsibility files are risk zones.
8. Allowed and forbidden files must be defined before each block.
9. Stop if ownership, lifecycle, contract, or component structure is unclear.
10. If stopped, produce a structural-fix report.
11. Tests/build gates define completion.
12. Every block requires a result bundle.
13. No scope drift.
14. Existing working behavior must be protected.
15. Project-specific control packs override generic AI suggestions.
16. Agents may implement within the architecture, not redefine it.
17. Commit only stable blocks.
18. Documentation must track architecture changes.
19. Quality over speed.
## Sprint Gate Rule

A sprint/block is not a continuous coding run.

Every sprint must pass internal gates before implementation continues:

- Gate 0: Preflight Architecture Review
- Gate 1: Contract / Model Validation
- Gate 2: Implementation Validation
- Gate 3: Integration / Test Validation

If Gate 0 or Gate 1 fails, no coding may continue.

If Gate 2 exposes ownership, lifecycle, contract, or component-structure problems, stop.

If Gate 3 fails because of structural weakness rather than a simple local defect, stop.

Do not build new functionality on deficient code.

## Sprint Type Rule

Every sprint must be classified as one of:

- Diagnostic sprint: inspect only, no code changes
- Remediation sprint: repair structure/contracts/tests, no new feature work
- Feature sprint: add functionality only after the affected area passes preflight and contract validation

No feature sprint may begin until the affected area passes Gate 0 and Gate 1.

## Foundation Gate Rule

Before implementing a sprint/block, validate that the target files, service ownership, data contracts, and component boundaries are fit for the proposed change.

If the target area is structurally deficient, stop and produce a structural-fix report or create a remediation sprint.

Do not continue developing on deficient code inside the same sprint.
