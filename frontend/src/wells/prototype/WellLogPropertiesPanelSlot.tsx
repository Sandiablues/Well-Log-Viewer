import React, { type ReactElement, useEffect, useRef, useState } from "react";
import "../../styles/curve-editor.css";
import "../../styles/modal-control-contract.css";
import { modalControlGeometry } from "../../ui/modalControlGeometry";
import { CurveLineStyleControl, type CurveLineStyleValue } from "./CurveLineStyleControl";
import { SharedInfillEditor } from "./SharedInfillEditor";
import { KrLithologyPatternPicker } from "./KrLithologyPatternPicker";
import { WdvExternalWindowPortal } from "./WdvExternalWindowPortal";
import type {
  WdvIdentityMetadataContract,
} from "../contracts/wdvIdentityMetadataContract";
import {
  resolveManagedCurveContract,
  type ManagedCurveSampleContractsByCurveId,
} from "./managedCurveSamples";
import type {
  CompletionTrackAppearance,
  CorePresentationMode,
  CoreTrackAppearance,
  DepthRangeLocatorConfig,
  MacroCoreImageConfig,
  TextOverlayConfig,
  CurveAssignment,
  CurveCatalogItem,
  CurveTrack,
  DepthBasis,
  FillSide,
  ScaleMode,
  SelectionRef,
  WellLogTrack,
} from "./trackLayoutModel";
import { DEFAULT_COMPLETION_TRACK_APPEARANCE, DEFAULT_CORE_TRACK_APPEARANCE, DEFAULT_DEPTH_RANGE_LOCATOR_CONFIG, DEFAULT_MACRO_CORE_IMAGE_CONFIG, DEFAULT_TEXT_OVERLAY_CONFIG, resolveTrackLattice } from "./trackLayoutModel";
import type {
  PropertiesPanelSection,
} from "./wellLogPropertiesPanelContract";
import { resolvePrototypePropertiesPanelContract } from "./wellLogPropertiesPanelContract";
import {
  findCurveForAssignment,
  normalizePropertiesSelection,
} from "./propertiesSelectionModel";
import {
  DEFAULT_FORMATION_TOP_OVERLAY_STYLE,
  type CompletionComponentRecord,
  type CoreImageInventoryItem,
  type FormationTopMarker,
  type FormationTopOverlayStyle,
  type LithologyIntervalRecord,
} from "../wdv/WdvPresentationPrimitives";
import {
  curveFillPaintCapabilitiesV2,
  fetchCurveFillCapabilitiesV2,
  type CanonicalCurveFillRuleV2,
  type CurveFillCapabilitiesV2,
  type CurveFillComparisonV2,
  type CurveFillRuleTypeV2,
} from "../wdv/curveFillV2";

const CURVE_TRACK_MIN_WIDTH = 120;
const CURVE_TRACK_MAX_WIDTH = 420;

function clampCurveTrackWidth(widthPx: number): number {
  if (!Number.isFinite(widthPx)) return 220;
  return Math.max(
    CURVE_TRACK_MIN_WIDTH,
    Math.min(CURVE_TRACK_MAX_WIDTH, Math.round(widthPx)),
  );
}

function resolveCoreTrackAppearance(
  track: WellLogTrack | null | undefined,
): CoreTrackAppearance {
  if (!track || track.trackType !== "core") {
    return { ...DEFAULT_CORE_TRACK_APPEARANCE };
  }
  return {
    ...DEFAULT_CORE_TRACK_APPEARANCE,
    ...(track.coreAppearance ?? {}),
  };
}

function detectCoreOverlayPlacement(
  style: FormationTopOverlayStyle,
): "left" | "center" | "right" {
  const left = style.trackLeftInsetPct ?? 0;
  const right = style.trackRightInsetPct ?? 0;
  if (left <= 10 && right >= 30) return "left";
  if (right <= 10 && left >= 30) return "right";
  return "center";
}

const CORE_OVERLAY_LANE_PRESETS: Record<"left" | "center" | "right", { trackLeftInsetPct: number; trackRightInsetPct: number }> = {
  left: { trackLeftInsetPct: 0, trackRightInsetPct: 56 },
  center: { trackLeftInsetPct: 20, trackRightInsetPct: 20 },
  right: { trackLeftInsetPct: 56, trackRightInsetPct: 0 },
};

