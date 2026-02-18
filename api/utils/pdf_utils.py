from datetime import datetime
import re
from html import escape
from typing import Any, Dict, List, Optional

from weasyprint import HTML


def model_label_from_id(model_id: str) -> str:
    lower = str(model_id or "").lower()
    if lower.startswith("gpt-") or lower.startswith("o-"):
        return "OpenAI"
    if lower.startswith("gemini-"):
        return "Google Gemini"
    if lower.startswith("deepseek-"):
        return "Deepseek"
    if lower.startswith("grok-"):
        return "Grok"
    return "Model"


def format_display_datetime(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        # Best-effort cleanup for non-ISO strings.
        cleaned = text.replace("T", " ")
        cleaned = re.sub(r"\.\d+", "", cleaned)
        cleaned = re.sub(r"(Z|[+-]\d{2}:?\d{2})$", "", cleaned)
        return cleaned.strip()


def create_report_html(data: Any) -> str:
    def friendly_model_label(model_id: str) -> str:
        return model_label_from_id(model_id)

    left_brand = "IdeaGen"
    right_title = "Business Idea Generation Report"
    right_date = datetime.now().strftime("%a, %B %d, %Y")

    chips_html = ", ".join(
        f'<span class="chip">{escape(friendly_model_label(m))}</span>'
        for m in data.models
    )

    results_parts = []
    for idx, model_id in enumerate(data.models, start=1):
        result_content = data.results.get(model_id, "<p>No result generated.</p>")
        model_display_name = escape(friendly_model_label(model_id))

        results_parts.append(f"""
        <section class="model">
          <div class="model-head">
            <div class="model-no">{idx}.</div>
            <div class="model-title">{model_display_name}</div>
          </div>
          <div class="model-body">
            {result_content}
          </div>
        </section>
        """)

    results_html = "\n".join(results_parts)

    rank_result = data.rank_result if isinstance(getattr(data, "rank_result", None), dict) else None
    rank_section_html = ""
    if rank_result:
        if rank_result.get("skipped"):
            rank_note = escape(str(rank_result.get("reason") or "Ranking not available for a single model."))
            rank_section_html = f"""
            <section class="rank">
              <div class="rank-title">Model ranking</div>
              <div class="rank-sub">Automatic ranking for this run based on clarity, feasibility, differentiation, actionability, risks, and stakeholder readiness.</div>
              <div class="rank-note">{rank_note}</div>
            </section>
            """
        else:
            summary = escape(str(rank_result.get("summary", "") or ""))
            highlights = rank_result.get("highlights") if isinstance(rank_result.get("highlights"), list) else []
            ranked_models = rank_result.get("ranked_models") if isinstance(rank_result.get("ranked_models"), list) else []
            title_map = rank_result.get("title_map") if isinstance(rank_result.get("title_map"), dict) else {}

            highlights_html = ""
            if highlights:
                items = "\n".join(f"<li>{escape(str(item))}</li>" for item in highlights if str(item).strip())
                highlights_html = f"""
                <div class="rank-block">
                  <div class="rank-block-title">Highlights</div>
                  <ul class="rank-list">
                    {items}
                  </ul>
                </div>
                """

            ranked_models_sorted = sorted(
                ranked_models,
                key=lambda item: (item or {}).get("rank") or 0,
            )
            rank_items = []
            for item in ranked_models_sorted:
                model_id = str((item or {}).get("model_id", "")).strip()
                model_label = friendly_model_label(model_id)
                title = (item or {}).get("title") or title_map.get(model_id) or model_label
                rationale = (item or {}).get("rationale")
                score = (item or {}).get("score")
                score_html = f" - Score {escape(str(score))}" if isinstance(score, (int, float)) else ""
                rationale_html = f'<div class="rank-item-body">{escape(str(rationale))}</div>' if rationale else ""
                rank_items.append(f"""
                <div class="rank-item">
                  <div class="rank-item-title">{escape(str((item or {}).get("rank") or ""))}. {escape(str(title))}</div>
                  <div class="rank-item-meta">Model: {escape(model_label)}{score_html}</div>
                  {rationale_html}
                </div>
                """)
            ranked_html = ""
            if rank_items:
                ranked_html = f"""
                <div class="rank-block">
                  <div class="rank-block-title">Ranked outputs</div>
                  {''.join(rank_items)}
                </div>
                """

            rank_section_html = f"""
            <section class="rank">
              <div class="rank-title">Model ranking</div>
              <div class="rank-sub">Automatic ranking for this run based on clarity, feasibility, differentiation, actionability, risks, and stakeholder readiness.</div>
              {f'<div class="rank-summary">{summary}</div>' if summary else ''}
              {highlights_html}
              {ranked_html}
            </section>
            """

    return f"""<!doctype html>
        <html>
        <head>
        <meta charset="utf-8" />
        <title>Business Idea Generation Report</title>
        <style>
            @page {{
            size: A4;
            margin: 0.75in;
            }}

            :root {{
            --ink: #111827;
            --muted: #6B7280;
            --line: #E5E7EB;
            --accent: #1F4E79;
            }}

            body {{
            font-family: Helvetica, Arial, sans-serif;
            font-size: 10.6pt;
            color: var(--ink);
            line-height: 1.45;
            }}

            /* ===== Header ===== */
            .header {{
            padding-bottom: 10px;
            border-bottom: 2px solid var(--accent);
            margin-bottom: 12px;
            }}

            .hdr-row {{
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            gap: 12px;
            }}

            .brand {{
            font-weight: 700;
            font-size: 12pt;
            white-space: nowrap;
            }}

            .hdr-right {{
            text-align: right;
            }}

            .hdr-title {{
            font-weight: 700;
            font-size: 10.8pt;
            margin: 0;
            }}

            .hdr-date {{
            margin-top: 3px;
            font-size: 9.4pt;
            color: var(--muted);
            }}

            /* ===== Config ===== */
            .config {{
            margin-bottom: 14px;
            }}

            table.config-table {{
            width: 100%;
            border-collapse: collapse;
            table-layout: fixed;
            }}

            table.config-table col.label-col {{ width: 30%; }}
            table.config-table col.value-col {{ width: 70%; }}

            table.config-table tr {{
            border-bottom: 1px solid var(--line);
            }}

            table.config-table td {{
            padding: 7px 0;
            vertical-align: middle;
            }}

            .cfg-label {{
            color: var(--muted);
            font-size: 9.2pt;
            }}

            .cfg-value {{
            font-weight: 700;
            word-wrap: break-word;
            overflow-wrap: anywhere;
            }}

            .chip {{
            display: inline-block;
            padding: 2px 7px;
            border: 1px solid var(--line);
            border-radius: 999px;
            font-weight: 700;
            font-size: 9.4pt;
            margin: 1px 5px 1px 0;
            background: #fff;
            color: var(--ink);
            white-space: nowrap;
            }}

            /* ===== Model Sections ===== */
            .model {{
            margin-top: 12px;
            page-break-inside: avoid;
            }}

            .model-head {{
            display: flex;
            gap: 8px;
            align-items: baseline;
            margin: 0 0 6px 0;
            page-break-after: avoid;
            }}

            .model-no {{
            font-weight: 700;
            color: var(--ink);
            }}

            .model-title {{
            font-weight: 700;
            color: var(--accent);
            letter-spacing: 0.2px;
            text-transform: uppercase;
            }}

            .model-body {{
            margin-left: 18px;
            }}

            /* ===== Ranking ===== */
            .rank {{
            margin: 14px 0 16px 0;
            padding: 6px 0 10px 0;
            border-bottom: 1px solid var(--line);
            }}

            .rank-title {{
            font-weight: 700;
            font-size: 11pt;
            }}

            .rank-sub {{
            font-size: 9.2pt;
            color: var(--muted);
            margin-top: 2px;
            }}

            .rank-summary {{
            margin-top: 6px;
            }}

            .rank-note {{
            margin-top: 6px;
            color: var(--muted);
            }}

            .rank-block {{
            margin-top: 8px;
            }}

            .rank-block-title {{
            font-weight: 700;
            margin-bottom: 4px;
            }}

            .rank-list {{
            margin: 0 0 0 16px;
            padding: 0;
            }}

            .rank-item {{
            margin-top: 8px;
            page-break-inside: avoid;
            }}

            .rank-item-title {{
            font-weight: 700;
            }}

            .rank-item-meta {{
            font-size: 9.2pt;
            color: var(--muted);
            margin-top: 2px;
            }}

            .rank-item-body {{
            margin-top: 4px;
            }}

            /* ===== Content Normalization (LLM HTML) ===== */
            h1, h2, h3 {{
            margin: 10px 0 6px 0;
            page-break-after: avoid;
            }}

            p {{
            margin: 0 0 7px 0;
            }}

            ul {{
            margin: 0 0 7px 16px;
            padding: 0;
            }}

            li {{
            margin: 0 0 4px 0;
            }}

            a {{
            color: var(--ink);
            text-decoration: underline;
            }}
        </style>
        </head>

        <body>
        <div class="header">
            <div class="hdr-row">
            <div class="brand">{escape(left_brand)}</div>
            <div class="hdr-right">
                <div class="hdr-title">{escape(right_title)}</div>
                <div class="hdr-date">{escape(right_date)}</div>
            </div>
            </div>
        </div>

        <div class="config">
            <table class="config-table">
            <colgroup>
                <col class="label-col" />
                <col class="value-col" />
            </colgroup>
            <tr>
                <td class="cfg-label">Target Industry</td>
                <td class="cfg-value">{escape(data.industry)}</td>
            </tr>
            <tr>
                <td class="cfg-label">Constraint</td>
                <td class="cfg-value">{escape(data.constraints_text)}</td>
            </tr>
            <tr>
                <td class="cfg-label">AI Persona</td>
                <td class="cfg-value">{escape(data.tone)}</td>
            </tr>
            <tr>
                <td class="cfg-label">Models Selected</td>
                <td class="cfg-value">{chips_html}</td>
            </tr>
            </table>
        </div>

        {rank_section_html}

        {results_html}

        </body>
        </html>
        """


def create_rank_report_html(
    runs: List[Dict[str, Any]],
    report: Dict[str, Any],
) -> str:
    def friendly_model_label(model_id: Any) -> str:
        return model_label_from_id(str(model_id or ""))

    title_re = re.compile(r"<h[1-3][^>]*>(.*?)</h[1-3]>", re.IGNORECASE | re.DOTALL)
    tag_re = re.compile(r"<[^>]+>")

    def strip_html(value: str) -> str:
        if not value:
            return ""
        return re.sub(r"\s+", " ", tag_re.sub(" ", value)).strip()

    def extract_title(value: str) -> str:
        if not value:
            return "Untitled result"
        match = title_re.search(value)
        title = strip_html(match.group(1)) if match else strip_html(value)
        if title:
            lower = title.lower()
            for marker in ("title:", "idea:", "concept:"):
                idx = lower.find(marker)
                if idx != -1:
                    snippet = title[idx + len(marker):].strip()
                    if snippet:
                        title = snippet
                        break
        if not title:
            return "Untitled result"
        if len(title) > 80:
            return title[:77].rstrip() + "..."
        return title

    summary = escape(str(report.get("summary", "") or ""))
    ranked_runs = report.get("ranked_runs", []) or []
    key_insights = report.get("key_insights", []) or []
    risks = report.get("risks", []) or []
    next_steps = report.get("next_steps", []) or []

    def run_label(run: Dict[str, Any]) -> str:
        industry = run.get("industry") or "Saved run"
        created_at = run.get("created_at") or ""
        return f"{industry} ({created_at})"

    ranked_html = ""
    if ranked_runs:
        rows = []
        for item in ranked_runs:
            run_id = item.get("run_id")
            score = item.get("score", "")
            rationale = escape(str(item.get("rationale", "") or ""))
            run = next((r for r in runs if r.get("id") == run_id), {})
            results = run.get("results") or {}
            rank_result = run.get("rank_result") if isinstance(run.get("rank_result"), dict) else {}
            title_map = rank_result.get("title_map") if isinstance(rank_result.get("title_map"), dict) else {}
            model_ids = run.get("models") or list(results.keys())
            outputs_list = []
            for model_id in model_ids:
                mid = str(model_id or "").strip()
                if not mid:
                    continue
                model_label = friendly_model_label(mid)
                title = str(title_map.get(mid) or "")
                if not title:
                    title = extract_title(str(results.get(mid) or ""))
                outputs_list.append(f"{escape(model_label)} - {escape(title or 'Untitled result')}")
            outputs_html = "<br/>".join(outputs_list) if outputs_list else "—"
            persona = escape(str(run.get("tone") or "Not specified"))
            constraints = run.get("constraints") or []
            constraints_text = escape(", ".join([str(c) for c in constraints if str(c).strip()]) or "None")
            persona_html = f"Persona: {persona}<br/>Constraints: {constraints_text}"
            rows.append(
                "<tr>"
                f"<td class='col-run'>{escape(run_label(run))}</td>"
                f"<td class='col-persona'>{persona_html}</td>"
                f"<td class='col-outputs'>{outputs_html}</td>"
                f"<td class='col-score'>{score}</td>"
                f"<td class='col-rationale'>{rationale}</td>"
                "</tr>"
            )
        ranked_html = (
            "<table class='rank-table'>"
            "<tr>"
            "<th class='col-run'>Run</th>"
            "<th class='col-persona'>Persona / Constraints</th>"
            "<th class='col-outputs'>Outputs</th>"
            "<th class='col-score'>Score</th>"
            "<th class='col-rationale'>Rationale</th>"
            "</tr>"
            + "".join(rows)
            + "</table>"
        )

    def list_html(items: List[str]) -> str:
        if not items:
            return "<p class='muted'>None</p>"
        return "<ul>" + "".join(f"<li>{escape(str(i))}</li>" for i in items) + "</ul>"

    run_sections = []
    for run in runs:
        constraints = run.get("constraints") or []
        models = run.get("models") or list((run.get("results") or {}).keys())
        display_models = [friendly_model_label(m) for m in models]
        results = run.get("results") or {}
        results_html = ""
        for model_id, html in results.items():
            model_label = friendly_model_label(model_id)
            title = extract_title(str(html or ""))
            results_html += (
                "<div class='result-card'>"
                f"<div class='result-title'>{escape(model_label)} - {escape(title)}</div>"
                f"<div class='result-body'>{html}</div>"
                "</div>"
            )
        run_sections.append(
            "<section class='run-block'>"
            f"<h3>{escape(run_label(run))}</h3>"
            "<table class='config-table'>"
            "<tr><td class='cfg-label'>Industry</td>"
            f"<td class='cfg-value'>{escape(str(run.get('industry') or ''))}</td></tr>"
            "<tr><td class='cfg-label'>Persona</td>"
            f"<td class='cfg-value'>{escape(str(run.get('tone') or ''))}</td></tr>"
            "<tr><td class='cfg-label'>Constraints</td>"
            f"<td class='cfg-value'>{escape(', '.join(constraints) if constraints else 'None')}</td></tr>"
            "<tr><td class='cfg-label'>Models</td>"
            f"<td class='cfg-value'>{escape(', '.join(display_models) if display_models else 'None')}</td></tr>"
            "</table>"
            f"{results_html}"
            "</section>"
        )

    return f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8" />
      <style>
        body {{
          font-family: Arial, sans-serif;
          font-size: 13px;
          color: #111;
        }}
        h1 {{ font-size: 20px; margin-bottom: 6px; }}
        h2 {{ font-size: 16px; margin: 18px 0 8px; }}
        h3 {{ font-size: 14px; margin: 16px 0 6px; }}
        .muted {{ color: #666; }}
        .summary {{
          padding: 10px;
          background: #f4f6ff;
          border: 1px solid #e4e8ff;
          border-radius: 8px;
        }}
        .rank-table {{
          width: 100%;
          border-collapse: collapse;
          table-layout: fixed;
        }}
        .rank-table th, .rank-table td {{
          border: 1px solid #e5e7eb;
          padding: 6px;
          text-align: left;
          vertical-align: top;
          word-break: break-word;
          overflow-wrap: anywhere;
        }}
        .rank-table th, .rank-table td {{
          font-size: 12px;
        }}
        .rank-table .col-run {{ width: 16%; }}
        .rank-table .col-persona {{ width: 24%; }}
        .rank-table .col-outputs {{ width: 28%; }}
        .rank-table .col-score {{ width: 8%; }}
        .rank-table .col-rationale {{ width: 24%; }}
        .config-table {{
          width: 100%;
          border-collapse: collapse;
          margin-bottom: 10px;
        }}
        .config-table td {{
          border: 1px solid #e5e7eb;
          padding: 6px;
          vertical-align: top;
        }}
        .cfg-label {{ width: 140px; font-weight: 600; background: #fafafa; }}
        .result-card {{
          border: 1px solid #e5e7eb;
          border-radius: 8px;
          padding: 8px;
          margin-bottom: 8px;
        }}
        .result-title {{ font-weight: 700; margin-bottom: 4px; }}
        .result-body {{ font-size: 11px; color: #222; }}
      </style>
    </head>
    <body>
      <h1>IdeaGen Decision Summary Report</h1>
      <div class="summary">
        <strong>Summary</strong>
        <p>{summary}</p>
      </div>

      <h2>Ranking</h2>
      {ranked_html or "<p class='muted'>No ranking available.</p>"}

      <h2>Key insights</h2>
      {list_html(key_insights)}

      <h2>Risks</h2>
      {list_html(risks)}

      <h2>Next steps</h2>
      {list_html(next_steps)}

      <h2>Runs</h2>
      {''.join(run_sections)}
    </body>
    </html>
    """


def create_compare_report_html(
    comparison: Dict[str, Any],
    run_a_id: int,
    run_b_id: int,
    created_at: Optional[str] = None,
    config: Optional[Dict[str, Any]] = None,
) -> str:
    summary = escape(str(comparison.get("summary", "") or ""))
    winner = str(comparison.get("winner", "tie")).upper()
    winner_label = "Tie"
    if winner == "A":
        winner_label = "Run A"
    elif winner == "B":
        winner_label = "Run B"

    key_changes = comparison.get("key_changes") if isinstance(comparison.get("key_changes"), list) else []
    risks = comparison.get("risks") if isinstance(comparison.get("risks"), list) else []
    rationale = escape(str(comparison.get("winner_rationale", "") or ""))
    top_outputs = comparison.get("top_outputs") if isinstance(comparison.get("top_outputs"), dict) else {}
    top_a = top_outputs.get("run_a") if isinstance(top_outputs.get("run_a"), dict) else {}
    top_b = top_outputs.get("run_b") if isinstance(top_outputs.get("run_b"), dict) else {}

    def list_html(items: List[str]) -> str:
        if not items:
            return "<p class='muted'>None</p>"
        return "<ul>" + "".join(f"<li>{escape(str(i))}</li>" for i in items) + "</ul>"

    def output_block(label: str, item: Dict[str, Any], is_winner: bool) -> str:
        title = escape(str(item.get("title", "") or "Untitled result"))
        model_label = escape(str(item.get("model_label", "") or "Model"))
        output_html = item.get("output_html") or "<p class='muted'>No output available.</p>"
        winner_badge = "<span class='winner-pill'>Winner</span>" if is_winner else ""
        winner_banner = f"<div class='winner-banner'>{winner_badge}</div>" if is_winner else ""
        winner_class = " winner" if is_winner else ""
        return f"""
        <section class="output-card{winner_class}">
          {winner_banner}
          <div class="output-title">{label}: {title} <span class="muted">({model_label})</span></div>
          <div class="output-body">{output_html}</div>
        </section>
        """

    created_text = escape(str(created_at or "").strip())
    created_html = f"<div class='meta'>Generated: {created_text}</div>" if created_text else ""

    criteria_html = ""
    if isinstance(config, dict):
        industry = escape(str(config.get("industry", "") or ""))
        persona = escape(str(config.get("persona", "") or ""))
        constraints = config.get("constraints") if isinstance(config.get("constraints"), list) else []
        constraints_text = escape(", ".join([str(c) for c in constraints if str(c).strip()]) or "None")
        if industry or persona or constraints:
            criteria_html = f"""
            <h2>Comparison criteria</h2>
            <table class="criteria-table">
              <tr><td class="criteria-label">Industry</td><td>{industry or "—"}</td></tr>
              <tr><td class="criteria-label">Persona</td><td>{persona or "—"}</td></tr>
              <tr><td class="criteria-label">Constraints</td><td>{constraints_text}</td></tr>
            </table>
            """

    winner_title = ""
    if winner == "A":
        winner_title = str(top_a.get("title") or "")
    elif winner == "B":
        winner_title = str(top_b.get("title") or "")
    winner_title_html = f" — {escape(winner_title)}" if winner_title else ""

    return f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8" />
      <style>
        body {{
          font-family: Arial, sans-serif;
          font-size: 12px;
          color: #111;
        }}
        h1 {{ font-size: 20px; margin-bottom: 6px; }}
        h2 {{ font-size: 16px; margin: 18px 0 8px; }}
        h3 {{ font-size: 14px; margin: 16px 0 6px; }}
        .muted {{ color: #666; }}
        .meta {{ color: #666; font-size: 11px; margin-bottom: 8px; }}
        .summary {{
          padding: 10px;
          background: #f4f6ff;
          border: 1px solid #e4e8ff;
          border-radius: 8px;
        }}
        .criteria-table {{
          width: 100%;
          border-collapse: collapse;
          margin-top: 6px;
        }}
        .criteria-table td {{
          border-bottom: 1px solid #e5e7eb;
          padding: 6px 0;
          vertical-align: top;
        }}
        .criteria-label {{
          width: 140px;
          color: #666;
          font-weight: 600;
        }}
        .outputs {{
          margin-top: 10px;
        }}
        .output-card {{
          border-radius: 8px;
          padding: 10px;
          margin-bottom: 10px;
          background: #f8fafc;
        }}
        .output-card.winner {{
          background: linear-gradient(90deg, #22c55e 0, #22c55e 6px, #dcfce7 6px, #ecfdf3 100%);
        }}
        .output-title {{
          font-weight: 700;
          margin-bottom: 6px;
        }}
        .winner-banner {{
          margin-bottom: 6px;
        }}
        .winner-pill {{
          display: inline-block;
          margin-left: 6px;
          padding: 2px 6px;
          font-size: 10px;
          font-weight: 800;
          color: #ffffff;
          background: #16a34a;
          border-radius: 999px;
          letter-spacing: 0.3px;
        }}
        .output-body {{
          font-size: 12px;
          color: #222;
        }}
      </style>
    </head>
    <body>
      <h1>IdeaGen Compare Report</h1>
      {created_html}

      <div class="summary">
        <strong>Winner</strong>
        <p>{winner_label}{winner_title_html} (A: {run_a_id} / B: {run_b_id})</p>
        <strong>Summary</strong>
        <p>{summary}</p>
      </div>

      {criteria_html}

      <h2>Key changes</h2>
      {list_html(key_changes)}

      <h2>Rationale</h2>
      <p>{rationale or "<span class='muted'>None</span>"}</p>

      <h2>Risks</h2>
      {list_html(risks)}

      <h2>Top outputs compared</h2>
      <div class="outputs">
        {output_block("Run A", top_a, winner == "A")}
        {output_block("Run B", top_b, winner == "B")}
      </div>
    </body>
    </html>
    """


def create_execution_plan_report_html(saved: Dict[str, Any]) -> str:
    dossier = saved.get("dossier") if isinstance(saved.get("dossier"), dict) else {}
    decision = dossier.get("decision") if isinstance(dossier.get("decision"), dict) else {}
    blueprint = dossier.get("execution_blueprint") if isinstance(dossier.get("execution_blueprint"), dict) else {}
    resources = dossier.get("resources") if isinstance(dossier.get("resources"), dict) else {}
    costs = dossier.get("costs") if isinstance(dossier.get("costs"), dict) else {}
    revenue_profit = dossier.get("revenue_profit") if isinstance(dossier.get("revenue_profit"), dict) else {}
    scenarios = dossier.get("scenarios") if isinstance(dossier.get("scenarios"), list) else []
    risks = dossier.get("risks") if isinstance(dossier.get("risks"), list) else []
    stakeholder_ask = dossier.get("stakeholder_ask") if isinstance(dossier.get("stakeholder_ask"), dict) else {}
    decision_support = dossier.get("decision_support") if isinstance(dossier.get("decision_support"), dict) else {}
    proposal_disclaimer = dossier.get("proposal_disclaimer") if isinstance(dossier.get("proposal_disclaimer"), dict) else {}
    sensitivity_analysis = dossier.get("sensitivity_analysis") if isinstance(dossier.get("sensitivity_analysis"), dict) else {}
    assumptions = saved.get("assumptions") if isinstance(saved.get("assumptions"), list) else []
    if not assumptions:
        assumptions = dossier.get("assumptions") if isinstance(dossier.get("assumptions"), list) else []

    source_type = escape(str(saved.get("source_type") or "source"))
    source_id = escape(str(saved.get("source_id") or ""))
    scenario_profile = escape(str(saved.get("scenario_profile") or "base"))
    horizon_months = escape(str(saved.get("horizon_months") or "12"))
    currency = escape(str(saved.get("currency") or "USD"))
    created_at = escape(format_display_datetime(saved.get("created_at")))
    model = escape(str(saved.get("model") or ""))

    winner = decision.get("winner") if isinstance(decision.get("winner"), dict) else {}
    report_title = escape(str(saved.get("title") or winner.get("title") or "Execution Plan"))
    winner_title = escape(str(winner.get("title") or "N/A"))
    winner_model = escape(model_label_from_id(str(winner.get("model_id") or "")))
    thesis = escape(str(decision.get("thesis") or "No decision thesis provided."))
    go_no_go = escape(str(decision.get("go_no_go") or "conditional_go"))
    confidence_value = decision.get("confidence")
    try:
        confidence_text = f"{round(float(confidence_value) * 100)}%"
    except Exception:
        confidence_text = "N/A"

    def fmt_currency(value: Any, decimals: int = 0) -> str:
        try:
            number = float(value)
        except Exception:
            return "N/A"
        return f"${number:,.{decimals}f}"

    def render_table(headers: List[str], rows: List[str], empty_text: str) -> str:
        if not rows:
            return f"<p class='muted'>{escape(empty_text)}</p>"
        head_html = "".join(f"<th>{escape(col)}</th>" for col in headers)
        return (
            "<table class='table'>"
            f"<thead><tr>{head_html}</tr></thead>"
            f"<tbody>{''.join(rows)}</tbody>"
            "</table>"
        )

    phases = blueprint.get("phases") if isinstance(blueprint.get("phases"), list) else []
    phases_rows = []
    for phase in phases:
        if not isinstance(phase, dict):
            continue
        name = escape(str(phase.get("name") or "Phase"))
        start_month = escape(str(phase.get("start_month") or ""))
        end_month = escape(str(phase.get("end_month") or ""))
        deliverables = phase.get("deliverables") if isinstance(phase.get("deliverables"), list) else []
        deliverables_text = escape(", ".join([str(x) for x in deliverables if str(x).strip()]) or "—")
        owners = phase.get("owner_roles") if isinstance(phase.get("owner_roles"), list) else []
        owner_text = escape(", ".join([str(x) for x in owners if str(x).strip()]) or "—")
        phases_rows.append(
            "<tr>"
            f"<td>{name}</td>"
            f"<td>{start_month}-{end_month}</td>"
            f"<td>{deliverables_text}</td>"
            f"<td>{owner_text}</td>"
            "</tr>"
        )
    phases_html = render_table(
        ["Phase", "Timeline", "Deliverables", "Owner Roles"],
        phases_rows,
        "No execution phases available.",
    )
    critical_path = blueprint.get("critical_path") if isinstance(blueprint.get("critical_path"), list) else []
    critical_path_html = (
        "<ul>" + "".join(f"<li>{escape(str(item))}</li>" for item in critical_path if str(item).strip()) + "</ul>"
    ) if critical_path else "<p class='muted'>No critical path listed.</p>"

    setup_cost = costs.get("setup_cost") if isinstance(costs.get("setup_cost"), dict) else {}
    unit_cogs = costs.get("unit_cogs") if isinstance(costs.get("unit_cogs"), dict) else {}
    pricing = revenue_profit.get("pricing") if isinstance(revenue_profit.get("pricing"), dict) else {}
    setup_total = escape(str(setup_cost.get("total") or "0"))
    setup_total_money = escape(fmt_currency(setup_cost.get("total"), 0))
    setup_engineering_money = escape(fmt_currency(setup_cost.get("engineering"), 0))
    setup_legal_money = escape(fmt_currency(setup_cost.get("legal_compliance"), 0))
    setup_marketing_money = escape(fmt_currency(setup_cost.get("launch_marketing"), 0))
    arpu_monthly_money = escape(fmt_currency(pricing.get("arpu_monthly"), 0))
    unit_cogs_monthly_money = escape(fmt_currency(unit_cogs.get("per_customer_monthly"), 0))
    break_even = escape(str(revenue_profit.get("break_even_month") or "N/A"))
    budget_required = escape(str(stakeholder_ask.get("budget_required") or "0"))

    projection = revenue_profit.get("monthly_projection") if isinstance(revenue_profit.get("monthly_projection"), list) else []
    projection_rows = []
    for row in projection:
        if not isinstance(row, dict):
            continue
        projection_rows.append(
            "<tr>"
            f"<td>{escape(str(row.get('month') or ''))}</td>"
            f"<td>{escape(str(row.get('customers') or ''))}</td>"
            f"<td>{escape(str(row.get('revenue') or ''))}</td>"
            f"<td>{escape(str(row.get('opex') or ''))}</td>"
            f"<td>{escape(str(row.get('net_profit') or ''))}</td>"
            f"<td>{escape(str(row.get('cumulative_net_profit') or ''))}</td>"
            "</tr>"
        )
    projection_html = render_table(
        ["Month", "Customers", "Revenue", "OpEx", "Net Profit", "Cumulative"],
        projection_rows,
        "No monthly projection available.",
    )

    scenario_rows = []
    for item in scenarios:
        if not isinstance(item, dict):
            continue
        scenario_rows.append(
            "<tr>"
            f"<td>{escape(str(item.get('name') or ''))}</td>"
            f"<td>{escape(str(item.get('probability') or ''))}</td>"
            f"<td>{escape(str(item.get('year_1_revenue') or ''))}</td>"
            f"<td>{escape(str(item.get('year_1_net_profit') or ''))}</td>"
            "</tr>"
        )
    scenarios_html = render_table(
        ["Scenario", "Probability", "Year 1 Revenue", "Year 1 Net Profit"],
        scenario_rows,
        "No scenario outcomes available.",
    )

    roles = resources.get("roles") if isinstance(resources.get("roles"), list) else []
    role_rows = []
    for role in roles:
        if not isinstance(role, dict):
            continue
        cost_monthly = role.get("cost_monthly") if isinstance(role.get("cost_monthly"), list) else []
        avg_monthly = 0.0
        if cost_monthly:
            try:
                avg_monthly = sum(float(x) for x in cost_monthly) / len(cost_monthly)
            except Exception:
                avg_monthly = 0.0
        role_rows.append(
            "<tr>"
            f"<td>{escape(str(role.get('role') or ''))}</td>"
            f"<td>{escape(str(role.get('employment_type') or ''))}</td>"
            f"<td>{escape(str(round(avg_monthly, 2)))}</td>"
            "</tr>"
        )
    resources_html = render_table(
        ["Role", "Type", "Avg Monthly Cost"],
        role_rows,
        "No team resource plan available.",
    )

    risk_items = []
    for item in risks:
        if not isinstance(item, dict):
            continue
        risk_items.append(
            "<li>"
            f"<strong>{escape(str(item.get('category') or 'Risk'))}</strong>: "
            f"{escape(str(item.get('description') or ''))} "
            f"(Mitigation: {escape(str(item.get('mitigation') or 'N/A'))})"
            "</li>"
        )
    risks_html = "<ul>" + "".join(risk_items) + "</ul>" if risk_items else "<p class='muted'>No risk register available.</p>"

    assumption_rows = []
    for item in assumptions:
        if not isinstance(item, dict):
            continue
        assumption_rows.append(
            "<tr>"
            f"<td>{escape(str(item.get('key') or ''))}</td>"
            f"<td>{escape(str(item.get('value') or ''))}</td>"
            f"<td>{escape(str(item.get('unit') or ''))}</td>"
            f"<td>{escape(str(item.get('source') or ''))}</td>"
            f"<td>{escape(str(item.get('confidence') or ''))}</td>"
            "</tr>"
        )
    assumptions_html = render_table(
        ["Assumption", "Value", "Unit", "Source", "Confidence"],
        assumption_rows,
        "No assumptions list available.",
    )

    next_actions = stakeholder_ask.get("next_30_days") if isinstance(stakeholder_ask.get("next_30_days"), list) else []
    next_actions_html = (
        "<ul>" + "".join(f"<li>{escape(str(x))}</li>" for x in next_actions if str(x).strip()) + "</ul>"
    ) if next_actions else "<p class='muted'>No next actions provided.</p>"
    support_reasons = decision_support.get("reasons") if isinstance(decision_support.get("reasons"), list) else []
    support_actions = decision_support.get("required_actions") if isinstance(decision_support.get("required_actions"), list) else []
    support_reasons_html = (
        "<ul>" + "".join(f"<li>{escape(str(x))}</li>" for x in support_reasons if str(x).strip()) + "</ul>"
    ) if support_reasons else "<p class='muted'>No financial gate blockers listed.</p>"
    support_actions_html = (
        "<ul>" + "".join(f"<li>{escape(str(x))}</li>" for x in support_actions if str(x).strip()) + "</ul>"
    ) if support_actions else "<p class='muted'>No mandatory remediation actions listed.</p>"
    support_gates = decision_support.get("gates") if isinstance(decision_support.get("gates"), dict) else {}
    support_year_1 = escape(str(support_gates.get("year_1_net_profit") or ""))
    support_expected = escape(str(support_gates.get("expected_year_1_net_profit") or ""))
    support_break_even = escape(str(support_gates.get("break_even_month") or break_even))
    support_status = escape(str(decision_support.get("status") or "not_set"))
    recovery = decision_support.get("profitability_recovery") if isinstance(decision_support.get("profitability_recovery"), dict) else {}
    recovery_enabled = bool(recovery.get("enabled"))
    recovery_gap = escape(str(recovery.get("monthly_profit_gap") or "0"))
    recovery_levers = recovery.get("levers") if isinstance(recovery.get("levers"), list) else []
    recovery_scenarios = recovery.get("scenarios") if isinstance(recovery.get("scenarios"), list) else []
    recovery_experiments = recovery.get("experiments_90_days") if isinstance(recovery.get("experiments_90_days"), list) else []
    recovery_approval_gate = escape(str(recovery.get("approval_gate") or ""))
    recovery_levers_html = (
        "<ul>" + "".join(
            "<li>"
            f"<strong>{escape(str((item or {}).get('name') or 'Lever'))}:</strong> "
            f"{escape(str((item or {}).get('target') or ''))} "
            f"(impact {escape(str((item or {}).get('estimated_monthly_impact') or 0))}/month)"
            "</li>"
            for item in recovery_levers
            if isinstance(item, dict)
        ) + "</ul>"
    ) if recovery_levers else "<p class='muted'>No recovery levers listed.</p>"
    recovery_scenarios_rows = []
    for item in recovery_scenarios:
        if not isinstance(item, dict):
            continue
        moves = item.get("moves") if isinstance(item.get("moves"), list) else []
        recovery_scenarios_rows.append(
            "<tr>"
            f"<td>{escape(str(item.get('name') or 'Scenario'))}</td>"
            f"<td>{escape('; '.join(str(x) for x in moves[:2] if str(x).strip()) or '—')}</td>"
            f"<td>{escape(str(item.get('estimated_monthly_impact') or '0'))}</td>"
            f"<td>{escape(str(item.get('estimated_year_1_net_profit') or '0'))}</td>"
            f"<td>{escape(str(item.get('estimated_break_even_month') or 'N/A'))}</td>"
            "</tr>"
        )
    recovery_scenarios_html = render_table(
        ["Scenario", "Moves", "Monthly Impact", "Est. Year 1 Net", "Est. Break-even"],
        recovery_scenarios_rows,
        "No recovery scenarios listed.",
    )
    recovery_experiments_html = (
        "<ul>" + "".join(
            "<li>"
            f"{escape(str((item or {}).get('name') or 'Experiment'))} - "
            f"{escape(str((item or {}).get('owner') or 'Owner'))}, "
            f"{escape(str((item or {}).get('target_metric') or 'Target'))}, "
            f"D{escape(str((item or {}).get('deadline_days') or '0'))}, "
            f"impact {escape(str((item or {}).get('expected_monthly_impact') or '0'))}/month"
            "</li>"
            for item in recovery_experiments
            if isinstance(item, dict)
        ) + "</ul>"
    ) if recovery_experiments else "<p class='muted'>No 90-day experiments listed.</p>"
    disclaimer_title = escape(str(proposal_disclaimer.get("title") or "Proposal estimate notice"))
    disclaimer_message = escape(str(proposal_disclaimer.get("message") or ""))
    disclaimer_basis = escape(str(proposal_disclaimer.get("data_basis") or ""))
    disclaimer_updated = escape(str(proposal_disclaimer.get("updated_at") or ""))
    sensitivity_tests = sensitivity_analysis.get("tests") if isinstance(sensitivity_analysis.get("tests"), list) else []
    sensitivity_rows = []
    for item in sensitivity_tests:
        if not isinstance(item, dict):
            continue
        sensitivity_rows.append(
            "<tr>"
            f"<td>{escape(str(item.get('name') or 'Test'))}</td>"
            f"<td>{escape(str(item.get('year_1_revenue') or '0'))}</td>"
            f"<td>{escape(str(item.get('year_1_net_profit') or '0'))}</td>"
            f"<td>{escape(str(item.get('break_even_month') or 'N/A'))}</td>"
            "</tr>"
        )
    sensitivity_html = render_table(
        ["Stress Test", "Year 1 Revenue", "Year 1 Net Profit", "Break-even Month"],
        sensitivity_rows,
        "No sensitivity stress tests provided.",
    )
    sensitivity_note = escape(str(sensitivity_analysis.get("interpretation") or ""))
    industry_assumption = next(
        (
            str((item or {}).get("value") or "").strip()
            for item in assumptions
            if isinstance(item, dict) and str((item or {}).get("key") or "").strip().lower() == "industry"
        ),
        "",
    )
    icp_plain_text = (
        f"{industry_assumption} buyers matching the selected persona and constraints."
        if industry_assumption
        else "Buyers matching the selected persona and constraints."
    )

    return f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8" />
      <style>
        @page {{ size: A4; margin: 0.6in; }}
        body {{ font-family: Arial, sans-serif; font-size: 11px; color: #121826; }}
        h1 {{ font-size: 22px; margin: 0 0 4px 0; }}
        h2 {{ font-size: 14px; margin: 14px 0 6px 0; }}
        .sub {{ color: #4b5563; margin-bottom: 10px; }}
        .meta {{
          display: grid;
          grid-template-columns: repeat(4, minmax(0, 1fr));
          gap: 8px;
          margin-bottom: 12px;
        }}
        .meta-card {{
          border: 1px solid #dbe0ea;
          border-radius: 8px;
          padding: 6px 8px;
          background: #f8faff;
        }}
        .meta-label {{ font-size: 9px; text-transform: uppercase; color: #6b7280; }}
        .meta-value {{ font-weight: 700; margin-top: 2px; }}
        .block {{
          border: 1px solid #e5e7eb;
          border-radius: 8px;
          padding: 10px;
          margin-bottom: 10px;
          page-break-inside: auto;
        }}
        .block-emphasis {{
          border-color: #f59e0b;
          background: #fff7ed;
        }}
        .block-emphasis h2 {{
          color: #9a3412;
        }}
        .block-emphasis .table th {{
          background: #ffedd5;
        }}
        .block-emphasis .muted {{
          color: #9a3412;
        }}
        .table {{
          width: 100%;
          border-collapse: collapse;
          table-layout: fixed;
          font-size: 10.5px;
          page-break-inside: auto;
        }}
        .table thead {{ display: table-header-group; }}
        .table tfoot {{ display: table-footer-group; }}
        .table tr {{ page-break-inside: avoid; page-break-after: auto; }}
        .table th, .table td {{
          border: 1px solid #e5e7eb;
          padding: 5px;
          vertical-align: top;
          word-break: break-word;
          overflow-wrap: anywhere;
          break-inside: avoid;
        }}
        .table th {{ background: #f8fafc; text-align: left; }}
        .muted {{ color: #6b7280; }}
        ul {{ margin: 6px 0 0 16px; padding: 0; }}
        li {{ margin: 0 0 4px 0; }}
        h2, h3 {{ page-break-after: avoid; }}
      </style>
    </head>
    <body>
      <h1>IdeaGen Execution Plan</h1>
      <div class="sub">Professional execution report for stakeholder decision and implementation planning.</div>
      <div class="sub"><strong>Report Title:</strong> {report_title}</div>

      <div class="meta">
        <div class="meta-card"><div class="meta-label">Saved At</div><div class="meta-value">{created_at}</div></div>
        <div class="meta-card"><div class="meta-label">Source</div><div class="meta-value">{source_type} #{source_id}</div></div>
        <div class="meta-card"><div class="meta-label">Scenario</div><div class="meta-value">{scenario_profile}</div></div>
        <div class="meta-card"><div class="meta-label">Horizon / Currency</div><div class="meta-value">{horizon_months} months / {currency}</div></div>
      </div>

      <div class="block">
        <h2>Decision Recommendation</h2>
        <p><strong>Winner:</strong> {winner_title} ({winner_model})</p>
        <p><strong>Recommendation:</strong> {go_no_go} &nbsp;|&nbsp; <strong>Confidence:</strong> {confidence_text}</p>
        <p><strong>Financial Gate Status:</strong> {support_status} &nbsp;|&nbsp; <strong>Year 1 Net:</strong> {support_year_1} &nbsp;|&nbsp; <strong>Expected Year 1 Net:</strong> {support_expected} &nbsp;|&nbsp; <strong>Break-even:</strong> Month {support_break_even}</p>
        <p>{thesis}</p>
        <h2>Financial Gate Rationale</h2>
        {support_reasons_html}
        <h2>Required Actions Before Approval</h2>
        {support_actions_html}
      </div>

      {(f"""
      <div class=\"block\" style=\"background:#fff7ed;border-color:#f59e0b;\">
        <h2>{disclaimer_title}</h2>
        <p>{disclaimer_message}</p>
        <p><strong>Data basis:</strong> {disclaimer_basis}{f" &nbsp;|&nbsp; <strong>Updated:</strong> {disclaimer_updated}" if disclaimer_updated else ""}</p>
      </div>
      """ if disclaimer_message else "")}

      <div class="block" style="background:#eef6ff;border-color:#bfdbfe;">
        <h2>Business Terms and Definitions</h2>
        <ul>
          <li><strong>ARPU:</strong> average revenue from one paying customer per month.</li>
          <li><strong>ICP:</strong> ideal customer profile — {escape(icp_plain_text)}</li>
          <li><strong>OpEx:</strong> monthly operating costs (team, tools, cloud, support, marketing).</li>
          <li><strong>COGS:</strong> service delivery cost per customer (AI usage, support, infra).</li>
          <li><strong>Break-even:</strong> first month cumulative profit reaches zero or above.</li>
          <li><strong>Confidence:</strong> confidence in winner selection quality, not guaranteed profitability.</li>
        </ul>
      </div>

      <div class="block">
        <h2>Execution Blueprint</h2>
        {phases_html}
        <h2>Critical path</h2>
        {critical_path_html}
      </div>

      <div class="block">
        <h2>Financial Overview</h2>
        <p><strong>Setup Cost:</strong> {setup_total} {currency} &nbsp;|&nbsp; <strong>Break-even Month:</strong> {break_even} &nbsp;|&nbsp; <strong>Stakeholder Ask:</strong> {budget_required} {currency}</p>
        <h2>Budget and unit economics</h2>
        <ul>
          <li><strong>Setup total:</strong> {setup_total_money}</li>
          <li><strong>Engineering:</strong> {setup_engineering_money}</li>
          <li><strong>Legal/Compliance:</strong> {setup_legal_money}</li>
          <li><strong>Launch Marketing:</strong> {setup_marketing_money}</li>
          <li><strong>ARPU (avg revenue per customer/month):</strong> {arpu_monthly_money}</li>
          <li><strong>Service delivery cost (COGS) per customer/month:</strong> {unit_cogs_monthly_money}</li>
        </ul>
        {projection_html}
      </div>

      <div class="block">
        <h2>Scenario Outcomes</h2>
        {scenarios_html}
      </div>

      <div class="block">
        <h2>Sensitivity Analysis</h2>
        {sensitivity_html}
        {f"<p>{sensitivity_note}</p>" if sensitivity_note else ""}
      </div>

      <div class="block">
        <h2>Resource Plan</h2>
        {resources_html}
      </div>

      <div class="block">
        <h2>Risk Register</h2>
        {risks_html}
      </div>

      <div class="block">
        <h2>Stakeholder Ask and Next 30 Days</h2>
        <p><strong>Decision Required:</strong> {escape(str(stakeholder_ask.get("decision_required") or "N/A"))}</p>
        {next_actions_html}
      </div>

      <div class="block">
        <h2>Assumptions and Provenance</h2>
        <p><strong>Model:</strong> {model}</p>
        {assumptions_html}
      </div>

      {""
      if not recovery_enabled
      else f"""
      <div class=\"block block-emphasis\">
        <h2>Profitability Recovery Plan</h2>
        <p><strong>Monthly profit gap to close:</strong> {recovery_gap}</p>
        <h2>Levers</h2>
        {recovery_levers_html}
        <h2>Recovery Scenarios</h2>
        {recovery_scenarios_html}
        <h2>90-Day Experiments</h2>
        {recovery_experiments_html}
        {f"<p><strong>Approval gate:</strong> {recovery_approval_gate}</p>" if recovery_approval_gate else ""}
      </div>
      """}
    </body>
    </html>
    """


def create_execution_plan_presentation_html(saved: Dict[str, Any]) -> str:
    dossier = saved.get("dossier") if isinstance(saved.get("dossier"), dict) else {}
    decision = dossier.get("decision") if isinstance(dossier.get("decision"), dict) else {}
    blueprint = dossier.get("execution_blueprint") if isinstance(dossier.get("execution_blueprint"), dict) else {}
    resources = dossier.get("resources") if isinstance(dossier.get("resources"), dict) else {}
    costs = dossier.get("costs") if isinstance(dossier.get("costs"), dict) else {}
    revenue_profit = dossier.get("revenue_profit") if isinstance(dossier.get("revenue_profit"), dict) else {}
    scenarios = dossier.get("scenarios") if isinstance(dossier.get("scenarios"), list) else []
    stakeholder_ask = dossier.get("stakeholder_ask") if isinstance(dossier.get("stakeholder_ask"), dict) else {}
    decision_support = dossier.get("decision_support") if isinstance(dossier.get("decision_support"), dict) else {}
    risks = dossier.get("risks") if isinstance(dossier.get("risks"), list) else []
    assumptions = saved.get("assumptions") if isinstance(saved.get("assumptions"), list) else []
    if not assumptions:
        assumptions = dossier.get("assumptions") if isinstance(dossier.get("assumptions"), list) else []
    provenance = dossier.get("provenance") if isinstance(dossier.get("provenance"), dict) else {}

    def to_float(value: Any, default: float = 0.0) -> float:
        try:
            return float(value)
        except Exception:
            return default

    def fmt_money(value: Any) -> str:
        return f"${to_float(value):,.0f}"

    def fmt_num(value: Any) -> str:
        return f"{to_float(value):,.0f}"

    def fmt_pct(value: Any) -> str:
        return f"{to_float(value) * 100:.0f}%"

    def to_clean_list(items: Any, max_items: int = 8) -> List[str]:
        if not isinstance(items, list):
            return []
        clean: List[str] = []
        for item in items:
            text = str(item or "").strip()
            if text:
                clean.append(text)
            if len(clean) >= max_items:
                break
        return clean

    def shorten_text(value: Any, max_len: int = 72) -> str:
        text = str(value or "").strip()
        if len(text) <= max_len:
            return text
        return text[: max_len - 3].rstrip() + "..."

    def bullet_html(items: Any, max_items: int = 8, empty_text: str = "No data available.") -> str:
        clean = to_clean_list(items, max_items=max_items)
        if not clean:
            return f"<p class='muted'>{escape(empty_text)}</p>"
        return "<ul>" + "".join(f"<li>{escape(item)}</li>" for item in clean) + "</ul>"

    thesis = escape(str(decision.get("thesis") or "No thesis provided."))
    go_no_go = escape(str(decision.get("go_no_go") or "conditional_go"))
    confidence_text = f"{round(to_float(decision.get('confidence')) * 100)}%"
    created_at = escape(format_display_datetime(saved.get("created_at")))
    source_text = f"{escape(str(saved.get('source_type') or 'source'))} #{escape(str(saved.get('source_id') or ''))}"
    scenario_text = escape(str(saved.get("scenario_profile") or "base"))
    horizon_text = escape(str(saved.get("horizon_months") or "12"))
    currency = escape(str(saved.get("currency") or "USD"))
    winner = decision.get("winner") if isinstance(decision.get("winner"), dict) else {}
    report_title = escape(str(saved.get("title") or winner.get("title") or "Execution Plan"))
    winner_title = escape(str(winner.get("title") or "N/A"))
    winner_model = escape(model_label_from_id(str(winner.get("model_id") or "")))

    setup_cost = costs.get("setup_cost") if isinstance(costs.get("setup_cost"), dict) else {}
    monthly_opex = costs.get("monthly_opex") if isinstance(costs.get("monthly_opex"), list) else []
    unit_cogs = costs.get("unit_cogs") if isinstance(costs.get("unit_cogs"), dict) else {}
    setup_total = fmt_money(setup_cost.get("total"))
    break_even = escape(str(revenue_profit.get("break_even_month") or "N/A"))
    ask_budget = fmt_money(stakeholder_ask.get("budget_required"))
    arpu = fmt_money((revenue_profit.get("pricing") or {}).get("arpu_monthly") if isinstance(revenue_profit.get("pricing"), dict) else 0)
    unit_cogs_value = fmt_money(unit_cogs.get("per_customer_monthly"))
    support_gates = decision_support.get("gates") if isinstance(decision_support.get("gates"), dict) else {}
    support_status = escape(str(decision_support.get("status") or "not_set"))
    support_year_1 = fmt_money(support_gates.get("year_1_net_profit"))
    support_expected = fmt_money(support_gates.get("expected_year_1_net_profit"))
    support_break_even = escape(str(support_gates.get("break_even_month") or break_even))
    support_reasons_html = bullet_html(
        decision_support.get("reasons"),
        max_items=3,
        empty_text="No financial gate blockers listed.",
    )
    support_actions_html = bullet_html(
        decision_support.get("required_actions"),
        max_items=3,
        empty_text="No mandatory remediation actions listed.",
    )
    industry_assumption = next(
        (
            str((item or {}).get("value") or "").strip()
            for item in assumptions
            if isinstance(item, dict) and str((item or {}).get("key") or "").strip().lower() == "industry"
        ),
        "",
    )
    icp_plain_text = (
        f"{industry_assumption} buyers matching the selected persona and constraints."
        if industry_assumption
        else "Buyers matching the selected persona and constraints."
    )
    proposal_disclaimer = dossier.get("proposal_disclaimer") if isinstance(dossier.get("proposal_disclaimer"), dict) else {}
    disclaimer_title = escape(str(proposal_disclaimer.get("title") or "Proposal estimate notice"))
    disclaimer_message = escape(str(proposal_disclaimer.get("message") or ""))
    disclaimer_basis = escape(str(proposal_disclaimer.get("data_basis") or ""))
    disclaimer_updated = escape(str(proposal_disclaimer.get("updated_at") or ""))
    sensitivity_analysis = dossier.get("sensitivity_analysis") if isinstance(dossier.get("sensitivity_analysis"), dict) else {}
    sensitivity_tests = sensitivity_analysis.get("tests") if isinstance(sensitivity_analysis.get("tests"), list) else []
    sensitivity_rows = []
    for item in sensitivity_tests[:4]:
        if not isinstance(item, dict):
            continue
        sensitivity_rows.append(
            "<tr>"
            f"<td>{escape(str(item.get('name') or 'Test'))}</td>"
            f"<td class='num'>{fmt_money(item.get('year_1_revenue'))}</td>"
            f"<td class='num'>{fmt_money(item.get('year_1_net_profit'))}</td>"
            f"<td class='num'>{escape(str(item.get('break_even_month') or 'N/A'))}</td>"
            "</tr>"
        )
    sensitivity_html = (
        "<table class='table compact'><tr><th>Stress Test</th><th>Year 1 Revenue</th><th>Year 1 Net</th><th>Break-even</th></tr>"
        + "".join(sensitivity_rows)
        + "</table>"
    ) if sensitivity_rows else "<p class='muted'>No sensitivity stress tests provided.</p>"
    sensitivity_note = escape(str(sensitivity_analysis.get("interpretation") or ""))
    recovery = decision_support.get("profitability_recovery") if isinstance(decision_support.get("profitability_recovery"), dict) else {}
    recovery_enabled = bool(recovery.get("enabled"))
    recovery_gap = fmt_money(recovery.get("monthly_profit_gap"))
    recovery_approval_gate = escape(str(recovery.get("approval_gate") or ""))
    recovery_levers = recovery.get("levers") if isinstance(recovery.get("levers"), list) else []
    recovery_levers_html = (
        "<ul>" + "".join(
            "<li>"
            f"<strong>{escape(str((item or {}).get('name') or 'Lever'))}:</strong> {escape(str((item or {}).get('target') or ''))} "
            f"(impact {fmt_money((item or {}).get('estimated_monthly_impact'))}/month)"
            "</li>"
            for item in recovery_levers[:4]
            if isinstance(item, dict)
        ) + "</ul>"
    ) if recovery_levers else "<p class='muted'>No recovery levers listed.</p>"
    recovery_scenarios = recovery.get("scenarios") if isinstance(recovery.get("scenarios"), list) else []
    recovery_rows = []
    for item in recovery_scenarios[:3]:
        if not isinstance(item, dict):
            continue
        recovery_rows.append(
            "<tr>"
            f"<td>{escape(str(item.get('name') or 'Scenario'))}</td>"
            f"<td class='num'>{fmt_money(item.get('estimated_monthly_impact'))}</td>"
            f"<td class='num'>{fmt_money(item.get('estimated_year_1_net_profit'))}</td>"
            f"<td class='num'>{escape(str(item.get('estimated_break_even_month') or 'N/A'))}</td>"
            "</tr>"
        )
    recovery_scenarios_html = (
        "<table class='table compact'><tr><th>Scenario</th><th>Monthly Impact</th><th>Est. Year 1 Net</th><th>Est. Break-even</th></tr>"
        + "".join(recovery_rows)
        + "</table>"
    ) if recovery_rows else "<p class='muted'>No recovery scenarios listed.</p>"

    base_scenario = None
    if scenarios:
        for item in scenarios:
            if isinstance(item, dict) and str(item.get("name") or "").strip().lower() == "base":
                base_scenario = item
                break
        if base_scenario is None:
            base_scenario = max(
                [s for s in scenarios if isinstance(s, dict)],
                key=lambda item: to_float((item or {}).get("probability")),
                default=None,
            )
    year1_revenue = fmt_money((base_scenario or {}).get("year_1_revenue"))
    year1_profit = fmt_money((base_scenario or {}).get("year_1_net_profit"))

    funnel = revenue_profit.get("funnel_assumptions") if isinstance(revenue_profit.get("funnel_assumptions"), dict) else {}
    funnel_text = (
        f"Traffic to Lead {fmt_pct(funnel.get('traffic_to_lead'))} | "
        f"Lead to SQL {fmt_pct(funnel.get('lead_to_sql'))} | "
        f"SQL to Customer {fmt_pct(funnel.get('sql_to_customer'))}"
    )

    phase_rows = []
    for phase in (blueprint.get("phases") if isinstance(blueprint.get("phases"), list) else [])[:6]:
        if not isinstance(phase, dict):
            continue
        workstreams = to_clean_list(phase.get("workstreams"), max_items=2)
        deliverables = to_clean_list(phase.get("deliverables"), max_items=2)
        owners = to_clean_list(phase.get("owner_roles"), max_items=2)
        phase_rows.append(
            "<tr>"
            f"<td>{escape(str(phase.get('name') or 'Phase'))}</td>"
            f"<td>M{escape(str(phase.get('start_month') or ''))} to M{escape(str(phase.get('end_month') or ''))}</td>"
            f"<td>{escape(', '.join(workstreams) or '—')}</td>"
            f"<td>{escape(', '.join(deliverables) or '—')}</td>"
            f"<td>{escape(', '.join(owners) or '—')}</td>"
            "</tr>"
        )
    phase_html = (
        "<table class='table'><tr><th>Phase</th><th>Timeline</th><th>Workstreams</th><th>Deliverables</th><th>Owners</th></tr>"
        + "".join(phase_rows)
        + "</table>"
    ) if phase_rows else "<p class='muted'>No phases available.</p>"

    projection = revenue_profit.get("monthly_projection") if isinstance(revenue_profit.get("monthly_projection"), list) else []
    projection_rows = []
    for row in projection[:8]:
        if not isinstance(row, dict):
            continue
        projection_rows.append(
            "<tr>"
            f"<td class='num'>{fmt_num(row.get('month'))}</td>"
            f"<td class='num'>{fmt_num(row.get('customers'))}</td>"
            f"<td class='num'>{fmt_money(row.get('revenue'))}</td>"
            f"<td class='num'>{fmt_money(row.get('cogs'))}</td>"
            f"<td class='num'>{fmt_money(row.get('opex'))}</td>"
            f"<td class='num'>{fmt_money(row.get('net_profit'))}</td>"
            "</tr>"
        )
    projection_html = (
        "<table class='table compact'><tr><th>Month</th><th>Customers</th><th>Revenue</th><th>COGS</th><th>OpEx</th><th>Net</th></tr>"
        + "".join(projection_rows)
        + "</table>"
    ) if projection_rows else "<p class='muted'>No monthly projection available.</p>"

    setup_breakdown_rows = [
        ("Engineering", setup_cost.get("engineering")),
        ("Legal/Compliance", setup_cost.get("legal_compliance")),
        ("Launch Marketing", setup_cost.get("launch_marketing")),
        ("Other", setup_cost.get("other")),
        ("Total", setup_cost.get("total")),
    ]
    setup_breakdown_html = (
        "<table class='table compact'><tr><th>Setup Cost Item</th><th>Amount</th></tr>"
        + "".join(
            "<tr>"
            f"<td>{escape(label)}</td>"
            f"<td class='num'>{fmt_money(value)}</td>"
            "</tr>"
            for label, value in setup_breakdown_rows
        )
        + "</table>"
    )

    opex_series = []
    for row in monthly_opex[:12]:
        if not isinstance(row, dict):
            continue
        opex_series.append((int(to_float(row.get("month"))), to_float(row.get("total"))))
    if opex_series:
        avg_opex = sum(v for _, v in opex_series) / len(opex_series)
        peak_month, peak_opex = max(opex_series, key=lambda item: item[1])
        start_month, start_opex = opex_series[0]
        end_month, end_opex = opex_series[-1]
        opex_profile_html = (
            "<ul>"
            f"<li>Average monthly OpEx: {escape(fmt_money(avg_opex))}</li>"
            f"<li>Peak OpEx: M{escape(str(peak_month))} at {escape(fmt_money(peak_opex))}</li>"
            f"<li>Run-rate trend: M{escape(str(start_month))} {escape(fmt_money(start_opex))} to M{escape(str(end_month))} {escape(fmt_money(end_opex))}</li>"
            "</ul>"
        )
    else:
        opex_profile_html = "<p class='muted'>No monthly OpEx breakdown.</p>"

    scenario_rows = []
    for s in scenarios[:4]:
        if not isinstance(s, dict):
            continue
        key_assumptions = to_clean_list(s.get("key_assumptions"), max_items=2)
        scenario_rows.append(
            "<tr>"
            f"<td>{escape(str(s.get('name') or ''))}</td>"
            f"<td class='num'>{fmt_pct(s.get('probability'))}</td>"
            f"<td class='num'>{fmt_money(s.get('year_1_revenue'))}</td>"
            f"<td class='num'>{fmt_money(s.get('year_1_net_profit'))}</td>"
            f"<td>{escape('; '.join(key_assumptions) or '—')}</td>"
            "</tr>"
        )
    scenario_html = (
        "<table class='table'><tr><th>Scenario</th><th>Probability</th><th>Year 1 Revenue</th><th>Year 1 Net</th><th>Key Assumptions</th></tr>"
        + "".join(scenario_rows)
        + "</table>"
    ) if scenario_rows else "<p class='muted'>No scenario outcomes available.</p>"

    role_rows = []
    for role in (resources.get("roles") if isinstance(resources.get("roles"), list) else [])[:6]:
        if not isinstance(role, dict):
            continue
        ftes = role.get("fte_by_month") if isinstance(role.get("fte_by_month"), list) else []
        costs_month = role.get("cost_monthly") if isinstance(role.get("cost_monthly"), list) else []
        avg_fte = sum(to_float(x) for x in ftes) / len(ftes) if ftes else 0.0
        peak_fte = max([to_float(x) for x in ftes], default=0.0)
        avg_cost = sum(to_float(x) for x in costs_month) / len(costs_month) if costs_month else 0.0
        role_rows.append(
            "<tr>"
            f"<td>{escape(str(role.get('role') or 'Role'))}</td>"
            f"<td>{escape(str(role.get('employment_type') or 'N/A'))}</td>"
            f"<td class='num'>{avg_fte:.2f}</td>"
            f"<td class='num'>{peak_fte:.2f}</td>"
            f"<td class='num'>{fmt_money(avg_cost)}</td>"
            "</tr>"
        )
    role_html = (
        "<table class='table'><tr><th>Role</th><th>Type</th><th>Avg FTE</th><th>Peak FTE</th><th>Avg Monthly Cost</th></tr>"
        + "".join(role_rows)
        + "</table>"
    ) if role_rows else "<p class='muted'>No resource plan available.</p>"

    tooling_rows = []
    for tool in (resources.get("tooling") if isinstance(resources.get("tooling"), list) else [])[:6]:
        if not isinstance(tool, dict):
            continue
        tooling_rows.append(
            "<tr>"
            f"<td>{escape(str(tool.get('name') or 'Tool'))}</td>"
            f"<td>{escape(str(tool.get('category') or 'N/A'))}</td>"
            f"<td class='num'>{fmt_money(tool.get('monthly_cost'))}</td>"
            "</tr>"
        )
    tooling_html = (
        "<table class='table compact'><tr><th>Tool</th><th>Category</th><th>Monthly Cost</th></tr>"
        + "".join(tooling_rows)
        + "</table>"
    ) if tooling_rows else "<p class='muted'>No tooling breakdown available.</p>"

    unit_cogs_rows = []
    for component in (unit_cogs.get("components") if isinstance(unit_cogs.get("components"), list) else [])[:8]:
        if not isinstance(component, dict):
            continue
        unit_cogs_rows.append(
            "<tr>"
            f"<td>{escape(str(component.get('name') or 'Component'))}</td>"
            f"<td class='num'>{fmt_money(component.get('amount'))}</td>"
            "</tr>"
        )
    unit_cogs_html = (
        "<table class='table compact'><tr><th>COGS Component</th><th>Amount</th></tr>"
        + "".join(unit_cogs_rows)
        + "</table>"
    ) if unit_cogs_rows else "<p class='muted'>No unit COGS components available.</p>"

    risks_rows = []
    for risk in risks[:5]:
        if not isinstance(risk, dict):
            continue
        risks_rows.append(
            "<tr>"
            f"<td>{escape(str(risk.get('category') or 'Risk'))}</td>"
            f"<td>{escape(str(risk.get('impact') or 'N/A'))}</td>"
            f"<td>{escape(str(risk.get('probability') or 'N/A'))}</td>"
            f"<td>{escape(str(risk.get('description') or ''))}</td>"
            f"<td>{escape(str(risk.get('mitigation') or ''))}</td>"
            "</tr>"
        )
    risks_html = (
        "<table class='table compact'><tr><th>Risk</th><th>Impact</th><th>Probability</th><th>Description</th><th>Mitigation</th></tr>"
        + "".join(risks_rows)
        + "</table>"
    ) if risks_rows else "<p class='muted'>No risk register available.</p>"

    assumptions_rows = []
    for item in assumptions[:5]:
        if not isinstance(item, dict):
            continue
        assumptions_rows.append(
            "<tr>"
            f"<td>{escape(str(item.get('key') or ''))}</td>"
            f"<td>{escape(shorten_text(item.get('value'), 52))}</td>"
            f"<td>{escape(str(item.get('unit') or ''))}</td>"
            f"<td>{escape(shorten_text(item.get('source'), 58))}</td>"
            f"<td>{escape(str(item.get('confidence') or ''))}</td>"
            "</tr>"
        )
    assumptions_html = (
        "<table class='table compact'><tr><th>Assumption</th><th>Value</th><th>Unit</th><th>Source</th><th>Confidence</th></tr>"
        + "".join(assumptions_rows)
        + "</table>"
    ) if assumptions_rows else "<p class='muted'>No assumptions listed.</p>"

    source_artifacts = provenance.get("source_artifacts") if isinstance(provenance.get("source_artifacts"), list) else []
    source_html = (
        "<ul>" + "".join(
            f"<li>{escape(str((artifact or {}).get('type') or 'artifact'))} #{escape(str((artifact or {}).get('id') or ''))}</li>"
            for artifact in source_artifacts[:8]
            if isinstance(artifact, dict)
        ) + "</ul>"
    ) if source_artifacts else "<p class='muted'>No source artifacts listed.</p>"

    external_dependencies_html = bullet_html(
        resources.get("external_dependencies"),
        max_items=8,
        empty_text="No external dependencies listed.",
    )
    next_actions_html = bullet_html(
        stakeholder_ask.get("next_30_days"),
        max_items=8,
        empty_text="No next actions listed.",
    )
    team_required_html = bullet_html(
        stakeholder_ask.get("team_required"),
        max_items=8,
        empty_text="No team requirement listed.",
    )
    critical_path_html = bullet_html(
        blueprint.get("critical_path"),
        max_items=6,
        empty_text="No critical path listed.",
    )
    gates_html = bullet_html(blueprint.get("gates"), max_items=6, empty_text="No gates listed.")
    kill_criteria_html = bullet_html(
        blueprint.get("kill_criteria"),
        max_items=6,
        empty_text="No kill criteria listed.",
    )
    total_slides = 7 if recovery_enabled else 6
    recovery_slide_number = 6 if recovery_enabled else None
    source_slide_number = 7 if recovery_enabled else 6
    recovery_approval_html = (
        f"<p style='margin-top:8px;'><strong>Approval gate:</strong> {recovery_approval_gate}</p>"
        if recovery_approval_gate
        else ""
    )
    recovery_slide_html = (
        ""
        if not recovery_enabled
        else f"""
      <section class=\"slide\">
        <div class=\"header\">
          <h2>Profitability Recovery</h2>
          <div class=\"meta\">Slide {recovery_slide_number} of {total_slides}</div>
        </div>
        <div class=\"grid-2\">
          <div class=\"panel\">
            <h3>Profitability Recovery Plan</h3>
            <p><strong>Monthly gap to close:</strong> {recovery_gap}</p>
            <h3 style=\"margin-top:8px;\">Profitability Levers</h3>
            {recovery_levers_html}
          </div>
          <div class=\"panel\">
            <h3>Recovery Scenarios</h3>
            {recovery_scenarios_html}
            {recovery_approval_html}
          </div>
        </div>
      </section>
      """
    )
    source_slide_html = f"""
      <section class=\"slide\">
        <div class=\"header\">
          <h2>Source Artifacts and Generation Metadata</h2>
          <div class=\"meta\">Slide {source_slide_number} of {total_slides}</div>
        </div>
        <div class=\"panel\">
          <h3>Source Artifacts</h3>
          {source_html}
        </div>
        <div class=\"panel\" style=\"margin-top:8px;\">
          <h3>Generation Metadata</h3>
          <p><strong>Model:</strong> {escape(str(saved.get("model") or "N/A"))}</p>
          <p><strong>Formula Version:</strong> {escape(str(provenance.get("formula_version") or "N/A"))}</p>
          <p><strong>Generator Version:</strong> {escape(str(provenance.get("generator_version") or "N/A"))}</p>
        </div>
        <div class=\"footer\">
          <span>IdeaGen Execution Plan</span>
          <span>Prepared for stakeholder review</span>
        </div>
      </section>
    """

    return f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8" />
      <style>
        @page {{ size: A4 landscape; margin: 0.32in; }}
        body {{ margin: 0; font-family: Arial, sans-serif; color: #0f172a; }}
        .slide {{
          page-break-after: always;
          min-height: 6.9in;
          border: 1px solid #d9e2f3;
          border-radius: 12px;
          padding: 14px 16px;
          background: linear-gradient(180deg, #f8fbff 0%, #ffffff 100%);
          box-sizing: border-box;
        }}
        .slide:last-child {{ page-break-after: auto; }}
        .header {{
          display: flex;
          justify-content: space-between;
          align-items: baseline;
          gap: 12px;
          margin-bottom: 8px;
        }}
        .header h1 {{ margin: 0; font-size: 24px; }}
        .header .meta {{ font-size: 11px; color: #475467; text-align: right; }}
        h2 {{ margin: 0 0 6px 0; font-size: 18px; }}
        h3 {{ margin: 0 0 6px 0; font-size: 13px; }}
        p {{ margin: 0 0 7px 0; font-size: 12px; line-height: 1.4; }}
        .subtle {{ color: #475467; font-size: 11px; }}
        .grid-2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }}
        .grid-3 {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; }}
        .panel {{
          border: 1px solid #dbe4f3;
          border-radius: 10px;
          background: #ffffff;
          padding: 8px;
          box-sizing: border-box;
          break-inside: avoid;
          page-break-inside: avoid;
        }}
        .kpi-card {{
          border: 1px solid #dbe4f3;
          border-radius: 10px;
          padding: 8px;
          background: #ffffff;
        }}
        .kpi-label {{ color: #64748b; font-size: 10px; text-transform: uppercase; letter-spacing: 0.03em; }}
        .kpi-value {{ margin-top: 2px; font-size: 20px; font-weight: 700; }}
        .table {{ width: 100%; border-collapse: collapse; font-size: 11px; table-layout: fixed; break-inside: avoid; page-break-inside: avoid; }}
        .table.compact {{ font-size: 9.5px; }}
        .table.compact th, .table.compact td {{ padding: 3px 4px; }}
        .table th, .table td {{
          border: 1px solid #dfe6f3;
          padding: 5px 6px;
          vertical-align: top;
          text-align: left;
          word-break: break-word;
          overflow-wrap: anywhere;
          break-inside: avoid;
          page-break-inside: avoid;
        }}
        .table th {{ background: #edf3ff; font-weight: 700; }}
        .num {{ text-align: right !important; font-variant-numeric: tabular-nums; }}
        ul {{ margin: 5px 0 0 14px; padding: 0; font-size: 11px; }}
        li {{ margin: 0 0 3px 0; }}
        .muted {{ color: #6b7280; font-size: 11px; }}
        .footer {{ margin-top: 8px; font-size: 10px; color: #64748b; display: flex; justify-content: space-between; }}
      </style>
    </head>
    <body>
      <section class="slide">
        <div class="header">
          <h1>Execution Plan - Stakeholder Deck</h1>
          <div class="meta">Slide 1 of {total_slides}<br/>Saved {created_at}</div>
        </div>
        <p class="subtle">Source {source_text} | Scenario {scenario_text} | Horizon {horizon_text} months | Currency {currency}</p>
        <p class="subtle"><strong>Report Title:</strong> {report_title}</p>
        <p><strong>Recommendation:</strong> {go_no_go} | <strong>Confidence:</strong> {confidence_text} | <strong>Winning concept:</strong> {winner_title} ({winner_model})</p>
        <p><strong>Financial Gate Status:</strong> {support_status} | <strong>Year 1 Net:</strong> {support_year_1} | <strong>Expected Year 1 Net:</strong> {support_expected} | <strong>Break-even:</strong> Month {support_break_even}</p>
        <p>{thesis}</p>
        <div class="grid-3" style="margin-top:8px;">
          <div class="kpi-card"><div class="kpi-label">Setup Cost</div><div class="kpi-value">{setup_total}</div></div>
          <div class="kpi-card"><div class="kpi-label">Budget Ask</div><div class="kpi-value">{ask_budget}</div></div>
          <div class="kpi-card"><div class="kpi-label">Break-even Month</div><div class="kpi-value">{break_even}</div></div>
          <div class="kpi-card"><div class="kpi-label">Base Year 1 Revenue</div><div class="kpi-value">{year1_revenue}</div></div>
          <div class="kpi-card"><div class="kpi-label">Base Year 1 Net</div><div class="kpi-value">{year1_profit}</div></div>
          <div class="kpi-card"><div class="kpi-label">ARPU / Unit COGS</div><div class="kpi-value">{arpu} / {unit_cogs_value}</div></div>
        </div>
        <div class="panel" style="margin-top:8px;background:#eef6ff;border-color:#bfdbfe;">
          <h3>Business Terms and Definitions</h3>
          <p><strong>ARPU</strong> = average revenue per customer/month · <strong>ICP</strong> = ideal customer profile ({escape(icp_plain_text)}) · <strong>OpEx</strong> = operating costs · <strong>COGS</strong> = delivery cost per customer · <strong>Break-even</strong> = first month cumulative profit is zero or positive.</p>
        </div>
        {(f"""
        <div class=\"panel\" style=\"margin-top:8px;background:#fff7ed;border-color:#f59e0b;\">
          <h3>{disclaimer_title}</h3>
          <p>{disclaimer_message}</p>
          <p class=\"subtle\"><strong>Data basis:</strong> {disclaimer_basis}{f" &nbsp;|&nbsp; <strong>Updated:</strong> {disclaimer_updated}" if disclaimer_updated else ""}</p>
        </div>
        """ if disclaimer_message else "")}
        <div class="grid-2" style="margin-top:8px;">
          <div class="panel">
            <h3>Decision Required</h3>
            <p>{escape(str(stakeholder_ask.get("decision_required") or "N/A"))}</p>
            <h3 style="margin-top:8px;">Gate Blockers</h3>
            {support_reasons_html}
          </div>
          <div class="panel">
            <h3>Funnel Assumptions</h3>
            <p>{escape(funnel_text)}</p>
            <h3 style="margin-top:8px;">Required Actions Before Approval</h3>
            {support_actions_html}
          </div>
        </div>
      </section>

      <section class="slide">
        <div class="header">
          <h2>Execution Blueprint and Governance</h2>
          <div class="meta">Slide 2 of {total_slides}</div>
        </div>
        <div class="panel">
          <h3>Phase Plan</h3>
          {phase_html}
        </div>
        <div class="grid-3" style="margin-top:8px;">
          <div class="panel"><h3>Critical Path</h3>{critical_path_html}</div>
          <div class="panel"><h3>Stage Gates</h3>{gates_html}</div>
          <div class="panel"><h3>Kill Criteria</h3>{kill_criteria_html}</div>
        </div>
      </section>

      <section class="slide">
        <div class="header">
          <h2>Financial Model</h2>
          <div class="meta">Slide 3 of {total_slides}</div>
        </div>
        <div class="grid-2">
          <div class="panel">
            <h3>Scenario Outcomes</h3>
            {scenario_html}
          </div>
          <div class="panel">
            <h3>Cost Drivers</h3>
            {setup_breakdown_html}
            <h3 style="margin-top:8px;">OpEx Profile</h3>
            {opex_profile_html}
            <h3 style="margin-top:8px;">Unit COGS Components</h3>
            {unit_cogs_html}
          </div>
        </div>
        <div class="panel" style="margin-top:8px;">
          <h3>Monthly Projection (8-month snapshot)</h3>
          {projection_html}
          <h3 style="margin-top:8px;">Sensitivity Analysis</h3>
          {sensitivity_html}
          {f"<p class='subtle'>{sensitivity_note}</p>" if sensitivity_note else ""}
        </div>
      </section>

      <section class="slide">
        <div class="header">
          <h2>Operating Plan and Delivery Readiness</h2>
          <div class="meta">Slide 4 of {total_slides}</div>
        </div>
        <div class="grid-2">
          <div class="panel">
            <h3>Team Resource Plan</h3>
            {role_html}
          </div>
          <div class="panel">
            <h3>Tooling Stack</h3>
            {tooling_html}
          </div>
        </div>
        <div class="grid-3" style="margin-top:8px;">
          <div class="panel"><h3>External Dependencies</h3>{external_dependencies_html}</div>
          <div class="panel"><h3>Team Required</h3>{team_required_html}</div>
          <div class="panel"><h3>Next 30 Days</h3>{next_actions_html}</div>
        </div>
      </section>

      <section class="slide">
        <div class="header">
          <h2>Risk and Assumptions</h2>
          <div class="meta">Slide 5 of {total_slides}</div>
        </div>
        <div class="panel">
          <h3>Risk Register</h3>
          {risks_html}
        </div>
        <div class="panel" style="margin-top:8px;">
          <h3>Assumptions</h3>
          {assumptions_html}
        </div>
      </section>
      {recovery_slide_html}
      {source_slide_html}
    </body>
    </html>
    """


def html_to_pdf_bytes(html_content: str) -> bytes:
    return HTML(string=html_content).write_pdf()
