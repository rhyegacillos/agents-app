from calendar import c
import os

import asyncio
from pathlib import Path
import re
from token import OP
from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi_clerk_auth import ClerkConfig, ClerkHTTPBearer, HTTPAuthorizationCredentials
import jwt
from jwt import PyJWKClient
from openai import AsyncOpenAI
from google import genai
from dotenv import load_dotenv
import io
from pydantic import BaseModel, Field
from typing import List, Dict
from datetime import datetime, timezone
from utils.pdf_utils import (
    create_compare_report_html,
    create_rank_report_html,
    create_report_html,
    html_to_pdf_bytes,
    model_label_from_id,
)
from instructions.instructions_prompt import system_instructions, user_instruction
from agent.email_agent import send_report_email
from agent.recommend_combination_agent import recommend_combination_agent
from agent.compare_results_agent import compare_results_agent
from agent.rank_report_agent import rank_report_agent
from agent.rank_result_agent import rank_result_agent
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
    force=True,
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("fontTools").setLevel(logging.WARNING)
logging.getLogger("fontTools.subset").setLevel(logging.WARNING)
logging.getLogger("fontTools.ttLib").setLevel(logging.WARNING)


# --- API Clients & Config ---
clerk_config = ClerkConfig(jwks_url=os.getenv("CLERK_JWKS_URL"))
logger = logging.getLogger(__name__)

# Initialize PyJWKClient
jwks_client = PyJWKClient(os.getenv("CLERK_JWKS_URL"))

class CustomClerkHTTPBearer(ClerkHTTPBearer):
    async def __call__(self, request: Request):
        auth = request.headers.get("Authorization")
        if not auth or not auth.startswith("Bearer "):
            raise HTTPException(status_code=403, detail="Not authenticated")

        token = auth.split(" ")[1]

        try:
            if not jwks_client:
                raise Exception("JWKS client not initialized")

            signing_key = jwks_client.get_signing_key_from_jwt(token)

            # Manual verification with leeway and relaxed audience check
            data = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                leeway=120,
                options={"verify_aud": False},
            )

            # Create the credentials object expected by the endpoint
            creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
            creds.decoded = data  # Attach decoded payload manually
            return creds

        except Exception as e:
            logger.error("Manual Token Verification Failed: %s", e)
            # Try to debug log the token content if possible
            try:
                decoded_debug = jwt.decode(token, options={"verify_signature": False})
                exp_ts = decoded_debug.get("exp", 0)
                iat_ts = decoded_debug.get("iat", 0)
                now_ts = datetime.now(timezone.utc).timestamp()
                logger.info(
                    "Debug Token: exp=%s, iat=%s, now=%s, skew=%.2fs",
                    exp_ts,
                    iat_ts,
                    now_ts,
                    iat_ts - now_ts,
                )
            except Exception:
                pass

            raise HTTPException(status_code=403, detail=f"Token verification failed: {str(e)}")

clerk_guard = CustomClerkHTTPBearer(clerk_config)
openai_client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
deepseek_client = AsyncOpenAI(api_key=os.getenv("DEEPSEEK_API_KEY"), base_url=os.getenv("DEEPSEEK_API_URL"))
grok_client = AsyncOpenAI(api_key=os.getenv("GROK_API_KEY"), base_url=os.getenv("GROK_API_URL"))
google_client = AsyncOpenAI(api_key=os.getenv("GEMINI_API_KEY"), base_url=os.getenv("GEMINI_API_URL"))
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
    rank_result: Optional[Dict[str, Any]] = None

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

class CompareEmailRequest(BaseModel):
    to_email: str

class RankReportEmailRequest(BaseModel):
    to_email: str

class SaveResultsRequest(BaseModel):
    industry: str
    constraints: List[str] = []
    tone: str
    models: List[str]
    results: Dict[str, str]
    rank_result: Optional[Dict[str, Any]] = None

class CompareResultsRequest(BaseModel):
    run_a_id: int
    run_b_id: int

class RankReportRequest(BaseModel):
    run_ids: List[int] = Field(default_factory=list)
    output: str
    email: Optional[str] = None
    include_all_runs: bool = False

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

_TITLE_TAG_RE = re.compile(r"<h[1-3][^>]*>(.*?)</h[1-3]>", re.IGNORECASE | re.DOTALL)


def _strip_html_text(value: str) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", value)).strip()


