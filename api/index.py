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
from instructions_prompt import system_instructions, user_instruction

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
    constraint: str
    tone: str
    models: List[str]
    results: Dict[str, str]

class IdeaRequest(BaseModel):
    industry: str
    constraint: str
    tone: str
    models: List[str]

class EmailRequest(ReportData):
    to_email: str

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
                <td class="cfg-value">{escape(data.constraint or "None")}</td>
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

# --- API Endpoints ---
@app.post("/api")
async def idea(request: IdeaRequest, creds: HTTPAuthorizationCredentials = Depends(clerk_guard)):
    system_instruction = system_instructions(request.tone)
    user_content = user_instruction(request.industry, request.constraint)

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
def send_email(request: EmailRequest, creds: HTTPAuthorizationCredentials = Depends(clerk_guard)):
    report_html = create_report_html(request)
    pdf_bytes = html_to_pdf_bytes(report_html)
    resend.Emails.send({
        "from": "no-reply@agentairg.site", "to": request.to_email,
        "subject": f"IdeaGen Report: {request.industry}", "html": "Your report is attached.",
        "attachments": [{"filename": "report.pdf", "content": list(pdf_bytes)}]
    })
    return {"status": "sent"}

@app.get("/health")
def health_check(): return {"status": "healthy"}

# --- Static Files (Must be last) ---
app.mount("/", StaticFiles(directory="static", html=True), name="static")
