from __future__ import annotations

import json
import os
import tempfile
import threading
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .repository import VALID_TOOLS

RULES_SCHEMA_VERSION = "toolbox_ai_rules_v1"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


DEFAULT_RULES: dict[str, dict[str, Any]] = {
    "WME": {
        "purpose": "Extract missing Well Info metadata for human review.",
        "instructions": [
            "Use supporting evidence; do not invent unsupported metadata.",
            "Return proposed values with source, evidence and confidence.",
            "Do not silently overwrite existing accepted Well Info values."
        ]
    },
    "FTM": {
        "purpose": "Discover and reconcile formation-top and useful stratigraphic marker candidates.",
        "instructions": [
            "Capture broadly, label precisely, and require marker-specific evidence.",
            "Preserve reported depth unit and reference; do not invent missing depths.",
            "A candidate without usable measured depth (MD) must have confidence invalid.",
            "Distinguish Actual, Prognosed, Interpreted and Imported picks.",
            "Do not automatically replace existing tops."
        ]
    },
    "CDM": {
        "purpose": "Extract completion components and defensible completion geometry for human review.",
        "instructions": [
            "Use explicit completion evidence and preserve source terminology.",
            "Do not invent component depths, dimensions or status.",
            "Keep uncertain or incomplete candidates clearly qualified."
        ]
    },
    "LCM": {'purpose': 'Discover, classify and reconcile defensible selected-well lithology intervals and secondary '
                'lithology observations for human review in the Lithology Column Manager.',
     'standard_revision': 'lcm-ai-standard-1.0.0',
     'governing_principles': ['Use only evidence contained in the supplied package and its managed KR lithology '
                              'catalogue reference. Do not use outside geological knowledge to fill gaps.',
                              'Selected-well identity is a mandatory gate. Evidence from another well, field, '
                              'prognosis or regional description must never be presented as direct selected-well '
                              'evidence.',
                              'Preserve source lithology wording, depth units, depth reference, qualifiers and '
                              'uncertainty.',
                              'Do not invent lithology boundaries, continuity, dominance or missing depths.',
                              'Return proposals for human review only. Never represent AI output as approved, '
                              'published or reviewed.'],
     'source_classification': {'direct_selected_well': 'Explicit lithology evidence tied to the managed well and '
                                                       'eligible to support primary intervals.',
                               'selected_well_graphical': 'A graphical selected-well lithology column, log, flag '
                                                          'or interpreted track with readable depth context.',
                               'selected_well_stratigraphic_only': 'Selected-well stratigraphic names/boundaries '
                                                                   'without explicit rock-type evidence; not '
                                                                   'sufficient alone to assign lithology.',
                               'analogue_well': 'Lithology evidence from another named well; context/correlation '
                                                'only.',
                               'field_or_regional': 'Field-wide or regional geology not demonstrated to be '
                                                    'selected-well specific.',
                               'planning_or_prognosis': 'Predicted/pre-drill geology; not direct drilled-well '
                                                        'evidence.',
                               'not_applicable': 'No usable lithology evidence for the managed well.'},
     'evidence_hierarchy': ['Selected-well core descriptions.',
                            'Selected-well cuttings, mudlog, wellsite or completion-report lithology '
                            'descriptions.',
                            'Selected-well interpreted composite logs, CPI outputs or graphical lithology '
                            'tracks.',
                            'Selected-well formation descriptions explicitly tied to depth intervals.',
                            'Explicitly correlated evidence from another well.',
                            'Field-wide, regional, planning or prognosed descriptions.'],
     'depth_rules': ['Populate Top MD and Base MD only when the source explicitly identifies MD/Measured Depth '
                     'or the enclosing table/track unambiguously defines the scale as MD.',
                     'Do not place TVD, TVDSS, subsea or unspecified depth into an MD field.',
                     'Do not calculate TVD, TVDSS, datum conversions or deviation-derived depths.',
                     'Use managed-well top/base depth only as validation bounds; flag credible out-of-range '
                     'evidence rather than silently changing it.',
                     'For explicit lithology change-point sequences, a change depth may be the Top MD of the new '
                     'interval and the Base MD of the preceding interval.',
                     'If Base MD is derived from the next explicit change/boundary rather than directly stated, '
                     'record that derivation and use no higher than Medium confidence.',
                     'Graphically estimated boundaries must be explicitly labelled approximate/graphical in '
                     'notes.',
                     'Do not infer one continuous interval from isolated occurrences.',
                     'Leave the final Base MD empty when the source does not support an ending boundary.'],
     'primary_interval_rules': ['Primary candidates represent dominant or explicitly mixed selected-well '
                                'lithology intervals.',
                                'Primary intervals should be non-overlapping. Preserve genuine gaps rather than '
                                'fabricating continuity.',
                                'Accept explicit From/To ranges, dash ranges, tabulated ranges and defensible '
                                'change-point sequences.',
                                'A formation/group/member/reservoir name is not a lithology. Do not infer rock '
                                'type from a stratigraphic name alone.',
                                'When several lithologies are stated within one interval without internal '
                                'boundaries, preserve one mixed interval rather than inventing subdivisions.',
                                'Remove exact duplicates, but do not collapse materially conflicting direct '
                                'interpretations.',
                                'Every candidate requires exact source filename and a traceable '
                                'page/table/section/figure/track/row reference.'],
     'secondary_observation_rules': ['Do not convert isolated subordinate features into overlapping primary '
                                     'intervals.',
                                     'Secondary observations include stringers, streaks, traces, minor '
                                     'lithologies, local grading, pyrite, glauconite, carbonate cement and '
                                     'isolated graphical flags.',
                                     'Record secondary observations separately with host interval, feature, '
                                     'depth, continuity, source, evidence location, confidence and boundary '
                                     'precision.',
                                     'COAL_FLAG supports coal occurrence only; it does not prove continuous coal '
                                     'across an enclosing interval.',
                                     'CARB_FLAG or CCARB supports carbonate-bearing/cemented material only; it '
                                     'does not by itself prove limestone.'],
     'lithology_matching_rules': ['Preserve original source wording in lithology and description.',
                                  'Use the lithology field for the explicitly dominant lithology; retain '
                                  'minor/trace components in description/notes.',
                                  'Use KR catalogue names and aliases as controlled mapping assistance, not as '
                                  'evidence that a lithology exists.',
                                  'Map to a canonical KR lithology only when the source evidence defensibly '
                                  'supports that family or representative family.',
                                  'Exact word-for-word matching is not required where a KR alias or stated '
                                  'alternative is equivalent.',
                                  'For mixed intervals, use the explicitly dominant component where stated; '
                                  'otherwise identify any representative KR mapping as representative in notes.',
                                  'Do not let a catalogue match create, extend or split an interval boundary.'],
     'confidence_rules': {'high': 'Selected-well lithology and both interval boundaries are explicit in a '
                                  'credible source with clear MD context.',
                          'medium': 'Selected-well lithology is explicit and boundaries are supported, but one '
                                    'boundary requires limited derivation, graphical reading or reconciliation.',
                          'low': 'Lithology/interval is selected-well relevant but materially approximate, '
                                 'ambiguous or supported by incomplete direct evidence.',
                          'invalid': 'A proposed primary interval lacks a defensible Top MD or Base MD required '
                                     'to define the interval. Keep as review evidence/observation rather than a '
                                     'usable primary interval.'},
     'multi_document_rules': ['Treat every supporting document as an independent extraction work unit.',
                              'Complete discovery within each document before cross-document reconciliation.',
                              'The deterministic screening page budget is per document and must not be shared '
                              'across documents.',
                              'Existing candidates are reconciliation context only and must not suppress '
                              'discoveries from a new document.',
                              'Preserve the union of valid per-document findings.',
                              'Consolidate only genuinely identical intervals while retaining evidence from '
                              'every supporting source.',
                              'Keep materially different boundaries or lithology interpretations as explicit '
                              'conflicts/alternatives.'],
     'provenance_rules': ['Every primary candidate and secondary observation must retain source document and '
                          'specific evidence location.',
                          'Evidence must be candidate-specific and auditable.',
                          'Do not attribute evidence from one document to another.',
                          'When multiple sources corroborate a candidate, retain each source independently.',
                          'State whether evidence is direct, graphical, derived, analogue, regional or '
                          'prognosed.'],
     'final_self_audit': ['Confirm all explicit selected-well lithology tables/ranges were captured.',
                          'Inspect selected-well narrative, core/cuttings descriptions and graphical lithology '
                          'columns for additional evidence.',
                          'Check all primary intervals for non-overlap and report gaps rather than filling them.',
                          'Check MD was not confused with TVD/TVDSS or an unspecified depth.',
                          'Check no stratigraphic name was silently converted into a lithology.',
                          'Check every candidate has source-specific provenance and confidence consistent with '
                          'boundary evidence.',
                          'Check KR mapping did not create unsupported geology or boundaries.',
                          'Check analogue/regional/prognosed evidence remains clearly separated from direct '
                          'selected-well evidence.'],
     'kr_lithology_reference': {'catalogue_id': 'multiviewer:lithology-catalogue',
                                'catalogue_version': '1.0.1',
                                'entry_count': 116,
                                'source_standard': 'FGDC-STD-013-2006',
                                'usage': 'Controlled vocabulary and representative mapping reference only; never '
                                         'a substitute for source evidence.'},
     'deterministic_screening': {'profile_name': 'LCM Lithology Interval Screening',
                                 'profile_revision': 'lcm-screening-1.0.0',
                                 'purpose': 'Select pages likely to contain selected-well lithology '
                                            'descriptions, lithology interval boundaries, graphical lithology '
                                            'columns, cuttings/core descriptions, or secondary lithology '
                                            'observations.',
                                 'target_terms': ['lithology',
                                                  'lithologic',
                                                  'lithological',
                                                  'lithofacies',
                                                  'facies',
                                                  'rock type',
                                                  'rock description',
                                                  'geological description',
                                                  'sandstone',
                                                  'sand',
                                                  'shale',
                                                  'mudstone',
                                                  'claystone',
                                                  'clay',
                                                  'siltstone',
                                                  'silt',
                                                  'limestone',
                                                  'dolomite',
                                                  'dolostone',
                                                  'marl',
                                                  'chalk',
                                                  'coal',
                                                  'lignite',
                                                  'conglomerate',
                                                  'gravel',
                                                  'breccia',
                                                  'diamicton',
                                                  'till',
                                                  'loess',
                                                  'chert',
                                                  'anhydrite',
                                                  'gypsum',
                                                  'halite',
                                                  'salt',
                                                  'evaporite',
                                                  'tuff',
                                                  'volcanic breccia',
                                                  'basalt',
                                                  'granite',
                                                  'igneous rock',
                                                  'gneiss',
                                                  'schist',
                                                  'serpentinite',
                                                  'quartz',
                                                  'quartzite'],
                                 'context_terms': ['cuttings',
                                                   'mud log',
                                                   'mudlog',
                                                   'mud logging',
                                                   'wellsite geology',
                                                   'wellsite geologist',
                                                   'core description',
                                                   'core analysis',
                                                   'sidewall core',
                                                   'composite log',
                                                   'CPI',
                                                   'formation evaluation',
                                                   'geological summary',
                                                   'geology summary',
                                                   'lithostratigraphy',
                                                   'sample description',
                                                   'ditch cuttings',
                                                   'returns',
                                                   'description',
                                                   'interval',
                                                   'from',
                                                   'to',
                                                   'top',
                                                   'base',
                                                   'percentage',
                                                   'percent',
                                                   'trace',
                                                   'minor',
                                                   'dominant',
                                                   'interbedded',
                                                   'interlaminated',
                                                   'stringer',
                                                   'streak',
                                                   'grading',
                                                   'grain size',
                                                   'fine grained',
                                                   'medium grained',
                                                   'coarse grained',
                                                   'colour',
                                                   'color',
                                                   'texture',
                                                   'cement',
                                                   'calcareous',
                                                   'argillaceous',
                                                   'carbonaceous',
                                                   'glauconite',
                                                   'pyrite',
                                                   'fossiliferous'],
                                 'depth_terms': ['MD',
                                                 'measured depth',
                                                 'm MD',
                                                 'ft MD',
                                                 'depth',
                                                 'top MD',
                                                 'base MD',
                                                 'from MD',
                                                 'to MD',
                                                 'RKB',
                                                 'RT',
                                                 'KB',
                                                 'TVD',
                                                 'TVDSS',
                                                 'm',
                                                 'ft'],
                                 'negative_terms': ['equipment list',
                                                    'distribution list',
                                                    'revision history',
                                                    'invoice',
                                                    'casing tally',
                                                    'completion string',
                                                    'perforation schedule',
                                                    'pressure test',
                                                    'directional survey',
                                                    'survey station',
                                                    'BHA',
                                                    'bit record'],
                                 'classifications': ['direct selected-well lithology interval',
                                                     'selected-well graphical lithology',
                                                     'selected-well core/cuttings description',
                                                     'mixed lithology interval',
                                                     'secondary lithology observation',
                                                     'analogue/regional context',
                                                     'planning/prognosis',
                                                     'not applicable'],
                                 'required_cooccurrence': [['lithology', 'depth'],
                                                           ['lithology', 'MD'],
                                                           ['cuttings', 'depth'],
                                                           ['core description', 'depth'],
                                                           ['sandstone', 'depth'],
                                                           ['shale', 'depth'],
                                                           ['limestone', 'depth'],
                                                           ['dolomite', 'depth'],
                                                           ['coal', 'depth'],
                                                           ['from', 'to'],
                                                           ['top', 'base']],
                                 'weights': {'target': 11,
                                             'context': 4,
                                             'depth': 4,
                                             'cooccurrence': 15,
                                             'negative': -3,
                                             'structured': 11},
                                 'context_pages': 1,
                                 'max_selected_pages': 50,
                                 'minimum_direct_score': 18,
                                 'budget_scope': 'per_document',
                                 'kr_vocabulary_reference': {'catalogue_id': 'multiviewer:lithology-catalogue',
                                                             'catalogue_version': '1.0.1',
                                                             'entry_count': 116,
                                                             'policy': 'KR catalogue names and aliases '
                                                                       'supplement screening vocabulary. They do '
                                                                       'not by themselves prove a lithology '
                                                                       'interval or boundary.'},
                                 'ocr_fallback': {'enabled': True,
                                                  'provider': 'macos_vision',
                                                  'ranking_mode': 'fast',
                                                  'selected_mode': 'accurate'}}},
    "DSM": {
        "purpose": "Extract deviation-survey stations and trajectory metadata for human review.",
        "instructions": [
            "Prefer explicit survey tables and preserve survey reference and units.",
            "Do not interpolate or invent missing survey stations unless explicitly requested.",
            "Keep MD, inclination and azimuth associations auditable to source evidence."
        ]
    },
    "CIM_JOIN": {
        "purpose": "Join photographed core panels without altering geological content.",
        "instructions": [
            "Preserve source-panel order, scale and visible geological features.",
            "Do not invent missing core material or conceal discontinuities.",
            "Return join and registration results with source-panel provenance."
        ]
    },
    "CIM_AIQC": {
        "purpose": "Perform end-to-end QA/QC on continuous core imagery.",
        "instructions": [
            "Identify join, continuity, depth-registration and image-quality issues.",
            "Do not modify accepted core interpretation during QA/QC.",
            "Report findings with auditable source or segment references."
        ]
    }
}


