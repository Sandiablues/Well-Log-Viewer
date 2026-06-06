from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel
from fastapi.responses import HTMLResponse

from app.services.document_metadata_evidence_service import build_package_document_evidence, record_recommendation_decision, load_recommendation_decisions, build_metadata_update_plan, build_metadata_apply_preview, build_document_evidence_review_bundle, export_document_evidence_review_bundle, get_document_text_cache_status, list_document_evidence_package_index


router = APIRouter(prefix="/api/document-evidence", tags=["document-evidence"])


class RecommendationDecisionRequest(BaseModel):
    decision: str
    reason: str | None = None
    decided_by: str = "local_user"





def _attach_stored_decisions(data, package_id: str):
    stored = load_recommendation_decisions(package_id)
    data["stored_decisions"] = stored

    counts = {}
    for rec in data.get("recommended_actions", []):
        rec_id = rec.get("recommendation_id", "")
        decision = stored.get(rec_id, {})
        decision_value = decision.get("decision", "pending")

        rec["stored_decision"] = decision_value
        rec["stored_decision_reason"] = decision.get("reason")
        rec["stored_decided_at"] = decision.get("decided_at")
        rec["stored_decided_by"] = decision.get("decided_by")

        counts[decision_value] = counts.get(decision_value, 0) + 1

    data["decision_summary"] = {
        "pending": counts.get("pending", 0),
        "accept": counts.get("accept", 0),
        "decline": counts.get("decline", 0),
        "ignore": counts.get("ignore", 0),
        "defer": counts.get("defer", 0),
        "stored_decision_count": len(stored),
    }

    return data


@router.get("/packages/{package_id}")
def get_package_document_evidence(package_id: str):
    """Return read-only document evidence recommendations for a staged package."""
    data = build_package_document_evidence(package_id)
    return _attach_stored_decisions(data, package_id)


