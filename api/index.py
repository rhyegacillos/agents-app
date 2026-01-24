from calendar import c
import os
import asyncio
from pathlib import Path
import re
from token import OP
from fastapi import FastAPI, Depends, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi_clerk_auth import ClerkConfig, ClerkHTTPBearer, HTTPAuthorizationCredentials
from openai import AsyncOpenAI
from google import genai
from dotenv import load_dotenv
import resend
import io
from weasyprint import HTML
from pydantic import BaseModel, Field
from typing import List, Dict
from datetime import datetime
from html import escape
from instructions.instructions_prompt import system_instructions, user_instruction
from agent.email_agent import run_email_agent
from agent.recommend_combination_agent import recommend_combination_agent
from agent.compare_results_agent import compare_results_agent, _build_decision_memo
from agent.rank_report_agent import rank_report_agent
from agent.idea_generation_agent import generate_idea_agentic


import json
from typing import Any, Optional

import logging
import uuid
try:
    from . import db
except ImportError:
    import db


# --- App Setup ---
load_dotenv()
app = FastAPI()

@app.on_event("startup")
def startup_event():
    db.init_db()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


# --- API Clients & Config ---
clerk_config = ClerkConfig(jwks_url=os.getenv("CLERK_JWKS_URL"))
clerk_guard = ClerkHTTPBearer(clerk_config)
openai_client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
deepseek_client = AsyncOpenAI(api_key=os.getenv("DEEPSEEK_API_KEY"), base_url=os.getenv("DEEPSEEK_API_URL"))
grok_client = AsyncOpenAI(api_key=os.getenv("GROK_API_KEY"), base_url=os.getenv("GROK_API_URL"))
google_client = AsyncOpenAI(api_key=os.getenv("GEMINI_API_KEY"), base_url=os.getenv("GEMINI_API_URL"))
resend.api_key = os.getenv("RESEND_API_KEY")
GROK_MODEL = "grok-4-1-fast-reasoning"
GEMINI_MODEL = "gemini-2.5-pro"
OPENAI_MODEL = "gpt-5-mini"
DEEPSEEK_MODEL = "deepseek-chat"
GROK_MODEL_FALLBACK = "grok-4-fast-non-reasoning"
GEMINI_MODEL_FALLBACK = "gemini-2.5-flash"
OPENAI_MODEL_FALLBACK = "gpt-4.1-mini"
DEEPSEEK_MODEL_FALLBACK = "deepseek-chat-v3.1"



FALLBACK_CHAINS = {
    # Grok
    GROK_MODEL: ("grok", [GROK_MODEL, GROK_MODEL_FALLBACK]),
    # Gemini
    GEMINI_MODEL: ("gemini", [GEMINI_MODEL, GEMINI_MODEL_FALLBACK]),
    # OpenAI    
    OPENAI_MODEL: ("openai", [OPENAI_MODEL, OPENAI_MODEL_FALLBACK]),
    # DeepSeek
    DEEPSEEK_MODEL: ("deepseek", [DEEPSEEK_MODEL, DEEPSEEK_MODEL_FALLBACK]),    
}


try:
    gemini_client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
except Exception as e:
    print(f"Error configuring Gemini: {e}")

# --- Pydantic Models ---
class ReportData(BaseModel):
    industry: str
    constraints: List[str] = []
    tone: str
    models: List[str]
    results: Dict[str, str]

    @property
    def constraints_text(self) -> str:
        if self.constraints:
            return ", ".join(self.constraints)
        return "None"

class IdeaRequest(BaseModel):
    industry: str
    constraints: List[str] = []
    tone: str
    models: Optional[List[str]] = None
    temperature: Optional[float] = 0.7
    top_p: Optional[float] = 0.9


class EmailRequest(ReportData):
    to_email: str

class SaveResultsRequest(BaseModel):
    industry: str
    constraints: List[str] = []
    tone: str
    models: List[str]
    results: Dict[str, str]

class CompareResultsRequest(BaseModel):
    run_a_id: int
    run_b_id: int

class AgenticReportRequest(BaseModel):
    run_ids: List[int] = Field(default_factory=list)
    output: str
    email: Optional[str] = None
    include_all_runs: bool = False
    include_diff_memo: bool = False

class PersonaOption(BaseModel):
    id: str
    label: str

class RecommendCombinationRequest(BaseModel):
    industry: str
    constraints: List[str]
    personas: List[PersonaOption]