function PropertiesContractTable({
  sections,
  collapsible = false,
  collapsed = false,
  onToggle,
}: {
  sections: PropertiesPanelSection[];
  collapsible?: boolean;
  collapsed?: boolean;
  onToggle?: () => void;
}) {
  return (
    <div
      className={`wlv-properties-contract-table${collapsed ? " is-collapsed" : ""}`}
    >
      {sections.map((section, sectionIndex) => {
        const canCollapseSection = collapsible && sectionIndex === 0;
        return (
          <section
            key={section.sectionId}
            className="wlv-properties-contract-section"
          >
            <h3>
              {canCollapseSection ? (
                <button
                  type="button"
                  className="wlv-properties-collapse-toggle"
                  aria-expanded={!collapsed}
                  onClick={onToggle}
                >
                  <span>{collapsed ? "▸" : "▾"}</span>
                  <strong>{section.title}</strong>
                </button>
              ) : (
                section.title
              )}
            </h3>
            {canCollapseSection && collapsed ? null : (
              <table>
                <tbody>
                  {section.rows.map((row) => (
                    <tr key={`${section.sectionId}-${row.label}`}>
                      <th scope="row">{row.label}</th>
                      <td>
                        <span>{row.value}</span>
                        {row.unit ? <em>{row.unit}</em> : null}
                        {row.source ? <small>{row.source}</small> : null}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>
        );
      })}
    </div>
  );
}


function ConsolidatedPropertiesInfo({
  title,
  sections,
  collapsed,
  onToggle,
}: {
  title: string;
  sections: PropertiesPanelSection[];
  collapsed: boolean;
  onToggle: () => void;
}) {
  return (
    <div
      className={`wlv-properties-contract-table wlv-properties-consolidated-info${collapsed ? " is-collapsed" : ""}`}
    >
      <section
        className={`wlv-properties-contract-section${collapsed ? " is-collapsed" : ""}`}
      >
        <h3>
          <button
            type="button"
            className="wlv-properties-collapse-toggle"
            aria-expanded={!collapsed}
            onClick={onToggle}
          >
            <span>{collapsed ? "▸" : "▾"}</span>
            <strong>{title}</strong>
          </button>
        </h3>
        {collapsed
          ? null
          : sections.map((section) => (
              <section
                key={section.sectionId}
                className="wlv-properties-contract-section"
              >
                <h3>{section.title}</h3>
                <table>
                  <tbody>
                    {section.rows.map((row) => (
                      <tr key={`${section.sectionId}-${row.label}`}>
                        <th scope="row">{row.label}</th>
                        <td>
                          <span>{row.value}</span>
                          {row.unit ? <em>{row.unit}</em> : null}
                          {row.source ? <small>{row.source}</small> : null}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </section>
            ))}
      </section>
    </div>
  );
}

function readableTrackType(track: WellLogTrack): string {
  switch (track.trackType) {
    case "core":
      return "Core";
    case "completion":
      return "Completion";
    case "interval":
      return "Interval";
    case "raster":
      return "Raster";
    case "lithology":
      return "Lithology";
    case "curve":
      return "Curve";
    case "depth":
      return "Depth";
  }
}

function corePropertiesMetadataSection(
  items: CoreImageInventoryItem[],
): PropertiesPanelSection {
  if (items.length === 0) {
    return {
      sectionId: "core-metadata",
      title: "Core Metadata",
      rows: [
        {
          label: "Core records",
          value: "No selected core inventory record",
          source: "Managed core inventory",
        },
      ],
    };
  }

  const finiteTops = items.map((item) => item.topMd).filter(Number.isFinite);
  const finiteBases = items.map((item) => item.baseMd).filter(Number.isFinite);
  const topMd = finiteTops.length > 0 ? Math.min(...finiteTops) : null;
  const baseMd = finiteBases.length > 0 ? Math.max(...finiteBases) : null;
  const units = Array.from(new Set(items.map((item) => item.depthUnit).filter(Boolean)));
  const imageTypes = Array.from(new Set(items.map((item) => item.imageType).filter(Boolean)));
  const runs = Array.from(new Set(items.map((item) => item.runNumber).filter((value): value is string => Boolean(value))));
  const sources = Array.from(new Set(items.map((item) => item.sourceLabel).filter((value): value is string => Boolean(value))));
  const descriptionCount = items.reduce(
    (sum, item) => sum + (Number.isFinite(item.descriptionCount) ? item.descriptionCount : 0),
    0,
  );

  return {
    sectionId: "core-metadata",
    title: "Core Metadata",
    rows: [
      { label: "Core records", value: String(items.length), source: "Managed core inventory" },
      { label: "Product / segment", value: items.map((item) => item.label).join(" / "), source: "Managed core inventory" },
      { label: "Top MD", value: topMd === null ? "—" : String(topMd), unit: units[0] ?? undefined },
      { label: "Base MD", value: baseMd === null ? "—" : String(baseMd), unit: units[0] ?? undefined },
      { label: "Depth unit", value: units.join(" / ") || "—" },
      { label: "Image type", value: imageTypes.join(" / ") || "—" },
      { label: "Descriptions", value: String(descriptionCount) },
      { label: "Run", value: runs.join(" / ") || "—" },
      { label: "Source", value: sources.join(" / ") || "—" },
    ],
  };
}

function completionPropertiesMetadataSection(
  items: CompletionComponentRecord[],
): PropertiesPanelSection {
  if (items.length === 0) {
    return {
      sectionId: "completion-metadata",
      title: "Completion Metadata",
      rows: [
        {
          label: "Components",
          value: "No selected completion component",
          source: "Managed completion inventory",
        },
      ],
    };
  }

  const finiteTops = items.map((item) => item.topMd).filter(Number.isFinite);
  const finiteBases = items
    .map((item) => item.baseMd)
    .filter((value): value is number => value !== null && Number.isFinite(value));
  const topMd = finiteTops.length > 0 ? Math.min(...finiteTops) : null;
  const baseMd = finiteBases.length > 0 ? Math.max(...finiteBases) : null;
  const units = Array.from(new Set(items.map((item) => item.depthUnit).filter(Boolean)));
  const datasets = Array.from(new Set(items.map((item) => item.datasetLabel).filter(Boolean)));
  const statuses = Array.from(new Set(items.map((item) => item.status).filter((value): value is string => Boolean(value))));
  const sources = Array.from(new Set(
    items
      .map((item) => item.sourceReference ?? item.sourceDocument)
      .filter((value): value is string => Boolean(value)),
  ));
  const confidences = Array.from(new Set(items.map((item) => item.confidence).filter((value): value is string => Boolean(value))));
  const diameters = Array.from(new Set(
    items
      .map((item) => item.diameter)
      .filter((value): value is number => value !== null && Number.isFinite(value)),
  ));

  return {
    sectionId: "completion-metadata",
    title: "Completion Metadata",
    rows: [
      { label: "Components", value: String(items.length), source: "Managed completion inventory" },
      { label: "Dataset", value: datasets.join(" / ") || "—" },
      { label: "Component", value: items.map((item) => item.label).join(" / ") },
      { label: "Top MD", value: topMd === null ? "—" : String(topMd), unit: units[0] ?? undefined },
      { label: "Base MD", value: baseMd === null ? "—" : String(baseMd), unit: units[0] ?? undefined },
      { label: "Depth unit", value: units.join(" / ") || "—" },
      { label: "Diameter", value: diameters.length > 0 ? diameters.join(" / ") : "—" },
      { label: "Status", value: statuses.join(" / ") || "—" },
      { label: "Confidence", value: confidences.join(" / ") || "—" },
      { label: "Source", value: sources.join(" / ") || "—" },
    ],
  };
}

function trackPropertiesMetadataSection(
  track: WellLogTrack,
): PropertiesPanelSection {
  const rows: PropertiesPanelSection["rows"] = [
    { label: "Track", value: track.title },
    { label: "Track type", value: readableTrackType(track) },
    { label: "Width", value: String(track.widthPx), unit: "px" },
    { label: "Visible", value: track.visible ? "Yes" : "No" },
  ];

  if (track.trackType === "lithology") {
    rows.push(
      { label: "Source", value: track.sourceName || "—" },
      { label: "Well", value: track.wellName || "—" },
    );
  } else if (
    track.trackType === "interval"
    || track.trackType === "raster"
    || track.trackType === "core"
    || track.trackType === "completion"
  ) {
    rows.push(
      { label: "Track role", value: track.trackRole ?? "—" },
      { label: "Renderer", value: track.rendererType ?? "—" },
      { label: "Reserved reason", value: track.reservedReason || "—" },
    );
  }

  return {
    sectionId: `${track.trackType}-track-metadata`,
    title: `${readableTrackType(track)} Track Metadata`,
    rows,
  };
}



function resolveCompletionTrackAppearance(
  track: WellLogTrack | null | undefined,
): CompletionTrackAppearance {
  if (!track || track.trackType !== "completion") {
    return { ...DEFAULT_COMPLETION_TRACK_APPEARANCE };
  }
  return {
    ...DEFAULT_COMPLETION_TRACK_APPEARANCE,
    ...(track.completionAppearance ?? {}),
  };
}

function CompletionAppearanceEditor({
  appearance,
  updateAppearance,
}: {
  appearance: CompletionTrackAppearance;
  updateAppearance: (patch: Partial<CompletionTrackAppearance>) => void;
}) {
  const sliderNumber = (
    label: string,
    value: number,
    min: number,
    max: number,
    step: number,
    onChange: (value: number) => void,
  ) => (
    <label>
      <span>{label}</span>
      <div style={{
        display: "grid",
        gridTemplateColumns: "var(--wlv-modal-slider) var(--wlv-modal-number-compact)",
        gap: "var(--wlv-modal-control-gap)",
        alignItems: "center",
      }}>
        <input
          type="range"
          min={min}
          max={max}
          step={step}
          value={value}
          onChange={(event) => onChange(Number(event.target.value))}
          onInput={(event) => onChange(Number(event.currentTarget.value))}
        />
        <input
          type="number"
          min={min}
          max={max}
          step={step}
          value={value}
          onChange={(event) => onChange(Number(event.target.value))}
          style={{ width: "var(--wlv-modal-number-compact)" }}
        />
      </div>
    </label>
  );

  return (
    <div className="wlv-edit-track-overlay-panel">
      <section className="wlv-edit-track-overlay-style-panel">
        <header className="wlv-edit-track-overlay-style-header">
          <div>
            <h3>Completion Display</h3>
            <p>Controls the completion schematic presentation only. Completion data selection remains in Well Data Inventory.</p>
          </div>
        </header>

        <div className="wlv-edit-track-overlay-style-body">
          <section className="wlv-edit-track-overlay-section">
            <h4>Schematic geometry</h4>
            <div style={{
              display: "grid",
              gridTemplateColumns:
                "calc(var(--wlv-modal-slider) + var(--wlv-modal-control-gap) + var(--wlv-modal-number-compact)) calc(var(--wlv-modal-slider) + var(--wlv-modal-control-gap) + var(--wlv-modal-number-compact))",
              columnGap: "24px",
              rowGap: "var(--wlv-modal-row-gap)",
              alignItems: "start",
              width: "max-content",
              maxWidth: "100%",
            }}>
              <label>
                <span>Position</span>
                <select
                  value={appearance.schematicPosition}
                  onChange={(event) => updateAppearance({
                    schematicPosition: event.target.value as CompletionTrackAppearance["schematicPosition"],
                  })}
                >
                  <option value="left">Left</option>
                  <option value="center">Centre</option>
                  <option value="right">Right</option>
                </select>
              </label>
              {sliderNumber(
                "Schematic width",
                appearance.schematicWidthPx,
                20,
                100,
                1,
                (schematicWidthPx) => updateAppearance({ schematicWidthPx }),
              )}
            </div>
            <div style={{
              display: "grid",
              gridTemplateColumns:
                "calc(var(--wlv-modal-slider) + var(--wlv-modal-control-gap) + var(--wlv-modal-number-compact)) calc(var(--wlv-modal-slider) + var(--wlv-modal-control-gap) + var(--wlv-modal-number-compact))",
              columnGap: "24px",
              rowGap: "var(--wlv-modal-row-gap)",
              alignItems: "start",
              width: "max-content",
              maxWidth: "100%",
            }}>
              {sliderNumber(
                "Symbol scale",
                appearance.symbolScale,
                0.5,
                2,
                0.05,
                (symbolScale) => updateAppearance({ symbolScale }),
              )}
              {sliderNumber(
                "Line weight",
                appearance.lineWeight,
                0.5,
                6,
                0.5,
                (lineWeight) => updateAppearance({ lineWeight }),
              )}
            </div>
          </section>

          <section className="wlv-edit-track-overlay-section">
            <h4>Labels</h4>
            <div style={{
              display: "grid",
              gridTemplateColumns: "var(--wlv-modal-select-short) var(--wlv-modal-number-standard)",
              gap: "var(--wlv-modal-control-gap)",
              alignItems: "end",
              width: "max-content",
              maxWidth: "100%",
            }}>
              <label>
                <span>Position</span>
                <select
                  value={appearance.labelPosition}
                  disabled={!appearance.showLabels}
                  onChange={(event) => updateAppearance({
                    labelPosition: event.target.value as CompletionTrackAppearance["labelPosition"],
                  })}
                >
                  <option value="auto">Auto</option>
                  <option value="left">Left</option>
                  <option value="right">Right</option>
                </select>
              </label>
              <label>
                <span>Font size</span>
                <input
                  type="number"
                  min={9}
                  max={14}
                  step={1}
                  value={appearance.labelFontSize}
                  disabled={!appearance.showLabels}
                  onChange={(event) => updateAppearance({ labelFontSize: Number(event.target.value) })}
                />
              </label>
            </div>

            <label className="wlv-checkbox-row">
              <input
                type="checkbox"
                checked={appearance.showLabels}
                onChange={(event) => updateAppearance({ showLabels: event.target.checked })}
              />
              <span>Show component labels</span>
            </label>

            <div style={{
              display: "grid",
              gridTemplateColumns: "var(--wlv-modal-select-short) max-content",
              gap: "var(--wlv-modal-control-gap)",
              alignItems: "end",
              width: "max-content",
              maxWidth: "100%",
            }}>
              <label>
                <span>Collision handling</span>
                <select
                  value={appearance.labelCollisionMode}
                  disabled={!appearance.showLabels}
                  onChange={(event) => updateAppearance({
                    labelCollisionMode: event.target.value as CompletionTrackAppearance["labelCollisionMode"],
                  })}
                >
                  <option value="auto">Auto</option>
                  <option value="off">Off</option>
                </select>
              </label>
              <label className="wlv-checkbox-row" style={{ marginBottom: 7 }}>
                <input
                  type="checkbox"
                  checked={appearance.labelWrap}
                  disabled={!appearance.showLabels}
                  onChange={(event) => updateAppearance({ labelWrap: event.target.checked })}
                />
                <span>Wrap labels</span>
              </label>
            </div>

            <div style={{
              display: "grid",
              gridTemplateColumns:
                "calc(var(--wlv-modal-slider) + var(--wlv-modal-control-gap) + var(--wlv-modal-number-compact)) calc(var(--wlv-modal-slider) + var(--wlv-modal-control-gap) + var(--wlv-modal-number-compact))",
              columnGap: "24px",
              rowGap: "var(--wlv-modal-row-gap)",
              alignItems: "start",
              width: "max-content",
              maxWidth: "100%",
            }}>
              {sliderNumber(
                "Horizontal offset",
                appearance.labelOffsetPx,
                0,
                60,
                1,
                (labelOffsetPx) => updateAppearance({ labelOffsetPx }),
              )}
              {sliderNumber(
                "Vertical offset",
                appearance.labelVerticalOffsetPx,
                -60,
                60,
                1,
                (labelVerticalOffsetPx) => updateAppearance({ labelVerticalOffsetPx }),
              )}
              {sliderNumber(
                "Maximum label width",
                appearance.labelMaxWidthPx,
                60,
                260,
                5,
                (labelMaxWidthPx) => updateAppearance({ labelMaxWidthPx }),
              )}
            </div>
          </section>

          <section className="wlv-edit-track-overlay-section">
            <h4>Component styling</h4>
            <div className="wlv-property-note">
              Component-type styling is reserved here for the next slice. This first modal establishes the canonical Completion presentation contract without changing the reviewed component data.
            </div>
          </section>
        </div>
      </section>
    </div>
  );
}

function TrackDesignControls({
  track,
  curveCatalogItems,
  updateTrack,
}: {
  track: WellLogTrack;
  curveCatalogItems: CurveCatalogItem[];
  updateTrack: (trackId: string, patch: Partial<WellLogTrack>) => void;
}) {
  if (track.trackType === "depth") {
    return (
      <div className="wlv-property-section wlv-properties-dark-section">
        <h3>Design Controls</h3>
        <label>
          Track title
          <input
            value={track.title}
            onChange={(event) =>
              updateTrack(track.trackId, { title: event.target.value })
            }
          />
        </label>
        <label>
          Depth type
          <select
            value={track.depthBasis}
            onChange={(event) =>
              updateTrack(track.trackId, {
                depthBasis: event.target.value as DepthBasis,
              })
            }
          >
            <option value="MD">MD</option>
            <option value="TVD">TVD</option>
            <option value="TVDSS">TVDSS</option>
          </select>
        </label>
        <div className="wlv-property-note">
          Depth track width is fixed in this prototype. Curve tracks can be
          resized from the toolbar.
        </div>
      </div>
    );
  }

  if (track.trackType === "curve") {
    const lattice = resolveTrackLattice(track, curveCatalogItems);
    return (
      <div className="wlv-property-section wlv-properties-dark-section">
        <h3>Track Controls</h3>
        <label>
          Track title
          <input
            value={track.title}
            onChange={(event) =>
              updateTrack(track.trackId, { title: event.target.value })
            }
          />
        </label>
        <label>
          Lattice
          <select
            value={lattice.lattice}
            onChange={(event) =>
              updateTrack(track.trackId, {
                lattice: event.target.value as CurveTrack["lattice"],
                latticeOverride: true,
                latticeSource: "user_override",
              })
            }
          >
            <option value="linear">Linear</option>
            <option value="logarithmic">Logarithmic</option>
          </select>
        </label>
        <button
          type="button"
          disabled={!track.latticeOverride}
          onClick={() =>
            updateTrack(track.trackId, {
              latticeOverride: false,
              latticeSource: "front_curve_default",
            })
          }
        >
          Reset lattice to front curve
        </button>
        <label>
          Scale mode
          <select
            value={track.scaleMode}
            onChange={(event) =>
              updateTrack(track.trackId, {
                scaleMode: event.target.value as ScaleMode,
              })
            }
          >
            <option value="shared">Shared</option>
            <option value="per_curve">Per curve</option>
            <option value="dual">Dual</option>
            <option value="normalized">Normalized</option>
          </select>
        </label>
        <label>
          Width
          <input
            type="number"
            min={CURVE_TRACK_MIN_WIDTH}
            max={CURVE_TRACK_MAX_WIDTH}
            value={track.widthPx}
            onChange={(event) =>
              updateTrack(track.trackId, {
                widthPx: clampCurveTrackWidth(Number(event.target.value)),
              })
            }
          />
        </label>
      </div>
    );
  }

  return (
    <div className="wlv-property-section wlv-properties-dark-section">
      <h3>Design Controls</h3>
      <div className="wlv-property-note">
        This selected item is read-only in the current prototype.
      </div>
    </div>
  );
}

export type WdvConfigurationSessionTarget = {
  trackId: string;
  trackType: WellLogTrack["trackType"];
  managedWellUid: string | null;
  assignmentId: string | null;
  openedTrackTitle: string;
};

function matchesWdvConfigurationSessionTarget(
  track: WellLogTrack,
  target: WdvConfigurationSessionTarget,
): boolean {
  return (
    track.trackId === target.trackId
    && track.trackType === target.trackType
    && (track.managedWellUid ?? null) === target.managedWellUid
  );
}

export function resolvePropertiesEditorCurve(
  selectedTrack: WellLogTrack | undefined,
  selectedCurveAssignment: CurveAssignment | null,
): CurveAssignment | null {
  return selectedTrack?.trackType === "curve" ? selectedCurveAssignment : null;
}

function CurveDesignControls({
  track,
  assignment,
  curveCatalogItems,
  updateCurveAssignment,
  previewCurveLineStyle,
  commitCurveLineStyle,
  backendCurveFillEnabled,
}: {
  track: CurveTrack;
  assignment: CurveAssignment;
  curveCatalogItems: CurveCatalogItem[];
  updateCurveAssignment: (
    trackId: string,
    assignmentId: string,
    patch: Partial<CurveAssignment>,
    options?: Readonly<{ persist?: boolean }>,
  ) => void;
  previewCurveLineStyle: (
    trackId: string,
    assignmentId: string,
    value: CurveLineStyleValue,
  ) => void;
  commitCurveLineStyle: (
    trackId: string,
    assignmentId: string,
    value: CurveLineStyleValue,
  ) => void;
  backendCurveFillEnabled: boolean;
}) {
  const curve = findCurveForAssignment(curveCatalogItems, assignment);
  if (!curve) {
    return (
      <div className="wlv-property-section wlv-properties-dark-section">
        <h3>Curve Controls</h3>
        <div className="wlv-property-note">
          The selected curve is no longer available in the active well catalog.
        </div>
      </div>
    );
  }
  const scaleType =
    assignment.scaleType ??
    (curve.defaultLattice === "logarithmic" ? "log" : "linear");
  const lineVisible = assignment.lineVisible ?? true;
  const lineOpacity = assignment.lineOpacity ?? 100;
  const positionAnchor = assignment.positionAnchor ?? "center";
  const horizontalOffsetPct = assignment.horizontalOffsetPct ?? 0;
  const clipToTrack = assignment.clipToTrack ?? true;
  const infillSource = assignment.infillSource ?? "solid";
  const infillPattern = assignment.infillPattern ?? "solid";
  const infillIntervalColumn = assignment.infillIntervalColumn ?? "lithology";
  const fillOpacity = assignment.fillOpacity ?? 55;

  const update = (
    patch: Partial<CurveAssignment>,
    options?: Readonly<{ persist?: boolean }>,
  ) => {
    updateCurveAssignment(
      track.trackId,
      assignment.assignmentId,
      patch,
      options,
    );
  };

  return (
    <div className="wlv-curve-editor-controls">

      <div className="wlv-curve-editor-section wlv-curve-editor-section--scale">
        <h4>Scale</h4>
        <label>
          Scale type
          <select
            value={scaleType}
            onChange={(event) =>
              update({
                scaleType: event.target.value as CurveAssignment["scaleType"],
              })
            }
          >
            <option value="linear">Linear</option>
            <option value="log">Log</option>
          </select>
        </label>
        <label>
          Range mode
          <select
            value={assignment.rangeOverrideMode ?? "governed"}
            onChange={(event) => {
              const rangeOverrideMode = event.target.value as NonNullable<
                CurveAssignment["rangeOverrideMode"]
              >;
              update(
                rangeOverrideMode === "manual"
                  ? {
                      rangeOverrideMode,
                      manualScaleMin:
                        assignment.manualScaleMin ?? assignment.scaleMin,
                      manualScaleMax:
                        assignment.manualScaleMax ?? assignment.scaleMax,
                    }
                  : {
                      rangeOverrideMode,
                      manualScaleMin: null,
                      manualScaleMax: null,
                    },
              );
            }}
          >
            <option value="governed">Governed</option>
            <option value="manual">Manual</option>
            <option value="fit_to_curve_p05_p95">
              Fit track to curve — P5–P95
            </option>
            <option value="fit_to_curve_p01_p99">
              Fit track to curve — P1–P99
            </option>
          </select>
        </label>
        <label>
          Range min
          <input
            type="number"
            value={
              assignment.rangeOverrideMode === "manual"
                ? (assignment.manualScaleMin ?? assignment.scaleMin)
                : assignment.scaleMin
            }
            disabled={assignment.rangeOverrideMode !== "manual"}
            step={assignment.rangeEditStep ?? 1}
            onChange={(event) =>
              update({
                rangeOverrideMode: "manual",
                manualScaleMin: Number(event.target.value),
              })
            }
          />
        </label>
        <label>
          Range max
          <input
            type="number"
            value={
              assignment.rangeOverrideMode === "manual"
                ? (assignment.manualScaleMax ?? assignment.scaleMax)
                : assignment.scaleMax
            }
            disabled={assignment.rangeOverrideMode !== "manual"}
            step={assignment.rangeEditStep ?? 1}
            onChange={(event) =>
              update({
                rangeOverrideMode: "manual",
                manualScaleMax: Number(event.target.value),
              })
            }
          />
        </label>
        {assignment.overrideWarningMessage ? (
          <div className="wlv-property-note" role="status">
            {assignment.overrideWarningMessage}
          </div>
        ) : null}
        <label className="wlv-curve-editor-checkbox-row">
          <input
            type="checkbox"
            checked={assignment.scaleDirection === "reverse"}
            onChange={(event) =>
              update({
                scaleDirection: event.target.checked ? "reverse" : "normal",
              })
            }
          />
          Reverse scale
        </label>
      </div>

      <CurveLineStyleControl
        value={{
          visible: lineVisible,
          color: assignment.color,
          width: assignment.lineWidth,
          style: assignment.lineStyle,
          opacity: lineOpacity,
        }}
        onPreview={(value) =>
          previewCurveLineStyle(track.trackId, assignment.assignmentId, value)
        }
        onCommit={(value) =>
          commitCurveLineStyle(track.trackId, assignment.assignmentId, value)
        }
      />

      <div className="wlv-curve-editor-section wlv-curve-editor-section--position">
        <h4>Position</h4>
        <label className="wlv-curve-editor-field wlv-curve-editor-field--position">
          <span className="wlv-curve-editor-field-label">Position</span>
          <select
            value={positionAnchor}
            onChange={(event) =>
              update({
                positionAnchor: event.target
                  .value as CurveAssignment["positionAnchor"],
              })
            }
          >
            <option value="left">Left</option>
            <option value="center">Center</option>
            <option value="right">Right</option>
          </select>
        </label>
        <label className="wlv-curve-editor-field wlv-curve-editor-field--offset">
          <span className="wlv-curve-editor-field-label">Offset</span>
          <input
            type="range"
            min={-100}
            max={100}
            step={5}
            value={horizontalOffsetPct}
            onChange={(event) =>
              update({ horizontalOffsetPct: Number(event.target.value) })
            }
          />
        </label>
        <label className="wlv-curve-editor-checkbox-row wlv-curve-editor-field--clip">
          <input
            type="checkbox"
            checked={clipToTrack}
            onChange={(event) => update({ clipToTrack: event.target.checked })}
          />
          Clip to track
        </label>
      </div>

      {!backendCurveFillEnabled ? (
        <div className="wlv-curve-control-group">
          <h4>Infill</h4>
          <label>
            Infill
            <select
              value={assignment.fillSide}
              onChange={(event) =>
                update({ fillSide: event.target.value as FillSide })
              }
            >
              <option value="none">Off</option>
              <option value="left">Left of curve</option>
              <option value="right">Right of curve</option>
              <option value="between">Between curves</option>
            </select>
          </label>
          {assignment.fillSide !== "none" ? (
            <>
              <label>
                Infill source
                <select
                  value={infillSource}
                  onChange={(event) =>
                    update({
                      infillSource: event.target
                        .value as CurveAssignment["infillSource"],
                    })
                  }
                >
                  <option value="solid">Solid color</option>
                  <option value="pattern">Pattern</option>
                  <option value="interval-column">Interval column</option>
                </select>
              </label>
              {assignment.fillSide === "between" ? (
                <label>
                  Infill with curve
                  <select
                    value={assignment.pairedCurveId ?? ""}
                    onChange={(event) =>
                      update({ pairedCurveId: event.target.value || undefined })
                    }
                  >
                    <option value="">Select curve</option>
                    {track.curves
                      .filter(
                        (candidate) =>
                          candidate.assignmentId !== assignment.assignmentId,
                      )
                      .map((candidate) => {
                        const pairedCurve = findCurveForAssignment(
                          curveCatalogItems,
                          candidate,
                        );
                        return pairedCurve ? (
                          <option
                            key={candidate.assignmentId}
                            value={candidate.assignmentId}
                          >
                            {pairedCurve.mnemonic}
                          </option>
                        ) : null;
                      })}
                  </select>
                </label>
              ) : null}
              {infillSource === "interval-column" ? (
                <label>
                  Interval column
                  <select
                    value={infillIntervalColumn}
                    onChange={(event) =>
                      update({
                        infillIntervalColumn: event.target
                          .value as CurveAssignment["infillIntervalColumn"],
                      })
                    }
                  >
                    <option value="lithology">Lithology</option>
                    <option value="biostratigraphy">Biostratigraphy</option>
                    <option value="formation">Formation / stratigraphy</option>
                    <option value="facies">Facies</option>
                    <option value="other">Other interval set</option>
                  </select>
                </label>
              ) : null}
              {infillSource === "pattern" ? (
                <label>
                  Pattern
                  <select
                    value={infillPattern}
                    onChange={(event) =>
                      update({
                        infillPattern: event.target
                          .value as CurveAssignment["infillPattern"],
                      })
                    }
                  >
                    <option value="solid">Solid</option>
                    <option value="hatch">Hatch</option>
                    <option value="dots">Dots</option>
                  </select>
                </label>
              ) : null}
              {infillSource !== "interval-column" ? (
                <>
                  <label>
                    Infill color
                    <input
                      type="color"
                      value={assignment.fillColor}
                      onChange={(event) =>
                        update({ fillColor: event.target.value })
                      }
                    />
                  </label>
                </>
              ) : null}
              <label>
                Opacity
                <input
                  type="range"
                  min={10}
                  max={100}
                  step={5}
                  value={fillOpacity}
                  onChange={(event) =>
                    update({ fillOpacity: Number(event.target.value) })
                  }
                />
              </label>
            </>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

const CURVE_FILL_MD_PICK_REQUEST_EVENT =
  "wlv:curve-fill-md-pick-request";
const CURVE_FILL_MD_PICK_RESULT_EVENT =
  "wlv:curve-fill-md-pick-result";
const CURVE_FILL_MD_PICK_CANCEL_EVENT =
  "wlv:curve-fill-md-pick-cancel";

type CurveFillMdPickField = "from" | "to";

type CurveFillMdPickResultDetail = {
  token: string;
  depth: number;
};

type CurveFillMdPickRequestDetail = {
  token: string;
  field: CurveFillMdPickField;
};

type CurveFillV2PanelContract = {
  enabled: boolean;
  managedWellUid: string | null;
  revision: number;
  rules: CanonicalCurveFillRuleV2[];
  pending: boolean;
  error: string | null;
  onCreateRule: (
    body: Readonly<Record<string, unknown>>,
  ) => Promise<string | null>;
  onUpdateRule: (
    ruleUid: string,
    patch: Readonly<Record<string, unknown>>,
  ) => Promise<void>;
  onRemoveRule: (ruleUid: string) => Promise<void>;
  onReorderRules: (
    trackUid: string,
    ruleUids: readonly string[],
  ) => Promise<void>;
};

function curveFillRuleLabel(ruleType: CurveFillRuleTypeV2): string {
  if (ruleType === "to_boundary") return "Curve to boundary";
  if (ruleType === "between_curves") return "Between curves";
  if (ruleType === "conditional") return "Conditional fill";
  if (ruleType === "crossover") return "Crossover fill";
  if (ruleType === "value_band") return "Value band fill";
  if (ruleType === "curve_to_value") return "Curve to value fill";
  if (ruleType === "threshold") return "Threshold fill";
  if (ruleType === "curve_envelope") return "Curve envelope fill";
  return "Separation fill";
}

const KR_LITHOLOGY_PATTERN_SELECTOR = "__kr_lithology_pattern__";
const NATIVE_CURVE_FILL_PATTERN_UIDS = new Set([
  "hatch-45-v1",
  "crosshatch-v1",
  "cross-hatch-v1",
  "dots-v1",
  "bricks-v1",
  "stipple-v1",
  "lithology-column-v1",
]);

function isKrLithologyPatternUid(value: string | null | undefined): boolean {
  return Boolean(
    value
    && value !== KR_LITHOLOGY_PATTERN_SELECTOR
    && !NATIVE_CURVE_FILL_PATTERN_UIDS.has(value),
  );
}
const CURVE_FILL_TRANSIENT_PREVIEW_EVENT =
  "wlv:curve-fill-transient-preview";
const CURVE_FILL_TRANSIENT_PREVIEW_CLEAR_EVENT =
  "wlv:curve-fill-transient-preview-clear";

function CurveFillV2Controls({
  track,
  assignment,
  curveCatalogItems,
  contract,
  lithologyIntervals,
  registerDraftApply,
}: {
  track: CurveTrack;
  assignment: CurveAssignment;
  curveCatalogItems: CurveCatalogItem[];
  contract: CurveFillV2PanelContract;
  lithologyIntervals: LithologyIntervalRecord[];
  registerDraftApply: (
    handler: (() => Promise<boolean>) | null,
  ) => void;
}) {
  const [capabilities, setCapabilities] =
    useState<CurveFillCapabilitiesV2 | null>(null);
  const [capabilityError, setCapabilityError] = useState<string | null>(null);
  const [ruleType, setRuleType] = useState<CurveFillRuleTypeV2>("to_boundary");
  const [curveB, setCurveB] = useState("");
  const [comparison, setComparison] =
    useState<CurveFillComparisonV2>("greater_than");
  const [boundary, setBoundary] = useState<"left" | "right">("right");
  const [thresholdFillRegion, setThresholdFillRegion] = useState<"left" | "threshold" | "right">("left");
  const [referenceValue, setReferenceValue] = useState("");
  const [bandMinValue, setBandMinValue] = useState("");
  const [bandMaxValue, setBandMaxValue] = useState("");
  const [envelopeOperands, setEnvelopeOperands] = useState<string[]>([]);
  const [minimumSeparationPx, setMinimumSeparationPx] = useState("5");
  const [separationMode, setSeparationMode] = useState<"absolute" | "a_right_of_b" | "a_left_of_b">("absolute");
  const [color, setColor] = useState("#d94841");
  const [opacity, setOpacity] = useState(0.45);
  const [appearance, setAppearance] = useState<"solid" | "pattern" | "raster">(
    "solid",
  );
  const [patternUid, setPatternUid] = useState("hatch-45-v1");
  const [selectedKrPatternUid, setSelectedKrPatternUid] =
    useState<string | null>(null);
  const [patternScale, setPatternScale] = useState(1);
  const [draftConfigured, setDraftConfigured] = useState(false);
  const loadedLithologyColumns = Array.from(
    new Map(
      lithologyIntervals.map((interval) => [
        interval.datasetId,
        {
          datasetId: interval.datasetId,
          datasetLabel:
            interval.datasetLabel || interval.datasetId,
        },
      ]),
    ).values(),
  );
  const markDraftChanged = () => {
    setDraftConfigured(true);
  };
  const selectedLithologyColumn =
    patternUid === "lithology-column-v1"
    && loadedLithologyColumns.length === 1
      ? loadedLithologyColumns[0]
      : null;
  const [rasterAssetUid, setRasterAssetUid] = useState("");
  const [depthExtent, setDepthExtent] = useState<"entire_track" | "specified_interval">(
    "entire_track",
  );
  const [intervalFromMd, setIntervalFromMd] = useState("");
  const [intervalToMd, setIntervalToMd] = useState("");
  const [activeMdPickField, setActiveMdPickField] =
    useState<CurveFillMdPickField | null>(null);
  const activeMdPickFieldRef =
    useRef<CurveFillMdPickField | null>(null);
  const mdPickTokenRef = useRef(
    `curve-fill-md-pick-${Math.random().toString(36).slice(2)}`,
  );
  const [expandedRuleUids, setExpandedRuleUids] = useState<Set<string>>(
    () => new Set(),
  );

  useEffect(() => {
    const handleResult = (event: Event) => {
      const detail = (event as CustomEvent<CurveFillMdPickResultDetail>).detail;
      if (!detail || detail.token !== mdPickTokenRef.current) return;

      const activeField = activeMdPickFieldRef.current;
      const formatted = detail.depth.toFixed(1);

      if (activeField === "from") {
        setIntervalFromMd(formatted);
      } else if (activeField === "to") {
        setIntervalToMd(formatted);
      } else {
        return;
      }

      activeMdPickFieldRef.current = null;
      setActiveMdPickField(null);
    };

    window.addEventListener(
      CURVE_FILL_MD_PICK_RESULT_EVENT,
      handleResult as EventListener,
    );
    return () => {
      window.removeEventListener(
        CURVE_FILL_MD_PICK_RESULT_EVENT,
        handleResult as EventListener,
      );
      window.dispatchEvent(
        new CustomEvent(CURVE_FILL_MD_PICK_CANCEL_EVENT, {
          detail: { token: mdPickTokenRef.current },
        }),
      );
    };
  }, []);

  const setMdPickField = (field: CurveFillMdPickField) => {
    if (activeMdPickFieldRef.current === field) {
      activeMdPickFieldRef.current = null;
      setActiveMdPickField(null);
      window.dispatchEvent(
        new CustomEvent(CURVE_FILL_MD_PICK_CANCEL_EVENT, {
          detail: { token: mdPickTokenRef.current },
        }),
      );
      return;
    }

    activeMdPickFieldRef.current = field;
    setActiveMdPickField(field);
    window.dispatchEvent(
      new CustomEvent<CurveFillMdPickRequestDetail>(
        CURVE_FILL_MD_PICK_REQUEST_EVENT,
        {
          detail: {
            token: mdPickTokenRef.current,
            field,
          },
        },
      ),
    );
  };

  useEffect(() => {
    if (depthExtent === "specified_interval") return;
    activeMdPickFieldRef.current = null;
    setActiveMdPickField(null);
    window.dispatchEvent(
      new CustomEvent(CURVE_FILL_MD_PICK_CANCEL_EVENT, {
        detail: { token: mdPickTokenRef.current },
      }),
    );
  }, [depthExtent]);

  useEffect(() => {
    if (!contract.enabled || !contract.managedWellUid) {
      setCapabilities(null);
      return;
    }
    let cancelled = false;
    setCapabilityError(null);
    void fetchCurveFillCapabilitiesV2(
      contract.managedWellUid,
      track.trackId,
      assignment.assignmentId,
    )
      .then((value) => {
        if (cancelled) return;
        setCapabilities(value);
        // Curve B is selected explicitly by the operator.
        setCurveB("");
      })
      .catch((error) => {
        if (!cancelled)
          setCapabilityError(
            error instanceof Error ? error.message : "Capabilities unavailable",
          );
      });
    return () => {
      cancelled = true;
    };
  }, [
    assignment.assignmentId,
    contract.enabled,
    contract.managedWellUid,
    contract.revision,
    ruleType,
    track.trackId,
  ]);

  if (!contract.enabled) return null;

  const trackRules = contract.rules
    .filter((rule) => rule.track_uid === track.trackId)
    .sort((a, b) => a.order - b.order);
  const rules = trackRules;
  const mode =
    capabilities?.modes.find((item) => item.rule_type === ruleType) ?? null;
  const paintCapabilities = curveFillPaintCapabilitiesV2(capabilities);
  const operands = mode?.curve_b_operands.filter((item) => item.eligible) ?? [];
  const curveAMnemonic = capabilities?.curve_a_mnemonic ?? "—";

  const assignmentName = (assignmentUid: string | null): string => {
    if (!assignmentUid) return "—";

    const trackAssignment = track.curves.find(
      (candidate) => candidate.assignmentId === assignmentUid,
    );
    if (trackAssignment) {
      const catalogCurve = findCurveForAssignment(
        curveCatalogItems,
        trackAssignment,
      );
      return (
        catalogCurve?.mnemonic
        ?? trackAssignment.observedMnemonic
        ?? trackAssignment.normalizedMnemonic
        ?? "—"
      );
    }

    return (
      capabilities?.modes
        .flatMap((item) => item.curve_b_operands)
        .find((item) => item.assignment_uid === assignmentUid)?.mnemonic ?? "—"
    );
  };

  const operandName = (assignmentUid: string | null): string =>
    assignmentName(assignmentUid);
  const requiresCurveB = ["between_curves", "conditional", "crossover", "separation"].includes(ruleType);
  const requiresReferenceValue = ruleType === "curve_to_value" || ruleType === "threshold";
  const referenceNumber = Number(referenceValue);
  const bandMinNumber = Number(bandMinValue);
  const bandMaxNumber = Number(bandMaxValue);
  const separationNumber = Number(minimumSeparationPx);
  const relationReady =
    (!requiresReferenceValue || (referenceValue.trim() !== "" && Number.isFinite(referenceNumber)))
    && (ruleType !== "value_band" || (bandMinValue.trim() !== "" && bandMaxValue.trim() !== "" && Number.isFinite(bandMinNumber) && Number.isFinite(bandMaxNumber) && bandMinNumber < bandMaxNumber))
    && (ruleType !== "curve_envelope" || envelopeOperands.length >= 1)
    && (ruleType !== "separation" || (Number.isFinite(separationNumber) && separationNumber >= 0));
  const paintReady =
    appearance === "raster"
      ? Boolean(rasterAssetUid)
      : appearance === "pattern"
        ? (
            patternUid !== KR_LITHOLOGY_PATTERN_SELECTOR
            || Boolean(selectedKrPatternUid)
          )
        : true;
  const intervalFrom = Number(intervalFromMd);
  const intervalTo = Number(intervalToMd);
  const intervalReady =
    depthExtent === "entire_track" ||
    (
      Number.isFinite(intervalFrom) &&
      Number.isFinite(intervalTo) &&
      intervalFrom < intervalTo
    );
  const canCreate = Boolean(
    mode?.eligible &&
    (!requiresCurveB || curveB) &&
    relationReady &&
    paintReady &&
    intervalReady &&
    contract.revision >= 0,
  );

  const buildDraftBody = (): Record<string, unknown> | null => {
    if (!mode || !canCreate) return null;

    const body: Record<string, unknown> = {
      track_uid: track.trackId,
      curve_a_assignment_uid: assignment.assignmentId,
      rule_type: ruleType,
      enabled: true,
      deadband: 0,
      minimum_interval: 0,
      depth_extent: depthExtent,
      interval_from_md:
        depthExtent === "specified_interval" ? intervalFrom : null,
      interval_to_md:
        depthExtent === "specified_interval" ? intervalTo : null,
      style: {
        appearance,
        color,
        opacity,
        pattern_uid:
          appearance === "pattern"
            ? (
                patternUid === KR_LITHOLOGY_PATTERN_SELECTOR
                  ? selectedKrPatternUid
                  : patternUid
              )
            : null,
        pattern_scale: patternScale,
        raster_asset_uid: appearance === "raster" ? rasterAssetUid : null,
      },
    };

    if (ruleType === "to_boundary") body.boundary = boundary;
    if (ruleType === "between_curves") {
      body.curve_b_assignment_uid = curveB;
    }
    if (ruleType === "conditional") {
      body.curve_b_assignment_uid = curveB;
      body.comparison = comparison;
    }
    if (ruleType === "crossover") {
      body.curve_b_assignment_uid = curveB;
      body.overlay_policy_uid = mode.overlay_policy_uid;
      body.overlay_policy_revision = mode.overlay_policy_revision;
    }
    if (ruleType === "value_band") {
      body.band_min_value = bandMinNumber;
      body.band_max_value = bandMaxNumber;
    }
    if (ruleType === "curve_to_value") body.reference_value = referenceNumber;
    if (ruleType === "threshold") {
      body.reference_value = referenceNumber;
      body.comparison = comparison;
      body.boundary = thresholdFillRegion === "threshold" ? null : thresholdFillRegion;
    }
    if (ruleType === "curve_envelope") {
      body.curve_operand_assignment_uids = [assignment.assignmentId, ...envelopeOperands];
    }
    if (ruleType === "separation") {
      body.curve_b_assignment_uid = curveB;
      body.minimum_separation_px = separationNumber;
      body.separation_mode = separationMode;
    }

    return body;
  };

  useEffect(() => {
    if (!draftConfigured || !canCreate) {
      window.dispatchEvent(
        new CustomEvent(CURVE_FILL_TRANSIENT_PREVIEW_CLEAR_EVENT, {
          detail: { trackId: track.trackId },
        }),
      );
      return;
    }

    const body = buildDraftBody();
    if (!body) return;

    window.dispatchEvent(
      new CustomEvent(CURVE_FILL_TRANSIENT_PREVIEW_EVENT, {
        detail: {
          trackId: track.trackId,
          curveAAssignmentId: assignment.assignmentId,
          body,
        },
      }),
    );
  }, [
    appearance,
    boundary,
    referenceValue,
    bandMinValue,
    bandMaxValue,
    envelopeOperands,
    minimumSeparationPx,
    separationMode,
    canCreate,
    color,
    comparison,
    thresholdFillRegion,
    curveB,
    depthExtent,
    draftConfigured,
    intervalFrom,
    intervalTo,
    opacity,
    patternScale,
    patternUid,
    selectedKrPatternUid,
    rasterAssetUid,
    ruleType,
    track.trackId,
    assignment.assignmentId,
  ]);

  useEffect(() => {
    if (!draftConfigured || !canCreate) {
      registerDraftApply(null);
      return () => registerDraftApply(null);
    }

    registerDraftApply(async () => {
      const body = buildDraftBody();
      if (!body) return false;

      const createdRuleUid = await contract.onCreateRule(body);
      if (!createdRuleUid) return false;

      setDraftConfigured(false);
      window.dispatchEvent(
        new CustomEvent(CURVE_FILL_TRANSIENT_PREVIEW_CLEAR_EVENT, {
          detail: { trackId: track.trackId },
        }),
      );
      return true;
    });

    return () => registerDraftApply(null);
  });

  const toggleRuleExpanded = (ruleUid: string) => {
    setExpandedRuleUids((current) => {
      const next = new Set(current);
      if (next.has(ruleUid)) next.delete(ruleUid);
      else next.add(ruleUid);
      return next;
    });
  };

  const ruleExpression = (rule: CanonicalCurveFillRuleV2): string => {
    const curveAName = assignmentName(rule.curve_a_assignment_uid);
    if (rule.rule_type === "to_boundary") {
      return `${curveAName} → ${rule.boundary === "left" ? "left boundary" : "right boundary"}`;
    }
    const curveBName = operandName(rule.curve_b_assignment_uid);
    if (rule.rule_type === "conditional") {
      return `${curveAName} ${rule.comparison === "less_than" ? "<" : ">"} ${curveBName}`;
    }
    if (rule.rule_type === "crossover") return `${curveAName} crossover ${curveBName}`;
    if (rule.rule_type === "between_curves") return `${curveAName} to ${curveBName}`;
    if (rule.rule_type === "value_band") return `${rule.band_min_value}–${rule.band_max_value}`;
    if (rule.rule_type === "curve_to_value") return `${curveAName} → ${rule.reference_value}`;
    if (rule.rule_type === "threshold") return `${curveAName} ${rule.comparison === "less_than" ? "<" : ">"} ${rule.reference_value}`;
    if (rule.rule_type === "curve_envelope") return `Envelope · ${rule.curve_operand_assignment_uids.map((uid) => assignmentName(uid)).join(", ")}`;
    return `${curveAName} / ${curveBName} · ≥${rule.minimum_separation_px}px`;
  };

  const rulePaintSummary = (rule: CanonicalCurveFillRuleV2): string => {
    const appearance = rule.style.appearance ?? "solid";
    if (appearance === "pattern") {
      const label =
        paintCapabilities.patterns.find(
          (item) => item.pattern_uid === rule.style.pattern_uid,
        )?.label ?? "Pattern";
      return `Pattern · ${label}`;
    }
    if (appearance === "raster") {
      const label =
        paintCapabilities.rasters.find(
          (item) => item.raster_asset_uid === rule.style.raster_asset_uid,
        )?.label ?? "Raster";
      return `Raster · ${label}`;
    }
    return "Solid";
  };

  const ruleDepthSummary = (rule: CanonicalCurveFillRuleV2): string =>
    rule.depth_extent === "specified_interval" &&
    rule.interval_from_md !== null &&
    rule.interval_to_md !== null
      ? `${rule.interval_from_md.toLocaleString()}–${rule.interval_to_md.toLocaleString()} MD`
      : "Entire track";

  const moveRule = async (ruleUid: string, direction: -1 | 1) => {
    const index = trackRules.findIndex((rule) => rule.rule_uid === ruleUid);
    const target = index + direction;
    if (index < 0 || target < 0 || target >= trackRules.length) return;
    const reordered = trackRules.map((rule) => rule.rule_uid);
    [reordered[index], reordered[target]] = [
      reordered[target],
      reordered[index],
    ];
    await contract.onReorderRules(track.trackId, reordered);
  };

  return (
    <div
      className="wlv-curve-control-group wlv-curve-fill-editor"
      data-curve-fill-v2="enabled"
    >
      <h4>Infill</h4>

      <div
        className="wlv-curve-fill-new-rule wlv-curve-fill-menu"
        onChangeCapture={() => {
          window.setTimeout(markDraftChanged, 0);
        }}
      >
        <SharedInfillEditor
          option={ruleType}
          optionOptions={(capabilities?.modes ?? []).map((item) => ({
            value: item.rule_type,
            label: curveFillRuleLabel(item.rule_type),
            disabled: !item.eligible,
          }))}
          onOptionChange={(value) => setRuleType(value as CurveFillRuleTypeV2)}
          showBoundary={ruleType === "to_boundary"}
          boundary={boundary}
          onBoundaryChange={setBoundary}
          showCurvePair={["between_curves", "conditional", "crossover", "separation"].includes(ruleType)}
          curveALabel={curveAMnemonic}
          curveAValue={assignment.assignmentId}
          curveAReadOnly
          operator={ruleType === "conditional" ? comparison : ruleType === "crossover" ? "crossover" : ruleType === "separation" ? "vs" : "to"}
          operatorOptions={ruleType === "conditional" ? [{ value: "greater_than", label: ">" }, { value: "less_than", label: "<" }] : []}
          onOperatorChange={(value) => setComparison(value as CurveFillComparisonV2)}
          curveBValue={curveB}
          curveBOptions={operands.map((item) => ({ value: item.assignment_uid, label: item.mnemonic }))}
          onCurveBChange={setCurveB}
          relationControls={ruleType === "value_band" ? (
            <>
              <label>Minimum value<input type="number" step="any" value={bandMinValue} onChange={(e) => { setBandMinValue(e.target.value); markDraftChanged(); }} /></label>
              <label>Maximum value<input type="number" step="any" value={bandMaxValue} onChange={(e) => { setBandMaxValue(e.target.value); markDraftChanged(); }} /></label>
            </>
          ) : ruleType === "curve_to_value" ? (
            <label>Reference value<input type="number" step="any" value={referenceValue} onChange={(e) => { setReferenceValue(e.target.value); markDraftChanged(); }} /></label>
          ) : ruleType === "threshold" ? (
            <>
              <label>Condition<select value={comparison} onChange={(e) => { setComparison(e.target.value as CurveFillComparisonV2); markDraftChanged(); }}><option value="greater_than">Above</option><option value="less_than">Below</option></select></label>
              <label>Threshold value<input type="number" step="any" value={referenceValue} onChange={(e) => { setReferenceValue(e.target.value); markDraftChanged(); }} /></label>
              <label>Fill region<select value={thresholdFillRegion} onChange={(e) => { setThresholdFillRegion(e.target.value as "left" | "threshold" | "right"); markDraftChanged(); }}><option value="left">Left boundary → Curve</option><option value="threshold">Curve → Threshold</option><option value="right">Curve → Right boundary</option></select></label>
            </>
          ) : ruleType === "curve_envelope" ? (
            <fieldset className="wlv-curve-fill-envelope-operands">
              <legend>Envelope curves</legend>
              <label><input type="checkbox" checked disabled /> {curveAMnemonic}</label>
              {operands.map((item) => (
                <label key={item.assignment_uid}><input type="checkbox" checked={envelopeOperands.includes(item.assignment_uid)} onChange={(e) => { setEnvelopeOperands((current) => e.target.checked ? [...current, item.assignment_uid] : current.filter((uid) => uid !== item.assignment_uid)); markDraftChanged(); }} /> {item.mnemonic}</label>
              ))}
            </fieldset>
          ) : ruleType === "separation" ? (
            <>
              <label>Separation<select value={separationMode} onChange={(e) => { setSeparationMode(e.target.value as typeof separationMode); markDraftChanged(); }}><option value="absolute">Absolute</option><option value="a_right_of_b">Curve A right of B</option><option value="a_left_of_b">Curve A left of B</option></select></label>
              <label>Minimum separation (px)<input type="number" min="0" step="0.5" value={minimumSeparationPx} onChange={(e) => { setMinimumSeparationPx(e.target.value); markDraftChanged(); }} /></label>
            </>
          ) : null}
          depthExtent={depthExtent}
          onDepthExtentChange={(value) => setDepthExtent(value as "entire_track" | "specified_interval")}
          fromMd={intervalFromMd}
          toMd={intervalToMd}
          activeMdPickField={activeMdPickField}
          onFromMdChange={setIntervalFromMd}
          onToMdChange={setIntervalToMd}
          onMdPick={setMdPickField}
          appearance={appearance}
          onAppearanceChange={setAppearance}
          patternValue={patternUid}
          patternOptions={[
            ...paintCapabilities.patterns
              .filter((item) => !item.pattern_uid.startsWith("lithology:") && item.pattern_uid !== "lithology-column-v1")
              .map((item) => ({ value: item.pattern_uid, label: item.label })),
            { value: KR_LITHOLOGY_PATTERN_SELECTOR, label: "KR lithology pattern" },
            { value: "lithology-column-v1", label: "Loaded lithology column", disabled: !lithologyIntervals.length },
          ]}
          onPatternChange={(value) => {
            setPatternUid(value);
            if (value !== KR_LITHOLOGY_PATTERN_SELECTOR) setSelectedKrPatternUid(null);
          }}
          rasterValue={rasterAssetUid}
          rasterOptions={paintCapabilities.rasters.map((item) => ({ value: item.raster_asset_uid, label: item.label }))}
          onRasterChange={setRasterAssetUid}
          selectorKind={appearance === "pattern" && patternUid === KR_LITHOLOGY_PATTERN_SELECTOR ? "kr" : appearance === "pattern" && patternUid === "lithology-column-v1" ? "lithology-column" : null}
          selectorContent={appearance === "pattern" && patternUid === KR_LITHOLOGY_PATTERN_SELECTOR ? (
            <KrLithologyPatternPicker
              selectedId={selectedKrPatternUid}
              buttonLabel="Choose KR lithology pattern"
              onSelect={(entry) => {
                setPatternUid(KR_LITHOLOGY_PATTERN_SELECTOR);
                setSelectedKrPatternUid(entry.id);
                setColor(entry.colors.defaultBackground);
                markDraftChanged();
              }}
            />
          ) : appearance === "pattern" && patternUid === "lithology-column-v1" ? (
            <>
              <button type="button" className="wlv-lithology-column-fill-launch" disabled={!loadedLithologyColumns.length} onClick={() => { if (loadedLithologyColumns.length === 1) { setPatternUid("lithology-column-v1"); markDraftChanged(); } }}>Choose lithology column</button>
              <div role="status" aria-live="polite" className="wlv-property-note">
                {selectedLithologyColumn ? `Selected: ${selectedLithologyColumn.datasetLabel}` : loadedLithologyColumns.length > 1 ? "Multiple lithology columns loaded; select one" : "No lithology column loaded for this well"}
              </div>
            </>
          ) : null}
          patternScale={patternScale}
          onPatternScaleChange={setPatternScale}
          color={color}
          onColorChange={setColor}
          opacity={opacity}
          onOpacityChange={setOpacity}
        />
        {mode && !mode.eligible ? (
          <div className="wlv-property-note">{mode.disable_reason}</div>
        ) : null}
      </div>

      <div className="wlv-curve-fill-layer-heading">
        <strong>Track infill layers</strong>
        <span>{rules.length}</span>
      </div>
      {rules.length === 0 ? (
        <div className="wlv-curve-fill-empty">
          No infill layers for this track.
        </div>
      ) : null}
      {rules.map((rule, index) => {
        const expanded = expandedRuleUids.has(rule.rule_uid);
        const existingSelectedLithologyColumn =
          rule.style.pattern_uid === "lithology-column-v1"
          && loadedLithologyColumns.length === 1
            ? loadedLithologyColumns[0]
            : null;
        return (
          <div
            key={rule.rule_uid}
            className={`wlv-curve-fill-rule-card wlv-curve-fill-layer-card${expanded ? " is-expanded" : ""}${rule.curve_a_assignment_uid === assignment.assignmentId || rule.curve_b_assignment_uid === assignment.assignmentId ? " involves-selected-curve" : ""}`}
          >
            <div
              className="wlv-curve-fill-layer-summary"
              onClick={() => toggleRuleExpanded(rule.rule_uid)}
            >
              <label
                className="wlv-checkbox-row wlv-curve-fill-layer-toggle"
                onClick={(event) => event.stopPropagation()}
              >
                <input
                  type="checkbox"
                  checked={rule.enabled}
                  disabled={contract.pending}
                  onChange={(event) =>
                    void contract.onUpdateRule(rule.rule_uid, {
                      enabled: event.target.checked,
                    })
                  }
                />
                <strong>Infill {index + 1}</strong>
              </label>
              <button
                type="button"
                className="wlv-curve-fill-layer-summary-button"
                aria-expanded={expanded}
                aria-label={`${expanded ? "Collapse" : "Expand"} infill ${index + 1}`}
                onClick={(event) => {
                  event.stopPropagation();
                  toggleRuleExpanded(rule.rule_uid);
                }}
              >
                <span className="wlv-curve-fill-layer-expression">
                  {ruleExpression(rule)}
                </span>
                <span className="wlv-curve-fill-layer-paint-summary">
                  {rulePaintSummary(rule)} · {ruleDepthSummary(rule)}
                </span>
                <span
                  className={`wlv-curve-fill-layer-state state-${rule.state}`}
                >
                  {rule.state}
                </span>
                <span
                  aria-hidden="true"
                  className="wlv-curve-fill-layer-chevron"
                >
                  {expanded ? "▴" : "▾"}
                </span>
              </button>
            </div>

            {expanded ? (
              <div className="wlv-curve-fill-layer-details">
                <div className="wlv-curve-fill-expression-row">
                  <strong>{assignmentName(rule.curve_a_assignment_uid)}</strong>
                  {rule.rule_type === "conditional" ? (
                    <select
                      aria-label="Conditional operator"
                      value={rule.comparison ?? "greater_than"}
                      disabled={contract.pending}
                      onChange={(event) =>
                        void contract.onUpdateRule(rule.rule_uid, {
                          comparison: event.target.value,
                        })
                      }
                    >
                      <option value="greater_than">&gt;</option>
                      <option value="less_than">&lt;</option>
                    </select>
                  ) : rule.rule_type === "crossover" ? (
                    <span className="wlv-curve-fill-policy-label">
                      crossover
                    </span>
                  ) : rule.rule_type === "between_curves" ? (
                    <span className="wlv-curve-fill-policy-label">to</span>
                  ) : (
                    <span className="wlv-curve-fill-policy-label">→</span>
                  )}
                  <strong>
                    {rule.rule_type === "to_boundary"
                      ? rule.boundary === "left"
                        ? "left boundary"
                        : "right boundary"
                      : operandName(rule.curve_b_assignment_uid)}
                  </strong>
                </div>

                <div className="wlv-curve-fill-rule-depth-extent">
                  <label>
                    Depth extent
                    <select
                      value={rule.depth_extent ?? "entire_track"}
                      disabled={contract.pending}
                      onChange={(event) => {
                        const next = event.target.value as
                          | "entire_track"
                          | "specified_interval";
                        if (next === "entire_track") {
                          void contract.onUpdateRule(rule.rule_uid, {
                            clear_interval: true,
                          });
                        } else {
                          const from =
                            rule.interval_from_md ??
                            Math.floor(track.curves.length ? 0 : 0);
                          const to =
                            rule.interval_to_md ?? from + 1;
                          void contract.onUpdateRule(rule.rule_uid, {
                            depth_extent: "specified_interval",
                            interval_from_md: from,
                            interval_to_md: to,
                          });
                        }
                      }}
                    >
                      <option value="entire_track">Entire track</option>
                      <option value="specified_interval">
                        Specified interval
                      </option>
                    </select>
                  </label>
                  {rule.depth_extent === "specified_interval" ? (
                    <>
                      <label>
                        From MD
                        <input
                          type="number"
                          step="0.1"
                          value={rule.interval_from_md ?? ""}
                          disabled={contract.pending}
                          onChange={(event) => {
                            const value = Number(event.target.value);
                            if (!Number.isFinite(value)) return;
                            void contract.onUpdateRule(rule.rule_uid, {
                              depth_extent: "specified_interval",
                              interval_from_md: value,
                              interval_to_md:
                                rule.interval_to_md ?? value + 1,
                            });
                          }}
                        />
                      </label>
                      <label>
                        To MD
                        <input
                          type="number"
                          step="0.1"
                          value={rule.interval_to_md ?? ""}
                          disabled={contract.pending}
                          onChange={(event) => {
                            const value = Number(event.target.value);
                            if (!Number.isFinite(value)) return;
                            void contract.onUpdateRule(rule.rule_uid, {
                              depth_extent: "specified_interval",
                              interval_from_md:
                                rule.interval_from_md ?? value - 1,
                              interval_to_md: value,
                            });
                          }}
                        />
                      </label>
                    </>
                  ) : null}
                </div>

                <div className="wlv-curve-fill-layer-controls">
                  <select
                    aria-label="Fill appearance"
                    value={rule.style.appearance ?? "solid"}
                    disabled={contract.pending}
                    onChange={(event) => {
                      const next = event.target.value as
                        "solid" | "pattern" | "raster";
                      void contract.onUpdateRule(rule.rule_uid, {
                        style: {
                          ...rule.style,
                          appearance: next,
                          pattern_uid:
                            next === "pattern"
                              ? (rule.style.pattern_uid ?? "hatch-45-v1")
                              : null,
                          raster_asset_uid:
                            next === "raster"
                              ? (rule.style.raster_asset_uid ??
                                paintCapabilities.rasters[0]
                                  ?.raster_asset_uid ??
                                null)
                              : null,
                        },
                      });
                    }}
                  >
                    <option value="solid">Solid</option>
                    <option value="pattern">Pattern</option>
                    <option
                      value="raster"
                      disabled={!paintCapabilities.rasters.length}
                    >
                      Raster
                    </option>
                  </select>

                  {rule.style.appearance === "pattern" ? (
                    <>
                      <select
                        aria-label="Pattern"
                        value={
                          isKrLithologyPatternUid(
                            rule.style.pattern_uid,
                          )
                            ? KR_LITHOLOGY_PATTERN_SELECTOR
                            : (rule.style.pattern_uid ?? "hatch-45-v1")
                        }
                        disabled={contract.pending}
                        onChange={(event) => {
                          const nextPatternUid = event.target.value;
                          if (
                            nextPatternUid
                            === KR_LITHOLOGY_PATTERN_SELECTOR
                          ) {
                            return;
                          }
                          void contract.onUpdateRule(rule.rule_uid, {
                            style: {
                              ...rule.style,
                              pattern_uid: nextPatternUid,
                            },
                          });
                        }}
                      >
                        {paintCapabilities.patterns
                          .filter(
                            (item) =>
                              !item.pattern_uid.startsWith("lithology:")
                              && item.pattern_uid !== "lithology-column-v1",
                          )
                          .map((item) => (
                            <option
                              key={item.pattern_uid}
                              value={item.pattern_uid}
                            >
                              {item.label}
                            </option>
                          ))}
                        <option value={KR_LITHOLOGY_PATTERN_SELECTOR}>
                          KR lithology pattern
                        </option>
                        <option
                          value="lithology-column-v1"
                          disabled={!lithologyIntervals.length}
                        >
                          Loaded lithology column
                        </option>
                      </select>
                      {isKrLithologyPatternUid(
                        rule.style.pattern_uid,
                      ) ? (
                        <KrLithologyPatternPicker
                          selectedId={rule.style.pattern_uid}
                          disabled={contract.pending}
                          buttonLabel="Choose KR lithology pattern"
                          onSelect={(entry) =>
                            void contract.onUpdateRule(rule.rule_uid, {
                              style: {
                                ...rule.style,
                                appearance: "pattern",
                                pattern_uid: entry.id,
                                color: entry.colors.defaultBackground,
                                raster_asset_uid: null,
                              },
                            })
                          }
                        />
                      ) : null}
                      {rule.style.pattern_uid === "lithology-column-v1" ? (
                        <div
                          style={{
                            display: "grid",
                            gridTemplateColumns:
                              "minmax(0, 1fr) minmax(240px, auto)",
                            gap: 14,
                            alignItems: "center",
                            width: "100%",
                          }}
                        >
                          <button
                            type="button"
                            className="wlv-lithology-column-fill-launch"
                            disabled={
                              contract.pending
                              || !loadedLithologyColumns.length
                            }
                            title={
                              loadedLithologyColumns.length === 1
                                ? "Use the loaded lithology column for the active well"
                                : loadedLithologyColumns.length > 1
                                  ? "Multiple lithology columns are loaded for the active well"
                                  : "No loaded lithology column is available for the active well"
                            }
                          >
                            Choose lithology column
                          </button>
                          <div
                            role="status"
                            aria-live="polite"
                            className="wlv-property-note"
                            style={{
                              margin: 0,
                              minWidth: 0,
                              color: existingSelectedLithologyColumn
                                ? "#82d89a"
                                : loadedLithologyColumns.length > 1
                                  ? "#f4c35a"
                                  : "#e78282",
                            }}
                          >
                            {existingSelectedLithologyColumn
                              ? `Selected: ${existingSelectedLithologyColumn.datasetLabel}`
                              : loadedLithologyColumns.length > 1
                                ? "Multiple lithology columns loaded; select one"
                                : "No lithology column loaded for this well"}
                          </div>
                        </div>
                      ) : null}
                      <label className="wlv-curve-fill-scale-compact">
                        Scale
                        <input
                          type="range"
                          min={0.25}
                          max={4}
                          step={0.25}
                          value={rule.style.pattern_scale ?? 1}
                          disabled={contract.pending}
                          onChange={(event) =>
                            void contract.onUpdateRule(rule.rule_uid, {
                              style: {
                                ...rule.style,
                                pattern_scale: Number(event.target.value),
                              },
                            })
                          }
                        />
                      </label>
                    </>
                  ) : null}

                  {rule.style.appearance === "raster" ? (
                    <select
                      aria-label="Raster"
                      value={rule.style.raster_asset_uid ?? ""}
                      disabled={contract.pending}
                      onChange={(event) =>
                        void contract.onUpdateRule(rule.rule_uid, {
                          style: {
                            ...rule.style,
                            raster_asset_uid: event.target.value,
                          },
                        })
                      }
                    >
                      {paintCapabilities.rasters.map((item) => (
                        <option
                          key={item.raster_asset_uid}
                          value={item.raster_asset_uid}
                        >
                          {item.label}
                        </option>
                      ))}
                    </select>
                  ) : null}

                  <label
                    className="wlv-curve-fill-color-compact"
                    title="Fill color"
                  >
                    <input
                      type="color"
                      value={rule.style.color}
                      disabled={contract.pending}
                      onChange={(event) =>
                        void contract.onUpdateRule(rule.rule_uid, {
                          style: { ...rule.style, color: event.target.value },
                        })
                      }
                    />
                  </label>

                  <label className="wlv-curve-fill-opacity-compact">
                    Opacity
                    <input
                      type="range"
                      min={0.1}
                      max={1}
                      step={0.05}
                      value={rule.style.opacity}
                      disabled={contract.pending}
                      onChange={(event) =>
                        void contract.onUpdateRule(rule.rule_uid, {
                          style: {
                            ...rule.style,
                            opacity: Number(event.target.value),
                          },
                        })
                      }
                    />
                  </label>

                  <div className="wlv-curve-fill-rule-actions">
                    <button
                      type="button"
                      aria-label="Move infill up"
                      disabled={contract.pending || rule.order === 0}
                      onClick={() => void moveRule(rule.rule_uid, -1)}
                    >
                      ↑
                    </button>
                    <button
                      type="button"
                      aria-label="Move infill down"
                      disabled={
                        contract.pending || rule.order === trackRules.length - 1
                      }
                      onClick={() => void moveRule(rule.rule_uid, 1)}
                    >
                      ↓
                    </button>
                    <button
                      type="button"
                      disabled={contract.pending}
                      onClick={() => void contract.onRemoveRule(rule.rule_uid)}
                    >
                      Delete
                    </button>
                  </div>
                </div>
                {rule.state_reason ? (
                  <div className="wlv-property-note">{rule.state_reason}</div>
                ) : null}
              </div>
            ) : null}
          </div>
        );
      })}

      {capabilityError ? (
        <div className="wlv-property-note" role="alert">
          {capabilityError}
        </div>
      ) : null}
      {contract.error ? (
        <div className="wlv-property-note" role="alert">
          {contract.error}
        </div>
      ) : null}
    </div>
  );
}


function FormationTopFillControls({
  track,
  markers,
  curveCatalogItems,
  lithologyIntervals,
  style,
  updateStyle,
  registerDraftApply,
  depthUnit,
}: {
  track: WellLogTrack;
  markers: FormationTopMarker[];
  curveCatalogItems: CurveCatalogItem[];
  lithologyIntervals: LithologyIntervalRecord[];
  style: FormationTopOverlayStyle;
  updateStyle: (trackId: string, patch: Partial<FormationTopOverlayStyle>) => void;
  registerDraftApply: (handler: (() => Promise<boolean>) | null) => void;
  depthUnit: 'm' | 'ft';
}) {
  type OverlayFillZone = FormationTopOverlayStyle["fillZones"][number];
  const DRAFT_ZONE_ID = "overlay-infill-draft";
  const sortedMarkers = [...markers].sort((left, right) => left.md - right.md);
  const curveAssignments = track.trackType === "curve" ? track.curves : [];
  const savedZones = (style.fillZones ?? []).filter((zone) => zone.zoneId !== DRAFT_ZONE_ID);
  const previewZone = (style.fillZones ?? []).find((zone) => zone.zoneId === DRAFT_ZONE_ID);
  const first = sortedMarkers[0];
  const second = sortedMarkers.find((marker) => first && marker.md > first.md);

  const makeDraftZone = (): OverlayFillZone => ({
    zoneId: DRAFT_ZONE_ID,
    enabled: true,
    depthExtent: first && second ? "top_boundaries" : "entire_track",
    intervalFromMd: undefined,
    intervalToMd: undefined,
    topMarkerId: first?.markerId,
    baseMarkerId: second?.markerId,
    source: "solid",
    color: "#f5b93f",
    opacity: 0.12,
    pattern: "solid",
    rasterUrl: undefined,
    rasterFit: "stretch",
    constraint: "track",
    coreObjectOnly: false,
    honorTieInGeometry: false,
    curveAId: curveAssignments[0]?.assignmentId,
    curveBId: curveAssignments[1]?.assignmentId,
    patternScale: 1,
  });

  const [draftZone, setDraftZone] = useState<OverlayFillZone>(() => makeDraftZone());
  const draftZoneRef = useRef<OverlayFillZone>(draftZone);
  const [editingZoneId, setEditingZoneId] = useState<string | null>(null);
  const [expandedLayerIds, setExpandedLayerIds] = useState<Set<string>>(() => new Set());
  const [activeZoneMdPick, setActiveZoneMdPick] = useState<CurveFillMdPickField | null>(null);
  const activeZoneMdPickRef = useRef<CurveFillMdPickField | null>(null);
  const zoneMdPickTokenRef = useRef(`formation-zone-md-pick-${Math.random().toString(36).slice(2)}`);

  const writePreview = (nextDraft: OverlayFillZone) => {
    updateStyle(track.trackId, { fillZones: [...savedZones, { ...nextDraft, zoneId: DRAFT_ZONE_ID }] });
  };

  const updateDraft = (patch: Partial<OverlayFillZone>) => {
    // Overlay preview is an external canvas-state update. Do not perform it
    // inside a React state-updater callback: that is render-phase work and can
    // be deferred until a later unrelated render. Keep a synchronous draft ref
    // and publish the preview directly from the input event.
    const next = {
      ...draftZoneRef.current,
      ...patch,
      zoneId: DRAFT_ZONE_ID,
    };
    draftZoneRef.current = next;
    setDraftZone(next);
    writePreview(next);
  };

  const clearDraft = () => {
    const next = makeDraftZone();
    draftZoneRef.current = next;
    setDraftZone(next);
    setEditingZoneId(null);
    setActiveZoneMdPick(null);
    activeZoneMdPickRef.current = null;
    updateStyle(track.trackId, { fillZones: savedZones });
  };

  useEffect(() => {
    registerDraftApply(async () => {
      const committedZone: OverlayFillZone = {
        ...draftZoneRef.current,
        zoneId: editingZoneId ?? `overlay-infill-${Date.now()}`,
        enabled: true,
      };
      const nextSaved = [...savedZones, committedZone];
      updateStyle(track.trackId, { fillZones: nextSaved });
      const nextDraft = makeDraftZone();
      draftZoneRef.current = nextDraft;
      setDraftZone(nextDraft);
      setEditingZoneId(null);
      setExpandedLayerIds((current) => new Set(current).add(committedZone.zoneId));
      return true;
    });
    return () => registerDraftApply(null);
  }, [draftZone, editingZoneId, savedZones, track.trackId]);

  useEffect(() => {
    const handleResult = (event: Event) => {
      const detail = (event as CustomEvent<CurveFillMdPickResultDetail>).detail;
      if (!detail || detail.token !== zoneMdPickTokenRef.current) return;
      const active = activeZoneMdPickRef.current;
      if (!active) return;
      updateDraft(active === "from" ? { intervalFromMd: detail.depth } : { intervalToMd: detail.depth });
      activeZoneMdPickRef.current = null;
      setActiveZoneMdPick(null);
    };
    window.addEventListener(CURVE_FILL_MD_PICK_RESULT_EVENT, handleResult as EventListener);
    return () => {
      window.removeEventListener(CURVE_FILL_MD_PICK_RESULT_EVENT, handleResult as EventListener);
      window.dispatchEvent(new CustomEvent(CURVE_FILL_MD_PICK_CANCEL_EVENT, { detail: { token: zoneMdPickTokenRef.current } }));
    };
  }, [savedZones]);

  const setZoneMdPickField = (field: CurveFillMdPickField) => {
    if (activeZoneMdPickRef.current === field) {
      activeZoneMdPickRef.current = null;
      setActiveZoneMdPick(null);
      window.dispatchEvent(new CustomEvent(CURVE_FILL_MD_PICK_CANCEL_EVENT, { detail: { token: zoneMdPickTokenRef.current } }));
      return;
    }
    activeZoneMdPickRef.current = field;
    setActiveZoneMdPick(field);
    window.dispatchEvent(new CustomEvent<CurveFillMdPickRequestDetail>(CURVE_FILL_MD_PICK_REQUEST_EVENT, { detail: { token: zoneMdPickTokenRef.current, field } }));
  };

  const editLayer = (zone: OverlayFillZone) => {
    const next = { ...zone, zoneId: DRAFT_ZONE_ID };
    setEditingZoneId(zone.zoneId);
    draftZoneRef.current = next;
    setDraftZone(next);
    updateStyle(track.trackId, { fillZones: [...savedZones.filter((item) => item.zoneId !== zone.zoneId), next] });
  };

  const toggleLayerExpanded = (zoneId: string) => {
    setExpandedLayerIds((current) => {
      const next = new Set(current);
      if (next.has(zoneId)) next.delete(zoneId); else next.add(zoneId);
      return next;
    });
  };

  const zoneExpression = (zone: OverlayFillZone) => {
    const curveName = (assignmentId?: string) => {
      const assignment = curveAssignments.find((item) => item.assignmentId === assignmentId);
      const curve = assignment ? findCurveForAssignment(curveCatalogItems, assignment) : null;
      return curve?.mnemonic ?? assignment?.displayName ?? assignment?.curveId ?? "Curve";
    };
    if (zone.constraint === "track" && zone.coreObjectOnly) return "Core object only";
    if (zone.constraint === "track") return "Full track";
    if (zone.constraint === "left-of-curve") return `Left of ${curveName(zone.curveAId)}`;
    if (zone.constraint === "right-of-curve") return `Right of ${curveName(zone.curveAId)}`;
    if (zone.constraint === "left-of-leftmost-curves") return `Track left to left-most of ${curveName(zone.curveAId)} / ${curveName(zone.curveBId)}`;
    if (zone.constraint === "right-of-rightmost-curves") return `Right-most of ${curveName(zone.curveAId)} / ${curveName(zone.curveBId)} to track right`;
    return `${curveName(zone.curveAId)} to ${curveName(zone.curveBId)}`;
  };

  const zonePaintSummary = (zone: OverlayFillZone) => {
    const appearance = zone.source === "solid" ? "Solid" : zone.source === "raster" ? "Raster" : zone.source === "lithology" ? "KR lithology" : zone.source === "lithology-column" ? "Lithology column" : "Pattern";
    const depth = zone.depthExtent === "top_boundaries" ? "Top boundaries" : zone.depthExtent === "specified_interval" ? "Specified interval" : "Entire track";
    return `${appearance} · ${depth}${zone.honorTieInGeometry ? " · Conform to Tie-In" : ""}`;
  };

  const topMarker = sortedMarkers.find((marker) => marker.markerId === draftZone.topMarkerId);
  const validBaseMarkers = topMarker ? sortedMarkers.filter((marker) => marker.md > topMarker.md) : sortedMarkers;
  const curveBOptions = curveAssignments.filter((assignment) => assignment.assignmentId !== draftZone.curveAId);

  return (
    <div className="wlv-edit-track-fill-zones">
      <section className="wlv-edit-track-fill-zones-content">
        <div className="wlv-edit-track-fill-zones-header">
          <div>
            <h3>Infill Options</h3>
            <div className="wlv-property-note">Preview updates live on the canvas while you edit. Apply Changes saves the current infill as a layer.</div>
          </div>
          <button type="button" onClick={clearDraft}>+ Add infill option</button>
        </div>

        <article className="wlv-edit-track-fill-zone-card is-draft" data-overlay-infill-draft="true">
          <header>
            <div className="wlv-edit-track-fill-zone-title"><strong>{editingZoneId ? "Edit overlay infill" : "New overlay infill"}</strong></div>
            {previewZone ? <button type="button" className="secondary" onClick={clearDraft}>Clear</button> : null}
          </header>
          <SharedInfillEditor
            option={track.trackType === "core" && draftZone.coreObjectOnly ? "core-object" : draftZone.constraint}
            optionOptions={track.trackType === "core" ? [
              { value: "track", label: "Full track" },
              { value: "core-object", label: "Core object only" },
            ] : [
              { value: "track", label: "Full track" },
              { value: "left-of-curve", label: "Left of curve", disabled: track.trackType !== "curve" },
              { value: "right-of-curve", label: "Right of curve", disabled: track.trackType !== "curve" },
              { value: "between-curves", label: "Between curves", disabled: track.trackType !== "curve" },
              { value: "left-of-leftmost-curves", label: "Track left to left-most curve", disabled: track.trackType !== "curve" },
              { value: "right-of-rightmost-curves", label: "Right-most curve to track right", disabled: track.trackType !== "curve" },
            ]}
            onOptionChange={(value) => {
              if (track.trackType === "core") {
                updateDraft({
                  constraint: "track",
                  coreObjectOnly: value === "core-object",
                  curveAId: undefined,
                  curveBId: undefined,
                });
                return;
              }
              const needsCurvePair = value === "between-curves"
                || value === "left-of-leftmost-curves"
                || value === "right-of-rightmost-curves";
              updateDraft({ constraint: value as OverlayFillZone["constraint"], coreObjectOnly: false, curveBId: needsCurvePair ? draftZone.curveBId : undefined });
            }}
            showCurvePair={draftZone.constraint !== "track" && track.trackType === "curve"}
            showCurveB={draftZone.constraint === "between-curves" || draftZone.constraint === "left-of-leftmost-curves" || draftZone.constraint === "right-of-rightmost-curves"}
            curveAValue={draftZone.curveAId ?? ""}
            curveAOptions={curveAssignments.map((assignment) => { const curve = findCurveForAssignment(curveCatalogItems, assignment); return { value: assignment.assignmentId, label: curve?.mnemonic ?? assignment.displayName ?? assignment.curveId }; })}
            onCurveAChange={(value) => updateDraft({ curveAId: value || undefined, curveBId: value === draftZone.curveBId ? undefined : draftZone.curveBId })}
            operator={draftZone.constraint === "between-curves" ? "to" : draftZone.constraint === "left-of-leftmost-curves" || draftZone.constraint === "right-of-rightmost-curves" ? "and" : draftZone.constraint === "left-of-curve" ? "left" : "right"}
            curveBValue={draftZone.curveBId ?? ""}
            curveBOptions={curveBOptions.map((assignment) => { const curve = findCurveForAssignment(curveCatalogItems, assignment); return { value: assignment.assignmentId, label: curve?.mnemonic ?? assignment.displayName ?? assignment.curveId }; })}
            onCurveBChange={(value) => updateDraft({ curveBId: value || undefined })}
            depthExtent={draftZone.depthExtent ?? "top_boundaries"}
            allowTopBoundaries
            onDepthExtentChange={(value) => updateDraft({ depthExtent: value })}
            fromMd={draftZone.intervalFromMd ?? ""}
            toMd={draftZone.intervalToMd ?? ""}
            activeMdPickField={activeZoneMdPick}
            onFromMdChange={(value) => updateDraft({ intervalFromMd: value === "" ? undefined : Number(value) })}
            onToMdChange={(value) => updateDraft({ intervalToMd: value === "" ? undefined : Number(value) })}
            onMdPick={setZoneMdPickField}
            topBoundaryValue={draftZone.topMarkerId ?? ""}
            baseBoundaryValue={draftZone.baseMarkerId ?? ""}
            topBoundaryOptions={sortedMarkers.map((marker) => ({ value: marker.markerId, label: `${marker.markerName} · ${marker.md.toLocaleString(undefined, { maximumFractionDigits: 1 })} ${depthUnit}` }))}
            baseBoundaryOptions={validBaseMarkers.map((marker) => ({ value: marker.markerId, label: `${marker.markerName} · ${marker.md.toLocaleString(undefined, { maximumFractionDigits: 1 })} ${depthUnit}` }))}
            onTopBoundaryChange={(value) => { const markerId = value || undefined; const nextTop = sortedMarkers.find((marker) => marker.markerId === markerId); const currentBase = sortedMarkers.find((marker) => marker.markerId === draftZone.baseMarkerId); updateDraft({ topMarkerId: markerId, baseMarkerId: nextTop && currentBase && currentBase.md > nextTop.md ? currentBase.markerId : undefined }); }}
            onBaseBoundaryChange={(value) => updateDraft({ baseMarkerId: value || undefined })}
            appearance={draftZone.source === "raster" ? "raster" : draftZone.source === "solid" ? "solid" : "pattern"}
            onAppearanceChange={(value) => updateDraft({ source: value === "raster" ? "raster" : value === "solid" ? "solid" : "pattern" })}
            patternValue={draftZone.source === "lithology" ? "kr-lithology" : draftZone.source === "lithology-column" ? "lithology-column" : draftZone.pattern}
            patternOptions={[{ value: "diagonal", label: "Diagonal" }, { value: "dots", label: "Dots" }, { value: "kr-lithology", label: "KR lithology pattern" }, { value: "lithology-column", label: "Loaded lithology column", disabled: !lithologyIntervals.length }]}
            onPatternChange={(value) => updateDraft(value === "kr-lithology" ? { source: "lithology" } : value === "lithology-column" ? { source: "lithology-column", lithologyId: undefined } : { source: "pattern", pattern: value as OverlayFillZone["pattern"] })}
            rasterValue={draftZone.rasterUrl ?? ""}
            rasterTextMode
            onRasterChange={(value) => updateDraft({ rasterUrl: value || undefined })}
            rasterFit={draftZone.rasterFit}
            onRasterFitChange={(value) => updateDraft({ rasterFit: value })}
            selectorKind={draftZone.source === "lithology" ? "kr" : draftZone.source === "lithology-column" ? "lithology-column" : null}
            selectorContent={draftZone.source === "lithology" ? <KrLithologyPatternPicker selectedId={draftZone.lithologyId ?? null} buttonLabel="Choose KR lithology pattern" onSelect={(entry) => updateDraft({ source: "lithology", lithologyId: entry.id, color: entry.colors.defaultBackground })} /> : draftZone.source === "lithology-column" ? <><button type="button" className="wlv-zone-lithology-column-launch" disabled={!lithologyIntervals.length} onClick={() => updateDraft({ source: "lithology-column", lithologyId: undefined })}>Choose lithology column</button><div role="status" aria-live="polite" className="wlv-property-note">{lithologyIntervals.length ? "Loaded lithology column selected" : "No lithology column loaded for this well"}</div></> : null}
            patternScale={draftZone.patternScale ?? 1}
            onPatternScaleChange={(value) => updateDraft({ patternScale: value })}
            color={draftZone.color}
            onColorChange={(value) => updateDraft({ color: value })}
            opacity={draftZone.opacity}
            opacityMax={0.8}
            onOpacityChange={(value) => updateDraft({ opacity: value })}
          />
          {track.trackType === "interval" ? (
            <div className="wlv-property-note" style={{ display: "grid", gap: 6, marginTop: 12 }}>
              <label className="wlv-checkbox-row">
                <input
                  type="checkbox"
                  checked={Boolean(draftZone.honorTieInGeometry)}
                  onChange={(event) => updateDraft({ honorTieInGeometry: event.target.checked })}
                />
                <span>Conform overlay to Tie-In</span>
              </label>
              <span>When enabled, overlay fills on this interval track follow the saved Tie-In geometry instead of extending straight across the track.</span>
            </div>
          ) : null}
        </article>

        <div className="wlv-curve-fill-layer-heading"><strong>Overlay infill layers</strong><span>{savedZones.length}</span></div>
        {savedZones.length === 0 ? <div className="wlv-curve-fill-empty">No saved overlay infill layers for this track.</div> : null}
        {savedZones.map((zone, index) => {
          const expanded = expandedLayerIds.has(zone.zoneId);
          return <div key={zone.zoneId} className={`wlv-curve-fill-rule-card wlv-curve-fill-layer-card${expanded ? " is-expanded" : ""}`}>
            <div className="wlv-curve-fill-layer-summary" onClick={() => toggleLayerExpanded(zone.zoneId)}>
              <label className="wlv-checkbox-row wlv-curve-fill-layer-toggle" onClick={(event) => event.stopPropagation()}>
                <input type="checkbox" checked={zone.enabled} onChange={(event) => updateStyle(track.trackId, { fillZones: savedZones.map((item) => item.zoneId === zone.zoneId ? { ...item, enabled: event.target.checked } : item) })} />
                <strong>Infill {index + 1}</strong>
              </label>
              <button type="button" className="wlv-curve-fill-layer-summary-button" aria-expanded={expanded} onClick={(event) => { event.stopPropagation(); toggleLayerExpanded(zone.zoneId); }}>
                <span className="wlv-curve-fill-layer-expression">{zoneExpression(zone)}</span>
                <span className="wlv-curve-fill-layer-paint-summary">{zonePaintSummary(zone)}</span>
                <span className="wlv-curve-fill-layer-state state-resolved">Saved</span>
                <span aria-hidden="true" className="wlv-curve-fill-layer-chevron">{expanded ? "▴" : "▾"}</span>
              </button>
            </div>
            {expanded ? <div className="wlv-curve-fill-layer-details"><div className="wlv-curve-fill-rule-actions"><button type="button" onClick={() => editLayer(zone)}>Edit</button><button type="button" onClick={() => updateStyle(track.trackId, { fillZones: savedZones.filter((item) => item.zoneId !== zone.zoneId) })}>Delete</button></div></div> : null}
          </div>;
        })}
      </section>
    </div>
  );
}

function sanitizeTextBoxHtml(value: string): string {
  const template = document.createElement("template");
  template.innerHTML = value.slice(0, 6000);
  const allowed = new Set(["DIV", "P", "BR", "B", "STRONG", "I", "EM", "U"]);

  const cleanNode = (node: Node): void => {
    [...node.childNodes].forEach((child) => {
      if (child.nodeType === Node.TEXT_NODE) return;
      if (!(child instanceof HTMLElement)) {
        child.remove();
        return;
      }
      cleanNode(child);
      if (!allowed.has(child.tagName)) {
        child.replaceWith(document.createTextNode(child.textContent ?? ""));
        return;
      }
      [...child.attributes].forEach((attribute) => child.removeAttribute(attribute.name));
    });
  };
  cleanNode(template.content);
  return template.innerHTML || "<div>Text</div>";
}

function textBoxSummary(value: string, fallback: string): string {
  const plain = value
    .replace(/<br\s*\/?>/gi, " ")
    .replace(/<\/(?:div|p)>/gi, " ")
    .replace(/<[^>]+>/g, "")
    .replace(/&nbsp;/gi, " ")
    .replace(/\s+/g, " ")
    .trim();
  return plain || fallback;
}

function RichTextBoxEditor({
  overlayUid,
  contentHtml,
  registerRef,
  onChange,
}: {
  overlayUid: string;
  contentHtml: string;
  registerRef: (overlayUid: string, node: HTMLDivElement | null) => void;
  onChange: (overlayUid: string, html: string) => void;
}) {
  const localRef = useRef<HTMLDivElement | null>(null);
  const initializedForUidRef = useRef<string | null>(null);

  useEffect(() => {
    const editor = localRef.current;
    if (!editor) return;

    registerRef(overlayUid, editor);

    // Initialize only when opening/switching to a different text box.
    // Do not overwrite innerHTML on every parent render; doing so resets
    // the browser caret to the start and causes typed text to appear backwards.
    if (initializedForUidRef.current !== overlayUid) {
      editor.innerHTML = sanitizeTextBoxHtml(contentHtml);
      initializedForUidRef.current = overlayUid;
    }

    return () => registerRef(overlayUid, null);
  }, [overlayUid, contentHtml, registerRef]);

  return (
    <div
      ref={localRef}
      className="wlv-text-box-rich-editor"
      contentEditable
      suppressContentEditableWarning
      role="textbox"
      aria-multiline="true"
      onInput={(event) => {
        const editor = event.currentTarget;
        onChange(overlayUid, sanitizeTextBoxHtml(editor.innerHTML));
      }}
      onBlur={(event) => {
        const editor = event.currentTarget;
        const sanitized = sanitizeTextBoxHtml(editor.innerHTML);
        if (editor.innerHTML !== sanitized) editor.innerHTML = sanitized;
        onChange(overlayUid, sanitized);
      }}
    />
  );
}

function TextOverlayEditor({
  overlays,
  updateOverlays,
  depthUnit,
  defaultMd,
}: {
  overlays: TextOverlayConfig[];
  updateOverlays: (next: TextOverlayConfig[]) => void;
  depthUnit: "m" | "ft";
  defaultMd: number;
}) {
  const [editingUid, setEditingUid] = useState<string | null>(null);
  const richEditorRefs = useRef<Record<string, HTMLDivElement | null>>({});

  const addOverlay = () => {
    const overlayUid = `text-box-${crypto.randomUUID()}`;
    const next: TextOverlayConfig = {
      overlayUid,
      md: defaultMd,
      ...DEFAULT_TEXT_OVERLAY_CONFIG,
    };
    updateOverlays([...overlays, next]);
    setEditingUid(overlayUid);
  };

  const patchOverlay = (overlayUid: string, patch: Partial<TextOverlayConfig>) => {
    updateOverlays(overlays.map((item) => (
      item.overlayUid === overlayUid ? { ...item, ...patch } : item
    )));
  };

  const syncEditor = (overlayUid: string) => {
    const editor = richEditorRefs.current[overlayUid];
    if (!editor) return;
    patchOverlay(overlayUid, {
      contentHtml: sanitizeTextBoxHtml(editor.innerHTML),
    });
  };

  const formatSelection = (
    overlayUid: string,
    command: "bold" | "italic" | "underline",
  ) => {
    const editor = richEditorRefs.current[overlayUid];
    if (!editor) return;
    editor.focus();
    document.execCommand(command, false);
    syncEditor(overlayUid);
  };

  const deleteOverlay = (overlayUid: string) => {
    updateOverlays(overlays.filter((item) => item.overlayUid !== overlayUid));
    if (editingUid === overlayUid) setEditingUid(null);
  };

  return (
    <section className="wlv-edit-track-overlay-section wlv-text-overlay-editor">
      <header className="wlv-edit-track-overlay-style-header">
        <div>
          <h3>Text Overlays</h3>
          <p>Depth-anchored multi-line text boxes with compact formatting and position controls.</p>
        </div>
        <button type="button" onClick={addOverlay}>Add Text Box</button>
      </header>

      {overlays.length === 0 ? (
        <p className="wlv-property-note">No text boxes on this track.</p>
      ) : null}

      <div className="wlv-text-overlay-list">
        {overlays.map((overlay, index) => {
          const expanded = editingUid === overlay.overlayUid;
          return (
            <div key={overlay.overlayUid} className="wlv-text-overlay-item">
              <div className="wlv-text-overlay-summary">
                <button
                  type="button"
                  className="wlv-text-overlay-summary-button"
                  onClick={() => setEditingUid(expanded ? null : overlay.overlayUid)}
                >
                  <span>{textBoxSummary(overlay.contentHtml, `Text Box ${index + 1}`)}</span>
                  <span>{overlay.md.toFixed(2)} {depthUnit}</span>
                </button>
                <button type="button" onClick={() => deleteOverlay(overlay.overlayUid)}>Delete</button>
              </div>

              {expanded ? (
                <div className="wlv-text-overlay-fields">
                  <div className="wlv-text-overlay-field wlv-text-overlay-field--text">
                    <span>Text box</span>
                    <div className="wlv-text-box-format-toolbar" aria-label="Text formatting">
                      <button
                        type="button"
                        title="Bold selected text"
                        onMouseDown={(event) => {
                          event.preventDefault();
                          formatSelection(overlay.overlayUid, "bold");
                        }}
                      ><strong>B</strong></button>
                      <button
                        type="button"
                        title="Italic selected text"
                        onMouseDown={(event) => {
                          event.preventDefault();
                          formatSelection(overlay.overlayUid, "italic");
                        }}
                      ><em>I</em></button>
                      <button
                        type="button"
                        title="Underline selected text"
                        onMouseDown={(event) => {
                          event.preventDefault();
                          formatSelection(overlay.overlayUid, "underline");
                        }}
                      ><u>U</u></button>
                    </div>
                    <RichTextBoxEditor
                      overlayUid={overlay.overlayUid}
                      contentHtml={overlay.contentHtml}
                      registerRef={(overlayUid, node) => {
                        richEditorRefs.current[overlayUid] = node;
                      }}
                      onChange={(overlayUid, html) => {
                        patchOverlay(overlayUid, { contentHtml: html });
                      }}
                    />
                  </div>

                  <label className="wlv-text-overlay-field">
                    <span>MD ({depthUnit})</span>
                    <input
                      type="number"
                      step="0.01"
                      value={overlay.md}
                      onChange={(event) => patchOverlay(overlay.overlayUid, { md: Number(event.target.value) })}
                    />
                  </label>

                  <label className="wlv-text-overlay-field">
                    <span>Horizontal anchor</span>
                    <select
                      value={overlay.horizontalAnchor}
                      onChange={(event) => patchOverlay(overlay.overlayUid, {
                        horizontalAnchor: event.target.value as TextOverlayConfig["horizontalAnchor"],
                      })}
                    >
                      <option value="left">Left</option>
                      <option value="center">Center</option>
                      <option value="right">Right</option>
                    </select>
                  </label>

                  <label className="wlv-text-overlay-field wlv-text-overlay-field--slider">
                    <span>Horizontal position</span>
                    <input
                      type="range"
                      min={-100}
                      max={100}
                      step={1}
                      value={overlay.horizontalOffset}
                      onChange={(event) => patchOverlay(overlay.overlayUid, {
                        horizontalOffset: Number(event.target.value),
                      })}
                    />
                  </label>

                  <label className="wlv-text-overlay-field wlv-text-overlay-field--slider">
                    <span>Vertical position</span>
                    <input
                      type="range"
                      min={-100}
                      max={100}
                      step={1}
                      value={overlay.verticalOffset}
                      onChange={(event) => patchOverlay(overlay.overlayUid, {
                        verticalOffset: Number(event.target.value),
                      })}
                    />
                  </label>

                  <label className="wlv-text-overlay-field wlv-text-overlay-field--slider">
                    <span>Box width</span>
                    <input
                      type="range"
                      min={25}
                      max={100}
                      step={1}
                      value={overlay.widthPercent}
                      onChange={(event) => patchOverlay(overlay.overlayUid, {
                        widthPercent: Number(event.target.value),
                      })}
                    />
                  </label>

                  <label className="wlv-text-overlay-field">
                    <span>Text alignment</span>
                    <select
                      value={overlay.textAlign}
                      onChange={(event) => patchOverlay(overlay.overlayUid, {
                        textAlign: event.target.value as TextOverlayConfig["textAlign"],
                      })}
                    >
                      <option value="left">Left</option>
                      <option value="center">Center</option>
                      <option value="right">Right</option>
                    </select>
                  </label>

                  <label className="wlv-text-overlay-field">
                    <span>Font size</span>
                    <select
                      value={overlay.fontSize}
                      onChange={(event) => patchOverlay(overlay.overlayUid, { fontSize: Number(event.target.value) })}
                    >
                      {[9, 10, 11, 12, 13, 14].map((size) => (
                        <option key={size} value={size}>{size} px</option>
                      ))}
                    </select>
                  </label>

                  <label className="wlv-text-overlay-field">
                    <span>Text colour</span>
                    <input
                      type="color"
                      value={overlay.color}
                      onChange={(event) => patchOverlay(overlay.overlayUid, { color: event.target.value })}
                    />
                  </label>

                  <label className="wlv-text-overlay-field">
                    <span>Background</span>
                    <select
                      value={overlay.background}
                      onChange={(event) => patchOverlay(overlay.overlayUid, {
                        background: event.target.value as TextOverlayConfig["background"],
                      })}
                    >
                      <option value="none">None</option>
                      <option value="light">Light</option>
                    </select>
                  </label>
                </div>
              ) : null}
            </div>
          );
        })}
      </div>
    </section>
  );
}

function DepthRangeLocatorEditor({
  track,
  tracks,
  config,
  updateConfig,
}: {
  track: WellLogTrack;
  tracks: WellLogTrack[];
  config: DepthRangeLocatorConfig;
  updateConfig: (patch: Partial<DepthRangeLocatorConfig>) => void;
}) {
  const compatibleSources = tracks.filter((candidate) => (
    candidate.trackId !== track.trackId
    && Boolean(candidate.managedWellUid)
    && candidate.managedWellUid === track.managedWellUid
  ));

  return (
    <section className="wlv-edit-track-overlay-section wlv-depth-range-locator-editor">
      <header className="wlv-edit-track-overlay-style-header">
        <div>
          <h3>Depth Range Locator</h3>
          <p>Project another track's content or live viewport range onto this track.</p>
        </div>
        <label className="wlv-checkbox-row">
          <input
            type="checkbox"
            checked={config.enabled}
            disabled={compatibleSources.length === 0}
            onChange={(event) => updateConfig({ enabled: event.target.checked })}
          />
          <span>Display on current track</span>
        </label>
      </header>
      <div className="wlv-depth-range-locator-grid">
        <label>
          <span>Source track</span>
          <select
            value={config.sourceTrackId}
            disabled={compatibleSources.length === 0}
            onChange={(event) => updateConfig({
              sourceTrackId: event.target.value,
              enabled: Boolean(event.target.value) && config.enabled,
            })}
          >
            <option value="">Select track…</option>
            {compatibleSources.map((candidate) => (
              <option key={candidate.trackId} value={candidate.trackId}>
                {`T${candidate.trackIndex + 1} · ${candidate.title}`}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>Range</span>
          <select value={config.mode} onChange={(event) => updateConfig({ mode: event.target.value as DepthRangeLocatorConfig['mode'] })}>
            <option value="content_extent">Content Extent</option>
            <option value="viewport_extent">Viewport Extent</option>
            <option value="auto">Auto</option>
          </select>
        </label>
        <label>
          <span>Presentation</span>
          <select value={config.presentation} onChange={(event) => updateConfig({ presentation: event.target.value as DepthRangeLocatorConfig['presentation'] })}>
            <option value="edge_arrows">Edge Arrows</option>
            <option value="wall_bar">Wall Bar</option>
            <option value="data_bar">Data Bar</option>
          </select>
        </label>
        <label>
          <span>Side</span>
          <select value={config.side} onChange={(event) => updateConfig({ side: event.target.value as DepthRangeLocatorConfig['side'] })}>
            <option value="auto">Auto</option>
            <option value="left">Left</option>
            <option value="right">Right</option>
          </select>
        </label>
      </div>
      {compatibleSources.length === 0 ? (
        <p className="wlv-property-note">No same-well source track is available.</p>
      ) : null}
    </section>
  );
}

function MacroCoreImageEditor({
  config,
  updateConfig,
  depthUnit,
}: {
  config: MacroCoreImageConfig;
  updateConfig: (patch: Partial<MacroCoreImageConfig>) => void;
  depthUnit: "m" | "ft";
}) {
  const validInterval = Number.isFinite(config.topMd)
    && Number.isFinite(config.baseMd)
    && config.baseMd > config.topMd;

  return (
    <section className="wlv-edit-track-overlay-section wlv-macro-core-image-editor">
      <header className="wlv-edit-track-overlay-style-header">
        <div>
          <h3>Macro Core Image</h3>
          <p>Place a reusable gray cylindrical core marker directly on the current track.</p>
        </div>
        <label className="wlv-checkbox-row">
          <input
            type="checkbox"
            checked={config.enabled}
            disabled={!validInterval}
            onChange={(event) => updateConfig({ enabled: event.target.checked })}
          />
          <span>Display on current track</span>
        </label>
      </header>
      <div className="wlv-macro-core-image-grid">
        <label>
          <span>Top MD ({depthUnit})</span>
          <input
            type="number"
            step="0.01"
            value={config.topMd}
            onChange={(event) => updateConfig({ topMd: Number(event.target.value) })}
          />
        </label>
        <label>
          <span>Base MD ({depthUnit})</span>
          <input
            type="number"
            step="0.01"
            value={config.baseMd}
            onChange={(event) => updateConfig({ baseMd: Number(event.target.value) })}
          />
        </label>
        <label>
          <span>Placement</span>
          <select
            value={config.placement}
            onChange={(event) => updateConfig({ placement: event.target.value as MacroCoreImageConfig['placement'] })}
          >
            <option value="left">Left</option>
            <option value="center">Center</option>
            <option value="right">Right</option>
          </select>
        </label>
        <label className="wlv-macro-core-image-offset-control">
          <span>Fine horizontal adjustment</span>
          <div className="wlv-macro-core-image-offset-row">
            <input
              type="range"
              min="-60"
              max="60"
              step="1"
              value={config.horizontalOffsetPx}
              onChange={(event) => updateConfig({ horizontalOffsetPx: Number(event.target.value) })}
              onInput={(event) => updateConfig({ horizontalOffsetPx: Number(event.currentTarget.value) })}
            />
            <input
              aria-label="Macro Core Image horizontal adjustment"
              type="number"
              min="-60"
              max="60"
              step="1"
              value={config.horizontalOffsetPx}
              onChange={(event) => updateConfig({ horizontalOffsetPx: Number(event.target.value) })}
            />
            <span>px</span>
          </div>
        </label>
      </div>
      {!validInterval ? (
        <p className="wlv-property-note">Base MD must be greater than Top MD before the Macro Core Image can be displayed.</p>
      ) : (
        <p className="wlv-property-note">The MCI is track-owned. It does not depend on a Core track or on the Depth Range Locator.</p>
      )}
    </section>
  );
}

function FormationTopOverlayEditor({
  track,
  tracks,
  markers,
  loadedMarkers,
  curveCatalogItems,
  lithologyIntervals,
  style,
  updateStyle,
  registerInfillDraftApply,
  depthUnit,
  locatorConfig,
  updateLocatorConfig,
  macroCoreImageConfig,
  updateMacroCoreImageConfig,
  textOverlays,
  updateTextOverlays,
  defaultTextOverlayMd,
}: {
  track: WellLogTrack;
  tracks: WellLogTrack[];
  markers: FormationTopMarker[];
  loadedMarkers: FormationTopMarker[];
  curveCatalogItems: CurveCatalogItem[];
  lithologyIntervals: LithologyIntervalRecord[];
  style: FormationTopOverlayStyle;
  updateStyle: (trackId: string, patch: Partial<FormationTopOverlayStyle>) => void;
  registerInfillDraftApply: (handler: (() => Promise<boolean>) | null) => void;
  depthUnit: "m" | "ft";
  locatorConfig: DepthRangeLocatorConfig;
  updateLocatorConfig: (patch: Partial<DepthRangeLocatorConfig>) => void;
  macroCoreImageConfig: MacroCoreImageConfig;
  updateMacroCoreImageConfig: (patch: Partial<MacroCoreImageConfig>) => void;
  textOverlays: TextOverlayConfig[];
  updateTextOverlays: (next: TextOverlayConfig[]) => void;
  defaultTextOverlayMd: number;
}) {
  const [overlaySectionTab, setOverlaySectionTab] =
    useState<"formation-tops" | "fill-zones" | "other-options">("formation-tops");
  const [otherOptionsTab, setOtherOptionsTab] = useState<"depth-range-locator" | "macro-core-image" | "text-overlays">("depth-range-locator");

  return (
    <div className="wlv-edit-track-overlay-panel">
      <div
        className="wlv-edit-track-subtabs"
        role="tablist"
        aria-label="Overlay controls"
      >
        <button
          type="button"
          role="tab"
          aria-selected={overlaySectionTab === "formation-tops"}
          className={
            overlaySectionTab === "formation-tops" ? "active" : ""
          }
          onClick={() => setOverlaySectionTab("formation-tops")}
        >
          Formation Tops
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={overlaySectionTab === "fill-zones"}
          className={overlaySectionTab === "fill-zones" ? "active" : ""}
          onClick={() => setOverlaySectionTab("fill-zones")}
        >
          Infill Options
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={overlaySectionTab === "other-options"}
          className={overlaySectionTab === "other-options" ? "active" : ""}
          onClick={() => setOverlaySectionTab("other-options")}
        >
          Other Options
        </button>
      </div>

      <div className="wlv-edit-track-overlay-editor">
        {overlaySectionTab === "formation-tops" ? (
      <section className="wlv-edit-track-overlay-style-panel">
        <header className="wlv-edit-track-overlay-style-header">
          <div>
            <h3>Formation Tops Overlay</h3>
            <p>{markers.length} selected formation top{markers.length === 1 ? "" : "s"} · {loadedMarkers.length} loaded available for infill options. Geological depths are read-only.</p>
          </div>
          <label className="wlv-checkbox-row">
            <input
              type="checkbox"
              checked={style.displayOnTrack}
              onChange={(event) =>
                updateStyle(track.trackId, {
                  displayOnTrack: event.target.checked,
                })
              }
            />
            <span>Display on current track</span>
          </label>
        </header>

        <div className="wlv-edit-track-overlay-style-body">
          <section className="wlv-edit-track-overlay-section">
            <h4>Boundary lines</h4>
            <div className="wlv-edit-track-overlay-boundary-table">
              <div className="wlv-edit-track-overlay-boundary-head">
                <span></span>
                <span>Colour</span>
                <span>Width</span>
                <span>Style</span>
              </div>

              <div className="wlv-edit-track-overlay-boundary-row">
                <strong>Formation Tops</strong>
                <input
                  aria-label="Formation Tops colour"
                  type="color"
                  value={style.topColor}
                  onChange={(event) =>
                    updateStyle(track.trackId, {
                      topColor: event.target.value,
                    })
                  }
                />
                <input
                  aria-label="Formation Tops width"
                  type="number"
                  min="0.5"
                  max="8"
                  step="0.5"
                  value={style.topWidth}
                  onChange={(event) =>
                    updateStyle(track.trackId, {
                      topWidth: Number(event.target.value),
                    })
                  }
                />
                <select
                  aria-label="Formation Tops style"
                  value={style.topLineStyle}
                  onChange={(event) =>
                    updateStyle(track.trackId, {
                      topLineStyle:
                        event.target.value as FormationTopOverlayStyle["topLineStyle"],
                    })
                  }
                >
                  <option value="solid">Solid</option>
                  <option value="dash">Dashed</option>
                  <option value="dot">Dotted</option>
                </select>
              </div>

              <div className="wlv-edit-track-overlay-boundary-row">
                <strong>Formation Bases</strong>
                <input
                  aria-label="Formation Bases colour"
                  type="color"
                  value={style.baseColor}
                  onChange={(event) =>
                    updateStyle(track.trackId, {
                      baseColor: event.target.value,
                    })
                  }
                />
                <input
                  aria-label="Formation Bases width"
                  type="number"
                  min="0.5"
                  max="8"
                  step="0.5"
                  value={style.baseWidth}
                  onChange={(event) =>
                    updateStyle(track.trackId, {
                      baseWidth: Number(event.target.value),
                    })
                  }
                />
                <select
                  aria-label="Formation Bases style"
                  value={style.baseLineStyle}
                  onChange={(event) =>
                    updateStyle(track.trackId, {
                      baseLineStyle:
                        event.target.value as FormationTopOverlayStyle["baseLineStyle"],
                    })
                  }
                >
                  <option value="solid">Solid</option>
                  <option value="dash">Dashed</option>
                  <option value="dot">Dotted</option>
                </select>
              </div>
            </div>
          </section>

          <section className="wlv-edit-track-overlay-section">
            <h4>Opacity</h4>
            <div className="wlv-edit-track-overlay-two-column-row">
              <label>
                <span>Line opacity</span>
                <input
                  type="range"
                  min="0.1"
                  max="1"
                  step="0.05"
                  value={style.opacity}
                  onChange={(event) =>
                    updateStyle(track.trackId, {
                      opacity: Number(event.target.value),
                    })
                  }
                />
              </label>
              <label>
                <span>Label background opacity</span>
                <input
                  type="range"
                  min="0"
                  max="1"
                  step="0.05"
                  value={style.labelBackgroundOpacity}
                  onChange={(event) =>
                    updateStyle(track.trackId, {
                      labelBackgroundOpacity: Number(event.target.value),
                    })
                  }
                />
              </label>
            </div>
          </section>

          {track.trackType === "core" ? (
            <section className="wlv-edit-track-overlay-section">
              <h4>Placement</h4>
              <div className="wlv-core-overlay-placement-grid">
                <label>
                  <span>Position</span>
                  <select
                    value={detectCoreOverlayPlacement(style)}
                    onChange={(event) =>
                      updateStyle(
                        track.trackId,
                        CORE_OVERLAY_LANE_PRESETS[
                          event.target.value as "left" | "center" | "right"
                        ],
                      )
                    }
                    onInput={(event) =>
                      updateStyle(
                        track.trackId,
                        CORE_OVERLAY_LANE_PRESETS[
                          event.currentTarget.value as "left" | "center" | "right"
                        ],
                      )
                    }
                  >
                    <option value="left">Left</option>
                    <option value="center">Center</option>
                    <option value="right">Right</option>
                  </select>
                </label>

                <label>
                  <span>Left inset</span>
                  <input
                    type="range"
                    min="0"
                    max="70"
                    step="1"
                    value={style.trackLeftInsetPct}
                    onChange={(event) =>
                      updateStyle(track.trackId, {
                        trackLeftInsetPct: Number(event.target.value),
                      })
                    }
                    onInput={(event) =>
                      updateStyle(track.trackId, {
                        trackLeftInsetPct: Number(event.currentTarget.value),
                      })
                    }
                  />
                </label>

                <label>
                  <span>Right inset</span>
                  <input
                    type="range"
                    min="0"
                    max="70"
                    step="1"
                    value={style.trackRightInsetPct}
                    onChange={(event) =>
                      updateStyle(track.trackId, {
                        trackRightInsetPct: Number(event.target.value),
                      })
                    }
                    onInput={(event) =>
                      updateStyle(track.trackId, {
                        trackRightInsetPct: Number(event.currentTarget.value),
                      })
                    }
                  />
                </label>
              </div>
              <div className="wlv-property-note">Placement applies to formation tops, KR patterns, and lithology-column overlays on the current core track. Preview updates live on the canvas while you adjust these controls.</div>
            </section>
          ) : null}

          <section className="wlv-edit-track-overlay-section">
            <div className="wlv-edit-track-overlay-section-heading">
              <h4>Labels</h4>
              <div className="wlv-edit-track-overlay-toggle-row">
                <label className="wlv-checkbox-row">
                  <input
                    type="checkbox"
                    checked={style.showLabels}
                    onChange={(event) =>
                      updateStyle(track.trackId, {
                        showLabels: event.target.checked,
                      })
                    }
                  />
                  <span>Show labels</span>
                </label>
                <label className="wlv-checkbox-row">
                  <input
                    type="checkbox"
                    checked={style.labelBackground}
                    onChange={(event) =>
                      updateStyle(track.trackId, {
                        labelBackground: event.target.checked,
                      })
                    }
                  />
                  <span>Label background</span>
                </label>
              </div>
            </div>

            <div className="wlv-edit-track-overlay-label-grid">
              <label>
                <span>Position</span>
                <select
                  value={style.labelPosition}
                  onChange={(event) =>
                    updateStyle(track.trackId, {
                      labelPosition:
                        event.target.value as FormationTopOverlayStyle["labelPosition"],
                    })
                  }
                >
                  <option value="left">Left</option>
                  <option value="center">Center</option>
                  <option value="right">Right</option>
                </select>
              </label>

              <label>
                <span>Font size</span>
                <input
                  type="number"
                  min="8"
                  max="20"
                  step="1"
                  value={style.labelFontSize}
                  onChange={(event) =>
                    updateStyle(track.trackId, {
                      labelFontSize: Number(event.target.value),
                    })
                  }
                />
              </label>

              <label>
                <span>Text colour</span>
                <input
                  aria-label="Formation label text colour"
                  type="color"
                  value={style.labelTextColor}
                  onChange={(event) =>
                    updateStyle(track.trackId, {
                      labelTextColor: event.target.value,
                    })
                  }
                />
              </label>

              <label>
                <span>Background colour</span>
                <input
                  aria-label="Formation label background colour"
                  type="color"
                  value={style.labelBackgroundColor}
                  disabled={!style.labelBackground}
                  onChange={(event) =>
                    updateStyle(track.trackId, {
                      labelBackgroundColor: event.target.value,
                    })
                  }
                />
              </label>

              <label>
                <span>Horizontal offset</span>
                <input
                  type="range"
                  min="-40"
                  max="80"
                  step="1"
                  value={style.labelOffsetX}
                  onChange={(event) =>
                    updateStyle(track.trackId, {
                      labelOffsetX: Number(event.target.value),
                    })
                  }
                />
              </label>

              <label>
                <span>Vertical offset</span>
                <input
                  type="range"
                  min="-40"
                  max="40"
                  step="1"
                  value={style.labelOffsetY}
                  onChange={(event) =>
                    updateStyle(track.trackId, {
                      labelOffsetY: Number(event.target.value),
                    })
                  }
                />
              </label>
            </div>
          </section>
        </div>

        <footer className="wlv-edit-track-overlay-style-footer">
          <button
            type="button"
            onClick={() =>
              tracks.forEach((candidateTrack) =>
                updateStyle(candidateTrack.trackId, { ...style }),
              )
            }
          >
            Extend to all tracks
          </button>
          <button
            type="button"
            className="secondary"
            onClick={() =>
              updateStyle(
                track.trackId,
                DEFAULT_FORMATION_TOP_OVERLAY_STYLE,
              )
            }
          >
            Reset styling
          </button>
        </footer>
      </section>
        ) : overlaySectionTab === "fill-zones" ? (
      <section className="wlv-edit-track-overlay-fill-panel">
        <FormationTopFillControls
          track={track}
          markers={loadedMarkers}
          curveCatalogItems={curveCatalogItems}
          lithologyIntervals={lithologyIntervals}
          style={style}
          updateStyle={updateStyle}
          registerDraftApply={registerInfillDraftApply}
          depthUnit={depthUnit}
        />
      </section>
        ) : (
          <div className="wlv-edit-track-overlay-panel">
            <div
              className="wlv-edit-track-subtabs wlv-edit-track-subtabs--secondary"
              role="tablist"
              aria-label="Other overlay options"
            >
              <button
                type="button"
                role="tab"
                aria-selected={otherOptionsTab === "depth-range-locator"}
                className={otherOptionsTab === "depth-range-locator" ? "active" : ""}
                onClick={() => setOtherOptionsTab("depth-range-locator")}
              >
                Depth Range Locator
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={otherOptionsTab === "macro-core-image"}
                className={otherOptionsTab === "macro-core-image" ? "active" : ""}
                onClick={() => setOtherOptionsTab("macro-core-image")}
              >
                Macro Core Image
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={otherOptionsTab === "text-overlays"}
                className={otherOptionsTab === "text-overlays" ? "active" : ""}
                onClick={() => setOtherOptionsTab("text-overlays")}
              >
                Text Overlays
              </button>
            </div>
            {otherOptionsTab === "depth-range-locator" ? (
              <DepthRangeLocatorEditor
                track={track}
                tracks={tracks}
                config={locatorConfig}
                updateConfig={updateLocatorConfig}
              />
            ) : otherOptionsTab === "macro-core-image" ? (
              <MacroCoreImageEditor
                config={macroCoreImageConfig}
                updateConfig={updateMacroCoreImageConfig}
                depthUnit={depthUnit}
              />
            ) : (
              <TextOverlayEditor
                overlays={textOverlays}
                updateOverlays={updateTextOverlays}
                depthUnit={depthUnit}
                defaultMd={defaultTextOverlayMd}
              />
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function CoreAppearanceEditor({
  appearance,
  updateAppearance,
}: {
  appearance: CoreTrackAppearance;
  updateAppearance: (patch: Partial<CoreTrackAppearance>) => void;
}) {
  return (
    <div className="wlv-edit-track-overlay-panel">
      <section className="wlv-edit-track-overlay-style-panel">
        <header className="wlv-edit-track-overlay-style-header">
          <div>
            <h3>Core Appearance</h3>
            <p>Control the core-body color, brightness, and cylindrical shading for zoomed-out core segments.</p>
            <p className="wlv-property-note">Preview updates live on the canvas while you drag. Apply saves. Cancel restores the prior committed state.</p>
          </div>
        </header>

        <div className="wlv-edit-track-overlay-style-body">
          <section className="wlv-edit-track-overlay-section">
            <div className="wlv-core-appearance-grid">
              <label>
                <span>Color</span>
                <input
                  aria-label="Core base colour"
                  type="color"
                  value={appearance.baseColor}
                  onChange={(event) => updateAppearance({ baseColor: event.target.value })}
                  onInput={(event) => updateAppearance({ baseColor: event.currentTarget.value })}
                />
              </label>

              <label>
                <span>Brightness</span>
                <input
                  type="range"
                  min="0.55"
                  max="1.45"
                  step="0.05"
                  value={appearance.brightness}
                  onChange={(event) => updateAppearance({ brightness: Number(event.target.value) })}
                  onInput={(event) => updateAppearance({ brightness: Number(event.currentTarget.value) })}
                />
              </label>

              <div className="wlv-core-appearance-toggle-row">
                <label className="wlv-checkbox-row">
                  <input
                    type="checkbox"
                    checked={appearance.shadingMode === "cylindrical"}
                    onChange={(event) =>
                      updateAppearance({
                        shadingMode: event.target.checked ? "cylindrical" : "flat",
                      })
                    }
                    onInput={(event) =>
                      updateAppearance({
                        shadingMode: event.currentTarget.checked ? "cylindrical" : "flat",
                      })
                    }
                  />
                  <span>3D shading</span>
                </label>
              </div>

              {appearance.shadingMode === "cylindrical" ? (
                <label>
                  <span>Strength</span>
                  <input
                    type="range"
                    min="0"
                    max="1"
                    step="0.05"
                    value={appearance.shadingStrength}
                    onChange={(event) =>
                      updateAppearance({ shadingStrength: Number(event.target.value) })
                    }
                    onInput={(event) =>
                      updateAppearance({ shadingStrength: Number(event.currentTarget.value) })
                    }
                  />
                </label>
              ) : null}
            </div>
          </section>

          <details className="wlv-core-description-presentation-section" open>
            <summary>Core Description</summary>
            <div className="wlv-core-description-overlay-controls">
              <label className="wlv-core-description-presentation-mode">
                <span>Presentation</span>
                <select
                  aria-label="Core presentation"
                  value={appearance.descriptionPresentationMode}
                  onChange={(event) =>
                    updateAppearance({
                      descriptionPresentationMode:
                        event.target.value as CorePresentationMode,
                    })
                  }
                >
                  <option value="core_left_description_right">
                    Core Left / Description Right
                  </option>
                  <option value="description_left_core_right">
                    Description Left / Core Right
                  </option>
                  <option value="core_centered">
                    Core Centered / No Description
                  </option>
                </select>
              </label>

              <label>
                <span>Description width</span>
                <div className="wlv-core-description-overlay-range-row">
                  <input
                    type="range"
                    min="20"
                    max="70"
                    step="1"
                    disabled={appearance.descriptionPresentationMode === "core_centered"}
                    value={appearance.descriptionOverlayWidthPct}
                    onChange={(event) =>
                      updateAppearance({
                        descriptionOverlayWidthPct: Number(event.target.value),
                      })
                    }
                    onInput={(event) =>
                      updateAppearance({
                        descriptionOverlayWidthPct: Number(event.currentTarget.value),
                      })
                    }
                  />
                  <input
                    aria-label="Core Description width percent"
                    type="number"
                    min="20"
                    max="70"
                    step="1"
                    disabled={appearance.descriptionPresentationMode === "core_centered"}
                    value={appearance.descriptionOverlayWidthPct}
                    onChange={(event) =>
                      updateAppearance({
                        descriptionOverlayWidthPct: Number(event.target.value),
                      })
                    }
                  />
                  <span>%</span>
                </div>
              </label>

              <label>
                <span>Text size</span>
                <div className="wlv-core-description-overlay-range-row">
                  <input
                    type="range"
                    min="8"
                    max="20"
                    step="1"
                    disabled={appearance.descriptionPresentationMode === "core_centered"}
                    value={appearance.descriptionOverlayFontSize}
                    onChange={(event) =>
                      updateAppearance({
                        descriptionOverlayFontSize: Number(event.target.value),
                      })
                    }
                    onInput={(event) =>
                      updateAppearance({
                        descriptionOverlayFontSize: Number(event.currentTarget.value),
                      })
                    }
                  />
                  <input
                    aria-label="Core Description text size"
                    type="number"
                    min="8"
                    max="20"
                    step="1"
                    disabled={appearance.descriptionPresentationMode === "core_centered"}
                    value={appearance.descriptionOverlayFontSize}
                    onChange={(event) =>
                      updateAppearance({
                        descriptionOverlayFontSize: Number(event.target.value),
                      })
                    }
                  />
                  <span>px</span>
                </div>
              </label>

              <label className="wlv-checkbox-row">
                <input
                  type="checkbox"
                  disabled={appearance.descriptionPresentationMode === "core_centered"}
                  checked={appearance.descriptionOverlayShowMd}
                  onChange={(event) =>
                    updateAppearance({
                      descriptionOverlayShowMd: event.target.checked,
                    })
                  }
                />
                <span>Show MD labels</span>
              </label>
            </div>
            <p className="wlv-property-note">
              Description records remain depth-anchored to the Core viewport.
              Text size remains fixed in screen pixels while zooming.
            </p>
          </details>
        </div>
      </section>
    </div>
  );
}

export function WellLogPropertiesPanelSlot({
  tracks,
  selection,
  completionComponentsByWellUid,
  selectedCompletionComponentIdsByWellUid,
  coreImageItemsByWellUid,
  selectedCoreImageIdsByWellUid,
  curveCatalogItems,
  managedSampleContractsByCurveId,
  managedSampleErrorsByCurveId,
  wdvIdentityMetadata,
  wdvIdentityMetadataError,
  wellNameByManagedWellUid,
  updateTrack,
  updateCurveAssignment,
  previewCurveLineStyle,
  commitCurveLineStyle,
  curveFillV2,
  curveEditRequest,
  formationTops,
  loadedFormationTops,
  lithologyIntervals,
  depthUnit,
  formationTopOverlayStylesByTrackId,
  updateFormationTopOverlayStyle,
  commitFormationTopOverlayStyles,
  collapsed = false,
  onToggleCollapsed,
  legacyPanel: _legacyPanel,
}: {
  tracks: WellLogTrack[];
  selection: SelectionRef;
  selectedTrackIds?: string[];
  completionComponentsByWellUid?: Record<string, CompletionComponentRecord[]>;
  selectedCompletionComponentIdsByWellUid?: Record<string, Set<string>>;
  coreImageItemsByWellUid?: Record<string, CoreImageInventoryItem[]>;
  selectedCoreImageIdsByWellUid?: Record<string, Set<string>>;
  curveCatalogItems: CurveCatalogItem[];
  managedSampleContractsByCurveId: ManagedCurveSampleContractsByCurveId;
  managedSampleErrorsByCurveId: Record<string, string>;
  wdvIdentityMetadata: WdvIdentityMetadataContract | null;
  wdvIdentityMetadataError: string | null;
  wellNameByManagedWellUid?: Record<string, string>;
  updateTrack: (trackId: string, patch: Partial<WellLogTrack>) => void;
  updateCurveAssignment: (
    trackId: string,
    assignmentId: string,
    patch: Partial<CurveAssignment>,
    options?: Readonly<{ persist?: boolean }>,
  ) => void;
  previewCurveLineStyle: (
    trackId: string,
    assignmentId: string,
    value: CurveLineStyleValue,
  ) => void;
  commitCurveLineStyle: (
    trackId: string,
    assignmentId: string,
    value: CurveLineStyleValue,
  ) => void;
  curveFillV2?: CurveFillV2PanelContract;
  curveEditRequest?: {
    trackId: string;
    assignmentId: string;
    requestId: number;
  } | null;
  formationTops: FormationTopMarker[];
  loadedFormationTops: FormationTopMarker[];
  lithologyIntervals: LithologyIntervalRecord[];
  depthUnit: 'm' | 'ft';
  formationTopOverlayStylesByTrackId: Record<string, FormationTopOverlayStyle>;
  updateFormationTopOverlayStyle: (trackId: string, patch: Partial<FormationTopOverlayStyle>) => void;
  commitFormationTopOverlayStyles: (stylesByTrackId: Record<string, FormationTopOverlayStyle>, touchedTrackIds: string[]) => void;
  collapsed?: boolean;
  onToggleCollapsed?: () => void;
  legacyPanel?: ReactElement;
}) {
  const [curveDesignCollapsed, setCurveDesignCollapsed] = useState(true);
  const [curveInfoCollapsed, setCurveInfoCollapsed] = useState(true);
  const [standardDesignCollapsed, setStandardDesignCollapsed] = useState(true);
  const [standardTrackMetadataCollapsed, setStandardTrackMetadataCollapsed] = useState(true);
  const [standardInfoCollapsed, setStandardInfoCollapsed] = useState(true);
  const [curveEditModalOpen, setCurveEditModalOpen] = useState(false);
  const [curveEditModalTab, setCurveEditModalTab] =
    useState<"curve" | "overlays" | "appearance" | "completion" | "interval">("curve");
  const [curveEditSectionTab, setCurveEditSectionTab] =
    useState<"controls" | "infill">("controls");
  const [editTrackOriginalCurve, setEditTrackOriginalCurve] =
    useState<CurveAssignment | null>(null);
  const [editTrackOriginalCurves, setEditTrackOriginalCurves] =
    useState<CurveAssignment[]>([]);
  const [editTrackCurveAssignmentId, setEditTrackCurveAssignmentId] =
    useState<string | null>(null);
  const [editTrackSessionTarget, setEditTrackSessionTarget] =
    useState<WdvConfigurationSessionTarget | null>(null);
  const [editTrackOriginalCoreAppearance, setEditTrackOriginalCoreAppearance] =
    useState<CoreTrackAppearance | null>(null);
  const [editTrackOriginalCompletionAppearance, setEditTrackOriginalCompletionAppearance] =
    useState<CompletionTrackAppearance | null>(null);
  const [editTrackCompletionCommitError, setEditTrackCompletionCommitError] =
    useState<string | null>(null);
  const [editTrackOriginalDepthRangeLocator, setEditTrackOriginalDepthRangeLocator] =
    useState<DepthRangeLocatorConfig | null>(null);
  const [editTrackOriginalMacroCoreImage, setEditTrackOriginalMacroCoreImage] =
    useState<MacroCoreImageConfig | null>(null);
  const [editTrackOriginalTextOverlays, setEditTrackOriginalTextOverlays] = useState<TextOverlayConfig[]>([]);
  const [editTrackTextOverlayCommitError, setEditTrackTextOverlayCommitError] = useState<string | null>(null);
  const [editTrackMacroCoreImageCommitError, setEditTrackMacroCoreImageCommitError] = useState<string | null>(null);
  const [editTrackMacroCoreImageDirty, setEditTrackMacroCoreImageDirty] = useState(false);
  const [editTrackOriginalOverlayStyles, setEditTrackOriginalOverlayStyles] =
    useState<Record<string, FormationTopOverlayStyle>>({});
  const [editTrackDirty, setEditTrackDirty] = useState(false);
  const [editTrackOverlayDirty, setEditTrackOverlayDirty] = useState(false);
  const liveOverlayStylesRef = useRef<Record<string, FormationTopOverlayStyle>>(
    formationTopOverlayStylesByTrackId,
  );
  const touchedOverlayTrackIdsRef = useRef<Set<string>>(new Set());
  const lastHandledCurveEditRequestIdRef = useRef<number | null>(null);
  const [curveEditModalOffset, setCurveEditModalOffset] = useState({
    x: 0,
    y: 0,
  });
  const [curveEditModalDrag, setCurveEditModalDrag] = useState<{
    pointerId: number;
    startX: number;
    startY: number;
    originX: number;
    originY: number;
  } | null>(null);
  const curveEditModalRef = useRef<HTMLElement | null>(null);
  const intervalConfigMountRef = useRef<HTMLDivElement | null>(null);
  const [intervalConfigTab, setIntervalConfigTab] =
    useState<"formation" | "depth" | "descriptions" | "tie_in">("formation");
  const curveFillDraftApplyRef = useRef<
    null | (() => Promise<boolean>)
  >(null);
  const overlayInfillDraftApplyRef = useRef<null | (() => Promise<boolean>)>(null);
  const [curveEditModalSize, setCurveEditModalSize] = useState<{
    width: number;
    height: number;
  } | null>(null);
  const [curveEditModalResize, setCurveEditModalResize] = useState<{
    startX: number;
    startY: number;
    originWidth: number;
    originHeight: number;
    originOffsetX: number;
    originOffsetY: number;
  } | null>(null);
  const normalizedSelection = normalizePropertiesSelection(
    tracks,
    selection,
    curveCatalogItems,
  );
  const selectedTrack =
    tracks.find((track) => track.trackId === normalizedSelection.trackId) ??
    tracks[0];
  const normalizedSelectionAssignmentId =
    normalizedSelection.kind === "curve"
      ? normalizedSelection.assignmentId
      : null;

  const contract = resolvePrototypePropertiesPanelContract({
    tracks,
    selection: normalizedSelection,
    curveCatalog: curveCatalogItems,
    managedSampleContractsByCurveId,
    managedSampleErrorsByCurveId,
    wdvIdentityMetadata,
    wdvIdentityMetadataError,
  });

  const standardNonDepthTrack =
    selectedTrack &&
    selectedTrack.trackType !== "depth" &&
    selectedTrack.trackType !== "curve"
      ? selectedTrack
      : null;
  const standardTrackTypeLabel = standardNonDepthTrack
    ? readableTrackType(standardNonDepthTrack)
    : "Track";
  const standardDesignSections: PropertiesPanelSection[] =
    standardNonDepthTrack
      ? contract.tabs.design.sections.map((section, index) =>
          index === 0
            ? {
                ...section,
                title: `${standardTrackTypeLabel} Design Parameters`,
              }
            : section,
        )
      : [];
  const standardTrackMetadataSection =
    standardNonDepthTrack &&
    (standardNonDepthTrack.trackType === "core"
      || standardNonDepthTrack.trackType === "completion")
      ? trackPropertiesMetadataSection(standardNonDepthTrack)
      : null;

  const commonWellSections = contract.tabs.info.sections.filter(
    (section) =>
      section.sectionId === "well-metadata"
      || section.sectionId === "qaqc-metadata",
  );

  const selectedTrackOwnerUid = standardNonDepthTrack?.managedWellUid ?? "";
  const allCoreItems =
    selectedTrackOwnerUid && coreImageItemsByWellUid
      ? coreImageItemsByWellUid[selectedTrackOwnerUid] ?? []
      : [];
  const selectedCoreIds =
    selectedTrackOwnerUid && selectedCoreImageIdsByWellUid
      ? selectedCoreImageIdsByWellUid[selectedTrackOwnerUid]
      : undefined;
  const coreItems =
    selectedCoreIds && selectedCoreIds.size > 0
      ? allCoreItems.filter((item) => selectedCoreIds.has(item.productId))
      : allCoreItems;

  const allCompletionItems =
    selectedTrackOwnerUid && completionComponentsByWellUid
      ? completionComponentsByWellUid[selectedTrackOwnerUid] ?? []
      : [];
  const selectedCompletionIds =
    selectedTrackOwnerUid && selectedCompletionComponentIdsByWellUid
      ? selectedCompletionComponentIdsByWellUid[selectedTrackOwnerUid]
      : undefined;
  const completionItems =
    selectedCompletionIds && selectedCompletionIds.size > 0
      ? allCompletionItems.filter((item) =>
          selectedCompletionIds.has(item.componentId),
        )
      : allCompletionItems;

  const standardInfoSections: PropertiesPanelSection[] =
    standardNonDepthTrack?.trackType === "core"
      ? [
          corePropertiesMetadataSection(coreItems),
          ...commonWellSections,
        ]
      : standardNonDepthTrack?.trackType === "completion"
        ? [
            completionPropertiesMetadataSection(completionItems),
            ...commonWellSections,
          ]
        : standardNonDepthTrack
          ? [
              trackPropertiesMetadataSection(standardNonDepthTrack),
              ...commonWellSections,
            ]
          : [];

  useEffect(() => {
    if (!curveEditModalResize) {
      return;
    }

    const handlePointerMove = (event: PointerEvent) => {
      const maxWidth = Math.max(520, window.innerWidth - 24);
      const maxHeight = Math.max(420, window.innerHeight - 24);

      const nextWidth = Math.min(
        maxWidth,
        Math.max(
          520,
          curveEditModalResize.originWidth +
            (event.clientX - curveEditModalResize.startX),
        ),
      );
      const nextHeight = Math.min(
        maxHeight,
        Math.max(
          420,
          curveEditModalResize.originHeight +
            (event.clientY - curveEditModalResize.startY),
        ),
      );

      setCurveEditModalSize({
        width: nextWidth,
        height: nextHeight,
      });

      /*
       * The backdrop centers the modal. Without offset compensation, changing
       * its size moves the top and left edges by half of the size delta.
       * Counter that movement so the top-left corner remains fixed and the
       * bottom-right resize handle is the only moving corner.
       */
      setCurveEditModalOffset({
        x:
          curveEditModalResize.originOffsetX +
          (nextWidth - curveEditModalResize.originWidth) / 2,
        y:
          curveEditModalResize.originOffsetY +
          (nextHeight - curveEditModalResize.originHeight) / 2,
      });
    };

    const handlePointerUp = () => {
      setCurveEditModalResize(null);
    };

    window.addEventListener("pointermove", handlePointerMove);
    window.addEventListener("pointerup", handlePointerUp);
    window.addEventListener("pointercancel", handlePointerUp);

    return () => {
      window.removeEventListener("pointermove", handlePointerMove);
      window.removeEventListener("pointerup", handlePointerUp);
      window.removeEventListener("pointercancel", handlePointerUp);
    };
  }, [curveEditModalResize]);

  useEffect(() => {
    liveOverlayStylesRef.current = formationTopOverlayStylesByTrackId;
  }, [formationTopOverlayStylesByTrackId]);

  const selectedCurve = resolvePropertiesEditorCurve(
    selectedTrack,
    contract.selectedCurveAssignment,
  );
  const selectedCurveTrackIdentity =
    selectedTrack?.trackType === "curve"
      ? selectedTrack.curves
          .map((curve) =>
            findCurveForAssignment(curveCatalogItems, curve)?.mnemonic
            ?? curve.observedMnemonic
            ?? "Curve",
          )
          .join(" / ")
      : null;
  const selectedCurveTrackHeaderSubtitle =
    selectedTrack?.trackType === "curve"
      ? (() => {
          const descriptions: string[] = [];
          const depthMins: number[] = [];
          const depthMaxs: number[] = [];
          const depthUnits: string[] = [];

          for (const assignment of selectedTrack.curves) {
            const catalogItem = findCurveForAssignment(curveCatalogItems, assignment);
            const sampleContract = resolveManagedCurveContract(
              managedSampleContractsByCurveId,
              {
                managedWellUid: assignment.managedWellUid ?? null,
                curveUid: assignment.curveUid ?? null,
                curveId: assignment.curveId,
              },
            );
            const description = (
              assignment.displayName
              ?? sampleContract?.display_name
              ?? catalogItem?.description
              ?? catalogItem?.mnemonic
              ?? assignment.observedMnemonic
              ?? "Curve"
            ).trim();
            if (description && !descriptions.includes(description)) {
              descriptions.push(description);
            }
            if (
              typeof sampleContract?.depth_min === "number"
              && Number.isFinite(sampleContract.depth_min)
            ) {
              depthMins.push(sampleContract.depth_min);
            }
            if (
              typeof sampleContract?.depth_max === "number"
              && Number.isFinite(sampleContract.depth_max)
            ) {
              depthMaxs.push(sampleContract.depth_max);
            }
            const depthUnit = sampleContract?.depth_unit?.trim();
            if (depthUnit && !depthUnits.includes(depthUnit)) {
              depthUnits.push(depthUnit);
            }
          }

          const depthRange =
            depthMins.length > 0 && depthMaxs.length > 0
              ? `${Math.min(...depthMins).toLocaleString(undefined, { maximumFractionDigits: 2 })}–${Math.max(...depthMaxs).toLocaleString(undefined, { maximumFractionDigits: 2 })}${depthUnits.length > 0 ? ` ${depthUnits.join(" / ")}` : ""}`
              : null;
          const hostWellUid =
            selectedTrack.managedWellUid
            ?? selectedTrack.curves.find((curve) => curve.managedWellUid)?.managedWellUid
            ?? null;
          const hostWell =
            (hostWellUid ? wellNameByManagedWellUid?.[hostWellUid] : null)
            ?? "Well not supplied";

          return [
            descriptions.join(" / ") || "Curve",
            depthRange,
            hostWell,
          ].filter((value): value is string => Boolean(value)).join(" · ");
        })()
      : null;
  const curveSelectionUnresolved =
    normalizedSelection.kind === "curve" &&
    selectedTrack?.trackType === "curve" &&
    selectedCurve === null;

  /*
   * EDIT TRACK MODAL TARGET AUTHORITY
   *
   * The Properties panel follows live WDV selection. Once a modal transaction
   * opens, the modal remains bound to the track that opened it until
   * Apply/Cancel/X closes the transaction.
   */
  const editTrackTarget =
    curveEditModalOpen && editTrackSessionTarget
      ? tracks.find((track) =>
          matchesWdvConfigurationSessionTarget(track, editTrackSessionTarget),
        ) ?? null
      : selectedTrack;

  useEffect(() => {
    if (
      !curveEditModalOpen
      || curveEditModalTab !== "interval"
      || editTrackTarget?.trackType !== "interval"
    ) {
      return;
    }

    const frame = window.requestAnimationFrame(() => {
      const portalTarget = intervalConfigMountRef.current;
      if (!portalTarget) return;

      window.dispatchEvent(
        new CustomEvent("wlv:open-interval-track-editor", {
          detail: {
            tab: intervalConfigTab,
            portalTarget,
            embedded: true,
          },
        }),
      );
    });

    return () => window.cancelAnimationFrame(frame);
  }, [
    curveEditModalOpen,
    curveEditModalTab,
    editTrackTarget?.trackId,
    editTrackTarget?.trackType,
    intervalConfigTab,
  ]);

  const editTrackTargetCurve =
    editTrackTarget?.trackType === "curve" && editTrackCurveAssignmentId
      ? editTrackTarget.curves.find(
          (curve) => curve.assignmentId === editTrackCurveAssignmentId,
        ) ?? null
      : null;

  const editTrackTargetCurveCatalogItem =
    editTrackTargetCurve
      ? findCurveForAssignment(curveCatalogItems, editTrackTargetCurve)
      : null;

  const beginEditTrackSession = (initialTab: "curve" | "overlays" | "appearance" | "completion" | "interval" = "curve") => {
    touchedOverlayTrackIdsRef.current = new Set();
    if (!selectedTrack) {
      return;
    }

    // Freeze the complete edit-session target. Curve Fill interactions and
    // ordinary canvas selection may legitimately change live Properties state
    // while this external window is open. None of those changes may retarget
    // the transaction. Missing/deleted targets invalidate the editor instead
    // of falling back to another track or curve.
    const frozenCurve = selectedTrack.trackType === "curve" ? selectedCurve : null;
    if (selectedTrack.trackType === "curve" && !frozenCurve) {
      return;
    }
    const frozenTarget: WdvConfigurationSessionTarget = {
      trackId: selectedTrack.trackId,
      trackType: selectedTrack.trackType,
      managedWellUid: selectedTrack.managedWellUid ?? null,
      assignmentId: frozenCurve?.assignmentId ?? null,
      openedTrackTitle: selectedTrack.title,
    };
    setEditTrackSessionTarget(frozenTarget);

    if (selectedTrack.trackType === "curve") {
      setEditTrackCurveAssignmentId(frozenCurve!.assignmentId);
      setEditTrackOriginalCurve({ ...frozenCurve! });
      setEditTrackOriginalCurves(selectedTrack.curves.map((curve) => ({ ...curve })));
      setEditTrackOriginalCoreAppearance(null);
      setEditTrackOriginalCompletionAppearance(null);
    } else if (selectedTrack.trackType === "core") {
      setEditTrackCurveAssignmentId(null);
      setEditTrackOriginalCurve(null);
      setEditTrackOriginalCurves([]);
      setEditTrackOriginalCoreAppearance(resolveCoreTrackAppearance(selectedTrack));
      setEditTrackOriginalCompletionAppearance(null);
    } else if (selectedTrack.trackType === "completion") {
      setEditTrackCurveAssignmentId(null);
      setEditTrackOriginalCurve(null);
      setEditTrackOriginalCurves([]);
      setEditTrackOriginalCoreAppearance(null);
      setEditTrackOriginalCompletionAppearance(resolveCompletionTrackAppearance(selectedTrack));
    } else {
      setEditTrackCurveAssignmentId(null);
      setEditTrackOriginalCurve(null);
      setEditTrackOriginalCurves([]);
      setEditTrackOriginalCoreAppearance(null);
      setEditTrackOriginalCompletionAppearance(null);
    }

    const currentOverlayStyles = Object.fromEntries(
      tracks.map((track) => [
        track.trackId,
        {
          ...DEFAULT_FORMATION_TOP_OVERLAY_STYLE,
          ...(liveOverlayStylesRef.current[track.trackId] ?? {}),
        },
      ]),
    );
    liveOverlayStylesRef.current = currentOverlayStyles;
    setEditTrackOriginalOverlayStyles(currentOverlayStyles);
    setEditTrackOriginalDepthRangeLocator({
      ...DEFAULT_DEPTH_RANGE_LOCATOR_CONFIG,
      ...(selectedTrack.depthRangeLocator ?? {}),
    });
    setEditTrackOriginalMacroCoreImage({
      ...DEFAULT_MACRO_CORE_IMAGE_CONFIG,
      ...(selectedTrack.macroCoreImage ?? {}),
    });
    setEditTrackOriginalTextOverlays((selectedTrack.textOverlays ?? []).map((item) => ({ ...item })));
    setEditTrackTextOverlayCommitError(null);
    setEditTrackMacroCoreImageCommitError(null);
    setEditTrackMacroCoreImageDirty(false);
    setEditTrackDirty(false);
    setEditTrackOverlayDirty(false);
    setCurveEditModalSize(null);
    setCurveEditModalResize(null);
    setCurveEditModalOffset({ x: 0, y: 0 });
    setCurveEditModalDrag(null);
    setCurveEditModalTab(initialTab);
    setCurveEditModalOpen(true);
  };

  const closeEditTrackSession = () => {
    if (editTrackTarget?.trackType === "interval") {
      window.dispatchEvent(
        new CustomEvent("wlv:cancel-interval-track-editor"),
      );
    }
    window.dispatchEvent(
      new CustomEvent(CURVE_FILL_MD_PICK_CANCEL_EVENT),
    );
    window.dispatchEvent(
      new CustomEvent(CURVE_FILL_TRANSIENT_PREVIEW_CLEAR_EVENT),
    );
    setCurveEditModalOpen(false);
    curveFillDraftApplyRef.current = null;
    overlayInfillDraftApplyRef.current = null;
    setEditTrackOriginalCurve(null);
    setEditTrackOriginalCurves([]);
    setEditTrackCurveAssignmentId(null);
    setEditTrackSessionTarget(null);
    setEditTrackOriginalCoreAppearance(null);
    setEditTrackOriginalCompletionAppearance(null);
    setEditTrackCompletionCommitError(null);
    setEditTrackOriginalDepthRangeLocator(null);
    setEditTrackOriginalMacroCoreImage(null);
    setEditTrackOriginalTextOverlays([]);
    setEditTrackTextOverlayCommitError(null);
    setEditTrackMacroCoreImageCommitError(null);
    setEditTrackMacroCoreImageDirty(false);
    setEditTrackOriginalOverlayStyles({});
    setEditTrackDirty(false);
    setEditTrackOverlayDirty(false);
    touchedOverlayTrackIdsRef.current = new Set();
  };

  const cancelEditTrackSession = () => {
    // Cancel is a transaction rollback. Never use the *current* properties
    // selection to choose the rollback target: Curve Fill picking can change
    // selectedCurve/selectedTrack while the modal is open. Using the current
    // assignment id here can overwrite a sibling curve (e.g. GR -> RDEP),
    // producing RDEP/RDEP after Cancel.
    const rollbackTrackId = editTrackSessionTarget?.trackId ?? null;

    if (rollbackTrackId && editTrackOriginalCurves.length > 0) {
      editTrackOriginalCurves.forEach((curve) => {
        updateCurveAssignment(rollbackTrackId, curve.assignmentId, curve);
      });
    } else if (rollbackTrackId && editTrackOriginalCurve) {
      updateCurveAssignment(
        rollbackTrackId,
        editTrackOriginalCurve.assignmentId,
        editTrackOriginalCurve,
      );
    }

    if (rollbackTrackId && editTrackOriginalCoreAppearance) {
      updateTrack(rollbackTrackId, {
        coreAppearance: editTrackOriginalCoreAppearance,
      } as Partial<WellLogTrack>);
      window.dispatchEvent(new CustomEvent('wlv:core-appearance-commit', {
        detail: {
          trackId: rollbackTrackId,
          appearance: editTrackOriginalCoreAppearance,
          immediate: true,
        },
      }));
    }

    if (rollbackTrackId && editTrackOriginalCompletionAppearance) {
      updateTrack(rollbackTrackId, {
        completionAppearance: { ...editTrackOriginalCompletionAppearance },
      } as Partial<WellLogTrack>);
    }

    if (rollbackTrackId && editTrackOriginalDepthRangeLocator) {
      updateTrack(rollbackTrackId, {
        depthRangeLocator: { ...editTrackOriginalDepthRangeLocator },
      } as Partial<WellLogTrack>);
    }
    if (rollbackTrackId && editTrackOriginalMacroCoreImage) {
      updateTrack(rollbackTrackId, {
        macroCoreImage: { ...editTrackOriginalMacroCoreImage },
      } as Partial<WellLogTrack>);
    }
    if (rollbackTrackId) {
      updateTrack(rollbackTrackId, {
        textOverlays: editTrackOriginalTextOverlays.map((item) => ({ ...item })),
      } as Partial<WellLogTrack>);
    }

    // A Curve/Core modal must not replay unrelated track overlay state merely
    // because it is closing. Restore the multi-track overlay snapshot only if
    // this edit session actually changed overlay state (including Extend All).
    if (editTrackOverlayDirty) {
      Object.entries(editTrackOriginalOverlayStyles).forEach(
        ([trackId, overlayStyle]) => {
          updateFormationTopOverlayStyle(trackId, overlayStyle);
        },
      );
    }

    closeEditTrackSession();
  };

  useEffect(() => {
    if (!curveEditModalOpen || !editTrackSessionTarget || editTrackTarget) return;

    // The frozen entity was removed/replaced while the configuration window
    // was open. Closing is safer than redirecting the transaction to live
    // selection. No fallback target is permitted.
    closeEditTrackSession();
  }, [curveEditModalOpen, editTrackSessionTarget, editTrackTarget]);

  /*
   * The external WDV Configuration window follows canvas TRACK selection.
   * Track selection owns the editor target; curve selection is a child choice
   * within a curve track. Switching tracks rolls back unapplied preview state
   * on the previous track and starts a fresh transaction for the new track.
   */
  useEffect(() => {
    if (
      !curveEditModalOpen
      || !editTrackSessionTarget
      || !selectedTrack
      || !normalizedSelection.trackId
    ) return;

    // Plain MB1 selection is a toggle. When the active track is toggled off,
    // normalizedSelection.trackId becomes empty and selectedTrack falls back to
    // tracks[0] for the static Properties panel. That fallback is NOT a real
    // WDV Configuration retarget request and must never rollback live overlay
    // preview state on the currently edited track.
    if (selectedTrack.trackId === editTrackSessionTarget.trackId) {
      if (
        selectedTrack.trackType === "curve"
        && normalizedSelection.kind === "curve"
        && selectedTrack.curves.some(
          (curve) => curve.assignmentId === normalizedSelection.assignmentId,
        )
      ) {
        setEditTrackCurveAssignmentId(normalizedSelection.assignmentId);
      }
      return;
    }

    // Restore any unapplied live preview on the previous track before moving
    // configuration authority to the newly selected canvas track.
    const previousTrackId = editTrackSessionTarget.trackId;
    if (editTrackOriginalCurves.length > 0) {
      editTrackOriginalCurves.forEach((curve) => {
        updateCurveAssignment(previousTrackId, curve.assignmentId, curve);
      });
    }
    if (editTrackOriginalCoreAppearance) {
      updateTrack(previousTrackId, {
        coreAppearance: editTrackOriginalCoreAppearance,
      } as Partial<WellLogTrack>);
    }
    if (editTrackOriginalCompletionAppearance) {
      updateTrack(previousTrackId, {
        completionAppearance: { ...editTrackOriginalCompletionAppearance },
      } as Partial<WellLogTrack>);
    }
    if (editTrackOriginalDepthRangeLocator) {
      updateTrack(previousTrackId, {
        depthRangeLocator: { ...editTrackOriginalDepthRangeLocator },
      } as Partial<WellLogTrack>);
    }
    if (editTrackOriginalMacroCoreImage) {
      updateTrack(previousTrackId, {
        macroCoreImage: { ...editTrackOriginalMacroCoreImage },
      } as Partial<WellLogTrack>);
    }
    updateTrack(previousTrackId, {
      textOverlays: editTrackOriginalTextOverlays.map((item) => ({ ...item })),
    } as Partial<WellLogTrack>);
    if (editTrackOverlayDirty) {
      Object.entries(editTrackOriginalOverlayStyles).forEach(([trackId, overlayStyle]) => {
        updateFormationTopOverlayStyle(trackId, overlayStyle);
      });
    }

    const nextCurve = selectedTrack.trackType === "curve"
      ? (selectedCurve ?? selectedTrack.curves[0] ?? null)
      : null;
    if (selectedTrack.trackType === "curve" && !nextCurve) return;

    setEditTrackSessionTarget({
      trackId: selectedTrack.trackId,
      trackType: selectedTrack.trackType,
      managedWellUid: selectedTrack.managedWellUid ?? null,
      assignmentId: nextCurve?.assignmentId ?? null,
      openedTrackTitle: selectedTrack.title,
    });
    setEditTrackCurveAssignmentId(nextCurve?.assignmentId ?? null);
    setEditTrackOriginalCurve(nextCurve ? { ...nextCurve } : null);
    setEditTrackOriginalCurves(
      selectedTrack.trackType === "curve"
        ? selectedTrack.curves.map((curve) => ({ ...curve }))
        : [],
    );
    setEditTrackOriginalCoreAppearance(
      selectedTrack.trackType === "core" ? resolveCoreTrackAppearance(selectedTrack) : null,
    );
    setEditTrackOriginalCompletionAppearance(
      selectedTrack.trackType === "completion" ? resolveCompletionTrackAppearance(selectedTrack) : null,
    );
    setEditTrackOriginalDepthRangeLocator({
      ...DEFAULT_DEPTH_RANGE_LOCATOR_CONFIG,
      ...(selectedTrack.depthRangeLocator ?? {}),
    });
    setEditTrackOriginalMacroCoreImage({
      ...DEFAULT_MACRO_CORE_IMAGE_CONFIG,
      ...(selectedTrack.macroCoreImage ?? {}),
    });
    setEditTrackOriginalTextOverlays(
      (selectedTrack.textOverlays ?? []).map((item) => ({ ...item })),
    );
    const currentOverlayStyles = Object.fromEntries(
      tracks.map((track) => [
        track.trackId,
        {
          ...DEFAULT_FORMATION_TOP_OVERLAY_STYLE,
          ...(liveOverlayStylesRef.current[track.trackId] ?? {}),
        },
      ]),
    );
    setEditTrackOriginalOverlayStyles(currentOverlayStyles);
    liveOverlayStylesRef.current = currentOverlayStyles;
    touchedOverlayTrackIdsRef.current = new Set();
    setEditTrackDirty(false);
    setEditTrackOverlayDirty(false);
    setEditTrackCompletionCommitError(null);
    setEditTrackTextOverlayCommitError(null);
    setEditTrackMacroCoreImageCommitError(null);
    setEditTrackMacroCoreImageDirty(false);
    setCurveEditModalTab(
      selectedTrack.trackType === "curve"
        ? "curve"
        : selectedTrack.trackType === "core"
          ? "appearance"
          : selectedTrack.trackType === "completion"
            ? "completion"
            : selectedTrack.trackType === "interval"
              ? "interval"
              : "overlays",
    );
  }, [
    curveEditModalOpen,
    editTrackSessionTarget?.trackId,
    normalizedSelection.kind,
    normalizedSelectionAssignmentId,
    selectedTrack?.trackId,
    selectedCurve?.assignmentId,
  ]);

  const updateLiveCurveAssignment = (
    trackId: string,
    assignmentId: string,
    patch: Partial<CurveAssignment>,
  ) => {
    updateCurveAssignment(trackId, assignmentId, patch);
    setEditTrackDirty(true);
  };

  const updateLiveCoreAppearance = (
    trackId: string,
    patch: Partial<CoreTrackAppearance>,
  ) => {
    if (!editTrackTarget || editTrackTarget.trackId !== trackId) return;
    const nextAppearance = {
      ...resolveCoreTrackAppearance(editTrackTarget),
      ...patch,
    };
    updateTrack(trackId, {
      coreAppearance: nextAppearance,
    } as Partial<WellLogTrack>);
    window.dispatchEvent(new CustomEvent('wlv:core-appearance-commit', {
      detail: { trackId, appearance: nextAppearance, immediate: false },
    }));
    setEditTrackDirty(true);
  };

  const updateLiveCompletionAppearance = (
    trackId: string,
    patch: Partial<CompletionTrackAppearance>,
  ) => {
    if (!editTrackTarget || editTrackTarget.trackId !== trackId || editTrackTarget.trackType !== "completion") return;
    const nextAppearance = {
      ...resolveCompletionTrackAppearance(editTrackTarget),
      ...patch,
    };
    updateTrack(trackId, {
      completionAppearance: nextAppearance,
    } as Partial<WellLogTrack>);
    setEditTrackDirty(true);
  };

  const updateLiveDepthRangeLocator = (
    trackId: string,
    patch: Partial<DepthRangeLocatorConfig>,
  ) => {
    if (!editTrackTarget || editTrackTarget.trackId !== trackId) return;
    const currentConfig = {
      ...DEFAULT_DEPTH_RANGE_LOCATOR_CONFIG,
      ...(editTrackTarget.depthRangeLocator ?? {}),
    };
    const nextConfig = { ...currentConfig, ...patch };
    if (nextConfig.enabled && !nextConfig.sourceTrackId) {
      const firstCompatible = tracks.find((candidate) => (
        candidate.trackId !== trackId
        && Boolean(candidate.managedWellUid)
        && candidate.managedWellUid === editTrackTarget.managedWellUid
      ));
      if (firstCompatible) nextConfig.sourceTrackId = firstCompatible.trackId;
      else nextConfig.enabled = false;
    }
    updateTrack(trackId, { depthRangeLocator: nextConfig } as Partial<WellLogTrack>);
    setEditTrackDirty(true);
  };

  const updateLiveMacroCoreImage = (
    trackId: string,
    patch: Partial<MacroCoreImageConfig>,
  ) => {
    if (!editTrackTarget || editTrackTarget.trackId !== trackId) return;
    const currentConfig = {
      ...DEFAULT_MACRO_CORE_IMAGE_CONFIG,
      ...(editTrackTarget.macroCoreImage ?? {}),
    };
    const nextConfig = { ...currentConfig, ...patch };
    updateTrack(trackId, { macroCoreImage: nextConfig } as Partial<WellLogTrack>);
    setEditTrackMacroCoreImageDirty(true);
    setEditTrackDirty(true);
  };

  const updateLiveTextOverlays = (
    trackId: string,
    next: TextOverlayConfig[],
  ) => {
    if (!editTrackTarget || editTrackTarget.trackId !== trackId) return;
    updateTrack(trackId, {
      textOverlays: next.map((item) => ({ ...item })),
    } as Partial<WellLogTrack>);
    setEditTrackDirty(true);
  };

  const updateLiveFormationTopOverlayStyle = (
    trackId: string,
    patch: Partial<FormationTopOverlayStyle>,
  ) => {
    touchedOverlayTrackIdsRef.current.add(trackId);
    const nextStyle = {
      ...DEFAULT_FORMATION_TOP_OVERLAY_STYLE,
      ...(liveOverlayStylesRef.current[trackId] ?? {}),
      ...patch,
    };
    liveOverlayStylesRef.current = {
      ...liveOverlayStylesRef.current,
      [trackId]: nextStyle,
    };
    updateFormationTopOverlayStyle(trackId, patch);
    setEditTrackDirty(true);
    setEditTrackOverlayDirty(true);
  };

  const applyEditTrackSession = async () => {
    if (
      curveEditModalTab === "interval"
      && editTrackTarget?.trackType === "interval"
    ) {
      try {
        await new Promise<void>((resolve, reject) => {
          window.dispatchEvent(
            new CustomEvent("wlv:apply-interval-track-editor", {
              detail: { resolve, reject },
            }),
          );
        });
        setEditTrackDirty(false);
      } catch (error) {
        console.error("Unable to apply Interval configuration", error);
        setEditTrackDirty(true);
      }
      return;
    }

    if (
      curveEditModalTab === "curve"
      && curveEditSectionTab === "infill"
      && curveFillDraftApplyRef.current
    ) {
      await curveFillDraftApplyRef.current();
    }

    if (curveEditModalTab === "overlays") {
      if (overlayInfillDraftApplyRef.current) {
        await overlayInfillDraftApplyRef.current();
      }
      const committedOverlayStyles = Object.fromEntries(
        tracks.map((track) => [
          track.trackId,
          {
            ...DEFAULT_FORMATION_TOP_OVERLAY_STYLE,
            ...(liveOverlayStylesRef.current[track.trackId] ?? {}),
            fillZones: [
              ...((liveOverlayStylesRef.current[track.trackId]?.fillZones) ?? []),
            ],
          },
        ]),
      );

      // Apply is the explicit persistence boundary. Commit the complete live
      // overlay snapshot synchronously rather than replaying partial state
      // updates and waiting for a React effect to write localStorage.
      commitFormationTopOverlayStyles(
        committedOverlayStyles,
        Array.from(touchedOverlayTrackIdsRef.current),
      );
      liveOverlayStylesRef.current = committedOverlayStyles;
      setEditTrackOriginalOverlayStyles(committedOverlayStyles);
      setEditTrackOverlayDirty(false);
      touchedOverlayTrackIdsRef.current = new Set();
    }

    if (editTrackTarget?.trackType === "curve") {
      setEditTrackOriginalCurves(editTrackTarget.curves.map((curve) => ({ ...curve })));
      if (editTrackTargetCurve) {
        setEditTrackOriginalCurve({ ...editTrackTargetCurve });
      }
    }
    if (editTrackTarget?.trackType === "core") {
      const committedAppearance = resolveCoreTrackAppearance(editTrackTarget);
      window.dispatchEvent(new CustomEvent('wlv:core-appearance-commit', {
        detail: {
          trackId: editTrackTarget.trackId,
          appearance: committedAppearance,
          immediate: true,
        },
      }));
      setEditTrackOriginalCoreAppearance(committedAppearance);
    }
    if (editTrackTarget?.trackType === "completion") {
      const committedAppearance = resolveCompletionTrackAppearance(editTrackTarget);
      setEditTrackCompletionCommitError(null);
      try {
        await new Promise<void>((resolve, reject) => {
          window.dispatchEvent(new CustomEvent('wlv:completion-appearance-commit', {
            detail: {
              trackId: editTrackTarget.trackId,
              managedWellUid: editTrackTarget.managedWellUid,
              appearance: committedAppearance,
              resolve,
              reject,
            },
          }));
        });
        setEditTrackOriginalCompletionAppearance(committedAppearance);
      } catch (error) {
        setEditTrackCompletionCommitError(
          error instanceof Error ? error.message : "Unable to save Completion appearance",
        );
        setEditTrackDirty(true);
        return;
      }
    }
    if (editTrackTarget) {
      const committedLocator = {
        ...DEFAULT_DEPTH_RANGE_LOCATOR_CONFIG,
        ...(editTrackTarget.depthRangeLocator ?? {}),
      };
      if (!committedLocator.enabled || committedLocator.sourceTrackId) {
        window.dispatchEvent(new CustomEvent('wlv:depth-range-locator-commit', {
          detail: { trackId: editTrackTarget.trackId, config: committedLocator },
        }));
        setEditTrackOriginalDepthRangeLocator(committedLocator);
      }
      if (editTrackMacroCoreImageDirty) {
        const committedMacroCoreImage = {
          ...DEFAULT_MACRO_CORE_IMAGE_CONFIG,
          ...(editTrackTarget.macroCoreImage ?? {}),
        };
        setEditTrackMacroCoreImageCommitError(null);
        try {
          await new Promise<void>((resolve, reject) => {
            window.dispatchEvent(new CustomEvent('wlv:macro-core-image-commit', {
              detail: {
                trackId: editTrackTarget.trackId,
                managedWellUid: editTrackTarget.managedWellUid,
                config: committedMacroCoreImage,
                resolve,
                reject,
              },
            }));
          });
          setEditTrackOriginalMacroCoreImage(committedMacroCoreImage);
          setEditTrackMacroCoreImageDirty(false);
        } catch (error) {
          setEditTrackMacroCoreImageCommitError(
            error instanceof Error ? error.message : "Unable to save Macro Core Image",
          );
          setEditTrackDirty(true);
          return;
        }
      }

      const committedTextOverlays = (editTrackTarget.textOverlays ?? []).map((item) => ({ ...item }));
      setEditTrackTextOverlayCommitError(null);
      try {
        await new Promise<void>((resolve, reject) => {
          window.dispatchEvent(new CustomEvent('wlv:text-overlays-commit', {
            detail: {
              trackId: editTrackTarget.trackId,
              managedWellUid: editTrackTarget.managedWellUid,
              textOverlays: committedTextOverlays,
              resolve,
              reject,
            },
          }));
        });
        setEditTrackOriginalTextOverlays(committedTextOverlays);
      } catch (error) {
        setEditTrackTextOverlayCommitError(
          error instanceof Error ? error.message : "Unable to save Text Box Overlay",
        );
        setEditTrackDirty(true);
        return;
      }
    }
    setEditTrackDirty(false);
  };

  useEffect(() => {
    if (!curveEditRequest) {
      return;
    }

    if (
      lastHandledCurveEditRequestIdRef.current === curveEditRequest.requestId
    ) {
      return;
    }

    if (
      normalizedSelection.kind !== "curve" ||
      normalizedSelection.trackId !== curveEditRequest.trackId ||
      normalizedSelectionAssignmentId !== curveEditRequest.assignmentId
    ) {
      return;
    }

    lastHandledCurveEditRequestIdRef.current = curveEditRequest.requestId;
    beginEditTrackSession("curve");
  }, [
    curveEditRequest,
    normalizedSelectionAssignmentId,
    normalizedSelection.kind,
    normalizedSelection.trackId,
    selectedCurve,
    selectedTrack,
  ]);

  if (collapsed) {
    return (
      <aside
        className="wlv-right-panel wlv-properties-panel-v2 collapsed"
        aria-label="Properties panel collapsed"
      >
        <button
          type="button"
          className="wlv-curve-inventory-collapse-toggle wlv-right-properties-collapse-toggle"
          onClick={onToggleCollapsed}
          aria-expanded={false}
          aria-label="Expand Properties panel"
          title="Expand Properties panel"
        >
          ‹
        </button>
      </aside>
    );
  }

  return (
    <>
    <aside className="wlv-right-panel wlv-properties-panel-v2">
      <div className="wlv-panel-heading wlv-properties-panel-heading-with-toggle">
        <h2>Properties</h2>
        <button
          type="button"
          className="wlv-curve-inventory-collapse-toggle wlv-right-properties-collapse-toggle"
          onClick={onToggleCollapsed}
          aria-expanded={!collapsed}
          aria-label="Collapse Properties panel"
          title="Collapse Properties panel"
        >
          ›
        </button>
      </div>

      <div className="wlv-properties-selected-entity">
        <strong>
          {selectedCurveTrackIdentity || contract.selectedEntity.title}
        </strong>
        <span>
          {selectedCurveTrackHeaderSubtitle || contract.selectedEntity.subtitle}
        </span>
      </div>

      {standardNonDepthTrack ? (
        <div
          className="wlv-properties-tab-body"
          role="region"
          aria-label={`${standardTrackTypeLabel} track controls`}
        >
          <button
            type="button"
            className="wlv-edit-curve-launcher wlv-edit-curve-launcher-design-top wlv-edit-track-launcher"
            onClick={() =>
              beginEditTrackSession(
                standardNonDepthTrack.trackType === "core"
                  ? "appearance"
                  : standardNonDepthTrack.trackType === "completion"
                    ? "completion"
                    : standardNonDepthTrack.trackType === "interval"
                      ? "interval"
                      : "overlays",
              )
            }
          >
            Open WDV Configuration
          </button>

          <PropertiesContractTable
            sections={standardDesignSections}
            collapsible
            collapsed={standardDesignCollapsed}
            onToggle={() => setStandardDesignCollapsed((value) => !value)}
          />

          {standardTrackMetadataSection ? (
            <PropertiesContractTable
              sections={[standardTrackMetadataSection]}
              collapsible
              collapsed={standardTrackMetadataCollapsed}
              onToggle={() =>
                setStandardTrackMetadataCollapsed((value) => !value)
              }
            />
          ) : null}

          <ConsolidatedPropertiesInfo
            title={`${standardTrackTypeLabel} / Well Info`}
            sections={standardInfoSections}
            collapsed={standardInfoCollapsed}
            onToggle={() => setStandardInfoCollapsed((value) => !value)}
          />
        </div>
      ) : selectedTrack &&
        selectedCurve &&
        selectedTrack.trackType === "curve" ? (
        <div
          className="wlv-properties-tab-body"
          role="region"
          aria-label="Curve track controls"
        >
          <button
            type="button"
            className="wlv-edit-curve-launcher wlv-edit-curve-launcher-design-top wlv-edit-track-launcher"
            onClick={() => beginEditTrackSession("curve")}
          >
            Open WDV Configuration
          </button>

          <PropertiesContractTable
            sections={contract.tabs.design.sections}
            collapsible
            collapsed={curveDesignCollapsed}
            onToggle={() => setCurveDesignCollapsed((value) => !value)}
          />

          <div
            className={`wlv-properties-contract-table wlv-properties-consolidated-info${curveInfoCollapsed ? " is-collapsed" : ""}`}
          >
            <section
              className={`wlv-properties-contract-section${curveInfoCollapsed ? " is-collapsed" : ""}`}
            >
              <h3>
                <button
                  type="button"
                  className="wlv-properties-collapse-toggle"
                  aria-expanded={!curveInfoCollapsed}
                  onClick={() => setCurveInfoCollapsed((value) => !value)}
                >
                  <span>{curveInfoCollapsed ? "▸" : "▾"}</span>
                  <strong>Curve / Log / Well Info</strong>
                </button>
              </h3>
              {curveInfoCollapsed
                ? null
                : contract.tabs.info.sections.map((section) => (
                    <section
                      key={section.sectionId}
                      className="wlv-properties-contract-section"
                    >
                      <h3>{section.title}</h3>
                      <table>
                        <tbody>
                          {section.rows.map((row) => (
                            <tr key={`${section.sectionId}-${row.label}`}>
                              <th scope="row">{row.label}</th>
                              <td>
                                <span>{row.value}</span>
                                {row.unit ? <em>{row.unit}</em> : null}
                                {row.source ? <small>{row.source}</small> : null}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </section>
                  ))}
            </section>
          </div>
        </div>
      ) : curveSelectionUnresolved ? (
        <div className="wlv-property-section wlv-properties-dark-section">
          <h3>Curve Controls</h3>
          <div className="wlv-property-note">
            The selected curve identity could not be resolved. Track controls
            are not shown because they would edit the wrong entity.
          </div>
        </div>
      ) : selectedTrack ? (
        <div className="wlv-properties-tab-body" role="region">
          <button
            type="button"
            className="wlv-edit-curve-launcher wlv-edit-curve-launcher-design-top wlv-edit-track-launcher"
            onClick={() => beginEditTrackSession(selectedTrack?.trackType === "interval" ? "interval" : "overlays")}
          >
            Open WDV Configuration
          </button>
          <TrackDesignControls
            track={selectedTrack}
            curveCatalogItems={curveCatalogItems}
            updateTrack={updateTrack}
          />
        </div>
      ) : null}

    </aside>

    {curveEditModalOpen &&
    editTrackTarget &&
    (editTrackTarget.trackType !== "curve" || editTrackTargetCurve)
      ? (
        <WdvExternalWindowPortal
          enabled
          windowName="multiviewer-wdv-configuration"
          title="MultiViewer — WDV Configuration"
          storageKey="multiviewer.wdv.configuration.windowBounds.v1"
          defaultWidth={980}
          defaultHeight={700}
          fitToContent
          onExternalClose={cancelEditTrackSession}
          onPopupBlocked={cancelEditTrackSession}
        >
          <div
            className="wlv-curve-edit-modal-backdrop wlv-wdv-external-editor-backdrop"
            role="presentation"
          >
            <section
              ref={curveEditModalRef}
              className="wlv-curve-edit-modal wlv-curve-editor wlv-edit-track-modal wlv-wdv-external-editor-modal"
              role="dialog"
              aria-modal="false"
              aria-label={editTrackTarget.trackType === "curve"
                ? `Edit ${editTrackTargetCurveCatalogItem?.mnemonic ?? editTrackTargetCurve?.observedMnemonic ?? "curve"}`
                : `Edit ${editTrackTarget.title}`}
              style={{
                ...(curveEditModalSize
                  ? {
                      width: `${curveEditModalSize.width}px`,
                      height: `${curveEditModalSize.height}px`,
                    }
                  : {}),
                transform: `translate(${curveEditModalOffset.x}px, ${curveEditModalOffset.y}px)`,
              }}
            >
              <header
                className={`wlv-curve-edit-modal-header${curveEditModalDrag ? " is-dragging" : ""}`}
                onPointerDown={(event) => {
                  if (event.button !== 0) return;

                  const target = event.target;
                  if (
                    target instanceof Element &&
                    target.closest("button, input, select, textarea")
                  ) {
                    return;
                  }

                  event.currentTarget.setPointerCapture(event.pointerId);
                  setCurveEditModalDrag({
                    pointerId: event.pointerId,
                    startX: event.clientX,
                    startY: event.clientY,
                    originX: curveEditModalOffset.x,
                    originY: curveEditModalOffset.y,
                  });
                }}
                onPointerMove={(event) => {
                  if (
                    !curveEditModalDrag ||
                    curveEditModalDrag.pointerId !== event.pointerId
                  ) {
                    return;
                  }

                  setCurveEditModalOffset({
                    x:
                      curveEditModalDrag.originX +
                      (event.clientX - curveEditModalDrag.startX),
                    y:
                      curveEditModalDrag.originY +
                      (event.clientY - curveEditModalDrag.startY),
                  });
                }}
                onPointerUp={(event) => {
                  if (
                    !curveEditModalDrag ||
                    curveEditModalDrag.pointerId !== event.pointerId
                  ) {
                    return;
                  }

                  if (
                    event.currentTarget.hasPointerCapture(event.pointerId)
                  ) {
                    event.currentTarget.releasePointerCapture(event.pointerId);
                  }
                  setCurveEditModalDrag(null);
                }}
                onPointerCancel={() => setCurveEditModalDrag(null)}
              >
                <div className="wlv-curve-edit-modal-title">
                  <span
                    className="wlv-curve-color"
                    style={{
                      background: editTrackTarget.trackType === "curve"
                        ? editTrackTargetCurve?.color
                        : resolveCoreTrackAppearance(editTrackTarget).baseColor,
                    }}
                  />
                  <div>
                    <span>WDV Configuration</span>
                    <h2>
                      {editTrackTarget.trackType === "curve"
                        ? `T${tracks.findIndex((track) => track.trackId === editTrackTarget.trackId) + 1} — ${editTrackTarget.curves.map((curve) => (
                            findCurveForAssignment(curveCatalogItems, curve)?.mnemonic
                            ?? curve.observedMnemonic
                            ?? curve.normalizedMnemonic
                            ?? curve.displayName
                            ?? "Curve"
                          )).join(" / ")}`
                        : `T${tracks.findIndex((track) => track.trackId === editTrackTarget.trackId) + 1} — ${editTrackTarget.trackType === "core" ? "Core" : editTrackTarget.title}`}
                    </h2>
                    <small>
                      {(() => {
                        const wellName = editTrackTarget.managedWellUid
                          ? wellNameByManagedWellUid?.[editTrackTarget.managedWellUid] ?? null
                          : null;
                        const editorDetail = editTrackTarget.trackType === "curve"
                          ? `Editing ${editTrackTargetCurveCatalogItem?.mnemonic ?? editTrackTargetCurve?.observedMnemonic ?? editTrackTargetCurve?.normalizedMnemonic ?? "Curve"}${editTrackTargetCurveCatalogItem?.unit ? ` · ${editTrackTargetCurveCatalogItem.unit}` : ""}`
                          : editTrackTarget.trackType === "core"
                            ? "Core appearance and overlays"
                            : editTrackTarget.trackType === "completion"
                              ? "Completion presentation and overlays"
                              : editTrackTarget.trackType === "interval"
                                ? "Interval configuration and overlays"
                                : "Track overlays";
                        return wellName ? `${wellName} · ${editorDetail}` : editorDetail;
                      })()}
                    </small>
                  </div>
                </div>

                <button
                  type="button"
                  className="wlv-curve-edit-modal-close"
                  aria-label="Close track editor"
                  onPointerDown={(event) => {
                    event.stopPropagation();
                  }}
                  onClick={(event) => {
                    event.stopPropagation();
                    cancelEditTrackSession();
                  }}
                >
                  ×
                </button>
              </header>

              <div
                className="wlv-curve-edit-modal-tabs wlv-edit-track-main-tabs"
                role="tablist"
                aria-label="WDV configuration tabs"
              >
                {editTrackTarget.trackType === "curve" ? (
                  <>
                    <button
                      type="button"
                      role="tab"
                      aria-selected={curveEditModalTab === "curve"}
                      className={curveEditModalTab === "curve" ? "active" : ""}
                      onClick={() => setCurveEditModalTab("curve")}
                    >
                      Curve
                    </button>

                    <button
                      type="button"
                      role="tab"
                      aria-selected={curveEditModalTab === "overlays"}
                      className={curveEditModalTab === "overlays" ? "active" : ""}
                      onClick={() => setCurveEditModalTab("overlays")}
                    >
                      Overlays
                    </button>
                  </>
                ) : editTrackTarget.trackType === "completion" ? (
                  <>
                    <button
                      type="button"
                      role="tab"
                      aria-selected={curveEditModalTab === "completion"}
                      className={curveEditModalTab === "completion" ? "active" : ""}
                      onClick={() => setCurveEditModalTab("completion")}
                    >
                      Completion
                    </button>
                    <button
                      type="button"
                      role="tab"
                      aria-selected={curveEditModalTab === "overlays"}
                      className={curveEditModalTab === "overlays" ? "active" : ""}
                      onClick={() => setCurveEditModalTab("overlays")}
                    >
                      Overlays
                    </button>
                  </>
                ) : editTrackTarget.trackType === "interval" ? (
                  <>
                    <button
                      type="button"
                      role="tab"
                      aria-selected={curveEditModalTab === "interval"}
                      className={curveEditModalTab === "interval" ? "active" : ""}
                      onClick={() => setCurveEditModalTab("interval")}
                    >
                      Interval
                    </button>
                    <button
                      type="button"
                      role="tab"
                      aria-selected={curveEditModalTab === "overlays"}
                      className={curveEditModalTab === "overlays" ? "active" : ""}
                      onClick={() => setCurveEditModalTab("overlays")}
                    >
                      Overlays
                    </button>
                  </>
                ) : (
                  <>
                    {editTrackTarget.trackType === "core" ? (
                      <button
                        type="button"
                        role="tab"
                        aria-selected={curveEditModalTab === "appearance"}
                        className={curveEditModalTab === "appearance" ? "active" : ""}
                        onClick={() => setCurveEditModalTab("appearance")}
                      >
                        Appearance
                      </button>
                    ) : null}

                    <button
                      type="button"
                      role="tab"
                      aria-selected={curveEditModalTab === "overlays"}
                      className={curveEditModalTab === "overlays" ? "active" : ""}
                      onClick={() => setCurveEditModalTab("overlays")}
                    >
                      Overlays
                    </button>
                  </>
                )}
              </div>

              <div
                className="wlv-curve-edit-modal-body wlv-edit-track-modal-body"
                style={{
                  "--wlv-modal-select-short": `${modalControlGeometry.dropdown.short.preferred}px`,
                  "--wlv-modal-select-medium": `${modalControlGeometry.dropdown.medium.preferred}px`,
                  "--wlv-modal-select-long": `${modalControlGeometry.dropdown.long.preferred}px`,
                  "--wlv-modal-number-compact": `${modalControlGeometry.numericInput.compact}px`,
                  "--wlv-modal-number-standard": `${modalControlGeometry.numericInput.standard}px`,
                  "--wlv-modal-number-depth": `${modalControlGeometry.numericInput.depth}px`,
                  "--wlv-modal-slider": `${modalControlGeometry.slider.width}px`,
                  "--wlv-modal-swatch": `${modalControlGeometry.colorSwatch.width}px`,
                  "--wlv-modal-label-control-gap": `${modalControlGeometry.spacing.labelControlGap}px`,
                  "--wlv-modal-control-gap": `${modalControlGeometry.spacing.controlGap}px`,
                  "--wlv-modal-row-gap": `${modalControlGeometry.spacing.rowGap}px`,
                  "--wlv-modal-section-gap": `${modalControlGeometry.spacing.sectionGap}px`,
                } as React.CSSProperties}
              >
                {editTrackTarget.trackType === "curve" && curveEditModalTab === "curve" ? (
                  <div className="wlv-edit-track-curve-panel">
                    {editTrackTarget.curves.length > 1 ? (
                      <div className="wlv-property-row" style={{ padding: "10px 12px 0" }}>
                        <label style={{ width: "var(--wlv-modal-select-medium)" }}>
                          <span>Curve</span>
                          <select
                            value={editTrackCurveAssignmentId ?? ""}
                            onChange={(event) => setEditTrackCurveAssignmentId(event.target.value)}
                          >
                            {editTrackTarget.curves.map((curve) => {
                              const catalogCurve = findCurveForAssignment(curveCatalogItems, curve);
                              return (
                                <option key={curve.assignmentId} value={curve.assignmentId}>
                                  {catalogCurve?.mnemonic ?? curve.observedMnemonic ?? curve.normalizedMnemonic ?? curve.displayName ?? "Curve"}
                                </option>
                              );
                            })}
                          </select>
                        </label>
                      </div>
                    ) : null}
                    <div className="wlv-edit-track-subtabs" role="tablist" aria-label="Curve controls">
                      <button
                        type="button"
                        role="tab"
                        aria-selected={curveEditSectionTab === "controls"}
                        className={curveEditSectionTab === "controls" ? "active" : ""}
                        onClick={() => setCurveEditSectionTab("controls")}
                      >
                        Curve Controls
                      </button>
                      <button
                        type="button"
                        role="tab"
                        aria-selected={curveEditSectionTab === "infill"}
                        className={curveEditSectionTab === "infill" ? "active" : ""}
                        onClick={() => setCurveEditSectionTab("infill")}
                      >
                        Infill
                      </button>
                    </div>
                    {curveEditSectionTab === "controls" ? (
                      <CurveDesignControls
                        track={editTrackTarget}
                        assignment={editTrackTargetCurve!}
                        curveCatalogItems={curveCatalogItems}
                        updateCurveAssignment={updateLiveCurveAssignment}
                        previewCurveLineStyle={previewCurveLineStyle}
                        commitCurveLineStyle={commitCurveLineStyle}
                        backendCurveFillEnabled={Boolean(curveFillV2?.enabled)}
                      />
                    ) : curveFillV2 ? (
                      <CurveFillV2Controls
                        track={editTrackTarget}
                        assignment={editTrackTargetCurve!}
                        curveCatalogItems={curveCatalogItems}
                        contract={curveFillV2}
                        lithologyIntervals={lithologyIntervals}
                        registerDraftApply={(handler) => {
                          curveFillDraftApplyRef.current = handler;
                        }}
                      />
                    ) : (
                      <div className="wlv-property-note">
                        Backend Curve Fill is not available.
                      </div>
                    )}
                  </div>
                ) : curveEditModalTab === "interval" && editTrackTarget.trackType === "interval" ? (
                  <div className="wlv-edit-track-curve-panel wlv-unified-interval-panel">
                    <div className="wlv-edit-track-subtabs" role="tablist" aria-label="Interval controls">
                      {([
                        ["formation", "Formation"],
                        ["depth", "Depth"],
                        ["descriptions", "Descriptions"],
                        ["tie_in", "Tie-In"],
                      ] as const).map(([tab, label]) => (
                        <button
                          key={tab}
                          type="button"
                          role="tab"
                          aria-selected={intervalConfigTab === tab}
                          className={intervalConfigTab === tab ? "active" : ""}
                          onClick={() => setIntervalConfigTab(tab)}
                        >
                          {label}
                        </button>
                      ))}
                    </div>
                    <div
                      ref={intervalConfigMountRef}
                      className="wlv-unified-interval-editor-mount"
                    />
                  </div>
                ) : curveEditModalTab === "appearance" && editTrackTarget.trackType === "core" ? (
                  <CoreAppearanceEditor
                    appearance={resolveCoreTrackAppearance(editTrackTarget)}
                    updateAppearance={(patch) => updateLiveCoreAppearance(editTrackTarget.trackId, patch)}
                  />
                ) : curveEditModalTab === "completion" && editTrackTarget.trackType === "completion" ? (
                  <CompletionAppearanceEditor
                    appearance={resolveCompletionTrackAppearance(editTrackTarget)}
                    updateAppearance={(patch) => updateLiveCompletionAppearance(editTrackTarget.trackId, patch)}
                  />
                ) : (
                  <FormationTopOverlayEditor
                    track={editTrackTarget}
                    tracks={tracks}
                    markers={formationTops}
                    loadedMarkers={loadedFormationTops}
                    curveCatalogItems={curveCatalogItems}
                    lithologyIntervals={lithologyIntervals}
                    style={{
                      ...DEFAULT_FORMATION_TOP_OVERLAY_STYLE,
                      ...(formationTopOverlayStylesByTrackId[editTrackTarget.trackId] ?? {}),
                    }}
                    updateStyle={updateLiveFormationTopOverlayStyle}
                    registerInfillDraftApply={(handler) => { overlayInfillDraftApplyRef.current = handler; }}
                    depthUnit={depthUnit}
                    locatorConfig={{
                      ...DEFAULT_DEPTH_RANGE_LOCATOR_CONFIG,
                      ...(editTrackTarget.depthRangeLocator ?? {}),
                    }}
                    updateLocatorConfig={(patch) => updateLiveDepthRangeLocator(editTrackTarget.trackId, patch)}
                    macroCoreImageConfig={{
                      ...DEFAULT_MACRO_CORE_IMAGE_CONFIG,
                      ...(editTrackTarget.macroCoreImage ?? {}),
                    }}
                    updateMacroCoreImageConfig={(patch) => updateLiveMacroCoreImage(editTrackTarget.trackId, patch)}
                    textOverlays={(editTrackTarget.textOverlays ?? []).map((item) => ({ ...item }))}
                    updateTextOverlays={(next) => updateLiveTextOverlays(editTrackTarget.trackId, next)}
                    defaultTextOverlayMd={loadedFormationTops[0]?.md ?? formationTops[0]?.md ?? 0}
                  />
                )}
              </div>

              <footer className="wlv-edit-track-modal-footer">
                <div className="wlv-edit-track-modal-footer-status">
                  {editTrackCompletionCommitError
                    ? `Completion save failed: ${editTrackCompletionCommitError}`
                    : editTrackMacroCoreImageCommitError
                      ? `Macro Core Image save failed: ${editTrackMacroCoreImageCommitError}`
                    : editTrackTextOverlayCommitError
                      ? `Text Box save failed: ${editTrackTextOverlayCommitError}`
                      : editTrackDirty
                      ? "Previewing changes on the track"
                      : "Changes preview live; Apply Changes saves"}
                </div>
                <div className="wlv-edit-track-modal-footer-actions">
                  <button
                    type="button"
                    className="secondary"
                    onClick={cancelEditTrackSession}
                  >
                    Cancel
                  </button>
                  <button
                    type="button"
                    className="primary"
                    onClick={applyEditTrackSession}
                  >
                    Apply Changes
                  </button>
                </div>
              </footer>

              <div
                className={`wlv-curve-edit-resize-handle${curveEditModalResize ? " is-resizing" : ""}`}
                role="separator"
                aria-label="Resize curve editor"
                title="Drag to resize"
                onPointerDown={(event) => {
                  if (event.button !== 0) {
                    return;
                  }

                  event.preventDefault();
                  event.stopPropagation();

                  const bounds =
                    curveEditModalRef.current?.getBoundingClientRect();
                  if (!bounds) {
                    return;
                  }

                  setCurveEditModalResize({
                    startX: event.clientX,
                    startY: event.clientY,
                    originWidth: bounds.width,
                    originHeight: bounds.height,
                    originOffsetX: curveEditModalOffset.x,
                    originOffsetY: curveEditModalOffset.y,
                  });
                }}
              />
            </section>
          </div>
        </WdvExternalWindowPortal>
      )
      : null}
    </>
  );
}
