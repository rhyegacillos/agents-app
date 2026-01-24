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


def html_to_pdf_bytes(html_content: str) -> bytes:
    return HTML(string=html_content).write_pdf()
