# MultiViewer Master Presentation Contract V1.0.0

## Purpose

This directory is the canonical application-presentation contract shared by WLV / WDV / WBV / SDV.

WLV remains the canonical application-style authority. SDV, WBV, WDV, and WLV may retain
domain-specific scientific rendering, but application chrome should converge on this contract.

## Layer order

1. `foundations.css`
   - typography
   - spacing
   - control heights
   - radii
   - border widths
   - modal dimensions

2. `theme.css`
   - dark/light neutral palette
   - application surfaces
   - text hierarchy
   - neutral controls and borders

3. `semantics.css`
   - meaning-bearing colors and states
   - success / warning / danger / info / selection
   - domain-independent semantic state only

4. `components.css`
   - canonical component identity and geometry
   - `.mv-*` application chrome primitives

5. `compatibility.css`
   - legacy aliases and transitional mappings only
   - must not become a second theme

## Governance rules

- Style is component identity and geometry.
- Theme is neutral palette.
- Semantics is meaning.
- Scientific rendering is viewer/domain-owned.
- Never globally replace scientific colors through the application theme.
- New shared application chrome should prefer `.mv-*` components or shared variables.
- Legacy page-specific overrides remain valid during migration but should be retired only after
  a matching component has moved onto the master contract.
- Dark/light switching must change theme variables, not component geometry.
- WLV application chrome is the reference when exact parity decisions are required.

## Scientific-rendering exclusions

Examples that must remain outside the master application theme:

- SDV seismic palettes, amplitudes, horizons, faults, seismic canvas.
- WBV 3D wellbore/material rendering and scientific overlays.
- WDV/WLV curves, lithology, formation tops, completion symbology and scientific colors.
- Any domain-specific QA/QC or confidence visualization whose color carries scientific meaning.

## Migration policy

Migration must be staged and auditable. Do not remove a legacy rule merely because an equivalent
master component exists. First migrate a specific UI surface, verify rendered parity and functional
behavior, then retire the redundant legacy rule in a separate package.