def extract_result_title(value: str) -> str:
    if not value:
        return "Untitled result"
    match = _TITLE_TAG_RE.search(value)
    if match:
        title = _strip_html_text(match.group(1))
    else:
        title = _strip_html_text(value)
        if title:
            for marker in ("title:", "idea:", "concept:"):
                idx = title.lower().find(marker)
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


def sanitize_rank_text(value: str, label_map: Dict[str, str]) -> str:
    if not value:
        return value
    out = str(value)
    for model_id, label in label_map.items():
        if model_id:
            out = out.replace(model_id, label)
    return out


def finalize_rank_result(
    rank_result: Optional[Dict[str, Any]],
    title_map: Dict[str, str],
    label_map: Dict[str, str],
) -> Optional[Dict[str, Any]]:
    if not isinstance(rank_result, dict):
        return rank_result
    if rank_result.get("skipped"):
        rank_result["title_map"] = title_map
        return rank_result
    if "summary" in rank_result:
        rank_result["summary"] = sanitize_rank_text(str(rank_result.get("summary", "")), label_map)
    ranked_models = rank_result.get("ranked_models")
    if isinstance(ranked_models, list):
        for item in ranked_models:
            model_id = str(item.get("model_id", "")).strip()
            if model_id and model_id in title_map:
                item["title"] = title_map[model_id]
            if "rationale" in item:
                item["rationale"] = sanitize_rank_text(str(item.get("rationale", "")), label_map)
    highlights = rank_result.get("highlights")
    if isinstance(highlights, list):
        rank_result["highlights"] = [
            sanitize_rank_text(str(item), label_map) for item in highlights if str(item).strip()
        ]
    rank_result["title_map"] = title_map
    return rank_result


def normalize_email_brief(
    brief: Any,
    *,
    fallback_subject: str,
    fallback_summary: str,
    fallback_highlights: List[str],
) -> Dict[str, Any]:
    if not isinstance(brief, dict):
        return {
            "subject": fallback_subject,
            "summary": fallback_summary,
            "highlights": fallback_highlights,
        }
    subject = str(brief.get("subject", "")).strip() or fallback_subject
    summary = str(brief.get("summary", "")).strip() or fallback_summary
    highlights = brief.get("highlights")
    if not isinstance(highlights, list):
        highlights = []
    cleaned_highlights = [str(item).strip() for item in highlights if str(item).strip()]
    if not cleaned_highlights:
        cleaned_highlights = fallback_highlights
    return {
        "subject": subject,
        "summary": summary,
        "highlights": cleaned_highlights[:4],
    }


def build_rank_report_email_brief(report: Dict[str, Any], runs: List[Dict[str, Any]]) -> Dict[str, Any]:
    summary = str(report.get("summary", "")).strip() or "Your rank report is ready."
    ranked_runs = report.get("ranked_runs", []) or []
    key_insights = report.get("key_insights", []) or []

    def run_label(run: Dict[str, Any]) -> str:
        industry = run.get("industry") or "Saved run"
        created_at = run.get("created_at") or ""
        return f"{industry} ({created_at})"

    highlights: List[str] = []
    if ranked_runs:
        top = ranked_runs[0]
        run_id = top.get("run_id")
        score = top.get("score")
        run = next((r for r in runs if r.get("id") == run_id), {})
        label = run_label(run) if run else f"Run {run_id}"
        score_text = f"{score}" if score is not None else "N/A"
        highlights.append(f"Top run: {label} (score {score_text}).")

    if isinstance(key_insights, list) and key_insights:
        for insight in key_insights[:2]:
            if str(insight).strip():
                highlights.append(str(insight).strip())

    if not highlights:
        highlights = [
            "Top run identified with a score and rationale.",
            "Key differences summarized for quick review.",
        ]

    return normalize_email_brief(
        report.get("email_brief"),
        fallback_subject="IdeaGen Rank Report",
        fallback_summary=summary,
        fallback_highlights=highlights,
    )


def build_idea_report_email_brief(request: "EmailRequest") -> Dict[str, Any]:
    summary = f"Your IdeaGen report for {request.industry} is attached."
    constraints_text = request.constraints_text
    highlights = [
        f"Persona: {request.tone or 'Neutral'}",
        f"Constraints: {constraints_text}",
    ]
    return normalize_email_brief(
        None,
        fallback_subject=f"IdeaGen Report: {request.industry}",
        fallback_summary=summary,
        fallback_highlights=highlights,
    )


