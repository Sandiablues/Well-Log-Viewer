import { type ReactNode } from "react";

export type SharedInfillOption = { value: string; label: string; disabled?: boolean };
export type SharedInfillCurveOption = { value: string; label: string };
export type SharedInfillBoundaryOption = { value: string; label: string; disabled?: boolean };
export type SharedInfillPatternOption = { value: string; label: string; disabled?: boolean };
export type SharedInfillRasterOption = { value: string; label: string };

export type SharedInfillEditorProps = {
  disabled?: boolean;
  option: string;
  optionOptions: SharedInfillOption[];
  onOptionChange: (value: string) => void;
  showBoundary?: boolean;
  boundary?: "left" | "right";
  onBoundaryChange?: (value: "left" | "right") => void;
  showCurvePair?: boolean;
  showCurveB?: boolean;
  curveALabel?: string;
  curveAValue?: string;
  curveAOptions?: SharedInfillCurveOption[];
  curveAReadOnly?: boolean;
  onCurveAChange?: (value: string) => void;
  operator?: string;
  operatorOptions?: SharedInfillOption[];
  onOperatorChange?: (value: string) => void;
  curveBValue?: string;
  curveBOptions?: SharedInfillCurveOption[];
  onCurveBChange?: (value: string) => void;
  relationControls?: ReactNode;
  depthExtent: "entire_track" | "specified_interval" | "top_boundaries";
  allowTopBoundaries?: boolean;
  onDepthExtentChange: (value: "entire_track" | "specified_interval" | "top_boundaries") => void;
  fromMd?: string | number;
  toMd?: string | number;
  activeMdPickField?: "from" | "to" | null;
  onFromMdChange?: (value: string) => void;
  onToMdChange?: (value: string) => void;
  onMdPick?: (field: "from" | "to") => void;
  topBoundaryValue?: string;
  baseBoundaryValue?: string;
  topBoundaryOptions?: SharedInfillBoundaryOption[];
  baseBoundaryOptions?: SharedInfillBoundaryOption[];
  onTopBoundaryChange?: (value: string) => void;
  onBaseBoundaryChange?: (value: string) => void;
  appearance: "solid" | "pattern" | "raster";
  onAppearanceChange: (value: "solid" | "pattern" | "raster") => void;
  patternValue?: string;
  patternOptions?: SharedInfillPatternOption[];
  onPatternChange?: (value: string) => void;
  rasterValue?: string;
  rasterOptions?: SharedInfillRasterOption[];
  rasterTextMode?: boolean;
  onRasterChange?: (value: string) => void;
  rasterFit?: "stretch" | "cover";
  onRasterFitChange?: (value: "stretch" | "cover") => void;
  selectorKind?: "kr" | "lithology-column" | null;
  selectorContent?: ReactNode;
  patternScale: number;
  onPatternScaleChange: (value: number) => void;
  color: string;
  onColorChange: (value: string) => void;
  opacity: number;
  opacityMax?: number;
  onOpacityChange: (value: number) => void;
};