def _html_escape(value):
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _render_document_evidence_report(data):
    summary = data.get("summary", {})
    docs = data.get("documents_scanned", [])
    recs = data.get("recommended_actions", [])
    discrepancies = data.get("discrepancies", [])
    stored_decisions = data.get("stored_decisions", {})

    raw_package = str(data.get("package", ""))
    package = _html_escape(raw_package)
    generated_at = _html_escape(data.get("generated_at", ""))
    note = _html_escape(data.get("note", ""))

    doc_rows = []
    for d in docs:
        doc_rows.append(f"""
        <tr>
          <td>{_html_escape(d.get('path', ''))}</td>
          <td>{_html_escape(d.get('suffix', ''))}</td>
          <td>{_html_escape(d.get('extract_method', ''))}</td>
          <td>{_html_escape(d.get('page_count', ''))}</td>
          <td>{_html_escape(d.get('text_chars', ''))}</td>
          <td>{_html_escape(d.get('status', ''))}</td>
        </tr>
        """)

    discrepancy_blocks = []
    for d in discrepancies:
        evidence_html = []
        for e in d.get("evidence", [])[:3]:
            evidence_html.append(f"""
            <div class="evidence">
              <div><strong>Source:</strong> {_html_escape(e.get('source_document', ''))}</div>
              <div class="snippet">{_html_escape(e.get('evidence_text', ''))}</div>
            </div>
            """)

        discrepancy_blocks.append(f"""
        <section class="card discrepancy">
          <h3>{_html_escape(d.get('field', ''))}</h3>
          <p><strong>Current/context value:</strong> {_html_escape(d.get('current_context_value', ''))}</p>
          <p><strong>Candidate value:</strong> {_html_escape(d.get('candidate_value', ''))}</p>
          <p><strong>Status:</strong> {_html_escape(d.get('status', ''))}</p>
          <p><strong>Recommended action:</strong> {_html_escape(d.get('recommended_action', ''))}</p>
          <details>
            <summary>Evidence snippets</summary>
            {''.join(evidence_html)}
          </details>
        </details>
        """)

    rec_blocks = []
    for r in recs:
        rec_id = r.get("recommendation_id", "")
        stored_decision = stored_decisions.get(rec_id, {})
        decision_value = stored_decision.get("decision", "pending")
        decision_class = f"decision-{decision_value}"
        collapsed = decision_value in {"decline", "ignore", "defer"}
        evidence_html = []
        for e in r.get("evidence", [])[:3]:
            evidence_html.append(f"""
            <div class="evidence">
              <div><strong>Source:</strong> {_html_escape(e.get('source_document', ''))}</div>
              <div><strong>Observation:</strong> {_html_escape(e.get('observation_id', ''))}</div>
              <div class="snippet">{_html_escape(e.get('evidence_text', ''))}</div>
            </div>
            """)

        details_open = "" if collapsed else " open"
        rec_blocks.append(f"""
        <details class="card recommendation {decision_class}"{details_open}>
          <summary>
            <span class="summary-title">{_html_escape(r.get('recommendation_id', ''))}: {_html_escape(r.get('field', ''))}</span>
            <span class="summary-value">{_html_escape(r.get('recommended_value', ''))}</span>
            <span class="summary-decision">{_html_escape(decision_value)}</span>
          </summary>
          <div class="rec-head">
            <div>
              <h3>{_html_escape(r.get('recommendation_id', ''))}: {_html_escape(r.get('field', ''))}</h3>
              <p class="value">{_html_escape(r.get('recommended_value', ''))}</p>
            </div>
            <div class="badges">
              <span>{_html_escape(r.get('confidence', ''))}</span>
              <span>{_html_escape(r.get('severity', ''))}</span>
              <span>{_html_escape(r.get('status', ''))}</span>
            </div>
          </div>
          <p><strong>Action:</strong> {_html_escape(r.get('action', ''))}</p>
          <div class="decision-box">
            <strong>Stored decision:</strong>
            {_html_escape(stored_decisions.get(r.get('recommendation_id', ''), {}).get('decision', 'pending'))}
            <br />
            <strong>Reason:</strong>
            {_html_escape(stored_decisions.get(r.get('recommendation_id', ''), {}).get('reason', ''))}
            <br />
            <strong>Decided at:</strong>
            {_html_escape(stored_decisions.get(r.get('recommendation_id', ''), {}).get('decided_at', ''))}
          </div>
          <div class="decision-actions">
            <button onclick="recordDecision('{_html_escape(raw_package)}', '{_html_escape(r.get('recommendation_id', ''))}', 'accept')">Accept</button>
            <button onclick="recordDecision('{_html_escape(raw_package)}', '{_html_escape(r.get('recommendation_id', ''))}', 'decline')">Decline</button>
            <button onclick="recordDecision('{_html_escape(raw_package)}', '{_html_escape(r.get('recommendation_id', ''))}', 'ignore')">Ignore</button>
            <button onclick="recordDecision('{_html_escape(raw_package)}', '{_html_escape(r.get('recommendation_id', ''))}', 'defer')">Defer</button>
          </div>
          <p><strong>Evidence count:</strong> {_html_escape(r.get('evidence_count', ''))} |
             <strong>Source count:</strong> {_html_escape(r.get('source_count', ''))}</p>
          <details>
            <summary>Evidence snippets</summary>
            {''.join(evidence_html)}
          </details>
        </section>
        """)

    decision_counts = {}
    for r in recs:
        rec_id = r.get("recommendation_id", "")
        decision_value = stored_decisions.get(rec_id, {}).get("decision", "pending")
        decision_counts[decision_value] = decision_counts.get(decision_value, 0) + 1

    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>Document Evidence Report — {package}</title>
  <style>
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      margin: 24px;
      background: #f7f7f7;
      color: #1f2933;
    }}
    h1, h2, h3 {{ margin-bottom: 6px; }}
    .muted {{ color: #64748b; font-size: 13px; }}
    .summary {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 12px;
      margin: 18px 0;
    }}
    .metric, .card {{
      background: white;
      border: 1px solid #d9e2ec;
      border-radius: 10px;
      padding: 12px;
      box-shadow: 0 1px 2px rgba(0,0,0,0.04);
    }}
    .metric .num {{ font-size: 24px; font-weight: 700; }}
    table {{
      width: 100%;
      border-collapse: collapse;
      background: white;
      border: 1px solid #d9e2ec;
      margin-bottom: 22px;
    }}
    th, td {{
      border-bottom: 1px solid #e5e7eb;
      padding: 8px;
      text-align: left;
      font-size: 13px;
      vertical-align: top;
    }}
    th {{ background: #eef2f7; }}
    .rec-head {{
      display: flex;
      justify-content: space-between;
      gap: 16px;
      align-items: flex-start;
    }}
    .value {{
      font-size: 16px;
      font-weight: 600;
      margin-top: 4px;
    }}
    .badges span {{
      display: inline-block;
      background: #eef2f7;
      border: 1px solid #d9e2ec;
      border-radius: 999px;
      padding: 3px 8px;
      margin-left: 4px;
      font-size: 12px;
    }}
    .recommendation {{ margin-bottom: 12px; }}
    details.recommendation {{
      margin-bottom: 12px;
    }}
    details.recommendation > summary {{
      cursor: pointer;
      display: grid;
      grid-template-columns: 220px 1fr 120px;
      gap: 12px;
      align-items: center;
      list-style: none;
    }}
    details.recommendation > summary::-webkit-details-marker {{
      display: none;
    }}
    .summary-title {{
      font-weight: 700;
      font-size: 14px;
    }}
    .summary-value {{
      font-weight: 600;
      font-size: 14px;
    }}
    .summary-decision {{
      justify-self: end;
      border-radius: 999px;
      padding: 3px 8px;
      border: 1px solid #cbd5e1;
      background: #f8fafc;
      font-size: 12px;
      text-transform: uppercase;
    }}
    .decision-accept {{
      border-left: 5px solid #15803d;
    }}
    .decision-decline {{
      border-left: 5px solid #b91c1c;
    }}
    .decision-ignore {{
      border-left: 5px solid #64748b;
    }}
    .decision-defer {{
      border-left: 5px solid #b45309;
    }}
    .decision-pending {{
      border-left: 5px solid #2563eb;
    }}
    .discrepancy {{
      border-left: 5px solid #b45309;
      margin-bottom: 12px;
    }}
    .evidence {{
      margin: 10px 0;
      padding: 10px;
      background: #f8fafc;
      border: 1px solid #e5e7eb;
      border-radius: 8px;
    }}
    .snippet {{
      margin-top: 6px;
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      font-size: 12px;
      white-space: pre-wrap;
      color: #334155;
    }}
    .top-note {{
      background: #fff7ed;
      border: 1px solid #fed7aa;
      border-radius: 10px;
      padding: 10px 12px;
      margin: 14px 0;
      font-size: 13px;
    }}
  </style>
</head>
<body>
  <h1>Document Evidence Report — {package}</h1>
  <p class="muted">Generated: {generated_at}</p>
  <p class="muted">{note}</p>

  <div class="top-note">
    Standalone read-only report page. No metadata is updated from this page.
  </div>

  <div class="summary">
    <div class="metric"><div class="num">{_html_escape(summary.get('documents_scanned', 0))}</div><div>Documents scanned</div></div>
    <div class="metric"><div class="num">{_html_escape(summary.get('raw_observations', 0))}</div><div>Raw observations</div></div>
    <div class="metric"><div class="num">{_html_escape(summary.get('grouped_recommendations', 0))}</div><div>Recommendations</div></div>
    <div class="metric"><div class="num">{_html_escape(summary.get('discrepancy_count', 0))}</div><div>Discrepancies</div></div>
    <div class="metric"><div class="num">{_html_escape(decision_counts.get('pending', 0))}</div><div>Pending decisions</div></div>
    <div class="metric"><div class="num">{_html_escape(decision_counts.get('defer', 0))}</div><div>Deferred</div></div>
    <div class="metric"><div class="num">{_html_escape(decision_counts.get('accept', 0))}</div><div>Accepted</div></div>
    <div class="metric"><div class="num">{_html_escape(decision_counts.get('decline', 0) + decision_counts.get('ignore', 0))}</div><div>Declined / ignored</div></div>
  </div>

  <h2>Documents scanned</h2>
  <table>
    <thead>
      <tr>
        <th>Document</th>
        <th>Type</th>
        <th>Extractor</th>
        <th>Pages</th>
        <th>Text chars</th>
        <th>Status</th>
      </tr>
    </thead>
    <tbody>
      {''.join(doc_rows)}
    </tbody>
  </table>

  <h2>Discrepancies</h2>
  {''.join(discrepancy_blocks) if discrepancy_blocks else '<p>No discrepancies identified.</p>'}

  <h2>Recommended actions</h2>
  {''.join(rec_blocks) if rec_blocks else '<p>No recommendations identified.</p>'}

<script>
async function recordDecision(packageId, recommendationId, decision) {{
  const reason = window.prompt("Reason for decision:", "");
  if (reason === null) {{
    return;
  }}

  const url = "/api/document-evidence/packages/"
    + encodeURIComponent(packageId)
    + "/recommendations/"
    + encodeURIComponent(recommendationId)
    + "/decision";

  const response = await fetch(url, {{
    method: "POST",
    headers: {{"Content-Type": "application/json"}},
    body: JSON.stringify({{
      decision: decision,
      reason: reason,
      decided_by: "local_user"
    }})
  }});

  const data = await response.json();

  if (!response.ok || !data.ok) {{
    alert("Decision was not recorded: " + JSON.stringify(data));
    return;
  }}

  alert("Decision recorded. No metadata was updated.");
  window.location.reload();
}}
</script>

</body>
</html>"""



@router.get("/packages/{package_id}/report", response_class=HTMLResponse)
def get_package_document_evidence_report(package_id: str):
    """Return a standalone, browser-readable, read-only document evidence report."""
    data = build_package_document_evidence(package_id)
    data["stored_decisions"] = load_recommendation_decisions(package_id)
    return _render_document_evidence_report(data)



@router.post("/packages/{package_id}/recommendations/{recommendation_id}/decision")
def post_recommendation_decision(
    package_id: str,
    recommendation_id: str,
    payload: RecommendationDecisionRequest,
):
    """Record accept/decline/ignore/defer decision without updating metadata."""
    return record_recommendation_decision(
        package_id=package_id,
        recommendation_id=recommendation_id,
        decision=payload.decision,
        reason=payload.reason,
        decided_by=payload.decided_by,
    )



@router.get("/packages/{package_id}/metadata-update-plan")
def get_metadata_update_plan(package_id: str):
    """Return a dry-run metadata update plan from accepted recommendations.

    This does not update metadata.
    """
    return build_metadata_update_plan(package_id)



def _render_metadata_update_plan_report(plan):
    package = _html_escape(plan.get("package", ""))
    generated_at = _html_escape(plan.get("generated_at", ""))
    note = _html_escape(plan.get("note", ""))
    summary = plan.get("summary", {})
    accepted = plan.get("accepted_updates", [])
    excluded = plan.get("excluded_decisions", [])

    accepted_blocks = []
    for u in accepted:
        sources_html = "".join(
            f"<li>{_html_escape(s)}</li>"
            for s in u.get("sources", [])
        )

        accepted_blocks.append(f"""
        <section class="card accepted">
          <h3>{_html_escape(u.get('recommendation_id', ''))}: {_html_escape(u.get('field', ''))}</h3>
          <p class="value">{_html_escape(u.get('proposed_value', ''))}</p>
          <p><strong>Status:</strong> {_html_escape(u.get('status', ''))}</p>
          <p><strong>Confidence:</strong> {_html_escape(u.get('confidence', ''))} |
             <strong>Severity:</strong> {_html_escape(u.get('severity', ''))}</p>
          <p><strong>Decision reason:</strong> {_html_escape(u.get('decision_reason', ''))}</p>
          <p><strong>Decided at:</strong> {_html_escape(u.get('decided_at', ''))}</p>
          <details>
            <summary>Sources</summary>
            <ul>{sources_html}</ul>
          </details>
        </section>
        """)

    excluded_rows = []
    for x in excluded:
        excluded_rows.append(f"""
        <tr>
          <td>{_html_escape(x.get('recommendation_id', ''))}</td>
          <td>{_html_escape(x.get('field', ''))}</td>
          <td>{_html_escape(x.get('proposed_value', ''))}</td>
          <td>{_html_escape(x.get('decision', ''))}</td>
          <td>{_html_escape(x.get('decision_reason', ''))}</td>
        </tr>
        """)

    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>Metadata Update Plan — {package}</title>
  <style>
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      margin: 24px;
      background: #f7f7f7;
      color: #1f2933;
    }}
    h1, h2, h3 {{ margin-bottom: 6px; }}
    .muted {{ color: #64748b; font-size: 13px; }}
    .warning {{
      background: #fff7ed;
      border: 1px solid #fed7aa;
      border-radius: 10px;
      padding: 10px 12px;
      margin: 14px 0;
      font-size: 13px;
      font-weight: 600;
    }}
    .summary {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 12px;
      margin: 18px 0;
    }}
    .metric, .card {{
      background: white;
      border: 1px solid #d9e2ec;
      border-radius: 10px;
      padding: 12px;
      box-shadow: 0 1px 2px rgba(0,0,0,0.04);
    }}
    .metric .num {{ font-size: 24px; font-weight: 700; }}
    .accepted {{
      border-left: 5px solid #15803d;
      margin-bottom: 12px;
    }}
    .value {{
      font-size: 16px;
      font-weight: 700;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      background: white;
      border: 1px solid #d9e2ec;
      margin-bottom: 22px;
    }}
    th, td {{
      border-bottom: 1px solid #e5e7eb;
      padding: 8px;
      text-align: left;
      font-size: 13px;
      vertical-align: top;
    }}
    th {{ background: #eef2f7; }}
  </style>
</head>
<body>
  <h1>Metadata Update Plan — {package}</h1>
  <p class="muted">Generated: {generated_at}</p>
  <p class="muted">{note}</p>

  <div class="warning">
    Dry-run page only. No metadata is updated from this page.
  </div>

  <div class="summary">
    <div class="metric"><div class="num">{_html_escape(plan.get('accepted_update_count', 0))}</div><div>Accepted updates</div></div>
    <div class="metric"><div class="num">{_html_escape(summary.get('stored_decision_count', 0))}</div><div>Stored decisions</div></div>
    <div class="metric"><div class="num">{_html_escape(summary.get('accepted', 0))}</div><div>Accepted</div></div>
    <div class="metric"><div class="num">{_html_escape(summary.get('deferred', 0))}</div><div>Deferred</div></div>
    <div class="metric"><div class="num">{_html_escape(summary.get('declined', 0) + summary.get('ignored', 0))}</div><div>Declined / ignored</div></div>
  </div>

  <h2>Accepted updates ready for later apply step</h2>
  {''.join(accepted_blocks) if accepted_blocks else '<p>No accepted recommendations are currently in the update plan.</p>'}

  <h2>Excluded decisions</h2>
  <table>
    <thead>
      <tr>
        <th>Recommendation</th>
        <th>Field</th>
        <th>Proposed value</th>
        <th>Decision</th>
        <th>Reason</th>
      </tr>
    </thead>
    <tbody>
      {''.join(excluded_rows)}
    </tbody>
  </table>
</body>
</html>"""



@router.get("/packages/{package_id}/metadata-update-plan/report", response_class=HTMLResponse)
def get_metadata_update_plan_report(package_id: str):
    """Return a standalone dry-run metadata update plan report.

    This does not update metadata.
    """
    plan = build_metadata_update_plan(package_id)
    return _render_metadata_update_plan_report(plan)



@router.post("/packages/{package_id}/metadata-update-plan/apply-preview")
def post_metadata_apply_preview(package_id: str):
    """Return a controlled dry-run apply preview for accepted recommendations.

    This does not update metadata.
    """
    return build_metadata_apply_preview(package_id)



def _render_metadata_apply_preview_report(preview):
    package = _html_escape(preview.get("package", ""))
    generated_at = _html_escape(preview.get("generated_at", ""))
    note = _html_escape(preview.get("note", ""))
    summary = preview.get("summary", {})
    updates = preview.get("preview_updates", [])
    blocked = preview.get("blocked_updates", [])

    update_blocks = []
    for u in updates:
        source_items = "".join(
            f"<li>{_html_escape(s)}</li>"
            for s in u.get("sources", [])
        )

        current_value = u.get("current_value")
        if current_value is None:
            current_value = "(missing / not found in current metadata context)"

        update_blocks.append(f"""
        <section class="card allowed">
          <h3>{_html_escape(u.get('recommendation_id', ''))}: {_html_escape(u.get('field', ''))}</h3>
          <div class="compare">
            <div>
              <div class="label">Current value</div>
              <div class="current">{_html_escape(current_value)}</div>
            </div>
            <div>
              <div class="label">Proposed value</div>
              <div class="proposed">{_html_escape(u.get('proposed_value', ''))}</div>
            </div>
          </div>
          <p><strong>Status:</strong> {_html_escape(u.get('apply_status', ''))}</p>
          <p><strong>Confidence:</strong> {_html_escape(u.get('confidence', ''))} |
             <strong>Severity:</strong> {_html_escape(u.get('severity', ''))}</p>
          <p><strong>Decision reason:</strong> {_html_escape(u.get('decision_reason', ''))}</p>
          <p><strong>Evidence count:</strong> {_html_escape(u.get('evidence_count', ''))} |
             <strong>Source count:</strong> {_html_escape(u.get('source_count', ''))}</p>
          <details>
            <summary>Sources</summary>
            <ul>{source_items}</ul>
          </details>
        </section>
        """)

    blocked_rows = []
    for b in blocked:
        blocked_rows.append(f"""
        <tr>
          <td>{_html_escape(b.get('recommendation_id', ''))}</td>
          <td>{_html_escape(b.get('field', ''))}</td>
          <td>{_html_escape(b.get('proposed_value', ''))}</td>
          <td>{_html_escape(b.get('apply_status', ''))}</td>
        </tr>
        """)

    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>Metadata Apply Preview — {package}</title>
  <style>
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      margin: 24px;
      background: #f7f7f7;
      color: #1f2933;
    }}
    h1, h2, h3 {{ margin-bottom: 6px; }}
    .muted {{ color: #64748b; font-size: 13px; }}
    .warning {{
      background: #fff7ed;
      border: 1px solid #fed7aa;
      border-radius: 10px;
      padding: 10px 12px;
      margin: 14px 0;
      font-size: 13px;
      font-weight: 600;
    }}
    .summary {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 12px;
      margin: 18px 0;
    }}
    .metric, .card {{
      background: white;
      border: 1px solid #d9e2ec;
      border-radius: 10px;
      padding: 12px;
      box-shadow: 0 1px 2px rgba(0,0,0,0.04);
    }}
    .metric .num {{ font-size: 24px; font-weight: 700; }}
    .allowed {{
      border-left: 5px solid #15803d;
      margin-bottom: 12px;
    }}
    .compare {{
      display: grid;
      grid-template-columns: minmax(220px, 1fr) minmax(220px, 1fr);
      gap: 12px;
      margin: 10px 0;
    }}
    .label {{
      font-size: 12px;
      color: #64748b;
      margin-bottom: 4px;
      text-transform: uppercase;
      letter-spacing: 0.03em;
    }}
    .current, .proposed {{
      border: 1px solid #d9e2ec;
      border-radius: 8px;
      padding: 10px;
      background: #f8fafc;
      font-weight: 600;
      min-height: 22px;
    }}
    .proposed {{
      background: #ecfdf5;
      border-color: #bbf7d0;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      background: white;
      border: 1px solid #d9e2ec;
      margin-bottom: 22px;
    }}
    th, td {{
      border-bottom: 1px solid #e5e7eb;
      padding: 8px;
      text-align: left;
      font-size: 13px;
      vertical-align: top;
    }}
    th {{ background: #eef2f7; }}
  </style>
</head>
<body>
  <h1>Metadata Apply Preview — {package}</h1>
  <p class="muted">Generated: {generated_at}</p>
  <p class="muted">{note}</p>

  <div class="warning">
    Preview only. This page shows what would be eligible for a later controlled apply step. No metadata is updated from this page.
  </div>

  <div class="summary">
    <div class="metric"><div class="num">{_html_escape(preview.get('preview_update_count', 0))}</div><div>Preview updates</div></div>
    <div class="metric"><div class="num">{_html_escape(preview.get('blocked_update_count', 0))}</div><div>Blocked updates</div></div>
    <div class="metric"><div class="num">{_html_escape(summary.get('accepted_update_count', 0))}</div><div>Accepted recommendations</div></div>
    <div class="metric"><div class="num">{_html_escape(summary.get('stored_decision_count', 0))}</div><div>Stored decisions</div></div>
  </div>

  <h2>Allowed preview updates</h2>
  {''.join(update_blocks) if update_blocks else '<p>No accepted recommendations are currently eligible for apply preview.</p>'}

  <h2>Blocked updates</h2>
  <table>
    <thead>
      <tr>
        <th>Recommendation</th>
        <th>Field</th>
        <th>Proposed value</th>
        <th>Status</th>
      </tr>
    </thead>
    <tbody>
      {''.join(blocked_rows)}
    </tbody>
  </table>
</body>
</html>"""



@router.get("/packages/{package_id}/metadata-update-plan/apply-preview/report", response_class=HTMLResponse)
def get_metadata_apply_preview_report(package_id: str):
    """Return a standalone controlled metadata apply-preview report.

    This does not update metadata.
    """
    preview = build_metadata_apply_preview(package_id)
    return _render_metadata_apply_preview_report(preview)



@router.get("/packages/{package_id}/review-bundle")
def get_document_evidence_review_bundle(package_id: str):
    """Return a consolidated standalone review bundle.

    This does not update metadata and does not link to the app database.
    """
    return build_document_evidence_review_bundle(package_id)



@router.post("/packages/{package_id}/review-bundle/export")
def post_document_evidence_review_bundle_export(package_id: str):
    """Export the consolidated review bundle to the package folder.

    This does not update metadata and does not link to the app database.
    """
    return export_document_evidence_review_bundle(package_id)



@router.get("/packages/{package_id}/text-cache/status")
def get_package_document_text_cache_status(package_id: str):
    """Return read-only package-local document text cache status.

    This does not extract text, update metadata, or link to the app database.
    """
    return get_document_text_cache_status(package_id)



def _render_document_evidence_package_index(index):
    packages = index.get("packages", [])

    rows = []
    for p in packages:
        links = p.get("links", {})
        package = _html_escape(p.get("package", ""))

        rows.append(f"""
        <tr>
          <td><strong>{package}</strong></td>
          <td>{_html_escape(p.get('document_count', ''))}</td>
          <td>{_html_escape(p.get('cache_hits_possible', ''))}</td>
          <td>{_html_escape(p.get('missing_or_stale_count', ''))}</td>
          <td>{_html_escape(p.get('grouped_recommendations', ''))}</td>
          <td>{_html_escape(p.get('discrepancy_count', ''))}</td>
          <td>{_html_escape(p.get('database_link_status', ''))}</td>
          <td>{_html_escape(p.get('target_status', ''))}</td>
          <td>{_html_escape(p.get('apply_allowed', ''))}</td>
          <td class="links">
            <a href="{_html_escape(links.get('evidence_report', '#'))}">Evidence report</a>
            <a href="{_html_escape(links.get('review_bundle_json', '#'))}">Review bundle JSON</a>
            <a href="{_html_escape(links.get('apply_preview_report', '#'))}">Apply preview</a>
            <a href="{_html_escape(links.get('text_cache_status', '#'))}">Cache status</a>
          </td>
        </tr>
        """)

    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>Document Evidence Package Index</title>
  <style>
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      margin: 24px;
      background: #f7f7f7;
      color: #1f2933;
    }}
    h1 {{ margin-bottom: 6px; }}
    .muted {{ color: #64748b; font-size: 13px; }}
    .warning {{
      background: #fff7ed;
      border: 1px solid #fed7aa;
      border-radius: 10px;
      padding: 10px 12px;
      margin: 14px 0;
      font-size: 13px;
      font-weight: 600;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      background: white;
      border: 1px solid #d9e2ec;
      margin-top: 16px;
    }}
    th, td {{
      border-bottom: 1px solid #e5e7eb;
      padding: 8px;
      text-align: left;
      font-size: 13px;
      vertical-align: top;
    }}
    th {{ background: #eef2f7; }}
    .links a {{
      display: block;
      margin-bottom: 4px;
      color: #0f766e;
      text-decoration: none;
      font-weight: 600;
    }}
  </style>
</head>
<body>
  <h1>Document Evidence Package Index</h1>
  <p class="muted">Generated: {_html_escape(index.get('generated_at', ''))}</p>
  <p class="muted">Packages: {_html_escape(index.get('package_count', 0))}</p>

  <div class="warning">
    Standalone document-evidence utility only. This page does not update metadata and does not link packages to application volumes or the app database.
  </div>

  <table>
    <thead>
      <tr>
        <th>Package</th>
        <th>Docs</th>
        <th>Cache hits</th>
        <th>Stale/missing</th>
        <th>Recommendations</th>
        <th>Discrepancies</th>
        <th>DB link</th>
        <th>Target status</th>
        <th>Apply allowed</th>
        <th>Links</th>
      </tr>
    </thead>
    <tbody>
      {''.join(rows)}
    </tbody>
  </table>
</body>
</html>"""



@router.get("/package-index")
def get_document_evidence_package_index():
    """Return a compact JSON index of staged document-evidence packages.

    This does not update metadata and does not link to the app database.
    """
    return list_document_evidence_package_index()


@router.get("/package-index/report", response_class=HTMLResponse)
def get_document_evidence_package_index_report():
    """Return a standalone HTML index of staged document-evidence packages.

    This does not update metadata and does not link to the app database.
    """
    index = list_document_evidence_package_index()
    return _render_document_evidence_package_index(index)