def format_rank_report_timestamp(value: datetime) -> str:
    return value.strftime("%Y%m%d_%H%M%S")


def build_rank_report_filename(value: Optional[datetime] = None) -> str:
    timestamp = format_rank_report_timestamp(value or datetime.now(timezone.utc))
    return f"IdeaGen_Rank_Report_{timestamp}.pdf"

# --- Compare Report Filename ---
def build_compare_report_filename(value: Optional[datetime] = None) -> str:
    timestamp = format_rank_report_timestamp(value or datetime.now(timezone.utc))
    return f"IdeaGen_Compare_Report_{timestamp}.pdf"

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
        + len(json.dumps(request.rank_result or {}).encode("utf-8"))
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
        rank_result=request.rank_result,
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

    run_a = db.get_saved_result(user_id, request.run_a_id)
    run_b = db.get_saved_result(user_id, request.run_b_id)
    if not run_a or not run_b:
        raise HTTPException(status_code=404, detail="Saved result not found.")

    def normalized_config(run: Dict[str, Any]) -> Dict[str, Any]:
        constraints = [str(c).strip().lower() for c in (run.get("constraints") or []) if str(c).strip()]
        models = run.get("models") or list((run.get("results") or {}).keys())
        model_ids = [str(m).strip().lower() for m in models if str(m).strip()]
        return {
            "industry": str(run.get("industry") or "").strip().lower(),
            "tone": str(run.get("tone") or "").strip().lower(),
            "constraints": sorted(constraints),
            "models": sorted(model_ids),
        }

    if normalized_config(run_a) != normalized_config(run_b):
        raise HTTPException(
            status_code=400,
            detail="Diff analysis requires the same industry, persona, constraints, and model set.",
        )

    cached = db.get_saved_comparison(user_id, request.run_a_id, request.run_b_id)
    if cached:
        comparison = cached.get("comparison", {}) or {}
        top_outputs = comparison.get("top_outputs") if isinstance(comparison.get("top_outputs"), dict) else {}
        if not (top_outputs.get("run_a", {}) or {}).get("output_html") or not (top_outputs.get("run_b", {}) or {}).get("output_html"):
            def select_cached_top(run: Dict[str, Any]) -> Dict[str, Any]:
                results = run.get("results") or {}
                if not results:
                    return {
                        "selected_model_id": "",
                        "selected_model_label": "",
                        "selected_title": "Untitled result",
                        "selected_output": "",
                    }
                rank_result = run.get("rank_result") if isinstance(run.get("rank_result"), dict) else None
                selected_model_id = None
                ranked = rank_result.get("ranked_models") if isinstance(rank_result, dict) else None
                if isinstance(ranked, list):
                    ranked_sorted = sorted(ranked, key=lambda item: int(item.get("rank", 9999)))
                    for item in ranked_sorted:
                        model_id = str(item.get("model_id", "")).strip()
                        if model_id and model_id in results:
                            selected_model_id = model_id
                            break
                if not selected_model_id:
                    selected_model_id = next(iter(results.keys()))
                output = results.get(selected_model_id) or ""
                title = extract_result_title(output)
                return {
                    "selected_model_id": selected_model_id,
                    "selected_model_label": model_label_from_id(selected_model_id),
                    "selected_title": title,
                    "selected_output": output,
                }

            cached_a = select_cached_top(run_a)
            cached_b = select_cached_top(run_b)
            comparison["top_outputs"] = {
                "run_a": {
                    "title": cached_a.get("selected_title") or "Untitled result",
                    "model_label": cached_a.get("selected_model_label") or "Model",
                    "model_id": cached_a.get("selected_model_id") or "",
                    "output_html": cached_a.get("selected_output") or "",
                },
                "run_b": {
                    "title": cached_b.get("selected_title") or "Untitled result",
                    "model_label": cached_b.get("selected_model_label") or "Model",
                    "model_id": cached_b.get("selected_model_id") or "",
                    "output_html": cached_b.get("selected_output") or "",
                },
            }
            cached["comparison"] = comparison
        return cached

    async def ensure_rank_result_for_run(run: Dict[str, Any], run_id: int) -> Optional[Dict[str, Any]]:
        rank_result = run.get("rank_result")
        if isinstance(rank_result, dict) and isinstance(rank_result.get("ranked_models"), list):
            return rank_result
        results = run.get("results") or {}
        if len(results.keys()) <= 1:
            return {"skipped": True, "reason": "Ranking not available for a single model."}
        title_map = {model_id: extract_result_title(text) for model_id, text in results.items()}
        label_map = {model_id: model_label_from_id(model_id) for model_id in results.keys()}
        run_payload = {
            "industry": run.get("industry") or "",
            "persona": run.get("tone") or "",
            "constraints": run.get("constraints") or [],
            "titles": title_map,
            "model_labels": label_map,
            "outputs": results,
        }
        rank_result_payload = await rank_result_agent(
            generate=generate_openai_compatible,
            extract_json=_extract_json_object,
            client=deepseek_client,
            model=DEEPSEEK_MODEL,
            run=run_payload,
            max_attempts=2,
            request_id=request_id,
        )
        rank_result = finalize_rank_result(rank_result_payload.get("rank_result"), title_map, label_map)
        if rank_result:
            db.update_saved_result_rank(user_id, run_id, rank_result)
        usage = rank_result_payload.get("usage", {})
        if usage and usage.get("total_tokens"):
            db.track_token_usage(user_id, usage.get("total_tokens", 0))
        return rank_result

    def select_top_output(run: Dict[str, Any], rank_result: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        results = run.get("results") or {}
        if not results:
            return {
                "selected_model_id": "",
                "selected_model_label": "",
                "selected_title": "Untitled result",
                "selected_output": "",
            }
        selected_model_id = None
        ranked = rank_result.get("ranked_models") if isinstance(rank_result, dict) else None
        if isinstance(ranked, list):
            ranked_sorted = sorted(ranked, key=lambda item: int(item.get("rank", 9999)))
            for item in ranked_sorted:
                model_id = str(item.get("model_id", "")).strip()
                if model_id and model_id in results:
                    selected_model_id = model_id
                    break
        if not selected_model_id:
            selected_model_id = next(iter(results.keys()))
        output = results.get(selected_model_id) or ""
        title = extract_result_title(output)
        return {
            "selected_model_id": selected_model_id,
            "selected_model_label": model_label_from_id(selected_model_id),
            "selected_title": title,
            "selected_output": output,
        }

    request_id = str(uuid.uuid4())
    rank_a = await ensure_rank_result_for_run(run_a, request.run_a_id)
    rank_b = await ensure_rank_result_for_run(run_b, request.run_b_id)
    selected_a = select_top_output(run_a, rank_a)
    selected_b = select_top_output(run_b, rank_b)
    run_a_payload = {
        "id": run_a.get("id"),
        "industry": run_a.get("industry"),
        "tone": run_a.get("tone"),
        "constraints": run_a.get("constraints") or [],
        **selected_a,
    }
    run_b_payload = {
        "id": run_b.get("id"),
        "industry": run_b.get("industry"),
        "tone": run_b.get("tone"),
        "constraints": run_b.get("constraints") or [],
        **selected_b,
    }
    result = await compare_results_agent(
        generate=generate_openai_compatible,
        extract_json=_extract_json_object,
        client=deepseek_client,
        model=DEEPSEEK_MODEL,
        run_a=run_a_payload,
        run_b=run_b_payload,
        max_attempts=2,
        request_id=request_id,
    )

    comparison = result.get("comparison", {}) or {}
    comparison["top_outputs"] = {
        "run_a": {
            "title": selected_a.get("selected_title") or "Untitled result",
            "model_label": selected_a.get("selected_model_label") or "Model",
            "model_id": selected_a.get("selected_model_id") or "",
            "output_html": selected_a.get("selected_output") or "",
        },
        "run_b": {
            "title": selected_b.get("selected_title") or "Untitled result",
            "model_label": selected_b.get("selected_model_label") or "Model",
            "model_id": selected_b.get("selected_model_id") or "",
            "output_html": selected_b.get("selected_output") or "",
        },
    }
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

@app.delete("/api/compare-results/{comparison_id}")
async def delete_compare_result(comparison_id: int, creds: HTTPAuthorizationCredentials = Depends(clerk_guard)):
    user_id = creds.decoded.get("sub")
    deleted = db.delete_saved_comparison(user_id, comparison_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Comparison not found.")
    return {"status": "deleted"}

@app.get("/api/compare-results/{comparison_id}/pdf")
async def download_compare_report(comparison_id: int, creds: HTTPAuthorizationCredentials = Depends(clerk_guard)):
    user_id = creds.decoded.get("sub")
    saved = db.get_saved_comparison_by_id(user_id, comparison_id)
    if not saved:
        raise HTTPException(status_code=404, detail="Comparison not found.")

    run_a_id = saved.get("run_a_id")
    run_b_id = saved.get("run_b_id")
    comparison = saved.get("comparison", {}) or {}

    top_outputs = comparison.get("top_outputs") if isinstance(comparison.get("top_outputs"), dict) else {}
    need_backfill = not (top_outputs.get("run_a", {}) or {}).get("output_html") or not (top_outputs.get("run_b", {}) or {}).get("output_html")

    if need_backfill:
        run_a = db.get_saved_result(user_id, run_a_id)
        run_b = db.get_saved_result(user_id, run_b_id)

        def select_top_output(run: Dict[str, Any]) -> Dict[str, Any]:
            results = run.get("results") or {}
            if not results:
                return {
                    "selected_model_id": "",
                    "selected_model_label": "",
                    "selected_title": "Untitled result",
                    "selected_output": "",
                }
            rank_result = run.get("rank_result") if isinstance(run.get("rank_result"), dict) else None
            selected_model_id = None
            ranked = rank_result.get("ranked_models") if isinstance(rank_result, dict) else None
            if isinstance(ranked, list):
                ranked_sorted = sorted(ranked, key=lambda item: int(item.get("rank", 9999)))
                for item in ranked_sorted:
                    model_id = str(item.get("model_id", "")).strip()
                    if model_id and model_id in results:
                        selected_model_id = model_id
                        break
            if not selected_model_id:
                selected_model_id = next(iter(results.keys()))
            output = results.get(selected_model_id) or ""
            title = extract_result_title(output)
            return {
                "selected_model_id": selected_model_id,
                "selected_model_label": model_label_from_id(selected_model_id),
                "selected_title": title,
                "selected_output": output,
            }

        if run_a and run_b:
            selected_a = select_top_output(run_a)
            selected_b = select_top_output(run_b)
            comparison["top_outputs"] = {
                "run_a": {
                    "title": selected_a.get("selected_title") or "Untitled result",
                    "model_label": selected_a.get("selected_model_label") or "Model",
                    "model_id": selected_a.get("selected_model_id") or "",
                    "output_html": selected_a.get("selected_output") or "",
                },
                "run_b": {
                    "title": selected_b.get("selected_title") or "Untitled result",
                    "model_label": selected_b.get("selected_model_label") or "Model",
                    "model_id": selected_b.get("selected_model_id") or "",
                    "output_html": selected_b.get("selected_output") or "",
                },
            }

    created_at = saved.get("created_at") or ""
    run_a = db.get_saved_result(user_id, run_a_id)
    config = None
    if run_a:
        config = {
            "industry": run_a.get("industry") or "",
            "persona": run_a.get("tone") or "",
            "constraints": run_a.get("constraints") or [],
        }
    html = create_compare_report_html(comparison, run_a_id, run_b_id, created_at, config=config)
    pdf_bytes = html_to_pdf_bytes(html)

    filename = build_compare_report_filename()
    headers = {"Content-Disposition": f"attachment;filename={filename}"}
    return StreamingResponse(io.BytesIO(pdf_bytes), media_type="application/pdf", headers=headers)


@app.post("/api/compare-results/{comparison_id}/email")
async def email_compare_report(comparison_id: int, request: "CompareEmailRequest", creds: HTTPAuthorizationCredentials = Depends(clerk_guard)):
    user_id = creds.decoded.get("sub")
    plan = get_user_plan(creds)
    allowed, msg = db.check_and_increment_email(user_id, plan)
    if not allowed:
        return JSONResponse(content={"error": msg}, status_code=429)

    saved = db.get_saved_comparison_by_id(user_id, comparison_id)
    if not saved:
        raise HTTPException(status_code=404, detail="Comparison not found.")

    run_a_id = saved.get("run_a_id")
    run_b_id = saved.get("run_b_id")
    comparison = saved.get("comparison", {}) or {}

    top_outputs = comparison.get("top_outputs") if isinstance(comparison.get("top_outputs"), dict) else {}
    need_backfill = not (top_outputs.get("run_a", {}) or {}).get("output_html") or not (top_outputs.get("run_b", {}) or {}).get("output_html")

    if need_backfill:
        run_a = db.get_saved_result(user_id, run_a_id)
        run_b = db.get_saved_result(user_id, run_b_id)

        def select_top_output(run: Dict[str, Any]) -> Dict[str, Any]:
            results = run.get("results") or {}
            if not results:
                return {
                    "selected_model_id": "",
                    "selected_model_label": "",
                    "selected_title": "Untitled result",
                    "selected_output": "",
                }
            rank_result = run.get("rank_result") if isinstance(run.get("rank_result"), dict) else None
            selected_model_id = None
            ranked = rank_result.get("ranked_models") if isinstance(rank_result, dict) else None
            if isinstance(ranked, list):
                ranked_sorted = sorted(ranked, key=lambda item: int(item.get("rank", 9999)))
                for item in ranked_sorted:
                    model_id = str(item.get("model_id", "")).strip()
                    if model_id and model_id in results:
                        selected_model_id = model_id
                        break
            if not selected_model_id:
                selected_model_id = next(iter(results.keys()))
            output = results.get(selected_model_id) or ""
            title = extract_result_title(output)
            return {
                "selected_model_id": selected_model_id,
                "selected_model_label": model_label_from_id(selected_model_id),
                "selected_title": title,
                "selected_output": output,
            }

        if run_a and run_b:
            selected_a = select_top_output(run_a)
            selected_b = select_top_output(run_b)
            comparison["top_outputs"] = {
                "run_a": {
                    "title": selected_a.get("selected_title") or "Untitled result",
                    "model_label": selected_a.get("selected_model_label") or "Model",
                    "model_id": selected_a.get("selected_model_id") or "",
                    "output_html": selected_a.get("selected_output") or "",
                },
                "run_b": {
                    "title": selected_b.get("selected_title") or "Untitled result",
                    "model_label": selected_b.get("selected_model_label") or "Model",
                    "model_id": selected_b.get("selected_model_id") or "",
                    "output_html": selected_b.get("selected_output") or "",
                },
            }

    created_at = saved.get("created_at") or ""
    run_a = db.get_saved_result(user_id, run_a_id)
    config = None
    if run_a:
        config = {
            "industry": run_a.get("industry") or "",
            "persona": run_a.get("tone") or "",
            "constraints": run_a.get("constraints") or [],
        }
    html = create_compare_report_html(comparison, run_a_id, run_b_id, created_at, config=config)
    pdf_bytes = html_to_pdf_bytes(html)

    filename = build_compare_report_filename()

    run_a_title = comparison.get("top_outputs", {}).get("run_a", {}).get("title") or f"Run A {run_a_id}"
    run_b_title = comparison.get("top_outputs", {}).get("run_b", {}).get("title") or f"Run B {run_b_id}"
    subject_hint = f"IdeaGen Compare Report: {run_a_title} vs {run_b_title}"

    try:
        await send_report_email(
            to_email=request.to_email,
            industry=f"{run_a_title} vs {run_b_title}",
            constraints_text="Compared top-ranked outputs",
            report_type="Compare Report",
            subject_hint=subject_hint,
            email_brief={
                "subject": subject_hint,
                "summary": comparison.get("summary") or "Your compare report is ready.",
                "highlights": (comparison.get("key_changes") or [])[:3],
            },
            attachment_filename=filename,
            attachment_bytes=pdf_bytes,
        )
    except Exception:
        logger.exception("compare_report.email_failed user_id=%s", user_id)
        raise HTTPException(status_code=502, detail="Email delivery failed. Please try again.")

    return {"status": "sent"}


@app.get("/api/rank-reports")
async def list_rank_reports(limit: int = 6, creds: HTTPAuthorizationCredentials = Depends(clerk_guard)):
    user_id = creds.decoded.get("sub")
    return {"reports": db.list_saved_rank_reports(user_id, limit=limit)}


@app.get("/api/rank-reports/{report_id}/pdf")
async def download_rank_report(report_id: int, creds: HTTPAuthorizationCredentials = Depends(clerk_guard)):
    user_id = creds.decoded.get("sub")
    saved = db.get_saved_rank_report_by_id(user_id, report_id)
    if not saved:
        raise HTTPException(status_code=404, detail="Report not found.")
    snapshot_runs = saved.get("runs_snapshot") or []
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
    html = create_rank_report_html(ordered_runs, report)
    pdf_bytes = html_to_pdf_bytes(html)
    created_at = saved.get("created_at")
    created_dt = None
    if isinstance(created_at, str):
        try:
            created_dt = datetime.fromisoformat(created_at)
        except ValueError:
            created_dt = None
    filename = build_rank_report_filename(created_dt)
    headers = {"Content-Disposition": f"attachment;filename={filename}"}
    if missing_runs:
        headers["X-Report-Runs-Missing"] = "true"
    return StreamingResponse(io.BytesIO(pdf_bytes), media_type="application/pdf", headers=headers)


@app.get("/api/rank-reports/{report_id}")
async def get_rank_report(report_id: int, creds: HTTPAuthorizationCredentials = Depends(clerk_guard)):
    user_id = creds.decoded.get("sub")
    saved = db.get_saved_rank_report_by_id(user_id, report_id)
    if not saved:
        raise HTTPException(status_code=404, detail="Report not found.")
    return saved


@app.post("/api/rank-reports/{report_id}/email")
async def email_rank_report(report_id: int, request: RankReportEmailRequest, creds: HTTPAuthorizationCredentials = Depends(clerk_guard)):
    user_id = creds.decoded.get("sub")
    plan = get_user_plan(creds)
    allowed, msg = db.check_and_increment_email(user_id, plan)
    if not allowed:
        return JSONResponse(content={"error": msg}, status_code=429)

    saved = db.get_saved_rank_report_by_id(user_id, report_id)
    if not saved:
        raise HTTPException(status_code=404, detail="Report not found.")

    snapshot_runs = saved.get("runs_snapshot") or []
    report = saved.get("report", {}) or {}
    html = create_rank_report_html(snapshot_runs, report)
    pdf_bytes = html_to_pdf_bytes(html)

    filename = build_rank_report_filename()
    industries = [r.get("industry") for r in snapshot_runs if r.get("industry")]
    industry_label = industries[0] if len(set(industries)) == 1 else "Saved runs"
    constraints_text = "Multiple constraints"
    if len(snapshot_runs) == 1:
        constraints = snapshot_runs[0].get("constraints") or []
        constraints_text = ", ".join(constraints) if constraints else "None"

    try:
        await send_report_email(
            to_email=request.to_email,
            industry=industry_label,
            constraints_text=constraints_text,
            report_type="Decision Summary Report",
            subject_hint=f"IdeaGen Decision Summary Report: {industry_label}",
            email_brief=build_rank_report_email_brief(report, snapshot_runs),
            attachment_filename=filename,
            attachment_bytes=pdf_bytes,
        )
    except Exception:
        logger.exception("rank_report.email_failed user_id=%s", user_id)
        raise HTTPException(status_code=502, detail="Email delivery failed. Please try again.")

    return {"status": "sent"}


@app.post("/api/rank-report")
async def rank_report(request: RankReportRequest, creds: HTTPAuthorizationCredentials = Depends(clerk_guard)):
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

    if include_all_runs:
        snapshot_runs = runs
    else:
        run_map = {r.get("id"): r for r in runs if r.get("id") is not None}
        snapshot_runs = [run_map[rid] for rid in run_ids if rid in run_map]

    run_ids_key = ",".join(str(i) for i in sorted(run_ids))
    cached = db.get_saved_rank_report(user_id, run_ids_key)

    if cached:
        report = cached.get("report", {}) or {}
        cached_flag = True
        cached_id = cached.get("id")
        if cached_id:
            needs_snapshot = not (cached.get("runs_snapshot") or [])
            if needs_snapshot:
                db.update_rank_report_snapshot(
                    user_id,
                    cached_id,
                    runs_snapshot=snapshot_runs if needs_snapshot else None,
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
        db.save_rank_report(
            user_id=user_id,
            run_ids_key=run_ids_key,
            run_ids=run_ids,
            report=report,
            model=DEEPSEEK_MODEL,
            runs_snapshot=snapshot_runs,
        )
        cached_flag = False

    html = create_rank_report_html(runs, report)
    pdf_bytes = html_to_pdf_bytes(html)
    email_brief = build_rank_report_email_brief(report, runs)

    def email_context() -> tuple[str, str]:
        if include_all_runs:
            return ("All saved runs", "Multiple constraints")
        industries = [r.get("industry") for r in runs if r.get("industry")]
        unique_industries = sorted({i for i in industries if i})
        if len(unique_industries) == 1:
            industry_label = unique_industries[0]
        elif unique_industries:
            industry_label = "Multiple industries"
        else:
            industry_label = "Saved runs"
        if len(runs) == 1:
            constraints = runs[0].get("constraints") or []
            constraints_text = ", ".join(constraints) if constraints else "None"
        else:
            constraints_text = "Multiple constraints"
        return (industry_label, constraints_text)

    email_sent = False
    email_failed = False
    if output in {"email", "both"}:
        try:
            industry_label, constraints_text = email_context()
            await send_report_email(
                to_email=request.email,
                industry=industry_label,
                constraints_text=constraints_text,
                report_type="Rank Report",
                subject_hint=email_brief.get("subject") or "IdeaGen Rank Report",
                email_brief=email_brief,
                attachment_filename=build_rank_report_filename(),
                attachment_bytes=pdf_bytes,
            )
            email_sent = True
        except Exception:
            logger.exception("rank_report.email_failed request_id=%s user_id=%s", request_id, user_id)
            email_failed = True
            if output == "email":
                raise HTTPException(status_code=502, detail="Email delivery failed. Please try again.")

    if output == "email":
        return {
            "status": "sent",
            "email_sent": email_sent,
            "email_failed": email_failed,
            "cached": cached_flag,
        }

    headers = {"Content-Disposition": f"attachment;filename={build_rank_report_filename()}"}
    if email_sent:
        headers["X-Report-Email-Sent"] = "true"
    if email_failed:
        headers["X-Report-Email-Failed"] = "true"
    if cached_flag:
        headers["X-Report-Cached"] = "true"
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

    rank_result = None
    title_map = {model_id: extract_result_title(text) for model_id, text in out_results.items()}
    label_map = {model_id: model_label_from_id(model_id) for model_id in out_results.keys()}
    if len(out_results.keys()) > 1:
        run_payload = {
            "industry": request.industry,
            "persona": request.tone,
            "constraints": request.constraints or [],
            "titles": title_map,
            "model_labels": label_map,
            "outputs": out_results,
        }
        try:
            rank_result_payload = await rank_result_agent(
                generate=generate_openai_compatible,
                extract_json=_extract_json_object,
                client=deepseek_client,
                model=DEEPSEEK_MODEL,
                run=run_payload,
                max_attempts=2,
                request_id=request_id,
            )
            rank_result = rank_result_payload.get("rank_result")
            rank_usage = rank_result_payload.get("usage", {})
            if rank_usage:
                total_usage["prompt_tokens"] += rank_usage.get("prompt_tokens", 0) or 0
                total_usage["completion_tokens"] += rank_usage.get("completion_tokens", 0) or 0
                total_usage["total_tokens"] += rank_usage.get("total_tokens", 0) or 0
                if rank_usage.get("total_tokens"):
                    db.track_token_usage(user_id, rank_usage.get("total_tokens", 0))
        except Exception:
            logger.exception("rank_result.failed request_id=%s user_id=%s", request_id, user_id)
            rank_result = {
                "skipped": True,
                "reason": "Ranking failed. Please try again.",
            }
    else:
        rank_result = {
            "skipped": True,
            "reason": "Ranking not available for a single model.",
        }

    rank_result = finalize_rank_result(rank_result, title_map, label_map)

    # Include updated limits in response
    stats = db.get_user_stats(user_id)
    total_usage["api_calls_count"] = stats["api_calls_count"]
    total_usage["emails_sent_count"] = stats["emails_sent_count"]

    return JSONResponse(content={"results": out_results, "usage": total_usage, "rank_result": rank_result})


@app.post("/api/download-pdf")
def download_pdf(request: ReportData):
    report_html = create_report_html(request)
    pdf_bytes = html_to_pdf_bytes(report_html)
    filename = build_pdf_filename(request.industry)
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment;filename={filename}"},
    )


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

    filename = build_pdf_filename(request.industry)
    try:
        email_brief = build_idea_report_email_brief(request)
        result = await send_report_email(
            to_email=request.to_email,
            industry=request.industry,
            constraints_text=constraints_text,
            report_type="Idea Report",
            subject_hint=email_brief.get("subject") or f"IdeaGen Report: {request.industry}",
            email_brief=email_brief,
            attachment_filename=filename,
            attachment_bytes=pdf_bytes,
        )
    except Exception:
        logger.exception("idea_report.email_failed user_id=%s", user_id)
        raise HTTPException(status_code=502, detail="Email delivery failed. Please try again.")

    return {
        "status": "sent",
        "subject": result.get("subject"),
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