class ToolboxAiRulesRepository:
    def __init__(self, path: Path | str | None = None) -> None:
        if path is None:
            path = Path(__file__).resolve().parents[3] / "runtime" / "toolbox_ai_rules_v1.json"
        self.path = Path(path)
        self._lock = threading.RLock()

    def _empty(self) -> dict[str, Any]:
        now = _utc_now()
        return {
            "schema_version": RULES_SCHEMA_VERSION,
            "tools": {
                tool: {
                    "tool": tool,
                    "rules": deepcopy(DEFAULT_RULES[tool]),
                    "previous_rules": None,
                    "updated_at": now,
                    "updated_by": "shipped-default",
                }
                for tool in sorted(VALID_TOOLS)
            },
        }

    def _load_unlocked(self) -> dict[str, Any]:
        if not self.path.exists():
            return self._empty()
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Toolbox AI rules registry is unreadable: {self.path}") from exc
        if payload.get("schema_version") != RULES_SCHEMA_VERSION or not isinstance(payload.get("tools"), dict):
            raise RuntimeError(f"Unsupported Toolbox AI rules registry: {self.path}")
        for tool in VALID_TOOLS:
            payload["tools"].setdefault(
                tool,
                {
                    "tool": tool,
                    "rules": deepcopy(DEFAULT_RULES[tool]),
                    "previous_rules": None,
                    "updated_at": _utc_now(),
                    "updated_by": "shipped-default",
                },
            )
        return payload

    def _write_unlocked(self, payload: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(
            prefix=f".{self.path.name}.",
            suffix=".tmp",
            dir=str(self.path.parent),
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, self.path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)

    @staticmethod
    def _tool(tool: str) -> str:
        value = str(tool or "").strip().upper()
        if value not in VALID_TOOLS:
            raise ValueError(f"Unsupported Toolbox AI tool: {value}")
        return value

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            payload = self._load_unlocked()
            return [deepcopy(payload["tools"][tool]) for tool in sorted(VALID_TOOLS)]

    def get(self, tool: str) -> dict[str, Any]:
        tool = self._tool(tool)
        with self._lock:
            return deepcopy(self._load_unlocked()["tools"][tool])

    def save(self, tool: str, rules: dict[str, Any], updated_by: str | None = None) -> dict[str, Any]:
        tool = self._tool(tool)
        if not isinstance(rules, dict):
            raise ValueError("rules must be a JSON object")
        with self._lock:
            payload = self._load_unlocked()
            record = payload["tools"][tool]
            record["previous_rules"] = deepcopy(record.get("rules"))
            record["rules"] = deepcopy(rules)
            record["updated_at"] = _utc_now()
            record["updated_by"] = str(updated_by or "operator").strip() or "operator"
            self._write_unlocked(payload)
            return deepcopy(record)

    def reset_default(self, tool: str, updated_by: str | None = None) -> dict[str, Any]:
        tool = self._tool(tool)
        return self.save(tool, deepcopy(DEFAULT_RULES[tool]), updated_by or "operator-default-reset")

    def restore_previous(self, tool: str, updated_by: str | None = None) -> dict[str, Any]:
        tool = self._tool(tool)
        with self._lock:
            payload = self._load_unlocked()
            record = payload["tools"][tool]
            previous = record.get("previous_rules")
            if not isinstance(previous, dict):
                raise ValueError("No previous rule set is available")
            current = deepcopy(record.get("rules"))
            record["rules"] = deepcopy(previous)
            record["previous_rules"] = current
            record["updated_at"] = _utc_now()
            record["updated_by"] = str(updated_by or "operator-restore-previous").strip() or "operator"
            self._write_unlocked(payload)
            return deepcopy(record)
