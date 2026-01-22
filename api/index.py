from calendar import c
import os
import asyncio
from pathlib import Path
import re
from fastapi import FastAPI, Depends
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi_clerk_auth import ClerkConfig, ClerkHTTPBearer, HTTPAuthorizationCredentials
from openai import AsyncOpenAI
from google import genai
from dotenv import load_dotenv
import resend
import io
from weasyprint import HTML
from pydantic import BaseModel
from typing import List, Dict
from datetime import datetime
from html import escape
from instructions.instructions_prompt import system_instructions, user_instruction
from agent.email_agent import run_email_agent
import json
from typing import Any, Optional



# --- App Setup ---
load_dotenv()
app = FastAPI()

# --- API Clients & Config ---
clerk_config = ClerkConfig(jwks_url=os.getenv("CLERK_JWKS_URL"))
clerk_guard = ClerkHTTPBearer(clerk_config)
openai_client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
deepseek_client = AsyncOpenAI(api_key=os.getenv("DEEPSEEK_API_KEY"), base_url=os.getenv("DEEPSEEK_API_URL"))
grok_client = AsyncOpenAI(api_key=os.getenv("GROK_API_KEY"), base_url=os.getenv("GROK_API_URL"))
resend.api_key = os.getenv("RESEND_API_KEY")

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
    models: List[str]


class EmailRequest(ReportData):
    to_email: str

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


def build_pdf_filename(industry: str) -> str:
    safe_industry = re.sub(r"[^a-zA-Z0-9_-]+", "_", industry.strip())
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    return f"IdeaGen_{safe_industry}_{ts}.pdf"

