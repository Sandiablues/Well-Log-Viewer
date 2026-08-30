import { useEffect, useMemo, useState } from 'react';
import type { ToolboxAiRevisionTool } from './toolboxAiRevision';
import AiQualificationHarnessPrototype from './AiQualificationHarnessPrototype';
import {
  deleteToolboxAiStandardVersion,
  fetchToolboxAiRules,
  fetchToolboxAiStandardVersion,
  restoreToolboxAiStandardAsNewVersion,
  saveNewToolboxAiStandardVersion,
  type ToolboxAiStandardActive,
} from './toolboxAiRulesClient';

type Props = { onBack: () => void };

const TOOLS: Array<{ value: ToolboxAiRevisionTool; label: string }> = [
  { value: 'WME', label: 'Well Metadata Extractor' },
  { value: 'FTM', label: 'Formation Tops Manager' },
  { value: 'CDM', label: 'Completion Data Manager' },
  { value: 'LCM', label: 'Lithology Column Manager' },
  { value: 'DSM', label: 'Deviation Survey Manager' },
  { value: 'CIM_JOIN', label: 'Core Image Manager — Join' },
  { value: 'CIM_AIQC', label: 'Core Image Manager — AIQC' },
];

const DEFAULT_DETERMINISTIC_SCREENING: Record<ToolboxAiRevisionTool, Record<string, unknown>> = {
  "WME": {
    "profile_name": "Well Metadata Screening",
    "target_terms": [
      "well name",
      "wellbore",
      "uwi",
      "api number",
      "latitude",
      "longitude",
      "northing",
      "easting",
      "datum",
      "coordinate system",
      "total depth",
      "measured depth",
      "vertical depth",
      "depth reference",
      "rotary table",
      "kelly bushing",
      "water depth"
    ],
    "context_terms": [
      "well summary",
      "well information",
      "survey",
      "position",
      "coordinates",
      "reference",
      "header",
      "well data"
    ],
    "depth_terms": [
      "MD",
      "TVD",
      "TVDSS",
      "m MD",
      "ft MD",
      "RKB",
      "RT",
      "KB",
      "MSL"
    ],
    "negative_terms": [
      "invoice",
      "distribution list",
      "revision history"
    ],
    "classifications": [
      "identity",
      "position",
      "crs",
      "depth reference",
      "well extent",
      "survey extent",
      "operational metadata"
    ],
    "required_cooccurrence": [
      [
        "total depth",
        "MD"
      ],
      [
        "latitude",
        "longitude"
      ],
      [
        "northing",
        "easting"
      ],
      [
        "depth",
        "reference"
      ]
    ],
    "weights": {
      "target": 10,
      "context": 4,
      "depth": 3,
      "cooccurrence": 12,
      "negative": -4,
      "structured": 8
    },
    "context_pages": 1,
    "max_selected_pages": 50
  },
  "FTM": {
    "profile_name": "Formation Tops Screening",
    "target_terms": [
      "formation top",
      "formation tops",
      "formation",
      "fm.",
      "member",
      "group",
      "top",
      "base",
      "marker",
      "unconformity",
      "stratigraph",
      "lithostrat",
      "chronostrat",
      "biostrat"
    ],
    "context_terms": [
      "geological summary",
      "geology",
      "drilling results",
      "well results",
      "formation evaluation",
      "reservoir",
      "prognosis",
      "actual",
      "composite log",
      "stratigraphy"
    ],
    "depth_terms": [
      "MD",
      "TVD",
      "TVDSS",
      "m MD",
      "ft MD",
      "RKB",
      "RT",
      "KB",
      "MSL",
      "depth"
    ],
    "negative_terms": [
      "casing shoe",
      "tool depth",
      "logging depth",
      "pressure test",
      "perforation"
    ],
    "classifications": [
      "Actual",
      "Prognosed",
      "Interpreted",
      "Imported"
    ],
    "required_cooccurrence": [
      [
        "formation",
        "depth"
      ],
      [
        "top",
        "MD"
      ],
      [
        "base",
        "MD"
      ],
      [
        "marker",
        "depth"
      ],
      [
        "stratigraph",
        "depth"
      ]
    ],
    "weights": {
      "target": 10,
      "context": 4,
      "depth": 3,
      "cooccurrence": 14,
      "negative": -3,
      "structured": 10
    },
    "context_pages": 1,
    "max_selected_pages": 50
  },
  "CDM": {
    "profile_name": "Completion Data Screening",
    "target_terms": [
      "completion",
      "perforation",
      "packer",
      "tubing",
      "casing",
      "liner",
      "screen",
      "valve",
      "plug",
      "mandrel",
      "completion interval"
    ],
    "context_terms": [
      "completion summary",
      "well completion",
      "completion design",
      "installation",
      "workover",
      "as built"
    ],
    "depth_terms": [
      "MD",
      "TVD",
      "top",
      "base",
      "from",
      "to",
      "m",
      "ft"
    ],
    "negative_terms": [
      "formation top",
      "survey station"
    ],
    "classifications": [
      "completion component",
      "perforation interval",
      "casing",
      "tubing",
      "packer",
      "other"
    ],
    "required_cooccurrence": [
      [
        "perforation",
        "MD"
      ],
      [
        "packer",
        "depth"
      ],
      [
        "tubing",
        "depth"
      ],
      [
        "casing",
        "depth"
      ]
    ],
    "weights": {
      "target": 10,
      "context": 4,
      "depth": 3,
      "cooccurrence": 12,
      "negative": -2,
      "structured": 8
    },
    "context_pages": 1,
    "max_selected_pages": 50
  },
  "LCM": {
    "profile_name": "LCM Lithology Interval Screening",
    "profile_revision": "lcm-screening-1.0.0",
    "purpose": "Select pages likely to contain selected-well lithology descriptions, lithology interval boundaries, graphical lithology columns, cuttings/core descriptions, or secondary lithology observations.",
    "target_terms": [
        "lithology",
        "lithologic",
        "lithological",
        "lithofacies",
        "facies",
        "rock type",
        "rock description",
        "geological description",
        "sandstone",
        "sand",
        "shale",
        "mudstone",
        "claystone",
        "clay",
        "siltstone",
        "silt",
        "limestone",
        "dolomite",
        "dolostone",
        "marl",
        "chalk",
        "coal",
        "lignite",
        "conglomerate",
        "gravel",
        "breccia",
        "diamicton",
        "till",
        "loess",
        "chert",
        "anhydrite",
        "gypsum",
        "halite",
        "salt",
        "evaporite",
        "tuff",
        "volcanic breccia",
        "basalt",
        "granite",
        "igneous rock",
        "gneiss",
        "schist",
        "serpentinite",
        "quartz",
        "quartzite"
    ],
    "context_terms": [
        "cuttings",
        "mud log",
        "mudlog",
        "mud logging",
        "wellsite geology",
        "wellsite geologist",
        "core description",
        "core analysis",
        "sidewall core",
        "composite log",
        "CPI",
        "formation evaluation",
        "geological summary",
        "geology summary",
        "lithostratigraphy",
        "sample description",
        "ditch cuttings",
        "returns",
        "description",
        "interval",
        "from",
        "to",
        "top",
        "base",
        "percentage",
        "percent",
        "trace",
        "minor",
        "dominant",
        "interbedded",
        "interlaminated",
        "stringer",
        "streak",
        "grading",
        "grain size",
        "fine grained",
        "medium grained",
        "coarse grained",
        "colour",
        "color",
        "texture",
        "cement",
        "calcareous",
        "argillaceous",
        "carbonaceous",
        "glauconite",
        "pyrite",
        "fossiliferous"
    ],
    "depth_terms": [
        "MD",
        "measured depth",
        "m MD",
        "ft MD",
        "depth",
        "top MD",
        "base MD",
        "from MD",
        "to MD",
        "RKB",
        "RT",
        "KB",
        "TVD",
        "TVDSS",
        "m",
        "ft"
    ],
    "negative_terms": [
        "equipment list",
        "distribution list",
        "revision history",
        "invoice",
        "casing tally",
        "completion string",
        "perforation schedule",
        "pressure test",
        "directional survey",
        "survey station",
        "BHA",
        "bit record"
    ],
    "classifications": [
        "direct selected-well lithology interval",
        "selected-well graphical lithology",
        "selected-well core/cuttings description",
        "mixed lithology interval",
        "secondary lithology observation",
        "analogue/regional context",
        "planning/prognosis",
        "not applicable"
    ],
    "required_cooccurrence": [
        [
            "lithology",
            "depth"
        ],
        [
            "lithology",
            "MD"
        ],
        [
            "cuttings",
            "depth"
        ],
        [
            "core description",
            "depth"
        ],
        [
            "sandstone",
            "depth"
        ],
        [
            "shale",
            "depth"
        ],
        [
            "limestone",
            "depth"
        ],
        [
            "dolomite",
            "depth"
        ],
        [
            "coal",
            "depth"
        ],
        [
            "from",
            "to"
        ],
        [
            "top",
            "base"
        ]
    ],
    "weights": {
        "target": 11,
        "context": 4,
        "depth": 4,
        "cooccurrence": 15,
        "negative": -3,
        "structured": 11
    },
    "context_pages": 1,
    "max_selected_pages": 50,
    "minimum_direct_score": 18,
    "budget_scope": "per_document",
    "kr_vocabulary_reference": {
        "catalogue_id": "multiviewer:lithology-catalogue",
        "catalogue_version": "1.0.1",
        "entry_count": 116,
        "policy": "KR catalogue names and aliases supplement screening vocabulary. They do not by themselves prove a lithology interval or boundary."
    },
    "ocr_fallback": {
        "enabled": true,
        "provider": "macos_vision",
        "ranking_mode": "fast",
        "selected_mode": "accurate"
    }
},
  "DSM": {
    "profile_name": "Deviation Survey Screening",
    "target_terms": [
      "survey",
      "deviation",
      "inclination",
      "azimuth",
      "dogleg",
      "northing",
      "easting",
      "vertical section"
    ],
    "context_terms": [
      "survey report",
      "trajectory",
      "directional",
      "survey station",
      "well path"
    ],
    "depth_terms": [
      "MD",
      "TVD",
      "TVDSS",
      "measured depth",
      "vertical depth"
    ],
    "negative_terms": [
      "formation top",
      "lithology"
    ],
    "classifications": [
      "survey station",
      "survey metadata",
      "trajectory reference"
    ],
    "required_cooccurrence": [
      [
        "MD",
        "inclination"
      ],
      [
        "MD",
        "azimuth"
      ],
      [
        "survey",
        "TVD"
      ]
    ],
    "weights": {
      "target": 10,
      "context": 4,
      "depth": 4,
      "cooccurrence": 14,
      "negative": -2,
      "structured": 10
    },
    "context_pages": 1,
    "max_selected_pages": 60
  },
  "CIM_JOIN": {
    "profile_name": "Core Join Screening",
    "target_terms": [
      "core",
      "core box",
      "core photograph",
      "core photo",
      "interval",
      "run",
      "recovery",
      "depth"
    ],
    "context_terms": [
      "core inventory",
      "core summary",
      "photograph",
      "image",
      "box"
    ],
    "depth_terms": [
      "MD",
      "top",
      "base",
      "from",
      "to",
      "m",
      "ft"
    ],
    "negative_terms": [
      "formation pressure",
      "completion"
    ],
    "classifications": [
      "core image",
      "core interval",
      "core run"
    ],
    "required_cooccurrence": [
      [
        "core",
        "depth"
      ],
      [
        "core",
        "MD"
      ],
      [
        "box",
        "depth"
      ]
    ],
    "weights": {
      "target": 10,
      "context": 4,
      "depth": 3,
      "cooccurrence": 12,
      "negative": -2,
      "structured": 8
    },
    "context_pages": 1,
    "max_selected_pages": 50
  },
  "CIM_AIQC": {
    "profile_name": "Core AIQC Screening",
    "target_terms": [
      "core",
      "image",
      "photograph",
      "blur",
      "overlap",
      "gap",
      "alignment",
      "scale",
      "depth label"
    ],
    "context_terms": [
      "quality",
      "qc",
      "join",
      "splice",
      "panel",
      "box"
    ],
    "depth_terms": [
      "MD",
      "top",
      "base",
      "from",
      "to",
      "m",
      "ft"
    ],
    "negative_terms": [
      "formation pressure",
      "completion"
    ],
    "classifications": [
      "image quality",
      "join quality",
      "depth alignment",
      "coverage"
    ],
    "required_cooccurrence": [
      [
        "core",
        "image"
      ],
      [
        "depth",
        "image"
      ],
      [
        "join",
        "core"
      ]
    ],
    "weights": {
      "target": 10,
      "context": 4,
      "depth": 2,
      "cooccurrence": 10,
      "negative": -2,
      "structured": 6
    },
    "context_pages": 1,
    "max_selected_pages": 50
  }
};