class RecommendCombinationResponse(BaseModel):
    recommended_constraints: List[str]
    recommended_persona: str
    reason_html: str
    usage: Optional[Dict[str, int]] = None


def build_pdf_filename(industry: str) -> str:
    safe_industry = re.sub(r"[^a-zA-Z0-9_-]+", "_", industry.strip())
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    return f"IdeaGen_{safe_industry}_{ts}.pdf"

# --- PDF Generation ---
def create_report_html(data: "ReportData") -> str:
    model_names = {
        OPENAI_MODEL: "OpenAI",
        GEMINI_MODEL: "Google",
        DEEPSEEK_MODEL: "DeepSeek",
        GROK_MODEL: "Grok",
    }

    left_brand = "IdeaGen"
    right_title = "Business Idea Generation Report"
    right_date = datetime.now().strftime("%a, %B %d, %Y")

    # comma-separated, no trailing comma
    chips_html = ", ".join(
        f'<span class="chip">{escape(model_names.get(m, m))}</span>'
        for m in data.models
    )

    # Results blocks (WeasyPrint-friendly; also OK in browsers)
    results_parts = []
    for idx, model_id in enumerate(data.models, start=1):
        result_content = data.results.get(model_id, "<p>No result generated.</p>")
        model_display_name = escape(model_names.get(model_id, model_id))

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

    # IMPORTANT: all literal { } inside this f-string are escaped as {{ }}
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

        {results_html}

        </body>
        </html>
        """


def create_agentic_report_html(
    runs: List[Dict[str, Any]],
    report: Dict[str, Any],
    diff_memo: Optional[Dict[str, Any]] = None,
    diff_memo_missing: bool = False,
) -> str:
    def friendly_model_label(model_id: Any) -> str:
        raw = str(model_id or "")
        lower = raw.lower()
        if lower.startswith("gpt-") or lower.startswith("o-"):
            return "OpenAI"
        if lower.startswith("gemini-"):
            return "Google Gemini"
        if lower.startswith("deepseek-"):
            return "Deepseek"
        if lower.startswith("grok-"):
            return "Grok"
        return raw

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
            rows.append(
                f"<tr><td>{escape(run_label(run))}</td><td>{score}</td><td>{rationale}</td></tr>"
            )
        ranked_html = (
            "<table class='rank-table'>"
            "<tr><th>Run</th><th>Score</th><th>Rationale</th></tr>"
            + "".join(rows)
            + "</table>"
        )

    def list_html(items: List[str]) -> str:
        if not items:
            return "<p class='muted'>None</p>"
        return "<ul>" + "".join(f"<li>{escape(str(i))}</li>" for i in items) + "</ul>"

    diff_memo_html = ""
    if diff_memo_missing:
        diff_memo_html = (
            "<h2>Diff memo</h2>"
            "<p class='muted'>Diff memo not available. Run Diff Mode first.</p>"
        )
    elif diff_memo:
        decision = escape(str(diff_memo.get("decision", "") or ""))
        memo_summary = escape(str(diff_memo.get("summary", "") or ""))
        memo_rationale = escape(str(diff_memo.get("rationale", "") or ""))
        memo_key_changes = list_html(diff_memo.get("key_changes", []) or [])
        memo_risks = list_html(diff_memo.get("risks", []) or [])
        memo_next_steps = list_html(diff_memo.get("next_steps", []) or [])
        diff_memo_html = f"""
        <h2>Diff memo</h2>
        <div class="summary">
          <strong>Decision</strong>
          <p>{decision}</p>
          <strong>Summary</strong>
          <p>{memo_summary}</p>
        </div>
        <h3>Key changes</h3>
        {memo_key_changes}
        <h3>Rationale</h3>
        <p>{memo_rationale or '<span class="muted">None</span>'}</p>
        <h3>Risks</h3>
        {memo_risks}
        <h3>Next steps</h3>
        {memo_next_steps}
        """

    run_sections = []
    for run in runs:
        constraints = run.get("constraints") or []
        models = run.get("models") or list((run.get("results") or {}).keys())
        display_models = [friendly_model_label(m) for m in models]
        results = run.get("results") or {}
        results_html = ""
        for model_id, html in results.items():
            model_label = friendly_model_label(model_id)
            results_html += (
                "<div class='result-card'>"
                f"<div class='result-title'>{escape(model_label)}</div>"
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
          font-size: 12px;
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
        }}
        .rank-table th, .rank-table td {{
          border: 1px solid #e5e7eb;
          padding: 6px;
          text-align: left;
          vertical-align: top;
        }}
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
      <h1>IdeaGen Rank Report</h1>
      <div class="summary">
        <strong>Summary</strong>
        <p>{summary}</p>
      </div>

      {diff_memo_html}

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

# --- PDF Conversion ---
def html_to_pdf_bytes(html_content: str) -> bytes:
    pdf_bytes = HTML(string=html_content).write_pdf()
    return pdf_bytes

# --- AI Generation Helpers ---
async def generate_openai_compatible(client, model, system_instruction, user_content, temperature=0.7, top_p=0.9):
    try:
        r = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": user_content},
            ],
            temperature=temperature,
            top_p=top_p,
        )
        usage = {}
        if r.usage:
            usage = {
                "prompt_tokens": r.usage.prompt_tokens,
                "completion_tokens": r.usage.completion_tokens,
                "total_tokens": r.usage.total_tokens
            }
        return r.choices[0].message.content or "", usage
    except Exception as e:
        msg = str(e).lower()
        # Handle "Unsupported value" or invalid param errors by retrying with defaults
        if "unsupported value" in msg or "parameter" in msg or "temperature" in msg:
            print(f"Model {model} does not support custom params. Retrying with defaults. Error: {e}")
            r = await client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_instruction},
                    {"role": "user", "content": user_content},
                ]
            )
            usage = {}
            if r.usage:
                usage = {
                    "prompt_tokens": r.usage.prompt_tokens,
                    "completion_tokens": r.usage.completion_tokens,
                    "total_tokens": r.usage.total_tokens
                }
            return r.choices[0].message.content or "", usage
        raise e


async def generate_gemini(model, system_instruction, user_content, temperature=0.7, top_p=0.9):
    try:
        config = genai.types.GenerateContentConfig(
            temperature=temperature,
            top_p=top_p
        )
        r = await gemini_client.aio.models.generate_content(
            model=model,
            contents=f"{system_instruction}\n\n{user_content}",
            config=config
        )
        usage = {}
        if r.usage_metadata:
            usage = {
                "prompt_tokens": r.usage_metadata.prompt_token_count,
                "completion_tokens": r.usage_metadata.candidates_token_count,
                "total_tokens": r.usage_metadata.total_token_count
            }
        return r.text, usage
    except Exception as e:
        if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
            try:
                fallback_model = GEMINI_MODEL_FALLBACK
                config = genai.types.GenerateContentConfig(
                    temperature=temperature,
                    top_p=top_p
                )
                r = await gemini_client.aio.models.generate_content(
                    model=fallback_model,
                    contents=f"{system_instruction}\n\n{user_content}",
                    config=config
                )
                usage = {}
                if r.usage_metadata:
                    usage = {
                        "prompt_tokens": r.usage_metadata.prompt_token_count,
                        "completion_tokens": r.usage_metadata.candidates_token_count,
                        "total_tokens": r.usage_metadata.total_token_count
                    }
                return r.text, usage
            except Exception as e2:
                return f"Error - Limit Reach: {e2}", {}
        return f"Error: {e}", {}


def _extract_json_object(text: str) -> Optional[dict]:
    if not text:
        return None
    text = text.strip()

    # direct JSON
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass

    # try to extract first {...} block
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = text[start:end+1]
        try:
            obj = json.loads(candidate)
            if isinstance(obj, dict):
                return obj
        except Exception:
            return None

    return None

PREMIUM_PLANS = {
    "u:premium_subscription",
    # keep these if you might use them later:
    "u:premium",
    "u:pro",
    "u:premium_user",
}

SAVED_RESULTS_LIMIT_FREE_BYTES = int(os.getenv("SAVED_RESULTS_LIMIT_FREE_BYTES", str(100 * 1024 * 1024)))
SAVED_RESULTS_LIMIT_PREMIUM_BYTES = int(os.getenv("SAVED_RESULTS_LIMIT_PREMIUM_BYTES", str(1024 * 1024 * 1024)))

def get_user_plan(creds):
    decoded = getattr(creds, "decoded", {}) or {}
    return decoded.get("pla") or "u:free_user"

def is_premium(creds) -> bool:
    plan = get_user_plan(creds)
    return plan in PREMIUM_PLANS


def require_premium(creds: HTTPAuthorizationCredentials):
    if not is_premium(creds):
        raise HTTPException(status_code=402, detail="Premium required")



# --- API Endpoints ---
# index.py (agentic /api replacement)
# index.py - updated /api endpoint using FALLBACK_CHAINS + agentic generation + partial success


@app.get("/api/subscription")
async def subscription(creds=Depends(clerk_guard)):
    decoded = getattr(creds, "decoded", {}) or {}
    user_id = decoded.get("sub")
    plan = decoded.get("pla") or "u:free_user"
    
    # print(f"subscription poll: {user_id}") # Optional: debug log

    # Sync plan/stats
    conn = db.get_db()
    db.get_or_create_user(conn, user_id, plan)
    conn.close()
    
    stats = db.get_user_stats(user_id)
    
    return {
        "user_id": user_id,
        "plan": plan,
        "is_premium": plan in PREMIUM_PLANS,
        "status": decoded.get("sts"),
        "usage": stats
    }


@app.post("/api/saved-results")
async def save_results(request: SaveResultsRequest, creds: HTTPAuthorizationCredentials = Depends(clerk_guard)):
    user_id = creds.decoded.get("sub")
    plan = get_user_plan(creds)
    if not request.results:
        raise HTTPException(status_code=400, detail="No results to save.")
    current_bytes = db.get_saved_results_usage_bytes(user_id)
    limit_bytes = SAVED_RESULTS_LIMIT_PREMIUM_BYTES if plan in PREMIUM_PLANS else SAVED_RESULTS_LIMIT_FREE_BYTES
    payload_bytes = (
        len((request.industry or "").encode("utf-8"))
        + len((request.tone or "").encode("utf-8"))
        + len(json.dumps(request.constraints or []).encode("utf-8"))
        + len(json.dumps(request.models or []).encode("utf-8"))
        + len(json.dumps(request.results or {}).encode("utf-8"))
    )
    if current_bytes + payload_bytes > limit_bytes:
        raise HTTPException(
            status_code=413,
            detail="Saved results storage limit reached. Delete older items to save new ones.",
        )
    return db.save_results(
        user_id=user_id,
        industry=request.industry,
        tone=request.tone,
        constraints=request.constraints,
        models=request.models,
        results=request.results,
    )


@app.get("/api/saved-results")
async def list_saved_results(limit: int = 6, creds: HTTPAuthorizationCredentials = Depends(clerk_guard)):
    user_id = creds.decoded.get("sub")
    plan = get_user_plan(creds)
    limit_bytes = SAVED_RESULTS_LIMIT_PREMIUM_BYTES if plan in PREMIUM_PLANS else SAVED_RESULTS_LIMIT_FREE_BYTES
    usage_bytes = db.get_saved_results_usage_bytes(user_id)
    return {
        "results": db.list_saved_results(user_id, limit=limit),
        "usage_bytes": usage_bytes,
        "limit_bytes": limit_bytes,
    }


@app.get("/api/saved-results/{saved_id}")
async def get_saved_result(saved_id: int, creds: HTTPAuthorizationCredentials = Depends(clerk_guard)):
    user_id = creds.decoded.get("sub")
    result = db.get_saved_result(user_id, saved_id)
    if not result:
        raise HTTPException(status_code=404, detail="Saved result not found.")
    return result


@app.delete("/api/saved-results/{saved_id}")
async def delete_saved_result(saved_id: int, creds: HTTPAuthorizationCredentials = Depends(clerk_guard)):
    user_id = creds.decoded.get("sub")
    deleted = db.delete_saved_result(user_id, saved_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Saved result not found.")
    return {"status": "deleted"}


@app.post("/api/compare-results")
async def compare_results(request: CompareResultsRequest, creds: HTTPAuthorizationCredentials = Depends(clerk_guard)):
    user_id = creds.decoded.get("sub")
    plan = get_user_plan(creds)
    allowed, msg = db.check_token_limit(user_id, plan)
    if not allowed:
        raise HTTPException(status_code=429, detail=msg)
    if request.run_a_id == request.run_b_id:
        raise HTTPException(status_code=400, detail="Choose two different saved results to compare.")

    cached = db.get_saved_comparison(user_id, request.run_a_id, request.run_b_id)
    if cached:
        return cached

    run_a = db.get_saved_result(user_id, request.run_a_id)
    run_b = db.get_saved_result(user_id, request.run_b_id)
    if not run_a or not run_b:
        raise HTTPException(status_code=404, detail="Saved result not found.")

    request_id = str(uuid.uuid4())
    result = await compare_results_agent(
        generate=generate_openai_compatible,
        extract_json=_extract_json_object,
        client=deepseek_client,
        model=DEEPSEEK_MODEL,
        run_a=run_a,
        run_b=run_b,
        max_attempts=2,
        request_id=request_id,
    )

    comparison = result.get("comparison", {}) or {}
    winner = str(comparison.get("winner", "tie")).upper()
    winner_run_id = None
    if winner == "A":
        winner_run_id = request.run_a_id
    elif winner == "B":
        winner_run_id = request.run_b_id
    comparison["winner"] = winner

    saved = db.save_comparison(
        user_id=user_id,
        run_a_id=request.run_a_id,
        run_b_id=request.run_b_id,
        winner_run_id=winner_run_id,
        comparison=comparison,
        model=DEEPSEEK_MODEL,
    )

    usage = result.get("usage", {})
    if usage and usage.get("total_tokens"):
        db.track_token_usage(user_id, usage.get("total_tokens", 0))

    return {
        "comparison_id": saved.get("id"),
        "created_at": saved.get("created_at"),
        "run_a_id": request.run_a_id,
        "run_b_id": request.run_b_id,
        "winner_run_id": winner_run_id,
        "comparison": comparison,
        "cached": False,
    }


@app.get("/api/compare-results")
async def list_compare_results(limit: int = 6, creds: HTTPAuthorizationCredentials = Depends(clerk_guard)):
    user_id = creds.decoded.get("sub")
    return {"comparisons": db.list_saved_comparisons(user_id, limit=limit)}


@app.get("/api/agentic-reports")
async def list_agentic_reports(limit: int = 6, creds: HTTPAuthorizationCredentials = Depends(clerk_guard)):
    user_id = creds.decoded.get("sub")
    return {"reports": db.list_saved_agentic_reports(user_id, limit=limit)}


@app.get("/api/agentic-reports/{report_id}/pdf")
async def download_agentic_report(report_id: int, creds: HTTPAuthorizationCredentials = Depends(clerk_guard)):
    user_id = creds.decoded.get("sub")
    saved = db.get_saved_agentic_report_by_id(user_id, report_id)
    if not saved:
        raise HTTPException(status_code=404, detail="Report not found.")
    snapshot_runs = saved.get("runs_snapshot") or []
    diff_memo = saved.get("diff_memo")
    diff_memo_missing = bool(saved.get("diff_memo_missing"))
    if snapshot_runs:
        ordered_runs = snapshot_runs
        missing_runs = False
    else:
        raw_run_ids = saved.get("run_ids") or []
        run_ids = []
        for run_id in raw_run_ids:
            try:
                run_ids.append(int(run_id))
            except (TypeError, ValueError):
                continue
        runs = db.get_saved_results_by_ids(user_id, run_ids)
        run_map = {r.get("id"): r for r in runs if r.get("id") is not None}
        ordered_runs = [run_map[rid] for rid in run_ids if rid in run_map]
        missing_runs = len(ordered_runs) != len(run_ids)
    report = saved.get("report", {}) or {}
    html = create_agentic_report_html(
        ordered_runs,
        report,
        diff_memo=diff_memo if isinstance(diff_memo, dict) else None,
        diff_memo_missing=diff_memo_missing,
    )
    pdf_bytes = html_to_pdf_bytes(html)
    headers = {"Content-Disposition": "attachment;filename=IdeaGen_Rank_Report.pdf"}
    if missing_runs:
        headers["X-Report-Runs-Missing"] = "true"
    return StreamingResponse(io.BytesIO(pdf_bytes), media_type="application/pdf", headers=headers)


@app.post("/api/agentic-report")
async def agentic_report(request: AgenticReportRequest, creds: HTTPAuthorizationCredentials = Depends(clerk_guard)):
    user_id = creds.decoded.get("sub")
    plan = get_user_plan(creds)
    request_id = str(uuid.uuid4())
    allowed, msg = db.check_token_limit(user_id, plan)
    if not allowed:
        raise HTTPException(status_code=429, detail=msg)
    output = (request.output or "").lower()
    if output not in {"pdf", "email", "both"}:
        raise HTTPException(status_code=400, detail="Output must be pdf, email, or both.")
    if output in {"email", "both"} and not request.email:
        raise HTTPException(status_code=400, detail="Email is required for email delivery.")
    include_all_runs = bool(request.include_all_runs)
    include_diff_memo = bool(request.include_diff_memo)
    run_ids = list(dict.fromkeys(request.run_ids or []))

    if include_all_runs:
        runs = db.list_saved_results_full(user_id)
        run_ids = [r.get("id") for r in runs if r.get("id") is not None]
        if not run_ids:
            raise HTTPException(status_code=400, detail="No saved runs available for a report.")
    else:
        if not run_ids:
            raise HTTPException(status_code=400, detail="Select at least one saved run.")
        if len(run_ids) > 5:
            raise HTTPException(status_code=400, detail="Select up to 5 runs per report.")
        runs = db.get_saved_results_by_ids(user_id, run_ids)
        if len(runs) != len(run_ids):
            raise HTTPException(status_code=404, detail="One or more saved runs were not found.")

    if include_diff_memo and len(run_ids) != 2:
        raise HTTPException(status_code=400, detail="Diff memo requires exactly two runs.")

    if include_all_runs:
        snapshot_runs = runs
    else:
        run_map = {r.get("id"): r for r in runs if r.get("id") is not None}
        snapshot_runs = [run_map[rid] for rid in run_ids if rid in run_map]

    run_ids_key = ",".join(str(i) for i in sorted(run_ids))
    cached = db.get_saved_agentic_report(user_id, run_ids_key)

    diff_memo = None
    diff_memo_missing = False
    if include_diff_memo:
        cached_comparison = db.get_saved_comparison(user_id, run_ids[0], run_ids[1])
        if cached_comparison:
            comparison = cached_comparison.get("comparison", {}) or {}
            memo = comparison.get("decision_memo")
            if isinstance(memo, dict) and memo:
                diff_memo = memo
            elif comparison:
                diff_memo = _build_decision_memo(comparison)
        if not diff_memo:
            diff_memo_missing = True

    if cached:
        report = cached.get("report", {}) or {}
        cached_flag = True
        cached_id = cached.get("id")
        if cached_id:
            needs_snapshot = not (cached.get("runs_snapshot") or [])
            needs_diff_memo = include_diff_memo and diff_memo and not cached.get("diff_memo")
            needs_missing_flag = include_diff_memo and diff_memo_missing and not cached.get("diff_memo_missing")
            if needs_snapshot or needs_diff_memo or needs_missing_flag:
                db.update_agentic_report_snapshot(
                    user_id,
                    cached_id,
                    runs_snapshot=snapshot_runs if needs_snapshot else None,
                    diff_memo=diff_memo if needs_diff_memo else None,
                    diff_memo_missing=diff_memo_missing if needs_missing_flag else None,
                )
    else:
        result = await rank_report_agent(
            generate=generate_openai_compatible,
            extract_json=_extract_json_object,
            client=deepseek_client,
            model=DEEPSEEK_MODEL,
            runs=runs,
            max_attempts=2,
            request_id=request_id,
        )
        report = result.get("report", {}) or {}
        usage = result.get("usage", {})
        if usage and usage.get("total_tokens"):
            db.track_token_usage(user_id, usage.get("total_tokens", 0))
        db.save_agentic_report(
            user_id=user_id,
            run_ids_key=run_ids_key,
            run_ids=run_ids,
            report=report,
            model=DEEPSEEK_MODEL,
            runs_snapshot=snapshot_runs,
            diff_memo=diff_memo if include_diff_memo else None,
            diff_memo_missing=diff_memo_missing if include_diff_memo else False,
        )
        cached_flag = False

    html = create_agentic_report_html(
        runs,
        report,
        diff_memo=diff_memo,
        diff_memo_missing=diff_memo_missing,
    )
    pdf_bytes = html_to_pdf_bytes(html)

    email_sent = False
    email_failed = False
    if output in {"email", "both"}:
        try:
            resend.Emails.send({
                "from": "no-reply@agentairg.site",
                "to": request.email,
                "subject": "IdeaGen Rank Report",
                "html": f"<div style='font-family: Arial, sans-serif; font-size:14px; color:#111;'>"
                        f"<p>Your rank report is attached.</p></div>",
                "attachments": [{
                    "filename": "IdeaGen_Rank_Report.pdf",
                    "content": list(pdf_bytes),
                }],
            })
            email_sent = True
        except Exception:
            logger.exception(
                "agentic_report.email_failed",
                extra={"request_id": request_id, "user_id": user_id},
            )
            email_failed = True
            if output == "email":
                raise HTTPException(status_code=502, detail="Email delivery failed. Please try again.")

    if output == "email":
        return {
            "status": "sent",
            "email_sent": email_sent,
            "email_failed": email_failed,
            "cached": cached_flag,
            "diff_memo_missing": diff_memo_missing,
        }

    headers = {"Content-Disposition": "attachment;filename=IdeaGen_Rank_Report.pdf"}
    if email_sent:
        headers["X-Report-Email-Sent"] = "true"
    if email_failed:
        headers["X-Report-Email-Failed"] = "true"
    if cached_flag:
        headers["X-Report-Cached"] = "true"
    if diff_memo_missing:
        headers["X-Diff-Memo-Missing"] = "true"
    return StreamingResponse(io.BytesIO(pdf_bytes), media_type="application/pdf", headers=headers)




@app.post("/api")
async def idea(request: IdeaRequest, creds: HTTPAuthorizationCredentials = Depends(clerk_guard)):
    request_id = str(uuid.uuid4())
    user_id = creds.decoded.get("sub")
    plan = get_user_plan(creds)
    print(f"user: {creds.decoded} temp: {request.temperature} top_p: {request.top_p}")

    allowed, msg = db.check_and_increment_api_call(user_id, plan)
    if not allowed:
        return JSONResponse(content={"error": msg}, status_code=429)

    constraints_text = ", ".join(request.constraints) if request.constraints else "None"
    system_instruction = system_instructions(request.tone)
    user_content = user_instruction(request.industry, constraints_text)

    def infer_provider(model_id: str) -> str:
        mid = (model_id or "").lower()
        if mid.startswith("grok-"):
            return "grok"
        if mid.startswith("gemini-"):
            return "gemini"
        if mid.startswith("deepseek-"):
            return "deepseek"
        if mid.startswith("gpt-") or mid.startswith("o-"):
            return "openai"
        return "unknown"

    async def run_one(model_id: str):
        provider, chain = FALLBACK_CHAINS.get(model_id, (infer_provider(model_id), [model_id]))
        
        temp = request.temperature if request.temperature is not None else 0.7
        tp = request.top_p if request.top_p is not None else 0.9

        print(f"model: {model_id} provider: {provider} chain: {chain} temp: {temp} top_p: {tp}")

        # Choose client + generator per provider
        if provider == "grok":
            client = grok_client
            async def gen(c, m, s, u): return await generate_openai_compatible(c, m, s, u, temperature=temp, top_p=tp)
        elif provider == "openai":
            client = openai_client
            async def gen(c, m, s, u): return await generate_openai_compatible(c, m, s, u, temperature=temp, top_p=tp)
        elif provider == "deepseek":
            client = deepseek_client
            async def gen(c, m, s, u): return await generate_openai_compatible(c, m, s, u, temperature=temp, top_p=tp)
        elif provider == "gemini":
            client = google_client

            async def gen(_client, _model, _sys, _user):
                return await generate_gemini(_model, _sys, _user, temperature=temp, top_p=tp)
        else:
            return {"text": "Error: Unknown model/provider.", "meta": {"fallback_used": True}}

        # Agentic generate (validate->retry) + model fallback (limit/timeout->lower model)
        return await generate_idea_agentic(
            generate=gen,
            client=client,
            provider=provider,
            model_chain=chain,
            system_instruction=system_instruction,
            user_content=user_content,
            max_attempts=3,
            request_id=request_id,
        )

    requested_labels = request.models or []
    models_to_run = []

    if not requested_labels:
        models_to_run = list(FALLBACK_CHAINS.keys())
    else:
        # Resolve labels (providers) to actual model IDs from FALLBACK_CHAINS
        for label in requested_labels:
            label_lower = label.lower()
            for model_id, (provider, _) in FALLBACK_CHAINS.items():
                if provider.lower() == label_lower:
                    models_to_run.append(model_id)
                    break
        
        # fallback if nothing matched (unlikely if frontend is synced, but safe)
        if not models_to_run:
            print(f"Warning: No valid models found for labels {requested_labels}")
            # Optional: return error or default to all? 
            # Let's default to all to be safe / nice
            models_to_run = list(FALLBACK_CHAINS.keys())

    tasks = [run_one(m) for m in models_to_run]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    out_results = {}
    total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    for model_id, r in zip(models_to_run, results):
        if isinstance(r, Exception):
            out_results[model_id] = "Error: Model call failed."
        else:
            out_results[model_id] = r.get("text", "Error: Empty response.")
            usage = r.get("usage", {})
            if usage:
                total_usage["prompt_tokens"] += usage.get("prompt_tokens", 0) or 0
                total_usage["completion_tokens"] += usage.get("completion_tokens", 0) or 0
                total_usage["total_tokens"] += usage.get("total_tokens", 0) or 0

    if total_usage["total_tokens"] > 0:
        db.track_token_usage(user_id, total_usage["total_tokens"])

    # Include updated limits in response
    stats = db.get_user_stats(user_id)
    total_usage["api_calls_count"] = stats["api_calls_count"]
    total_usage["emails_sent_count"] = stats["emails_sent_count"]

    return JSONResponse(content={"results": out_results, "usage": total_usage})


@app.post("/api/download-pdf")
def download_pdf(request: ReportData):
    report_html = create_report_html(request)
    pdf_bytes = html_to_pdf_bytes(report_html)
    return StreamingResponse(io.BytesIO(pdf_bytes), media_type="application/pdf", headers={"Content-Disposition": "attachment;filename=report.pdf"})


@app.post("/api/email")
async def send_email(
    request: EmailRequest,
    creds: HTTPAuthorizationCredentials = Depends(clerk_guard),
):
    user_id = creds.decoded.get("sub")
    plan = get_user_plan(creds)

    allowed, msg = db.check_and_increment_email(user_id, plan)
    if not allowed:
        return JSONResponse(content={"error": msg}, status_code=429)

    report_html = create_report_html(request)
    pdf_bytes = html_to_pdf_bytes(report_html)

    constraints_text = ", ".join(request.constraints) if request.constraints else "None"

    agent_result = await run_email_agent(
        to_email=request.to_email,
        industry=request.industry,
        constraints_text=constraints_text,
    )

    # enforced wrapper (final authority)
    final_html = f"""
    <div style="font-family: Arial, sans-serif; font-size:14px; color:#111;">
      {agent_result["html_body"]}
    </div>
    """

    filename = build_pdf_filename(request.industry)

    resend.Emails.send({
        "from": "no-reply@agentairg.site",
        "to": agent_result["to"],
        "subject": agent_result["subject"],
        "html": final_html,
        "attachments": [{
            "filename": filename,
            "content": list(pdf_bytes),
        }],
    })

    return {
        "status": "sent",
        "subject": agent_result["subject"],
    }



import uuid

@app.post("/api/recommend-combination", response_model=RecommendCombinationResponse)
async def recommend_combination(
    request: RecommendCombinationRequest,
    creds: HTTPAuthorizationCredentials = Depends(clerk_guard)
):
    require_premium(creds)
    
    user_id = creds.decoded.get("sub")
    plan = get_user_plan(creds)

    allowed, msg = db.check_and_increment_api_call(user_id, plan)
    if not allowed:
        raise HTTPException(status_code=429, detail=msg)

    request_id = str(uuid.uuid4())

    allowed_constraints = request.constraints or []

    result = await recommend_combination_agent(
        generate=generate_openai_compatible,
        extract_json=_extract_json_object,
        client=grok_client,
        model=GROK_MODEL,
        industry=request.industry,
        allowed_constraints=allowed_constraints,
        personas=[p.model_dump() for p in (request.personas or [])],
        max_attempts=3,
        request_id=request_id,
    )
    
    usage = result.get("usage", {})
    if usage:
        total = usage.get("total_tokens", 0)
        if total > 0:
            db.track_token_usage(user_id, total)

    return RecommendCombinationResponse(
        recommended_constraints=result["recommended_constraints"],
        recommended_persona=result["recommended_persona"],
        reason_html=result["reason_html"],
        usage=result.get("usage", {}),
    )

    



@app.get("/health")
def health_check(): return {"status": "healthy"}

# --- Static Files (Must be last) ---
app.mount("/", StaticFiles(directory="static", html=True), name="static")