# --- PDF Generation ---
def create_report_html(data: "ReportData") -> str:
    model_names = {
        "gpt-5-nano": "OpenAI",
        "gemini-3-pro-preview": "Google",
        "deepseek-chat": "DeepSeek",
        "grok-4-1-fast-reasoning": "Grok",
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

# --- PDF Conversion ---
def html_to_pdf_bytes(html_content: str) -> bytes:
    pdf_bytes = HTML(string=html_content).write_pdf()
    return pdf_bytes

# --- AI Generation Helpers ---
async def generate_openai_compatible(client, model, system_instruction, user_content):
    try:
        r = await client.chat.completions.create(model=model, messages=[{"role": "system", "content": system_instruction}, {"role": "user", "content": user_content}])
        return r.choices[0].message.content or ""
    except Exception as e: return f"Error: {e}"

async def generate_gemini(model, system_instruction, user_content):
    try:
        r = await gemini_client.aio.models.generate_content(
            model=model,
            contents=f"{system_instruction}\n\n{user_content}"
        )
        return r.text
    except Exception as e:
        if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
            try:
                fallback_model = "gemini-2.5-pro"
                r = await gemini_client.aio.models.generate_content(
                    model=fallback_model,
                    contents=f"{system_instruction}\n\n{user_content}"
                )
                return r.text
            except Exception as e2:
                return f"Error - Limit Reach: {e2}"
        return f"Error: {e}"


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


# --- API Endpoints ---
@app.post("/api")
async def idea(request: IdeaRequest, creds: HTTPAuthorizationCredentials = Depends(clerk_guard)):
    constraints_text = ", ".join(request.constraints) if request.constraints else "None"
    system_instruction = system_instructions(request.tone)
    user_content = user_instruction(request.industry, constraints_text)
    

    tasks = []
    for model_id in request.models:
        if model_id == "gpt-5-nano": tasks.append(generate_openai_compatible(openai_client, "gpt-5-nano", system_instruction, user_content))
        elif model_id == "deepseek-chat": tasks.append(generate_openai_compatible(deepseek_client, "deepseek-chat", system_instruction, user_content))
        elif model_id == "grok-4-1-fast-reasoning": tasks.append(generate_openai_compatible(grok_client, "grok-4-1-fast-reasoning", system_instruction, user_content))
        elif model_id == "gemini-3-pro-preview": tasks.append(generate_gemini("gemini-3-pro-preview", system_instruction, user_content))
    
    if not tasks:
        return JSONResponse(content={"error": "No valid models selected."}, status_code=400)
        
    results = await asyncio.gather(*tasks)
    return JSONResponse(content={model: result for model, result in zip(request.models, results)})

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
      <p>Hi There,</p>

      {agent_result["html_body"]}

      <p style="margin-top:24px;">
        Best regards,<br/>
        <strong>Ideagen</strong>
      </p>

      <p style="font-size:12px;color:#666;">
        This is an auto-generated email. Please do not reply.
      </p>
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



@app.post("/api/recommend-combination", response_model=RecommendCombinationResponse)
async def recommend_combination(
    request: RecommendCombinationRequest,
    creds: HTTPAuthorizationCredentials = Depends(clerk_guard)
):
    allowed_constraints = request.constraints
    allowed_persona_ids = [p.id for p in request.personas]

    system_prompt = """
    You are a product strategist selecting the best configuration for generating a high-quality AI agent business idea.

    STRICT RULES (DO NOT VIOLATE):
    - You MUST select constraints ONLY from the provided "Allowed constraints" list.
    - You MUST select persona ONLY from the provided "Allowed personas" list (use the persona id exactly).
    - You MUST NOT invent, paraphrase, shorten, or modify any option text.
    - All selected strings MUST match the allowed options EXACTLY (character-for-character).
    - Choose 1 or 2 constraints only. NEVER choose more than 2.
    - If unsure, choose the FIRST option(s) from the allowed lists.
    - Return ONLY valid JSON. No prose, no markdown, no explanation outside JSON.

    OPTIMIZATION GOALS:
    - Fastest path to validation
    - Clear economic ROI
    - Strong workflow alignment in the selected industry
    - Practical execution feasibility for a small team

    SELECTION GUIDELINES:
    - Prefer constraints that force concrete workflows and measurable outcomes.
    - Avoid combinations that contradict each other.
    - If multiple options are plausible, choose the one that reduces ambiguity and increases execution clarity.

    FAILURE HANDLING:
    - If any requirement cannot be satisfied, fall back to the first allowed constraint and first allowed persona.
    """

    user_prompt = f"""
    Industry: "{request.industry}"

    Allowed constraints (use EXACT strings from this list only):
    {json.dumps(allowed_constraints, ensure_ascii=False)}
    IMPORTANT: Copy the chosen constraint strings exactly as they appear in the Allowed constraints list.


    Allowed personas (use EXACT persona id from this list only):
    {json.dumps([p.model_dump() for p in request.personas], ensure_ascii=False)}

    Return ONLY valid JSON with this exact schema:
    {{
    "recommended_constraints": ["string", "string"],
    "recommended_persona": "string",
    "reason_html": "<section data-section='recommendation_reason'><h3>Why this combination</h3><ul><li>...</li></ul></section>"
    }}

    Rules:
    - recommended_constraints MUST be an array with 1 or 2 items.
    - Each item in recommended_constraints MUST exactly match one item in Allowed constraints.
    - recommended_persona MUST exactly match one persona id in Allowed personas.
    - Do NOT output any constraint/persona that is not in the allowed lists.
    - If you are unsure, choose the FIRST constraint and FIRST persona from the allowed lists.

    Rules for reason_html:
    - Must be semantic HTML only.
    - Must contain 3–5 <li> bullet points explaining:
    1) why the chosen constraints fit the industry's workflows,
    2) why the chosen persona lens is best for producing useful output,
    3) one explicit tradeoff/risk of this choice.
    """


    raw = await generate_openai_compatible(
        grok_client,
        "grok-4-1-fast-reasoning",
        system_prompt,
        user_prompt
    )

    obj = _extract_json_object(raw) or {}

    # recommended_constraint = str(obj.get("recommended_constraint", "")).strip()
    recommended_persona = str(obj.get("recommended_persona", "")).strip()
    reason_html = str(obj.get("reason_html", "")).strip()

    # Validate membership; fallback safely
    raw_constraints = obj.get("recommended_constraints", [])
    if isinstance(raw_constraints, str):
        # if model mistakenly returns a single string, wrap it
        raw_constraints = [raw_constraints]

    if not isinstance(raw_constraints, list):
        raw_constraints = []

    # normalize + validate + dedupe
    seen = set()
    recommended_constraints: List[str] = []
    for c in raw_constraints:
        c = str(c).strip()
        if c in allowed_constraints and c not in seen:
            seen.add(c)
            recommended_constraints.append(c)

    # cap to 3
    recommended_constraints = recommended_constraints[:3]

    # fallback
    if not recommended_constraints:
        recommended_constraints = [allowed_constraints[0]] if allowed_constraints else ["None"]


    if recommended_persona not in allowed_persona_ids:
        recommended_persona = allowed_persona_ids[0] if allowed_persona_ids else "Neutral"

    if not reason_html:
        reason_html = (
            "<section data-section='recommendation_reason'>"
            "<h3>Recommendation</h3>"
            "<ul><li>No rationale provided.</li></ul>"
            "</section>"
        )

    return RecommendCombinationResponse(
        recommended_constraints=recommended_constraints,
        recommended_persona=recommended_persona,
        reason_html=reason_html
    )




@app.get("/health")
def health_check(): return {"status": "healthy"}

# --- Static Files (Must be last) ---
app.mount("/", StaticFiles(directory="static", html=True), name="static")