function splitStandardRules(rules: Record<string, unknown>) {
  const copy = { ...rules };
  const deterministic = (
    copy.deterministic_screening
    && typeof copy.deterministic_screening === 'object'
    && !Array.isArray(copy.deterministic_screening)
  ) ? copy.deterministic_screening as Record<string, unknown> : null;
  delete copy.deterministic_screening;
  return { aiRules: copy, deterministic };
}

export default function AiStandardsManagerPage({ onBack }: Props) {
  const [tool, setTool] = useState<ToolboxAiRevisionTool>('FTM');
  const [active, setActive] = useState<ToolboxAiStandardActive | null>(null);
  const [selectedVersion, setSelectedVersion] = useState<number>(1);
  const [text, setText] = useState('');
  const [changeNote, setChangeNote] = useState('');
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState('');
  const [error, setError] = useState('');
  const [mode, setMode] = useState<'standards' | 'qualification'>('standards');
  const [standardPane, setStandardPane] = useState<'ai' | 'deterministic'>('ai');
  const [deterministicText, setDeterministicText] = useState('');

  const selectedIsActive = selectedVersion === active?.active_version;

  const loadActive = async (selectedTool = tool) => {
    setLoading(true);
    setError('');
    setStatus('');
    try {
      const next = await fetchToolboxAiRules(selectedTool);
      setActive(next);
      setSelectedVersion(next.active_version);
      const split = splitStandardRules(next.rules);
      setText(JSON.stringify(split.aiRules, null, 2));
      setDeterministicText(JSON.stringify(
        split.deterministic ?? DEFAULT_DETERMINISTIC_SCREENING[selectedTool],
        null,
        2,
      ));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { void loadActive(tool); }, [tool]);

  const loadVersion = async (version: number) => {
    if (!active) return;
    setSelectedVersion(version);
    setError('');
    setStatus('');
    if (version === active.active_version) {
      const split = splitStandardRules(active.rules);
      setText(JSON.stringify(split.aiRules, null, 2));
      setDeterministicText(JSON.stringify(
        split.deterministic ?? DEFAULT_DETERMINISTIC_SCREENING[tool],
        null,
        2,
      ));
      return;
    }
    try {
      const record = await fetchToolboxAiStandardVersion(tool, version);
      const split = splitStandardRules(record.rules);
      setText(JSON.stringify(split.aiRules, null, 2));
      setDeterministicText(JSON.stringify(
        split.deterministic ?? DEFAULT_DETERMINISTIC_SCREENING[tool],
        null,
        2,
      ));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const parsedRules = useMemo(() => {
    try {
      const parsed = JSON.parse(text);
      return parsed && typeof parsed === 'object' && !Array.isArray(parsed)
        ? parsed as Record<string, unknown>
        : null;
    } catch {
      return null;
    }
  }, [text]);

  const parsedDeterministic = useMemo(() => {
    try {
      const parsed = JSON.parse(deterministicText);
      return parsed && typeof parsed === 'object' && !Array.isArray(parsed)
        ? parsed as Record<string, unknown>
        : null;
    } catch {
      return null;
    }
  }, [deterministicText]);

  const saveNewVersion = async () => {
    if (!parsedRules) {
      setError('AI rules must be a valid JSON object.');
      return;
    }
    if (!parsedDeterministic) {
      setError('Deterministic screening profile must be a valid JSON object.');
      return;
    }
    setError('');
    try {
      const next = await saveNewToolboxAiStandardVersion(tool, { ...parsedRules, deterministic_screening: parsedDeterministic }, changeNote);
      setActive(next);
      setSelectedVersion(next.active_version);
      const split = splitStandardRules(next.rules);
      setText(JSON.stringify(split.aiRules, null, 2));
      setDeterministicText(JSON.stringify(
        split.deterministic ?? DEFAULT_DETERMINISTIC_SCREENING[tool],
        null,
        2,
      ));
      setChangeNote('');
      setStatus(`Version ${next.active_version} saved and activated.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const deleteSelectedVersion = async () => {
    if (!active || selectedIsActive) return;
    const versionToDelete = selectedVersion;
    const toolLabel = TOOLS.find((item) => item.value === tool)?.label ?? tool;
    const confirmed = window.confirm(
      `Delete ${toolLabel} v${versionToDelete}? This permanently removes the inactive version.`
    );
    if (!confirmed) return;

    setLoading(true);
    setError('');
    setStatus('');
    try {
      const next = await deleteToolboxAiStandardVersion(tool, versionToDelete);
      setActive(next);
      setSelectedVersion(next.active_version);
      const split = splitStandardRules(next.rules);
      setText(JSON.stringify(split.aiRules, null, 2));
      setDeterministicText(JSON.stringify(
        split.deterministic ?? DEFAULT_DETERMINISTIC_SCREENING[tool],
        null,
        2,
      ));
      setChangeNote('');
      setStatus(`Version ${versionToDelete} deleted. Active version remains v${next.active_version}.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  };

  const restoreAsNewVersion = async () => {
    if (!active || selectedIsActive) return;
    setError('');
    try {
      const next = await restoreToolboxAiStandardAsNewVersion(tool, selectedVersion, changeNote);
      setActive(next);
      setSelectedVersion(next.active_version);
      const split = splitStandardRules(next.rules);
      setText(JSON.stringify(split.aiRules, null, 2));
      setDeterministicText(JSON.stringify(
        split.deterministic ?? DEFAULT_DETERMINISTIC_SCREENING[tool],
        null,
        2,
      ));
      setChangeNote('');
      setStatus(`Version ${selectedVersion} restored as new Version ${next.active_version}.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  return (
    <section className="wlv-metadata-tool wlv-ftm-tool">
      <header className="wlv-metadata-tool__header">
        <button type="button" className="wlv-metadata-tool__back" onClick={onBack}>‹ Toolbox</button>
        <div className="wlv-metadata-tool__title">
          <h1>AI Standards Manager</h1>
          <p>Manage the active AI rules and immutable standards versions used by Toolbox AI workflows.</p>
        </div>
        <div className="wlv-metadata-tool__window-actions">
          <button
            type="button"
            className="wlv-metadata-tool__close"
            aria-label="Close AI Standards Manager"
            onClick={onBack}
          >
            ×
          </button>
        </div>
      </header>

      <div className="wlv-metadata-tool__action-row">
        <button
          type="button"
          onClick={() => setMode('standards')}
          disabled={mode === 'standards'}
        >
          Standards
        </button>
        <button
          type="button"
          onClick={() => setMode('qualification')}
          disabled={mode === 'qualification'}
        >
          Qualification
        </button>
        <span className="wlv-metadata-tool__session-summary">
          {mode === 'standards'
            ? 'AI rule and version management'
            : 'AI qualification harness prototype'}
        </span>
      </div>

      {mode === 'standards' ? (
        <>
      <div
        className="wlv-metadata-tool__action-row"
        style={{ alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}
      >
        <label
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '6px',
            color: '#dbe3eb',
            fontSize: '11px',
            fontWeight: 600,
          }}
        >
          <span>Tool</span>
          <select
            value={tool}
            aria-label="Select AI standards tool"
            onChange={(event) => setTool(event.target.value as ToolboxAiRevisionTool)}
            style={{
              height: '32px',
              minWidth: '230px',
              padding: '0 28px 0 10px',
              border: '1px solid #465466',
              borderRadius: '5px',
              background: '#18202a',
              color: '#dbe3eb',
              font: 'inherit',
              fontSize: '10px',
              fontWeight: 600,
            }}
          >
            {TOOLS.map((item) => (
              <option key={item.value} value={item.value}>{item.label}</option>
            ))}
          </select>
        </label>

        <label
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '6px',
            color: '#dbe3eb',
            fontSize: '11px',
            fontWeight: 600,
          }}
        >
          <span>Version</span>
          <select
            value={selectedVersion}
            aria-label="Select AI standards version"
            onChange={(event) => void loadVersion(Number(event.target.value))}
            disabled={!active}
            style={{
              height: '32px',
              minWidth: '150px',
              padding: '0 28px 0 10px',
              border: '1px solid #465466',
              borderRadius: '5px',
              background: '#18202a',
              color: '#dbe3eb',
              font: 'inherit',
              fontSize: '10px',
              fontWeight: 600,
              opacity: active ? 1 : .5,
            }}
          >
            {(active?.versions ?? []).slice().reverse().map((item) => (
              <option key={item.version} value={item.version}>
                v{item.version}{item.version === active?.active_version ? ' — Active' : ''}
              </option>
            ))}
          </select>
        </label>

        <button type="button" onClick={() => void loadActive()} disabled={loading}>
          Reload
        </button>

        {selectedIsActive ? (
          <button
            type="button"
            onClick={() => void saveNewVersion()}
            disabled={!parsedRules || !parsedDeterministic || loading}
          >
            Save New Version
          </button>
        ) : (
          <>
            <button
              type="button"
              onClick={() => void restoreAsNewVersion()}
              disabled={loading}
            >
              Restore as New Version
            </button>
            <button
              type="button"
              onClick={() => void deleteSelectedVersion()}
              disabled={loading}
              title="Delete this inactive version. Referenced audit or qualification versions are protected by the backend."
            >
              Delete Version
            </button>
          </>
        )}

        <span className="wlv-metadata-tool__session-summary">
          {active
            ? `${TOOLS.find((item) => item.value === tool)?.label ?? tool} · Active v${active.active_version} · Viewing v${selectedVersion}`
            : 'No standard loaded'}
        </span>
      </div>

      <div className="wlv-metadata-tool__message" role="status">
        <span>
          {error
            || status
            || (selectedIsActive
              ? 'Active standard ready for review.'
              : `Historical version v${selectedVersion} is read-only.`)}
        </span>
        <span className="wlv-ftm-tool__counts">
          {active
            ? `v${active.active_version} active · ${active.updated_by} · ${active.versions.length} version${active.versions.length === 1 ? '' : 's'}`
            : '—'}
        </span>
      </div>

      <div
        className="wlv-metadata-tool__action-row"
        style={{ paddingTop: '6px', paddingBottom: '6px' }}
      >
        <button
          type="button"
          onClick={() => setStandardPane('ai')}
          disabled={standardPane === 'ai'}
        >
          Active AI Standard
        </button>
        <button
          type="button"
          onClick={() => setStandardPane('deterministic')}
          disabled={standardPane === 'deterministic'}
        >
          Deterministic Screening
        </button>
        <span className="wlv-metadata-tool__session-summary">
          {standardPane === 'ai'
            ? 'LLM interpretation and output rules'
            : 'Local evidence screening profile · no LLM/API usage'}
        </span>
      </div>

      <section className="wlv-metadata-tool__review">
        <header>
          <h2>
            {standardPane === 'ai'
              ? (selectedIsActive ? 'Active AI standard' : `AI standard history · v${selectedVersion}`)
              : (selectedIsActive ? 'Deterministic screening' : `Deterministic screening history · v${selectedVersion}`)}
          </h2>
          <div
            className="wlv-ftm-tool__bulk-selection"
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'flex-end',
              gap: '8px',
              marginLeft: 'auto',
              color: '#9ca9b7',
              fontSize: '10px',
              fontWeight: 600,
            }}
          >
            <span>{selectedIsActive ? 'Editable' : 'Read-only'}</span>
            <span>·</span>
            <span>{active ? `Updated ${active.updated_at}` : '—'}</span>
          </div>
        </header>

        <div style={{ padding: '12px' }}>
          <textarea
            value={standardPane === 'ai' ? text : deterministicText}
            onChange={(event) => {
              if (selectedIsActive) {
                if (standardPane === 'ai') setText(event.target.value);
                else setDeterministicText(event.target.value);
                setStatus('');
              }
            }}
            readOnly={!selectedIsActive}
            spellCheck={false}
            aria-label={standardPane === 'ai' ? 'AI standard rules' : 'Deterministic screening profile'}
            style={{
              display: 'block',
              width: '100%',
              minHeight: '430px',
              maxHeight: '62vh',
              resize: 'vertical',
              boxSizing: 'border-box',
              padding: '12px',
              border: '1px solid #374454',
              borderRadius: '5px',
              background: selectedIsActive ? '#10161e' : '#0d131a',
              color: selectedIsActive ? '#dbe3eb' : '#a8b2bd',
              fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
              fontSize: '11px',
              lineHeight: 1.5,
            }}
          />
        </div>

        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '10px',
            padding: '0 12px 12px',
          }}
        >
          <label
            htmlFor="ai-standards-change-note"
            style={{
              flex: '0 0 auto',
              color: '#dbe3eb',
              fontSize: '10px',
              fontWeight: 700,
            }}
          >
            Change note
          </label>
          <input
            id="ai-standards-change-note"
            value={changeNote}
            onChange={(event) => setChangeNote(event.target.value)}
            placeholder={selectedIsActive ? 'Optional note for the new version' : 'Optional note for the restore'}
            style={{
              flex: '1 1 auto',
              minWidth: 0,
              height: '30px',
              boxSizing: 'border-box',
            }}
          />
        </div>
      </section>
        </>
      ) : (
        <AiQualificationHarnessPrototype
          tool={tool}
          toolLabel={TOOLS.find((item) => item.value === tool)?.label ?? tool}
          standardVersion={selectedVersion}
          rules={parsedRules}
          deterministicProfile={parsedDeterministic ?? DEFAULT_DETERMINISTIC_SCREENING[tool]}
        />
      )}
    </section>
  );
}
