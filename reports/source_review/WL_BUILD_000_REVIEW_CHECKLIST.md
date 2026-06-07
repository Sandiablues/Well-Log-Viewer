# WL-BUILD-000 — Equinor Source Review / Dependency Validation

## Purpose

Diagnostic only. No product scaffold and no MultiViewer implementation.

## Questions to answer

1. Which exact @equinor/videx-wellog package version is available?
2. What license is declared?
3. What peer dependencies and runtime dependencies are declared?
4. What React / TypeScript compatibility risks exist?
5. Which ViDEx components should MultiViewer wrap first?
6. What input/data shape does ViDEx expect?
7. What examples or Storybook files show correct usage?
8. What adapter is needed from MultiViewer well_multitrack_v1?
9. Does webviz-subsurface-components add useful wrapper examples?
10. Are there reasons not to use webviz as the base architecture?

## Architecture rule

MultiViewer MSI remains the backend authority.

Equinor ViDEx is only the frontend rendering component layer.

Do not make Equinor's internal data shape the backend API contract.

## Acceptance

Pass only if the review supports using ViDEx as an adapter-wrapped renderer
without violating MSI/backend ownership.
