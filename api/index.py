import os
import asyncio
from pathlib import Path
from fastapi import FastAPI, Depends
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi_clerk_auth import ClerkConfig, ClerkHTTPBearer, HTTPAuthorizationCredentials
from openai import AsyncOpenAI
import google.generativeai as genai
from dotenv import load_dotenv
import resend
import io
from xhtml2pdf import pisa
from pydantic import BaseModel
from typing import List, Dict
from datetime import datetime

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
    genai.configure(api_key=os.environ["GEMINI_API_KEY"])
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
def create_report_html(data: ReportData) -> str:
    model_names = {"gpt-5-nano": "OpenAI", "gemini-3-pro-preview": "Google", "deepseek-chat": "DeepSeek", "grok-4-1-fast-reasoning": "Grok"}
    results_html = ""
    for model_id in data.models:
        result_content = data.results.get(model_id, "<p>No result generated.</p>")
        model_display_name = model_names.get(model_id, model_id)
        results_html += f'<div class="card result-card"><div class="card-header"><h3>{model_display_name}</h3></div><div class="card-content">{result_content}</div></div>'
    
    return f"""
    <html>
    <head>
        <title>Business Idea Generation Report</title>
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
            @page {{ margin: 0.75in; }}
            body {{ font-family: 'Inter', Arial, sans-serif; font-size: 10pt; color: #374151; }}
            h1, h2, h3 {{ color: #111827; font-weight: 600; }}
            .report-header {{ text-align: center; margin-bottom: 2.5rem; }}
            .report-header h1 {{ font-size: 24pt; font-weight: 700; margin: 0; }}
            .report-header .subtitle {{ font-size: 10pt; color: #6B7280; margin-top: 4px; }}
            .card {{ border: 1px solid #E5E7EB; border-radius: 12px; margin-bottom: 2rem; page-break-inside: avoid; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05); }}
            .card-header {{ background-color: #F9FAFB; padding: 1rem 1.5rem; border-bottom: 1px solid #E5E7EB; border-top-left-radius: 12px; border-top-right-radius: 12px; }}
            .card-header h2, .card-header h3 {{ font-size: 14pt; margin: 0; }}
            .card-content {{ padding: 1.5rem; }}
            .config-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 1rem 2rem; }}
            .config-item strong {{ display: block; color: #4B5563; font-weight: 500; font-size: 9pt; text-transform: uppercase; margin-bottom: 2px; }}
            .result-content h2 {{ font-size: 16pt; color: #1E40AF; margin-top: 0; border-bottom: 2px solid #DBEAFE; padding-bottom: 0.4rem; margin-bottom: 1rem; }}
            .result-content h3 {{ font-size: 12pt; margin-top: 1.5rem; margin-bottom: 0.5rem; }}
        </style>
    </head>
    <body>
        <div class="report-header">
            <h1>Business Idea Report</h1>
            <p class="subtitle">Generated on {datetime.now().strftime("%B %d, %Y")}</p>
        </div>
        <div class="card">
            <div class="card-header"><h2>Configuration</h2></div>
            <div class="card-content">
                <div class="config-grid">
                    <div class="config-item"><strong>Industry:</strong> {data.industry}</div>
                    <div class="config-item"><strong>Constraint:</strong> {data.constraint or 'None'}</div>
                    <div class="config-item"><strong>AI Persona:</strong> {data.tone}</div>
                    <div class="config-item"><strong>Models Used:</strong> {', '.join(model_names.get(m, m) for m in data.models)}</div>
                </div>
            </div>
        </div>
        {results_html}
    </body>
    </html>
    """

def html_to_pdf_bytes(html_content: str) -> bytes:
    buffer = io.BytesIO()
    pisa.CreatePDF(html_content, dest=buffer)
    buffer.seek(0)
    return buffer.read()

# --- AI Generation Helpers ---
async def generate_openai_compatible(client, model, system_instruction, user_content):
    try:
        r = await client.chat.completions.create(model=model, messages=[{"role": "system", "content": system_instruction}, {"role": "user", "content": user_content}])
        return r.choices[0].message.content or ""
    except Exception as e: return f"Error: {e}"

async def generate_gemini(model, system_instruction, user_content):
    try:
        m = genai.GenerativeModel(model_name=model)
        r = await m.generate_content_async(f"{system_instruction}\\n\\n{user_content}")
        return r.text
    except Exception as e: return f"Error: {e}"

# --- API Endpoints ---
@app.post("/api")
async def idea(request: IdeaRequest, creds: HTTPAuthorizationCredentials = Depends(clerk_guard)):
    system_instruction = f"You are a business idea generator. Format as semantic HTML. Persona: {request.tone}"
    user_content = f"Generate a business idea for AI Agents in '{request.industry}' with constraint: {request.constraint or 'None'}."
    
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
