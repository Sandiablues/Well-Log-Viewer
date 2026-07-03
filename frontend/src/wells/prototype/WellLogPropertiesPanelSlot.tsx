import { type ReactElement, useEffect, useRef, useState } from "react";
import {
  fullDepthRange,
  realCurveSamplesByCurveId,
  wellHeader,
} from "./realLasTrackLayoutData";
import type {
  CurveAssignment,
  CurveCatalogItem,
  CurveTrack,
  DepthBasis,
  FillSide,
  LineStyle,
  ScaleMode,
  SelectionRef,
  WellLogTrack,
} from "./trackLayoutModel";
import { resolveTrackLattice } from "./trackLayoutModel";
import type {
  PropertiesPanelSection,
  PropertiesPanelTabKey,
} from "./wellLogPropertiesPanelContract";
import { resolvePrototypePropertiesPanelContract } from "./wellLogPropertiesPanelContract";
import {
  findCurveForAssignment,
  normalizePropertiesSelection,
} from "./propertiesSelectionModel";
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
  backendCurveFillEnabled,
}: {
  track: CurveTrack;
  assignment: CurveAssignment;
  curveCatalogItems: CurveCatalogItem[];
  updateCurveAssignment: (
    trackId: string,
    assignmentId: string,
    patch: Partial<CurveAssignment>,
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

  const update = (patch: Partial<CurveAssignment>) => {
    updateCurveAssignment(track.trackId, assignment.assignmentId, patch);
  };

  return (
    <div className="wlv-property-section wlv-properties-dark-section wlv-curve-control-panel">
      <h3>Curve Controls</h3>
      <div className="wlv-selected-curve-title">
        <span
          className="wlv-curve-color"
          style={{ background: assignment.color }}
        />
        <strong>{curve.mnemonic}</strong>
        <span>{curve.description}</span>
      </div>

      <div className="wlv-curve-control-group">
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
        <label className="wlv-checkbox-row">
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

      <div className="wlv-curve-control-group">
        <h4>Line</h4>
        <label className="wlv-checkbox-row">
          <input
            type="checkbox"
            checked={lineVisible}
            onChange={(event) => update({ lineVisible: event.target.checked })}
          />
          Show line
        </label>
        <label>
          Color
          <input
            type="color"
            value={assignment.color}
            onChange={(event) => update({ color: event.target.value })}
          />
        </label>
        <label>
          Width
          <input
            type="number"
            min={0.5}
            max={8}
            step={0.1}
            value={assignment.lineWidth}
            onChange={(event) =>
              update({ lineWidth: Number(event.target.value) })
            }
          />
        </label>
        <label>
          Style
          <select
            value={assignment.lineStyle}
            onChange={(event) =>
              update({ lineStyle: event.target.value as LineStyle })
            }
          >
            <option value="solid">Solid</option>
            <option value="dash">Dashed</option>
            <option value="dot">Dotted</option>
          </select>
        </label>
        <label>
          Opacity
          <input
            type="range"
            min={0}
            max={100}
            step={5}
            value={lineOpacity}
            onChange={(event) =>
              update({ lineOpacity: Number(event.target.value) })
            }
          />
        </label>
      </div>

      <div className="wlv-curve-control-group">
        <h4>Position</h4>
        <label>
          Position
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
        <label>
          Offset
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
        <label className="wlv-checkbox-row">
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

type CurveFillV2PanelContract = {
  enabled: boolean;
  managedWellUid: string | null;
  revision: number;
  rules: CanonicalCurveFillRuleV2[];
  pending: boolean;
  error: string | null;
  onCreateRule: (body: Readonly<Record<string, unknown>>) => Promise<void>;
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
  return "Crossover fill";
}

function CurveFillV2Controls({
  track,
  assignment,
  contract,
}: {
  track: CurveTrack;
  assignment: CurveAssignment;
  contract: CurveFillV2PanelContract;
}) {
  const [capabilities, setCapabilities] =
    useState<CurveFillCapabilitiesV2 | null>(null);
  const [capabilityError, setCapabilityError] = useState<string | null>(null);
  const [ruleType, setRuleType] = useState<CurveFillRuleTypeV2>("to_boundary");
  const [curveB, setCurveB] = useState("");
  const [comparison, setComparison] =
    useState<CurveFillComparisonV2>("greater_than");
  const [boundary, setBoundary] = useState<"left" | "right">("right");
  const [color, setColor] = useState("#d94841");
  const [opacity, setOpacity] = useState(0.45);
  const [appearance, setAppearance] = useState<"solid" | "pattern" | "raster">(
    "solid",
  );
  const [patternUid, setPatternUid] = useState("hatch-45-v1");
  const [patternScale, setPatternScale] = useState(1);
  const [rasterAssetUid, setRasterAssetUid] = useState("");
  const [expandedRuleUids, setExpandedRuleUids] = useState<Set<string>>(
    () => new Set(),
  );

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
        const selectedMode = value.modes.find(
          (item) => item.rule_type === ruleType,
        );
        const first = selectedMode?.curve_b_operands.find(
          (item) => item.eligible,
        );
        setCurveB(first?.assignment_uid ?? "");
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
  const rules = trackRules.filter(
    (rule) => rule.curve_a_assignment_uid === assignment.assignmentId,
  );
  const mode =
    capabilities?.modes.find((item) => item.rule_type === ruleType) ?? null;
  const paintCapabilities = curveFillPaintCapabilitiesV2(capabilities);
  const operands = mode?.curve_b_operands.filter((item) => item.eligible) ?? [];
  const curveAMnemonic = capabilities?.curve_a_mnemonic ?? "—";
  const operandName = (assignmentUid: string | null): string => {
    if (!assignmentUid) return "—";
    return (
      capabilities?.modes
        .flatMap((item) => item.curve_b_operands)
        .find((item) => item.assignment_uid === assignmentUid)?.mnemonic ?? "—"
    );
  };
  const requiresCurveB = ruleType !== "to_boundary";
  const paintReady = appearance !== "raster" || Boolean(rasterAssetUid);
  const canCreate = Boolean(
    mode?.eligible &&
    (!requiresCurveB || curveB) &&
    paintReady &&
    contract.revision >= 0,
  );

  const create = async () => {
    if (!mode || !canCreate) return;
    const body: Record<string, unknown> = {
      track_uid: track.trackId,
      curve_a_assignment_uid: assignment.assignmentId,
      rule_type: ruleType,
      enabled: true,
      deadband: 0,
      minimum_interval: 0,
      style: {
        appearance,
        color,
        opacity,
        pattern_uid: appearance === "pattern" ? patternUid : null,
        pattern_scale: patternScale,
        raster_asset_uid: appearance === "raster" ? rasterAssetUid : null,
      },
    };
    if (ruleType === "to_boundary") body.boundary = boundary;
    if (ruleType === "between_curves") body.curve_b_assignment_uid = curveB;
    if (ruleType === "conditional") {
      body.curve_b_assignment_uid = curveB;
      body.comparison = comparison;
    }
    if (ruleType === "crossover") {
      body.curve_b_assignment_uid = curveB;
      body.overlay_policy_uid = mode.overlay_policy_uid;
      body.overlay_policy_revision = mode.overlay_policy_revision;
    }
    await contract.onCreateRule(body);
  };

  const toggleRuleExpanded = (ruleUid: string) => {
    setExpandedRuleUids((current) => {
      const next = new Set(current);
      if (next.has(ruleUid)) next.delete(ruleUid);
      else next.add(ruleUid);
      return next;
    });
  };

  const ruleExpression = (rule: CanonicalCurveFillRuleV2): string => {
    if (rule.rule_type === "to_boundary") {
      return `${curveAMnemonic} → ${rule.boundary === "left" ? "left boundary" : "right boundary"}`;
    }
    const curveBName = operandName(rule.curve_b_assignment_uid);
    if (rule.rule_type === "conditional") {
      return `${curveAMnemonic} ${rule.comparison === "less_than" ? "<" : ">"} ${curveBName}`;
    }
    if (rule.rule_type === "crossover")
      return `${curveAMnemonic} crossover ${curveBName}`;
    return `${curveAMnemonic} to ${curveBName}`;
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

      <div className="wlv-curve-fill-new-rule wlv-curve-fill-menu">
        <label>
          Infill option
          <select
            value={ruleType}
            onChange={(event) =>
              setRuleType(event.target.value as CurveFillRuleTypeV2)
            }
          >
            {(capabilities?.modes ?? []).map((item) => (
              <option
                key={item.rule_type}
                value={item.rule_type}
                disabled={!item.eligible}
              >
                {curveFillRuleLabel(item.rule_type)}
              </option>
            ))}
          </select>
        </label>
        {ruleType === "to_boundary" ? (
          <label>
            Boundary
            <select
              value={boundary}
              onChange={(event) =>
                setBoundary(event.target.value as "left" | "right")
              }
            >
              <option value="left">Left of curve</option>
              <option value="right">Right of curve</option>
            </select>
          </label>
        ) : (
          <div className="wlv-curve-fill-expression wlv-curve-fill-expression-compact">
            <span>Curve A</span>
            <strong>{curveAMnemonic}</strong>
            {ruleType === "conditional" ? (
              <select
                aria-label="New conditional operator"
                value={comparison}
                onChange={(event) =>
                  setComparison(event.target.value as CurveFillComparisonV2)
                }
              >
                <option value="greater_than">&gt;</option>
                <option value="less_than">&lt;</option>
              </select>
            ) : ruleType === "crossover" ? (
              <span className="wlv-curve-fill-policy-label">crossover</span>
            ) : (
              <span className="wlv-curve-fill-policy-label">to</span>
            )}
            <label>
              Curve B
              <select
                value={curveB}
                onChange={(event) => setCurveB(event.target.value)}
              >
                <option value="">Select curve</option>
                {operands.map((item) => (
                  <option key={item.assignment_uid} value={item.assignment_uid}>
                    {item.mnemonic}
                  </option>
                ))}
              </select>
            </label>
          </div>
        )}
        <div className="wlv-curve-fill-paint-editor">
          <label>
            Fill appearance
            <select
              value={appearance}
              onChange={(event) =>
                setAppearance(
                  event.target.value as "solid" | "pattern" | "raster",
                )
              }
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
          </label>
          {appearance === "pattern" ? (
            <>
              <label>
                Pattern
                <select
                  value={patternUid}
                  onChange={(event) => setPatternUid(event.target.value)}
                >
                  {paintCapabilities.patterns.map((item) => (
                    <option key={item.pattern_uid} value={item.pattern_uid}>
                      {item.label}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Pattern scale
                <input
                  type="range"
                  min={0.25}
                  max={4}
                  step={0.25}
                  value={patternScale}
                  onChange={(event) =>
                    setPatternScale(Number(event.target.value))
                  }
                />
              </label>
            </>
          ) : null}
          {appearance === "raster" ? (
            <label>
              Raster
              <select
                value={rasterAssetUid}
                onChange={(event) => setRasterAssetUid(event.target.value)}
              >
                <option value="">Select raster</option>
                {paintCapabilities.rasters.map((item) => (
                  <option
                    key={item.raster_asset_uid}
                    value={item.raster_asset_uid}
                  >
                    {item.label}
                  </option>
                ))}
              </select>
            </label>
          ) : null}
          {appearance === "raster" && !paintCapabilities.rasters.length ? (
            <div className="wlv-property-note">
              No backend-registered depth-calibrated raster is available for
              this well.
            </div>
          ) : null}
        </div>
        <div className="wlv-curve-fill-style-row">
          <label>
            Color
            <input
              type="color"
              value={color}
              onChange={(event) => setColor(event.target.value)}
            />
          </label>
          <label>
            Opacity
            <input
              type="range"
              min={0.1}
              max={1}
              step={0.05}
              value={opacity}
              onChange={(event) => setOpacity(Number(event.target.value))}
            />
          </label>
        </div>
        {mode && !mode.eligible ? (
          <div className="wlv-property-note">{mode.disable_reason}</div>
        ) : null}
        <button
          type="button"
          disabled={!canCreate || contract.pending}
          onClick={() => void create()}
        >
          {contract.pending ? "Applying…" : "+ Add Infill Rule"}
        </button>
      </div>

      <div className="wlv-curve-fill-layer-heading">
        <strong>Infill layers</strong>
        <span>{rules.length}</span>
      </div>
      {rules.length === 0 ? (
        <div className="wlv-curve-fill-empty">
          No infill layers for this curve.
        </div>
      ) : null}
      {rules.map((rule, index) => {
        const expanded = expandedRuleUids.has(rule.rule_uid);
        return (
          <div
            key={rule.rule_uid}
            className={`wlv-curve-fill-rule-card wlv-curve-fill-layer-card${expanded ? " is-expanded" : ""}`}
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
                  {rulePaintSummary(rule)}
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
                  <strong>{curveAMnemonic}</strong>
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
                        value={rule.style.pattern_uid ?? "hatch-45-v1"}
                        disabled={contract.pending}
                        onChange={(event) =>
                          void contract.onUpdateRule(rule.rule_uid, {
                            style: {
                              ...rule.style,
                              pattern_uid: event.target.value,
                            },
                          })
                        }
                      >
                        {paintCapabilities.patterns.map((item) => (
                          <option
                            key={item.pattern_uid}
                            value={item.pattern_uid}
                          >
                            {item.label}
                          </option>
                        ))}
                      </select>
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

export function WellLogPropertiesPanelSlot({
  tracks,
  selection,
  curveCatalogItems,
  updateTrack,
  updateCurveAssignment,
  curveFillV2,
  legacyPanel: _legacyPanel,
}: {
  tracks: WellLogTrack[];
  selection: SelectionRef;
  curveCatalogItems: CurveCatalogItem[];
  updateTrack: (trackId: string, patch: Partial<WellLogTrack>) => void;
  updateCurveAssignment: (
    trackId: string,
    assignmentId: string,
    patch: Partial<CurveAssignment>,
  ) => void;
  curveFillV2?: CurveFillV2PanelContract;
  legacyPanel?: ReactElement;
}) {
  const [activeTab, setActiveTab] = useState<PropertiesPanelTabKey>("info");
  const [designParametersCollapsed, setDesignParametersCollapsed] =
    useState(false);
  const [metadataCollapsedSectionIds, setMetadataCollapsedSectionIds] =
    useState<Set<string>>(() => new Set());
  const metadataCollapseInitializedRef = useRef(false);

  const toggleMetadataSection = (sectionId: string) => {
    setMetadataCollapsedSectionIds((current) => {
      const next = new Set(current);
      if (next.has(sectionId)) {
        next.delete(sectionId);
      } else {
        next.add(sectionId);
      }
      return next;
    });
  };

  const normalizedSelection = normalizePropertiesSelection(
    tracks,
    selection,
    curveCatalogItems,
  );
  const selectedTrack =
    tracks.find((track) => track.trackId === normalizedSelection.trackId) ??
    tracks[0];

  const contract = resolvePrototypePropertiesPanelContract({
    tracks,
    selection: normalizedSelection,
    curveCatalog: curveCatalogItems,
    wellHeader,
    curveSamplesByCurveId: realCurveSamplesByCurveId,
    fullDepthRange,
  });

  useEffect(() => {
    if (metadataCollapseInitializedRef.current) {
      return;
    }

    metadataCollapseInitializedRef.current = true;
    setMetadataCollapsedSectionIds(
      new Set(contract.tabs.info.sections.map((section) => section.sectionId)),
    );
  }, [contract.tabs.info.sections]);

  const selectedCurve = resolvePropertiesEditorCurve(
    selectedTrack,
    contract.selectedCurveAssignment,
  );
  const curveSelectionUnresolved =
    normalizedSelection.kind === "curve" &&
    selectedTrack?.trackType === "curve" &&
    selectedCurve === null;

  return (
    <aside className="wlv-right-panel wlv-properties-panel-v2">
      <div className="wlv-panel-heading">
        <h2>Properties</h2>
        <span>{contract.selectedEntity.type}</span>
      </div>

      <div className="wlv-properties-selected-entity">
        <strong>{contract.selectedEntity.title}</strong>
        <span>{contract.selectedEntity.subtitle}</span>
      </div>

      <div
        className="wlv-properties-tabs"
        role="tablist"
        aria-label="Properties tabs"
      >
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === "design"}
          className={activeTab === "design" ? "active" : ""}
          onClick={() => setActiveTab("design")}
        >
          {contract.tabs.design.label}
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === "info"}
          className={activeTab === "info" ? "active" : ""}
          onClick={() => setActiveTab("info")}
        >
          {contract.tabs.info.label}
        </button>
      </div>

      {activeTab === "design" ? (
        <div
          className="wlv-properties-tab-body"
          role="tabpanel"
          aria-label={contract.tabs.design.label}
        >
          <PropertiesContractTable
            sections={contract.tabs.design.sections}
            collapsible
            collapsed={designParametersCollapsed}
            onToggle={() => setDesignParametersCollapsed((value) => !value)}
          />
          {selectedTrack &&
          selectedCurve &&
          selectedTrack.trackType === "curve" ? (
            <>
              <CurveDesignControls
                track={selectedTrack}
                assignment={selectedCurve}
                curveCatalogItems={curveCatalogItems}
                updateCurveAssignment={updateCurveAssignment}
                backendCurveFillEnabled={Boolean(curveFillV2?.enabled)}
              />
              {curveFillV2 ? (
                <CurveFillV2Controls
                  track={selectedTrack}
                  assignment={selectedCurve}
                  contract={curveFillV2}
                />
              ) : null}
            </>
          ) : curveSelectionUnresolved ? (
            <div className="wlv-property-section wlv-properties-dark-section">
              <h3>Curve Controls</h3>
              <div className="wlv-property-note">
                The selected curve identity could not be resolved. Track
                controls are not shown because they would edit the wrong entity.
              </div>
            </div>
          ) : selectedTrack ? (
            <TrackDesignControls
              track={selectedTrack}
              curveCatalogItems={curveCatalogItems}
              updateTrack={updateTrack}
            />
          ) : null}
        </div>
      ) : (
        <div
          className="wlv-properties-tab-body"
          role="tabpanel"
          aria-label={contract.tabs.info.label}
        >
          <div className="wlv-properties-contract-table">
            {contract.tabs.info.sections.map((section) => {
              const sectionCollapsed = metadataCollapsedSectionIds.has(
                section.sectionId,
              );
              return (
                <section
                  key={section.sectionId}
                  className={`wlv-properties-contract-section${sectionCollapsed ? " is-collapsed" : ""}`}
                >
                  <h3>
                    <button
                      type="button"
                      className="wlv-properties-collapse-toggle"
                      aria-expanded={!sectionCollapsed}
                      onClick={() => toggleMetadataSection(section.sectionId)}
                    >
                      <span>{sectionCollapsed ? "▸" : "▾"}</span>
                      <strong>{section.title}</strong>
                    </button>
                  </h3>
                  {sectionCollapsed ? null : (
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
        </div>
      )}
    </aside>
  );
}
