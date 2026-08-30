import { useEffect, useRef, useState } from "react";

export type CurveLineStyleValue = Readonly<{
  visible: boolean;
  color: string;
  width: number;
  style: "solid" | "dash" | "dot";
  opacity: number;
}>;

export type CurveLineStyleControlProps = Readonly<{
  value: CurveLineStyleValue;
  onPreview: (value: CurveLineStyleValue) => void;
  onCommit: (value: CurveLineStyleValue) => void;
}>;

const normalize = (value: CurveLineStyleValue): CurveLineStyleValue => ({
  visible: Boolean(value.visible),
  color: /^#[0-9a-fA-F]{6}$/.test(value.color) ? value.color : "#ffffff",
  width: Math.max(0.5, Math.min(8, Math.round(value.width * 10) / 10)),
  style: value.style === "dash" || value.style === "dot" ? value.style : "solid",
  opacity: Math.max(0, Math.min(100, Math.round(value.opacity / 5) * 5)),
});

const equal = (a: CurveLineStyleValue, b: CurveLineStyleValue): boolean =>
  a.visible === b.visible &&
  a.color === b.color &&
  a.width === b.width &&
  a.style === b.style &&
  a.opacity === b.opacity;

export function CurveLineStyleControl({
  value,
  onPreview,
  onCommit,
}: CurveLineStyleControlProps) {
  const [draft, setDraft] = useState<CurveLineStyleValue>(() => normalize(value));
  const draftRef = useRef(draft);
  const interactingRef = useRef(false);
  const committedRef = useRef(draft);

  useEffect(() => {
    if (interactingRef.current) return;
    const next = normalize(value);
    draftRef.current = next;
    committedRef.current = next;
    setDraft(next);
  }, [value.visible, value.color, value.width, value.style, value.opacity]);

  const preview = (patch: Partial<CurveLineStyleValue>) => {
    const next = normalize({ ...draftRef.current, ...patch });
    draftRef.current = next;
    setDraft(next);
    onPreview(next);
    return next;
  };

  const commit = (candidate: CurveLineStyleValue = draftRef.current) => {
    const next = normalize(candidate);
    interactingRef.current = false;
    draftRef.current = next;
    setDraft(next);
    if (equal(next, committedRef.current)) return;
    committedRef.current = next;
    onCommit(next);
  };

  return (
    <div className="wlv-curve-editor-section wlv-curve-editor-section--line">
      <h4>Line</h4>
      <label className="wlv-curve-editor-checkbox-row">
        <input
          type="checkbox"
          checked={draft.visible}
          onChange={(event) => {
            const next = preview({ visible: event.currentTarget.checked });
            commit(next);
          }}
        />
        Show line
      </label>
      <label className="wlv-curve-editor__line-color">
        <span>Color</span>
        <input
          type="color"
          value={draft.color}
          onChange={(event) => {
            const next = preview({ color: event.currentTarget.value });
            commit(next);
          }}
        />
      </label>
      <label className="wlv-curve-editor-field wlv-curve-editor-field--line-width">
        <span className="wlv-curve-editor-field-label">Width</span>
        <input
          type="number"
          min={0.5}
          max={8}
          step={0.1}
          value={draft.width}
          onFocus={() => { interactingRef.current = true; }}
          onChange={(event) => preview({ width: Number(event.currentTarget.value) })}
          onBlur={() => commit()}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              commit();
              event.currentTarget.blur();
            }
          }}
        />
      </label>
      <label className="wlv-curve-editor-field wlv-curve-editor-field--line-style">
        <span className="wlv-curve-editor-field-label">Style</span>
        <select
          value={draft.style}
          onChange={(event) => {
            const next = preview({
              style: event.currentTarget.value as CurveLineStyleValue["style"],
            });
            commit(next);
          }}
        >
          <option value="solid">Solid</option>
          <option value="dash">Dashed</option>
          <option value="dot">Dotted</option>
        </select>
      </label>
      <label className="wlv-curve-editor-field wlv-curve-editor-field--line-opacity">
        <span className="wlv-curve-editor-field-label">Opacity</span>
        <input
          aria-label="Curve line opacity"
          type="range"
          min={0}
          max={100}
          step={5}
          value={draft.opacity}
          onPointerDown={() => { interactingRef.current = true; }}
          onInput={(event) => preview({ opacity: Number(event.currentTarget.value) })}
          onPointerUp={() => commit()}
          onPointerCancel={() => commit()}
          onBlur={() => commit()}
          onKeyDown={() => { interactingRef.current = true; }}
          onKeyUp={(event) => {
            if (
              event.key === "ArrowLeft" ||
              event.key === "ArrowRight" ||
              event.key === "ArrowUp" ||
              event.key === "ArrowDown" ||
              event.key === "Home" ||
              event.key === "End" ||
              event.key === "PageUp" ||
              event.key === "PageDown"
            ) commit();
          }}
        />
      </label>
    </div>
  );
}