export function SharedInfillEditor(props: SharedInfillEditorProps) {
  const {
    disabled = false,
    option,
    optionOptions,
    onOptionChange,
    showBoundary = false,
    boundary = "right",
    onBoundaryChange,
    showCurvePair = false,
    showCurveB = true,
    curveALabel = "Curve A",
    curveAValue = "",
    curveAOptions = [],
    curveAReadOnly = false,
    onCurveAChange,
    operator = "to",
    operatorOptions = [],
    onOperatorChange,
    curveBValue = "",
    curveBOptions = [],
    onCurveBChange,
    relationControls,
    depthExtent,
    allowTopBoundaries = false,
    onDepthExtentChange,
    fromMd = "",
    toMd = "",
    activeMdPickField = null,
    onFromMdChange,
    onToMdChange,
    onMdPick,
    topBoundaryValue = "",
    baseBoundaryValue = "",
    topBoundaryOptions = [],
    baseBoundaryOptions = [],
    onTopBoundaryChange,
    onBaseBoundaryChange,
    appearance,
    onAppearanceChange,
    patternValue = "",
    patternOptions = [],
    onPatternChange,
    rasterValue = "",
    rasterOptions = [],
    rasterTextMode = false,
    onRasterChange,
    rasterFit = "stretch",
    onRasterFitChange,
    selectorKind = null,
    selectorContent,
    patternScale,
    onPatternScaleChange,
    color,
    onColorChange,
    opacity,
    opacityMax = 1,
    onOpacityChange,
  } = props;

  return (
    <div className="wlv-shared-infill-editor" data-shared-infill-editor="true">
      <div className="wlv-shared-infill-row wlv-shared-infill-row--option">
        <label>
          Infill option
          <select disabled={disabled} value={option} onChange={(e) => onOptionChange(e.target.value)}>
            {optionOptions.map((item) => (
              <option key={item.value} value={item.value} disabled={item.disabled}>{item.label}</option>
            ))}
          </select>
        </label>
        {showBoundary ? (
          <label>
            Boundary
            <select disabled={disabled} value={boundary} onChange={(e) => onBoundaryChange?.(e.target.value as "left" | "right")}>
              <option value="left">Left of curve</option>
              <option value="right">Right of curve</option>
            </select>
          </label>
        ) : null}
        {showCurvePair ? (
          <div className="wlv-shared-infill-curve-pair">
            {curveAReadOnly ? (
              <div className="wlv-shared-infill-curve-box" aria-label={`Curve A ${curveALabel}`}>{curveALabel}</div>
            ) : (
              <label>
                Curve A
                <select disabled={disabled} value={curveAValue} onChange={(e) => onCurveAChange?.(e.target.value)}>
                  <option value="">Select Curve A</option>
                  {curveAOptions.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
                </select>
              </label>
            )}
            {showCurveB ? (
              <>
                {operatorOptions.length ? (
                  <select className="wlv-shared-infill-operator" aria-label="Infill operator" disabled={disabled} value={operator} onChange={(e) => onOperatorChange?.(e.target.value)}>
                    {operatorOptions.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
                  </select>
                ) : (
                  <span className="wlv-shared-infill-operator-label">{operator}</span>
                )}
                <label>
                  Curve B
                  <select disabled={disabled || !curveAValue} value={curveBValue} onChange={(e) => onCurveBChange?.(e.target.value)}>
                    <option value="">Select Curve B</option>
                    {curveBOptions.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
                  </select>
                </label>
              </>
            ) : null}
          </div>
        ) : null}
      </div>

      {relationControls ? (
        <div className="wlv-shared-infill-row wlv-shared-infill-row--relation">{relationControls}</div>
      ) : null}

      <div className="wlv-shared-infill-row wlv-shared-infill-row--depth">
        <label>
          Depth extent
          <select disabled={disabled} value={depthExtent} onChange={(e) => onDepthExtentChange(e.target.value as SharedInfillEditorProps["depthExtent"])}>
            <option value="entire_track">Entire track</option>
            <option value="specified_interval">Specified interval</option>
            {allowTopBoundaries ? <option value="top_boundaries">Top boundaries</option> : null}
          </select>
        </label>
        {depthExtent === "specified_interval" ? (["from", "to"] as const).map((field) => (
          <label key={field}>
            {field === "from" ? "From MD" : "To MD"}
            <span className="wlv-curve-fill-md-pick-field">
              <button type="button" className={`wlv-curve-fill-md-pick-target${activeMdPickField === field ? " is-active" : ""}`} aria-pressed={activeMdPickField === field} aria-label={`Pick ${field === "from" ? "From" : "To"} MD from the curve track`} onClick={() => onMdPick?.(field)}><span aria-hidden="true" /></button>
              <input type="number" step="0.1" disabled={disabled} value={field === "from" ? fromMd : toMd} onChange={(e) => (field === "from" ? onFromMdChange?.(e.target.value) : onToMdChange?.(e.target.value))} />
            </span>
          </label>
        )) : null}
      </div>

      {depthExtent === "top_boundaries" ? (
        <div className="wlv-shared-infill-row wlv-shared-infill-row--boundaries">
          <label>Top boundary<select disabled={disabled} value={topBoundaryValue} onChange={(e) => onTopBoundaryChange?.(e.target.value)}><option value="">Select top</option>{topBoundaryOptions.map((item) => <option key={item.value} value={item.value} disabled={item.disabled}>{item.label}</option>)}</select></label>
          <label>Base boundary<select disabled={disabled || !topBoundaryValue} value={baseBoundaryValue} onChange={(e) => onBaseBoundaryChange?.(e.target.value)}><option value="">Select base</option>{baseBoundaryOptions.map((item) => <option key={item.value} value={item.value} disabled={item.disabled}>{item.label}</option>)}</select></label>
        </div>
      ) : null}

      <div className="wlv-shared-infill-row wlv-shared-infill-row--appearance">
        <label>Fill appearance<select disabled={disabled} value={appearance} onChange={(e) => onAppearanceChange(e.target.value as SharedInfillEditorProps["appearance"])}><option value="solid">Solid</option><option value="pattern">Pattern</option><option value="raster">Raster</option></select></label>
        {appearance === "pattern" ? <label>Pattern<select disabled={disabled} value={patternValue} onChange={(e) => onPatternChange?.(e.target.value)}>{patternOptions.map((item) => <option key={item.value} value={item.value} disabled={item.disabled}>{item.label}</option>)}</select></label> : null}
        {appearance === "raster" ? rasterTextMode ? (
          <><label>Raster image URL<input type="text" disabled={disabled} value={rasterValue} onChange={(e) => onRasterChange?.(e.target.value)} /></label><label>Fit<select disabled={disabled} value={rasterFit} onChange={(e) => onRasterFitChange?.(e.target.value as "stretch" | "cover")}><option value="stretch">Stretch</option><option value="cover">Preserve aspect / cover</option></select></label></>
        ) : <label>Raster<select disabled={disabled} value={rasterValue} onChange={(e) => onRasterChange?.(e.target.value)}><option value="">Select raster</option>{rasterOptions.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label> : null}
      </div>

      {selectorKind && selectorContent ? <div className={`wlv-shared-infill-row wlv-shared-infill-row--selector is-${selectorKind}`}>{selectorContent}</div> : null}

      <div className="wlv-shared-infill-row wlv-shared-infill-row--style">
        <label>Pattern scale<input type="range" min={0.25} max={4} step={0.25} disabled={disabled || appearance !== "pattern"} value={patternScale} onChange={(e) => onPatternScaleChange(Number(e.target.value))} /></label>
        <label className="wlv-curve-editor__color-control"><span className="wlv-curve-editor__color-label">Color</span><input className="wlv-curve-editor__color-swatch" type="color" disabled={disabled} value={color} onChange={(e) => onColorChange(e.target.value)} /></label>
        <label>Opacity<input type="range" min={0} max={opacityMax} step={0.05} disabled={disabled} value={opacity} onChange={(e) => onOpacityChange(Number(e.target.value))} /></label>
      </div>
    </div>
  );
}
