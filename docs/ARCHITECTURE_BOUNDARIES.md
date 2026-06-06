# Architecture Boundaries

The local desktop app is being hardened into a single-node local deployment profile of a broader enterprise-shaped architecture.

## Boundaries

1. Viewer UI  
   React/Vite frontend and rendering components.

2. Backend API  
   FastAPI route layer. Route files should stay thin.

3. Metadata Service Layer  
   Canonical metadata, normalized metadata, completeness, validation, evidence, and scoring.

4. Report Service  
   Shared report rendering, templates, and CSS.

5. Ingestion / Worker Service  
   SEG-Y indexing, header extraction, optimized Zarr conversion, durable jobs, and cache promotion.

6. Storage Layer  
   Local filesystem now; NAS/object storage later through an abstraction.

7. Ops / Runtime  
   Launcher contract, health checks, diagnostics, backup/sync, and later container startup.

## Immediate rule

Report formatting must not live inside large route-handler HTML/CSS blocks.
