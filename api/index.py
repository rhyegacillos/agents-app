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
from pydantic import BaseModel
from typing import List, Dict
from datetime import datetime
from html import escape
from instructions.instructions_prompt import system_instructions, user_instruction
from agent.email_agent import run_email_agent
from agent.recommend_combination_agent import recommend_combination_agent
from agent.idea_generation_agent import generate_idea_agentic


import json
from typing import Any, Optional

import logging
import uuid


# --- App Setup ---
load_dotenv()
app = FastAPI()

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
    plan = decoded.get("pla") or "u:free_user"
    return {
        "user_id": decoded.get("sub"),
        "plan": plan,
        "is_premium": plan in PREMIUM_PLANS,
        "status": decoded.get("sts"),
    }




@app.post("/api")
async def idea(request: IdeaRequest, creds: HTTPAuthorizationCredentials = Depends(clerk_guard)):
    request_id = str(uuid.uuid4())
    print(f"user: {creds.decoded} temp: {request.temperature} top_p: {request.top_p}")

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
