# WBV Canonical Depth-Unit Contract — Foundation V1.0.0

This document defines the architecture that future WBV depth-unit work must obey.

## Canonical runtime domain
- Runtime depth geometry: **metres**
- Display unit: `m | ft`
- Source records retain their native unit and provenance.

## Immutable under display-unit switching
- displayed well IDs
- active well
- trajectory/model-space `x/y/z`
- east/north departure model geometry
- trajectory point count
- canonical MD/TVD/TVDSS
- bounding/model geometry
- camera
- rotation center
- layer IDs and counts
- curve sample attachment
- core chunk attachment
- formation/lithology/completion physical locations
- saved interaction canonical values

## Allowed to change
- displayed numerical text
- displayed unit labels
- interpretation of newly typed depth input
- display preference
- dogleg presentation basis (`deg/30m` vs `deg/100ft`)

## Layer migration rule
Every depth-bearing layer must normalize source depths to canonical metres at its
data boundary before being consumed by WBV geometry. The m/ft control must never
be responsible for normalizing layer geometry.

## Forbidden mechanisms
- re-fetching viewer packages solely to change display units
- replacing multi-well scene membership on a unit switch
- scaling Three.js/model coordinates on a unit switch
- converting bounding-box spatial axes on a unit switch
- persisting converted scientific depths
- assigning display preferences independently to each displayed well
- changing package identity solely to update a label/readout
