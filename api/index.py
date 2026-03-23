from calendar import c
import copy
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
    create_execution_plan_presentation_html,
    create_execution_plan_report_html,
    create_rank_report_html,
    create_report_html,
    html_to_pdf_bytes,
    model_label_from_id,
)
from agent.execution_plan_agent import (
    build_stakeholder_dossier as util_build_stakeholder_dossier,
    merge_assumptions as util_merge_assumptions,
)
from instructions.instructions_prompt import system_instructions, user_instruction
from agent.email_agent import send_report_email
from agent.recommend_combination_agent import recommend_combination_agent
from agent.compare_results_agent import compare_results_agent
from agent.rank_report_agent import rank_report_agent
from agent.rank_result_agent import rank_result_agent
from agent.idea_generation_agent import generate_idea_agentic


import json
from typing import Any, Optional, Tuple

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

DEFAULT_ALLOWED_HOSTS = {"localhost", "127.0.0.1", "::1", "testserver"}
_allowed_hosts_raw = os.getenv("ALLOWED_HOSTS", "ideagen.agentairg.site")
ALLOWED_HOSTS = {
    host.strip().lower()
    for host in _allowed_hosts_raw.split(",")
    if host.strip()
}
if ALLOWED_HOSTS:
    ALLOWED_HOSTS = ALLOWED_HOSTS.union(DEFAULT_ALLOWED_HOSTS)


def _is_allowed_host(incoming_host: str) -> bool:
    if incoming_host in ALLOWED_HOSTS:
        return True

    for allowed_host in ALLOWED_HOSTS:
        if allowed_host.startswith("*."):
            suffix = allowed_host[1:]
            if incoming_host.endswith(suffix):
                return True

    return False


def _normalize_host(value: str) -> str:
    host = (value or "").strip().lower()
    if not host:
        return ""
    if host.startswith("[") and "]" in host:
        host = host[1 : host.index("]")]
    elif ":" in host:
        host = host.split(":", 1)[0]
    return host


def _extract_request_host(request: Request) -> str:
    host_value = (request.headers.get("host", "") or "").strip()
    if not host_value:
        forwarded_host = request.headers.get("x-forwarded-host", "")
        if forwarded_host:
            host_value = forwarded_host.split(",", 1)[0].strip()
    return _normalize_host(host_value)


@app.middleware("http")
async def enforce_allowed_hosts(request: Request, call_next):
    # Keep health probe reachable for App Runner health checks.
    if request.url.path == "/health" or not ALLOWED_HOSTS:
        return await call_next(request)

    incoming_host = _extract_request_host(request)
    if not _is_allowed_host(incoming_host):
        logger.warning(
            "blocked_request.invalid_host host=%s path=%s",
            incoming_host,
            request.url.path,
        )
        return JSONResponse(status_code=403, content={"detail": "Host not allowed."})
    return await call_next(request)

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
GEMINI_MODEL = "gemini-2.5-flash"
OPENAI_MODEL = "gpt-5-nano"
DEEPSEEK_MODEL = "deepseek-chat"
GROK_MODEL_FALLBACK = "grok-4-fast-non-reasoning"
GEMINI_MODEL_FALLBACK = "gemini-2.5-flash-lite"
OPENAI_MODEL_FALLBACK = "gpt-5-mini"
DEEPSEEK_MODEL_FALLBACK = "deepseek-chat-v3.1"
EXECUTION_PLAN_MODEL = os.getenv("EXECUTION_PLAN_MODEL", GEMINI_MODEL)
EXECUTION_PLAN_MODEL_FALLBACK = os.getenv("EXECUTION_PLAN_MODEL_FALLBACK", GEMINI_MODEL_FALLBACK)
GEMINI_EXECUTION_COMPAT_MODELS = [
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
    "gemini-1.5-flash",
]



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


class StakeholderReportSource(BaseModel):
    mode: str
    decision_report_id: Optional[int] = None
    compare_result_id: Optional[int] = None
    selected_run_id: Optional[int] = None
    selected_model_id: Optional[str] = None


class StakeholderReportRequest(BaseModel):
    source: StakeholderReportSource
    scenario_profile: str = "base"
    horizon_months: int = Field(default=12, ge=6, le=24)
    currency: str = "USD"
    region: str = "US"
    output: str = "json"
    finance_mode: str = "grounded_v2"

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


def build_execution_plan_filename(value: Optional[datetime] = None) -> str:
    timestamp = format_rank_report_timestamp(value or datetime.now(timezone.utc))
    return f"IdeaGen_Execution_Plan_{timestamp}.pdf"


def build_execution_plan_presentation_filename(value: Optional[datetime] = None) -> str:
    timestamp = format_rank_report_timestamp(value or datetime.now(timezone.utc))
    return f"IdeaGen_Execution_Presentation_{timestamp}.pdf"

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


def _resolve_top_model_for_run(run: Dict[str, Any], preferred_model_id: Optional[str] = None) -> Dict[str, Any]:
    results = run.get("results") or {}
    if not isinstance(results, dict) or not results:
        return {
            "model_id": "",
            "model_label": "",
            "title": "Untitled result",
            "output_html": "",
            "confidence": 0.55,
        }
    if preferred_model_id and preferred_model_id in results:
        model_id = preferred_model_id
    else:
        model_id = None
        rank_result = run.get("rank_result") if isinstance(run.get("rank_result"), dict) else {}
        ranked_models = rank_result.get("ranked_models") if isinstance(rank_result, dict) else []
        if isinstance(ranked_models, list):
            ranked_sorted = sorted(ranked_models, key=lambda item: int(item.get("rank", 9999)))
            for item in ranked_sorted:
                candidate = str(item.get("model_id", "")).strip()
                if candidate and candidate in results:
                    model_id = candidate
                    break
        if not model_id:
            model_id = next(iter(results.keys()))
    output_html = str(results.get(model_id) or "")
    title = extract_result_title(output_html)
    confidence = 0.62
    rank_result = run.get("rank_result") if isinstance(run.get("rank_result"), dict) else {}
    ranked_models = rank_result.get("ranked_models") if isinstance(rank_result, dict) else []
    if isinstance(ranked_models, list):
        for item in ranked_models:
            if str(item.get("model_id", "")) == model_id:
                score = item.get("score")
                try:
                    score_num = float(score)
                    confidence = max(0.0, min(1.0, score_num / 100.0))
                except (TypeError, ValueError):
                    pass
                break
    return {
        "model_id": model_id,
        "model_label": model_label_from_id(model_id),
        "title": title,
        "output_html": output_html,
        "confidence": round(confidence, 3),
    }


def _resolve_stakeholder_source(user_id: str, source: StakeholderReportSource) -> Dict[str, Any]:
    mode = (source.mode or "").strip().lower()
    if mode not in {"decision_report", "compare_result", "saved_run"}:
        raise HTTPException(status_code=400, detail="source.mode must be decision_report, compare_result, or saved_run.")

    if mode == "decision_report":
        if not source.decision_report_id:
            raise HTTPException(status_code=400, detail="decision_report_id is required for decision_report mode.")
        saved_report = db.get_saved_rank_report_by_id(user_id, source.decision_report_id)
        if not saved_report:
            raise HTTPException(status_code=404, detail="Decision report not found.")
        runs_snapshot = saved_report.get("runs_snapshot") or []
        if not runs_snapshot:
            run_ids = saved_report.get("run_ids") or []
            runs_snapshot = db.get_saved_results_by_ids(user_id, run_ids)
        if not runs_snapshot:
            raise HTTPException(status_code=400, detail="Decision report has no source runs.")
        run_map = {int(r.get("id")): r for r in runs_snapshot if r.get("id") is not None}
        selected_run_id = source.selected_run_id
        if selected_run_id is None:
            ranked_runs = (saved_report.get("report") or {}).get("ranked_runs") or []
            if ranked_runs:
                try:
                    selected_run_id = int(ranked_runs[0].get("run_id"))
                except (TypeError, ValueError):
                    selected_run_id = None
        if selected_run_id is None:
            selected_run_id = int(runs_snapshot[0].get("id"))
        run = run_map.get(int(selected_run_id))
        if not run:
            raise HTTPException(status_code=400, detail="selected_run_id is not part of the decision report.")
        return {
            "source_type": "decision_report",
            "source_id": int(source.decision_report_id),
            "run": run,
            "preferred_model_id": source.selected_model_id,
            "evidence": {
                "summary": str((saved_report.get("report") or {}).get("summary") or ""),
                "key_points": list((saved_report.get("report") or {}).get("key_insights") or []),
            },
        }

    if mode == "compare_result":
        if not source.compare_result_id:
            raise HTTPException(status_code=400, detail="compare_result_id is required for compare_result mode.")
        saved_compare = db.get_saved_comparison_by_id(user_id, source.compare_result_id)
        if not saved_compare:
            raise HTTPException(status_code=404, detail="Compare result not found.")
        run_a_id = int(saved_compare.get("run_a_id"))
        run_b_id = int(saved_compare.get("run_b_id"))
        runs = db.get_saved_results_by_ids(user_id, [run_a_id, run_b_id])
        run_map = {int(r.get("id")): r for r in runs if r.get("id") is not None}
        selected_run_id = source.selected_run_id or saved_compare.get("winner_run_id") or run_a_id
        if int(selected_run_id) not in run_map:
            raise HTTPException(status_code=400, detail="selected_run_id is not part of the compare result.")
        top_outputs = (saved_compare.get("comparison") or {}).get("top_outputs") or {}
        preferred_model_id = source.selected_model_id
        if not preferred_model_id:
            if int(selected_run_id) == run_a_id:
                preferred_model_id = str((top_outputs.get("run_a") or {}).get("model_id") or "").strip() or None
            else:
                preferred_model_id = str((top_outputs.get("run_b") or {}).get("model_id") or "").strip() or None
        return {
            "source_type": "compare_result",
            "source_id": int(source.compare_result_id),
            "run": run_map[int(selected_run_id)],
            "preferred_model_id": preferred_model_id,
            "evidence": {
                "summary": str((saved_compare.get("comparison") or {}).get("summary") or ""),
                "key_points": list((saved_compare.get("comparison") or {}).get("key_changes") or []),
            },
        }

    if not source.selected_run_id:
        raise HTTPException(status_code=400, detail="selected_run_id is required for saved_run mode.")
    saved_run = db.get_saved_result(user_id, source.selected_run_id)
    if not saved_run:
        raise HTTPException(status_code=404, detail="Saved run not found.")
    return {
        "source_type": "saved_run",
        "source_id": int(source.selected_run_id),
        "run": saved_run,
        "preferred_model_id": source.selected_model_id,
        "evidence": {
            "summary": str((saved_run.get("rank_result") or {}).get("summary") or ""),
            "key_points": list((saved_run.get("rank_result") or {}).get("highlights") or []),
        },
    }


def _build_stakeholder_dossier(
    source_ctx: Dict[str, Any],
    scenario_profile: str,
    horizon_months: int,
    currency: str,
    region: str,
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    run = source_ctx["run"]
    selected_model = _resolve_top_model_for_run(run, source_ctx.get("preferred_model_id"))
    return util_build_stakeholder_dossier(
        source_ctx=source_ctx,
        scenario_profile=scenario_profile,
        horizon_months=horizon_months,
        currency=currency,
        region=region,
        selected_model=selected_model,
    )


def _apply_execution_plan_financial_baseline(
    llm_dossier: Dict[str, Any],
    baseline_dossier: Dict[str, Any],
    baseline_assumptions: List[Dict[str, Any]],
    source_ctx: Dict[str, Any],
    horizon_months: int,
    currency: str,
) -> Dict[str, Any]:
    """
    Keep narrative sections from the LLM but force all financial sections to use
    deterministic assumption-pack projections so values are reproducible.
    """
    merged = copy.deepcopy(llm_dossier)
    for key in (
        "resources",
        "costs",
        "revenue_profit",
        "scenarios",
        "stakeholder_ask",
        "proposal_disclaimer",
        "sensitivity_analysis",
    ):
        if key in baseline_dossier:
            merged[key] = copy.deepcopy(baseline_dossier[key])
    merged["assumptions"] = copy.deepcopy(baseline_assumptions)

    source_run = source_ctx.get("run") or {}
    source_selected = _resolve_top_model_for_run(source_run, source_ctx.get("preferred_model_id"))
    decision = merged.get("decision") if isinstance(merged.get("decision"), dict) else {}
    winner = decision.get("winner") if isinstance(decision.get("winner"), dict) else {}
    decision["winner"] = {
        "run_id": _to_int(winner.get("run_id")) or _to_int(source_run.get("id")) or 0,
        "model_id": str(winner.get("model_id") or source_selected.get("model_id") or ""),
        "title": str(
            winner.get("title")
            or source_selected.get("title")
            or extract_result_title(str(source_selected.get("output_html") or ""))
        ),
    }
    decision["confidence"] = round(
        float(source_selected.get("confidence") or decision.get("confidence") or 0.6),
        3,
    )
    merged["decision"] = decision

    provenance = merged.get("provenance") if isinstance(merged.get("provenance"), dict) else {}
    provenance["financials_grounded"] = True
    provenance["formula_version"] = "stakeholder_finance_v2"
    provenance["generator_version"] = "hybrid_llm_narrative_grounded_finance_v1"
    merged["provenance"] = provenance

    validated, validation_errors = _validate_execution_plan_dossier(
        merged,
        horizon_months,
        currency,
        source_ctx,
    )
    if validation_errors or not validated:
        detail = "Execution plan grounding failed schema validation."
        if validation_errors:
            detail = f"{detail} First issue: {validation_errors[0]}"
        raise HTTPException(status_code=502, detail=detail)
    return validated


def _execution_plan_model_chain() -> List[str]:
    chain = [EXECUTION_PLAN_MODEL]
    if EXECUTION_PLAN_MODEL_FALLBACK:
        chain.append(EXECUTION_PLAN_MODEL_FALLBACK)
    if any(str(model or "").strip().startswith("gemini-") for model in chain):
        chain.extend(GEMINI_EXECUTION_COMPAT_MODELS)
    chain.append(OPENAI_MODEL)
    if OPENAI_MODEL_FALLBACK:
        chain.append(OPENAI_MODEL_FALLBACK)
    # Keep order but remove duplicates/empties.
    out = []
    seen = set()
    for model in chain:
        key = str(model or "").strip()
        if not key or key in seen:
            continue
        out.append(key)
        seen.add(key)
    return out or [OPENAI_MODEL, OPENAI_MODEL_FALLBACK]


def _to_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_text_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    out: List[str] = []
    for item in value:
        text = str(item).strip()
        if text:
            out.append(text)
    return out


def _validate_execution_plan_dossier(
    raw: Dict[str, Any],
    horizon_months: int,
    currency: str,
    source_ctx: Dict[str, Any],
) -> Tuple[Optional[Dict[str, Any]], List[str]]:
    errors: List[str] = []
    if not isinstance(raw, dict):
        return None, ["Execution plan output must be a JSON object."]

    meta = raw.get("meta") if isinstance(raw.get("meta"), dict) else {}
    decision = raw.get("decision") if isinstance(raw.get("decision"), dict) else {}
    winner = decision.get("winner") if isinstance(decision.get("winner"), dict) else {}

    thesis = str(decision.get("thesis") or "").strip()
    if not thesis:
        errors.append("decision.thesis is required.")
    go_no_go = str(decision.get("go_no_go") or "").strip().lower()
    if go_no_go not in {"go", "conditional_go", "no_go"}:
        errors.append("decision.go_no_go must be go, conditional_go, or no_go.")
        go_no_go = "conditional_go"
    confidence = _to_float(decision.get("confidence"))
    if confidence is None:
        errors.append("decision.confidence must be numeric.")
        confidence = 0.6
    confidence = max(0.0, min(1.0, confidence))

    blueprint = raw.get("execution_blueprint") if isinstance(raw.get("execution_blueprint"), dict) else {}
    phases = blueprint.get("phases")
    normalized_phases: List[Dict[str, Any]] = []
    if not isinstance(phases, list) or not phases:
        errors.append("execution_blueprint.phases must contain at least one phase.")
    else:
        for idx, phase in enumerate(phases, start=1):
            if not isinstance(phase, dict):
                errors.append(f"execution_blueprint.phases[{idx}] must be an object.")
                continue
            name = str(phase.get("name") or "").strip() or f"Phase {idx}"
            start_month = _to_int(phase.get("start_month"))
            end_month = _to_int(phase.get("end_month"))
            if start_month is None or end_month is None:
                errors.append(f"{name}: start_month and end_month are required integers.")
                continue
            if start_month < 1 or end_month < start_month or end_month > horizon_months:
                errors.append(f"{name}: start/end months must be within 1..{horizon_months} and start<=end.")
                continue
            normalized_phases.append(
                {
                    "name": name,
                    "start_month": start_month,
                    "end_month": end_month,
                    "workstreams": _as_text_list(phase.get("workstreams")),
                    "deliverables": _as_text_list(phase.get("deliverables")),
                    "dependencies": _as_text_list(phase.get("dependencies")),
                    "owner_roles": _as_text_list(phase.get("owner_roles")),
                }
            )

    costs = raw.get("costs") if isinstance(raw.get("costs"), dict) else {}
    setup_cost = costs.get("setup_cost") if isinstance(costs.get("setup_cost"), dict) else {}
    setup_total = _to_float(setup_cost.get("total"))
    if setup_total is None or setup_total <= 0:
        errors.append("costs.setup_cost.total must be a positive number.")
        setup_total = 0.0

    revenue_profit = raw.get("revenue_profit") if isinstance(raw.get("revenue_profit"), dict) else {}
    break_even_month = _to_int(revenue_profit.get("break_even_month"))
    if break_even_month is None or break_even_month < 1:
        errors.append("revenue_profit.break_even_month must be a positive integer.")
        break_even_month = horizon_months + 1

    monthly_projection = revenue_profit.get("monthly_projection")
    normalized_projection: List[Dict[str, Any]] = []
    if not isinstance(monthly_projection, list) or len(monthly_projection) < horizon_months:
        errors.append(f"revenue_profit.monthly_projection must include at least {horizon_months} rows.")
    else:
        for idx, row in enumerate(monthly_projection[:horizon_months], start=1):
            if not isinstance(row, dict):
                errors.append(f"revenue_profit.monthly_projection[{idx}] must be an object.")
                continue
            month = _to_int(row.get("month"))
            customers = _to_float(row.get("customers"))
            revenue = _to_float(row.get("revenue"))
            cogs = _to_float(row.get("cogs"))
            gross_profit = _to_float(row.get("gross_profit"))
            opex = _to_float(row.get("opex"))
            net_profit = _to_float(row.get("net_profit"))
            cumulative = _to_float(row.get("cumulative_net_profit"))
            if None in {month, customers, revenue, cogs, gross_profit, opex, net_profit, cumulative}:
                errors.append(f"revenue_profit.monthly_projection[{idx}] has invalid numeric fields.")
                continue
            normalized_projection.append(
                {
                    "month": month,
                    "customers": round(float(customers), 2),
                    "revenue": round(float(revenue), 2),
                    "cogs": round(float(cogs), 2),
                    "gross_profit": round(float(gross_profit), 2),
                    "opex": round(float(opex), 2),
                    "net_profit": round(float(net_profit), 2),
                    "cumulative_net_profit": round(float(cumulative), 2),
                }
            )

    scenarios = raw.get("scenarios")
    normalized_scenarios: List[Dict[str, Any]] = []
    if not isinstance(scenarios, list) or not scenarios:
        errors.append("scenarios must contain at least one scenario.")
    else:
        for idx, scenario in enumerate(scenarios, start=1):
            if not isinstance(scenario, dict):
                errors.append(f"scenarios[{idx}] must be an object.")
                continue
            name = str(scenario.get("name") or "").strip().lower()
            probability = _to_float(scenario.get("probability"))
            year_1_revenue = _to_float(scenario.get("year_1_revenue"))
            year_1_net_profit = _to_float(scenario.get("year_1_net_profit"))
            if not name:
                errors.append(f"scenarios[{idx}].name is required.")
                continue
            if None in {probability, year_1_revenue, year_1_net_profit}:
                errors.append(f"scenarios[{idx}] requires numeric probability/year_1_revenue/year_1_net_profit.")
                continue
            normalized_scenarios.append(
                {
                    "name": name,
                    "probability": round(max(0.0, min(1.0, float(probability))), 4),
                    "key_assumptions": _as_text_list(scenario.get("key_assumptions")),
                    "year_1_revenue": round(float(year_1_revenue), 2),
                    "year_1_net_profit": round(float(year_1_net_profit), 2),
                }
            )

    stakeholder_ask = raw.get("stakeholder_ask") if isinstance(raw.get("stakeholder_ask"), dict) else {}
    budget_required = _to_float(stakeholder_ask.get("budget_required"))
    if budget_required is None or budget_required <= 0:
        errors.append("stakeholder_ask.budget_required must be a positive number.")
        budget_required = 0.0

    assumptions = raw.get("assumptions")
    normalized_assumptions: List[Dict[str, Any]] = []
    if isinstance(assumptions, list):
        for item in assumptions:
            if not isinstance(item, dict):
                continue
            key = str(item.get("key") or "").strip()
            if not key:
                continue
            normalized_assumptions.append(
                {
                    "key": key,
                    "value": item.get("value"),
                    "unit": str(item.get("unit") or "").strip() or "unit",
                    "source": str(item.get("source") or "").strip() or "llm_inference",
                    "confidence": str(item.get("confidence") or "").strip().lower() or "medium",
                }
            )

    year_1_rows = normalized_projection[: min(12, len(normalized_projection))]
    year_1_net_profit = round(sum(float(row.get("net_profit") or 0.0) for row in year_1_rows), 2)
    year_1_revenue = round(sum(float(row.get("revenue") or 0.0) for row in year_1_rows), 2)
    year_1_gross_profit = round(sum(float(row.get("gross_profit") or 0.0) for row in year_1_rows), 2)
    gross_margin_ratio: Optional[float] = None
    if year_1_revenue > 0:
        gross_margin_ratio = round(year_1_gross_profit / year_1_revenue, 4)

    expected_year_1_net_profit: Optional[float] = None
    if normalized_scenarios:
        expected_year_1_net_profit = round(
            sum(
                float(item.get("probability") or 0.0) * float(item.get("year_1_net_profit") or 0.0)
                for item in normalized_scenarios
            ),
            2,
        )

    break_even_within_horizon = break_even_month <= horizon_months
    profitability_reasons: List[str] = []
    required_actions: List[str] = []

    if year_1_net_profit < 0:
        profitability_reasons.append(f"Year-1 net profit is negative ({year_1_net_profit:.2f}).")
        required_actions.append("Raise ARPU or tighten scope before full rollout.")
    if not break_even_within_horizon:
        profitability_reasons.append(f"Break-even month ({break_even_month}) is beyond the selected horizon ({horizon_months}).")
        required_actions.append("Cut fixed OpEx and stage hiring until post-pilot conversion.")
    if expected_year_1_net_profit is not None and expected_year_1_net_profit < 0:
        profitability_reasons.append(
            f"Probability-weighted Year-1 net profit is negative ({expected_year_1_net_profit:.2f})."
        )
        required_actions.append("Rework funnel conversion targets and demand plan assumptions.")
    if gross_margin_ratio is not None and gross_margin_ratio < 0.45:
        profitability_reasons.append(f"Gross margin ({gross_margin_ratio * 100:.1f}%) is below the 45% target.")
        required_actions.append("Reduce variable COGS per customer before scaling acquisition.")

    go_no_go_rank = {"go": 0, "conditional_go": 1, "no_go": 2}
    forced_go_no_go = go_no_go
    if profitability_reasons:
        forced_go_no_go = "conditional_go"
        severe_loss = year_1_net_profit < -max(50000.0, setup_total * 0.35)
        if severe_loss and not break_even_within_horizon:
            forced_go_no_go = "no_go"
    forced_by_rules = go_no_go_rank.get(forced_go_no_go, 1) > go_no_go_rank.get(go_no_go, 1)
    if forced_by_rules:
        go_no_go = forced_go_no_go

    decision_status = "viable"
    if go_no_go == "no_go":
        decision_status = "not_viable"
    elif go_no_go == "conditional_go":
        decision_status = "conditional"

    recovery_enabled = bool(profitability_reasons) or go_no_go in {"conditional_go", "no_go"}
    avg_monthly_net = year_1_net_profit / max(1, len(year_1_rows))
    monthly_profit_gap = round(max(0.0, -avg_monthly_net), 2)
    avg_customers = (
        sum(float(row.get("customers") or 0.0) for row in year_1_rows) / max(1, len(year_1_rows))
        if year_1_rows
        else 0.0
    )
    avg_revenue = (
        sum(float(row.get("revenue") or 0.0) for row in year_1_rows) / max(1, len(year_1_rows))
        if year_1_rows
        else 0.0
    )
    avg_opex = (
        sum(float(row.get("opex") or 0.0) for row in year_1_rows) / max(1, len(year_1_rows))
        if year_1_rows
        else 0.0
    )
    pricing = revenue_profit.get("pricing") if isinstance(revenue_profit.get("pricing"), dict) else {}
    baseline_arpu = _to_float(pricing.get("arpu_monthly")) or 0.0
    arpu_uplift = round(monthly_profit_gap / max(1.0, avg_customers), 2)
    opex_cut_pct = round(min(0.6, monthly_profit_gap / max(1.0, avg_opex)), 4) if avg_opex > 0 else 0.0
    conversion_uplift_pct = round(min(0.5, monthly_profit_gap / max(1.0, avg_revenue)), 4) if avg_revenue > 0 else 0.0

    def estimate_break_even_with_uplift(monthly_uplift: float) -> int:
        cumulative = 0.0
        for row in normalized_projection[:horizon_months]:
            cumulative += float(row.get("net_profit") or 0.0) + float(monthly_uplift)
            if cumulative >= 0:
                return int(row.get("month") or horizon_months + 1)
        return horizon_months + 1

    def build_recovery_scenario(name: str, uplift_ratio: float, moves: List[str]) -> Dict[str, Any]:
        monthly_uplift = round(monthly_profit_gap * uplift_ratio, 2)
        new_year_1_net = round(year_1_net_profit + (monthly_uplift * min(12, horizon_months)), 2)
        return {
            "name": name,
            "moves": moves,
            "estimated_monthly_impact": monthly_uplift,
            "estimated_year_1_net_profit": new_year_1_net,
            "estimated_break_even_month": estimate_break_even_with_uplift(monthly_uplift),
        }

    recovery_scenarios = [
        build_recovery_scenario(
            "Cost-Down",
            0.45,
            [
                f"Reduce fixed OpEx by {round(opex_cut_pct * 100, 1)}%",
                "Delay non-critical hires until paid pilot conversion",
            ],
        ),
        build_recovery_scenario(
            "Price-Up",
            0.40,
            [
                f"Increase ARPU by {currency} {arpu_uplift:.2f}/customer/month",
                "Introduce premium workflow automation package",
            ],
        ),
        build_recovery_scenario(
            "Combined Plan",
            1.05,
            [
                f"Raise ARPU from {currency} {baseline_arpu:.2f} to {currency} {baseline_arpu + arpu_uplift:.2f}",
                f"Improve conversion funnel by {round(conversion_uplift_pct * 100, 1)}% and reduce OpEx",
            ],
        ),
    ]

    recovery_experiments = [
        {
            "name": "Price packaging test",
            "owner": "GTM Lead",
            "target_metric": f"+{currency} {arpu_uplift:.2f} ARPU",
            "deadline_days": 21,
            "expected_monthly_impact": round(monthly_profit_gap * 0.22, 2),
        },
        {
            "name": "Onboarding conversion sprint",
            "owner": "Product Manager",
            "target_metric": f"+{round(conversion_uplift_pct * 100, 1)}% SQL-to-customer",
            "deadline_days": 30,
            "expected_monthly_impact": round(monthly_profit_gap * 0.2, 2),
        },
        {
            "name": "Model-inference cost optimization",
            "owner": "AI Engineer",
            "target_metric": "Reduce variable AI + infra unit cost",
            "deadline_days": 21,
            "expected_monthly_impact": round(monthly_profit_gap * 0.18, 2),
        },
        {
            "name": "Hiring gate review",
            "owner": "Product Manager",
            "target_metric": f"-{round(opex_cut_pct * 100, 1)}% fixed OpEx run-rate",
            "deadline_days": 14,
            "expected_monthly_impact": round(monthly_profit_gap * 0.2, 2),
        },
        {
            "name": "Pilot-to-paid conversion campaign",
            "owner": "Customer Success",
            "target_metric": "2+ additional paid pilots in-cycle",
            "deadline_days": 30,
            "expected_monthly_impact": round(monthly_profit_gap * 0.2, 2),
        },
    ]

    source_run = source_ctx.get("run") or {}
    source_selected = _resolve_top_model_for_run(source_run, source_ctx.get("preferred_model_id"))
    source_selected_model_id = str(source_selected.get("model_id") or "")
    source_selected_title = str(source_selected.get("title") or "")
    normalized = dict(raw)
    normalized["meta"] = {
        "report_version": str(meta.get("report_version") or "execution_plan_v1"),
        "generated_at": str(meta.get("generated_at") or datetime.now(timezone.utc).isoformat()),
        "currency": currency,
        "horizon_months": horizon_months,
    }
    normalized["decision"] = {
        "winner": {
            "run_id": _to_int(winner.get("run_id")) or _to_int(source_run.get("id")) or 0,
            "model_id": str(winner.get("model_id") or source_selected_model_id),
            "title": str(
                winner.get("title")
                or source_selected_title
                or extract_result_title(str((source_selected.get("output_html") or "")))
            ),
        },
        "thesis": thesis,
        "go_no_go": go_no_go,
        "confidence": round(confidence, 3),
    }
    normalized["execution_blueprint"] = {
        "phases": normalized_phases,
        "critical_path": _as_text_list(blueprint.get("critical_path")),
        "gates": _as_text_list(blueprint.get("gates")),
        "kill_criteria": _as_text_list(blueprint.get("kill_criteria")),
    }
    normalized["costs"] = {
        "setup_cost": {
            "engineering": round(_to_float(setup_cost.get("engineering")) or 0.0, 2),
            "legal_compliance": round(_to_float(setup_cost.get("legal_compliance")) or 0.0, 2),
            "launch_marketing": round(_to_float(setup_cost.get("launch_marketing")) or 0.0, 2),
            "other": round(_to_float(setup_cost.get("other")) or 0.0, 2),
            "total": round(float(setup_total), 2),
        },
        "monthly_opex": costs.get("monthly_opex") if isinstance(costs.get("monthly_opex"), list) else [],
        "unit_cogs": costs.get("unit_cogs") if isinstance(costs.get("unit_cogs"), dict) else {},
    }
    normalized["revenue_profit"] = {
        "pricing": revenue_profit.get("pricing") if isinstance(revenue_profit.get("pricing"), dict) else {},
        "funnel_assumptions": revenue_profit.get("funnel_assumptions") if isinstance(revenue_profit.get("funnel_assumptions"), dict) else {},
        "monthly_projection": normalized_projection,
        "break_even_month": break_even_month,
    }
    normalized["scenarios"] = normalized_scenarios
    normalized["risks"] = raw.get("risks") if isinstance(raw.get("risks"), list) else []
    normalized["stakeholder_ask"] = {
        "budget_required": round(float(budget_required), 2),
        "team_required": _as_text_list(stakeholder_ask.get("team_required")),
        "decision_required": str(stakeholder_ask.get("decision_required") or ""),
        "next_30_days": _as_text_list(stakeholder_ask.get("next_30_days")),
    }
    normalized["decision_support"] = {
        "status": decision_status,
        "forced_by_rules": forced_by_rules,
        "reasons": profitability_reasons,
        "required_actions": required_actions,
        "profitability_recovery": {
            "enabled": recovery_enabled,
            "monthly_profit_gap": monthly_profit_gap,
            "target_year_1_net_profit": 0.0,
            "levers": [
                {
                    "name": "Pricing",
                    "target": f"Increase ARPU by {currency} {arpu_uplift:.2f}/customer/month",
                    "estimated_monthly_impact": round(monthly_profit_gap * 0.35, 2),
                },
                {
                    "name": "Conversion",
                    "target": f"Improve lead-to-customer conversion by {round(conversion_uplift_pct * 100, 1)}%",
                    "estimated_monthly_impact": round(monthly_profit_gap * 0.3, 2),
                },
                {
                    "name": "Cost",
                    "target": f"Reduce fixed OpEx by {round(opex_cut_pct * 100, 1)}%",
                    "estimated_monthly_impact": round(monthly_profit_gap * 0.35, 2),
                },
            ],
            "scenarios": recovery_scenarios,
            "experiments_90_days": recovery_experiments,
            "approval_gate": (
                f"Approve scale only when projected break-even is <= month {horizon_months} "
                "and probability-weighted Year-1 net profit is non-negative."
            ),
        },
        "gates": {
            "year_1_net_profit": year_1_net_profit,
            "expected_year_1_net_profit": expected_year_1_net_profit,
            "break_even_month": break_even_month,
            "break_even_within_horizon": break_even_within_horizon,
            "gross_margin_ratio": gross_margin_ratio,
            "horizon_months": horizon_months,
        },
    }
    normalized["assumptions"] = normalized_assumptions
    raw_provenance = raw.get("provenance") if isinstance(raw.get("provenance"), dict) else {}
    normalized["provenance"] = {
        "source_artifacts": raw_provenance.get("source_artifacts")
        if isinstance(raw_provenance.get("source_artifacts"), list)
        else [{"type": source_ctx["source_type"], "id": source_ctx["source_id"]}],
        "selected_run_id": _to_int(raw_provenance.get("selected_run_id")) or _to_int(source_run.get("id")) or 0,
        "selected_model_id": str(raw_provenance.get("selected_model_id") or source_selected_model_id),
        "selected_output_title": str(raw_provenance.get("selected_output_title") or source_selected_title),
        "formula_version": str(raw_provenance.get("formula_version") or "llm_estimate_v1"),
        "generator_version": str(raw_provenance.get("generator_version") or "full_llm_execution_plan_v1"),
        "financials_grounded": bool(raw_provenance.get("financials_grounded")),
        "finance_mode": str(raw_provenance.get("finance_mode") or ""),
        "narrative_model": str(raw_provenance.get("narrative_model") or ""),
    }
    return normalized, errors


async def _generate_execution_plan_text(
    system_instruction: str,
    user_content: str,
    model_chain: List[str],
    temperature: float = 0.2,
    top_p: float = 0.9,
) -> Tuple[str, Dict[str, int], str]:
    last_error: Optional[Exception] = None
    for model in model_chain:
        print(f"model execution plan: {model}")
        try:
            model_key = str(model or "").strip().lower()
            if model_key.startswith("gemini-"):
                text, usage = await generate_gemini(
                    model=model,
                    system_instruction=system_instruction,
                    user_content=user_content,
                    temperature=temperature,
                    top_p=top_p,
                )
                if str(text or "").strip().lower().startswith("error"):
                    raise RuntimeError(str(text))
            elif model_key.startswith("grok-"):
                text, usage = await generate_openai_compatible(
                    client=grok_client,
                    model=model,
                    system_instruction=system_instruction,
                    user_content=user_content,
                    temperature=temperature,
                    top_p=top_p,
                )
            elif model_key.startswith("deepseek-"):
                text, usage = await generate_openai_compatible(
                    client=deepseek_client,
                    model=model,
                    system_instruction=system_instruction,
                    user_content=user_content,
                    temperature=temperature,
                    top_p=top_p,
                )
            else:
                text, usage = await generate_openai_compatible(
                    client=openai_client,
                    model=model,
                    system_instruction=system_instruction,
                    user_content=user_content,
                    temperature=temperature,
                    top_p=top_p,
                )
            return text or "", usage or {}, model
        except Exception as e:
            last_error = e
            logger.warning("execution_plan.model_failed model=%s error=%s", model, e)
            continue
    raise HTTPException(status_code=502, detail=f"Execution plan model call failed: {last_error}")


def _normalize_execution_plan_narrative(
    raw: Dict[str, Any],
    baseline_dossier: Dict[str, Any],
    horizon_months: int,
) -> Dict[str, Any]:
    baseline_blueprint = (
        baseline_dossier.get("execution_blueprint")
        if isinstance(baseline_dossier.get("execution_blueprint"), dict)
        else {}
    )
    baseline_risks = baseline_dossier.get("risks") if isinstance(baseline_dossier.get("risks"), list) else []
    baseline_ask = (
        baseline_dossier.get("stakeholder_ask")
        if isinstance(baseline_dossier.get("stakeholder_ask"), dict)
        else {}
    )

    thesis = str(raw.get("decision_thesis") or raw.get("thesis") or "").strip()

    raw_blueprint = raw.get("execution_blueprint") if isinstance(raw.get("execution_blueprint"), dict) else {}
    normalized_phases: List[Dict[str, Any]] = []
    for idx, phase in enumerate(raw_blueprint.get("phases") if isinstance(raw_blueprint.get("phases"), list) else [], start=1):
        if not isinstance(phase, dict):
            continue
        start_month = _to_int(phase.get("start_month"))
        end_month = _to_int(phase.get("end_month"))
        if start_month is None or end_month is None:
            continue
        start_month = max(1, min(horizon_months, start_month))
        end_month = max(start_month, min(horizon_months, end_month))
        normalized_phases.append(
            {
                "name": str(phase.get("name") or f"Phase {idx}").strip(),
                "start_month": start_month,
                "end_month": end_month,
                "workstreams": _as_text_list(phase.get("workstreams")),
                "deliverables": _as_text_list(phase.get("deliverables")),
                "dependencies": _as_text_list(phase.get("dependencies")),
                "owner_roles": _as_text_list(phase.get("owner_roles")),
            }
        )

    normalized_blueprint = {
        "phases": normalized_phases
        if normalized_phases
        else (
            baseline_blueprint.get("phases")
            if isinstance(baseline_blueprint.get("phases"), list)
            else []
        ),
        "critical_path": _as_text_list(raw_blueprint.get("critical_path"))
        or _as_text_list(baseline_blueprint.get("critical_path")),
        "gates": _as_text_list(raw_blueprint.get("gates")) or _as_text_list(baseline_blueprint.get("gates")),
        "kill_criteria": _as_text_list(raw_blueprint.get("kill_criteria"))
        or _as_text_list(baseline_blueprint.get("kill_criteria")),
    }

    normalized_risks: List[Dict[str, Any]] = []
    for item in raw.get("risks") if isinstance(raw.get("risks"), list) else []:
        if not isinstance(item, dict):
            continue
        category = str(item.get("category") or "").strip()
        description = str(item.get("description") or "").strip()
        if not category or not description:
            continue
        impact = str(item.get("impact") or "medium").strip().lower()
        if impact not in {"low", "medium", "high"}:
            impact = "medium"
        probability = str(item.get("probability") or "medium").strip().lower()
        if probability not in {"low", "medium", "high"}:
            probability = "medium"
        normalized_risks.append(
            {
                "category": category,
                "description": description,
                "impact": impact,
                "probability": probability,
                "mitigation": str(item.get("mitigation") or "").strip(),
                "owner_role": str(item.get("owner_role") or "").strip(),
                "trigger": str(item.get("trigger") or "").strip(),
            }
        )
    if not normalized_risks:
        normalized_risks = [item for item in baseline_risks if isinstance(item, dict)]

    raw_ask = raw.get("stakeholder_ask") if isinstance(raw.get("stakeholder_ask"), dict) else {}
    decision_required = str(raw_ask.get("decision_required") or "").strip()
    next_30_days = _as_text_list(raw_ask.get("next_30_days"))
    normalized_ask = {
        "decision_required": decision_required or str(baseline_ask.get("decision_required") or ""),
        "next_30_days": next_30_days or _as_text_list(baseline_ask.get("next_30_days")),
    }

    return {
        "decision_thesis": thesis,
        "execution_blueprint": normalized_blueprint,
        "risks": normalized_risks,
        "stakeholder_ask": normalized_ask,
    }


async def _build_execution_plan_narrative_llm(
    source_ctx: Dict[str, Any],
    baseline_dossier: Dict[str, Any],
    scenario_profile: str,
    horizon_months: int,
    currency: str,
    region: str,
) -> Tuple[Dict[str, Any], str, Dict[str, int]]:
    run = source_ctx["run"]
    industry = str(run.get("industry") or "General")
    constraints = run.get("constraints") or []
    persona = str(run.get("tone") or "Neutral")
    selected_model = _resolve_top_model_for_run(run, source_ctx.get("preferred_model_id"))
    selected_output_text = _strip_html_text(selected_model.get("output_html") or "")[:5000]
    baseline_projection = (
        baseline_dossier.get("revenue_profit")
        if isinstance(baseline_dossier.get("revenue_profit"), dict)
        else {}
    )
    model_chain = _execution_plan_model_chain()

    context_payload = {
        "source_type": source_ctx["source_type"],
        "source_id": source_ctx["source_id"],
        "industry": industry,
        "constraints": constraints,
        "persona": persona,
        "scenario_profile": scenario_profile,
        "horizon_months": horizon_months,
        "currency": currency,
        "region": region,
        "selected_model_id": selected_model.get("model_id"),
        "selected_model_label": selected_model.get("model_label"),
        "selected_output_title": selected_model.get("title"),
        "selected_output_excerpt": selected_output_text,
        "evidence_summary": str((source_ctx.get("evidence") or {}).get("summary") or ""),
        "evidence_key_points": list((source_ctx.get("evidence") or {}).get("key_points") or []),
        "baseline_financials": {
            "break_even_month": baseline_projection.get("break_even_month"),
            "year_1_revenue": sum(
                float((row or {}).get("revenue") or 0.0)
                for row in (baseline_projection.get("monthly_projection") if isinstance(baseline_projection.get("monthly_projection"), list) else [])[:12]
            ),
            "year_1_net_profit": sum(
                float((row or {}).get("net_profit") or 0.0)
                for row in (baseline_projection.get("monthly_projection") if isinstance(baseline_projection.get("monthly_projection"), list) else [])[:12]
            ),
        },
        "baseline_blueprint": baseline_dossier.get("execution_blueprint"),
        "baseline_risks": baseline_dossier.get("risks"),
        "baseline_stakeholder_ask": baseline_dossier.get("stakeholder_ask"),
    }

    system_instruction = (
        "You are a principal strategy consultant. Produce narrative-only execution planning guidance. "
        "Return ONLY one valid JSON object with the requested schema and no markdown."
    )
    user_content = (
        "Generate ONLY these fields as JSON:\n"
        "{"
        "\"decision_thesis\":\"string\","
        "\"execution_blueprint\":{\"phases\":[{\"name\":\"string\",\"start_month\":number,\"end_month\":number,\"workstreams\":[\"string\"],\"deliverables\":[\"string\"],\"dependencies\":[\"string\"],\"owner_roles\":[\"string\"]}],\"critical_path\":[\"string\"],\"gates\":[\"string\"],\"kill_criteria\":[\"string\"]},"
        "\"risks\":[{\"category\":\"string\",\"description\":\"string\",\"impact\":\"low|medium|high\",\"probability\":\"low|medium|high\",\"mitigation\":\"string\",\"owner_role\":\"string\",\"trigger\":\"string\"}],"
        "\"stakeholder_ask\":{\"decision_required\":\"string\",\"next_30_days\":[\"string\"]}"
        "}\n\n"
        "Strict rules:\n"
        "- Do NOT generate costs, revenue, margins, break-even, assumptions, or any financial tables.\n"
        "- Do NOT change financial numbers; finance is deterministic and provided separately.\n"
        f"- Ensure phase month ranges stay within 1..{horizon_months}.\n"
        "- Keep language concise, investor-grade, and operationally specific.\n\n"
        f"Context JSON:\n{json.dumps(context_payload, ensure_ascii=False)}"
    )

    text, usage, used_model = await _generate_execution_plan_text(
        system_instruction=system_instruction,
        user_content=user_content,
        model_chain=model_chain,
        temperature=0.2,
        top_p=0.9,
    )
    parsed = _extract_json_object(text)
    if not isinstance(parsed, dict):
        return _normalize_execution_plan_narrative({}, baseline_dossier, horizon_months), used_model, usage
    return _normalize_execution_plan_narrative(parsed, baseline_dossier, horizon_months), used_model, usage


async def _build_execution_plan_grounded_v2(
    source_ctx: Dict[str, Any],
    scenario_profile: str,
    horizon_months: int,
    currency: str,
    region: str,
) -> Tuple[Dict[str, Any], List[Dict[str, Any]], str, Dict[str, int]]:
    selected_profile = "base" if scenario_profile == "all" else scenario_profile
    baseline_dossier, baseline_assumptions = _build_stakeholder_dossier(
        source_ctx=source_ctx,
        scenario_profile=selected_profile,
        horizon_months=horizon_months,
        currency=currency,
        region=region,
    )

    narrative: Dict[str, Any] = {}
    usage: Dict[str, int] = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    used_model = "grounded_finance_v2_deterministic"
    try:
        narrative, used_model, usage = await _build_execution_plan_narrative_llm(
            source_ctx=source_ctx,
            baseline_dossier=baseline_dossier,
            scenario_profile=selected_profile,
            horizon_months=horizon_months,
            currency=currency,
            region=region,
        )
    except Exception as e:
        logger.warning("execution_plan.grounded_v2_narrative_failed error=%s", e)
        narrative = _normalize_execution_plan_narrative({}, baseline_dossier, horizon_months)

    dossier = copy.deepcopy(baseline_dossier)
    decision = dossier.get("decision") if isinstance(dossier.get("decision"), dict) else {}
    if narrative.get("decision_thesis"):
        decision["thesis"] = str(narrative.get("decision_thesis"))
    dossier["decision"] = decision
    if isinstance(narrative.get("execution_blueprint"), dict):
        dossier["execution_blueprint"] = narrative["execution_blueprint"]
    if isinstance(narrative.get("risks"), list):
        dossier["risks"] = narrative["risks"]
    ask = dossier.get("stakeholder_ask") if isinstance(dossier.get("stakeholder_ask"), dict) else {}
    narrative_ask = narrative.get("stakeholder_ask") if isinstance(narrative.get("stakeholder_ask"), dict) else {}
    if narrative_ask.get("decision_required"):
        ask["decision_required"] = str(narrative_ask.get("decision_required"))
    if isinstance(narrative_ask.get("next_30_days"), list) and narrative_ask.get("next_30_days"):
        ask["next_30_days"] = _as_text_list(narrative_ask.get("next_30_days"))
    dossier["stakeholder_ask"] = ask

    source_run = source_ctx.get("run") or {}
    source_selected = _resolve_top_model_for_run(source_run, source_ctx.get("preferred_model_id"))
    provenance = dossier.get("provenance") if isinstance(dossier.get("provenance"), dict) else {}
    provenance.update(
        {
            "source_artifacts": [{"type": source_ctx["source_type"], "id": source_ctx["source_id"]}],
            "selected_run_id": _to_int(source_run.get("id")) or 0,
            "selected_model_id": str(source_selected.get("model_id") or ""),
            "selected_output_title": str(source_selected.get("title") or ""),
            "financials_grounded": True,
            "finance_mode": "grounded_v2",
            "formula_version": "stakeholder_finance_v2",
            "generator_version": "grounded_finance_v2_narrative_llm_v1",
            "narrative_model": used_model,
        }
    )
    dossier["provenance"] = provenance

    validated, errors = _validate_execution_plan_dossier(dossier, horizon_months, currency, source_ctx)
    if errors or not validated:
        logger.warning("execution_plan.grounded_v2_validation_failed errors=%s", errors[:3] if errors else [])
        fallback_dossier = copy.deepcopy(baseline_dossier)
        fallback_provenance = (
            fallback_dossier.get("provenance")
            if isinstance(fallback_dossier.get("provenance"), dict)
            else {}
        )
        fallback_provenance.update(provenance)
        fallback_provenance["generator_version"] = "grounded_finance_v2_deterministic_fallback"
        fallback_dossier["provenance"] = fallback_provenance
        validated, fallback_errors = _validate_execution_plan_dossier(
            fallback_dossier,
            horizon_months,
            currency,
            source_ctx,
        )
        if fallback_errors or not validated:
            detail = "Grounded Finance v2 dossier validation failed."
            if fallback_errors:
                detail = f"{detail} First issue: {fallback_errors[0]}"
            raise HTTPException(status_code=502, detail=detail)

    assumptions_list = validated.get("assumptions") if isinstance(validated.get("assumptions"), list) else baseline_assumptions
    return validated, assumptions_list, used_model, usage


async def _build_execution_plan_llm(
    source_ctx: Dict[str, Any],
    scenario_profile: str,
    horizon_months: int,
    currency: str,
    region: str,
) -> Tuple[Dict[str, Any], List[Dict[str, Any]], str, Dict[str, int]]:
    run = source_ctx["run"]
    industry = str(run.get("industry") or "General")
    constraints = run.get("constraints") or []
    persona = str(run.get("tone") or "Neutral")
    selected_model = _resolve_top_model_for_run(run, source_ctx.get("preferred_model_id"))
    selected_output_text = _strip_html_text(selected_model.get("output_html") or "")[:6000]
    assumptions = util_merge_assumptions(industry)
    selected_profile = "base" if scenario_profile == "all" else scenario_profile
    model_chain = _execution_plan_model_chain()
    baseline_dossier, baseline_assumptions = _build_stakeholder_dossier(
        source_ctx=source_ctx,
        scenario_profile=selected_profile,
        horizon_months=horizon_months,
        currency=currency,
        region=region,
    )

    context_payload = {
        "source_type": source_ctx["source_type"],
        "source_id": source_ctx["source_id"],
        "industry": industry,
        "constraints": constraints,
        "persona": persona,
        "selected_model_id": selected_model.get("model_id"),
        "selected_model_label": selected_model.get("model_label"),
        "selected_output_title": selected_model.get("title"),
        "selected_output_excerpt": selected_output_text,
        "evidence_summary": str((source_ctx.get("evidence") or {}).get("summary") or ""),
        "evidence_key_points": list((source_ctx.get("evidence") or {}).get("key_points") or []),
        "assumption_pack": assumptions,
        "scenario_profile": selected_profile,
        "horizon_months": horizon_months,
        "currency": currency,
        "region": region,
        "grounded_financial_baseline": {
            "costs": baseline_dossier.get("costs"),
            "revenue_profit": baseline_dossier.get("revenue_profit"),
            "scenarios": baseline_dossier.get("scenarios"),
            "stakeholder_ask": baseline_dossier.get("stakeholder_ask"),
        },
    }

    system_instruction = (
        "You are a principal strategy consultant producing investor-grade execution plans. "
        "Return ONLY one valid JSON object (no markdown, no prose, no code fences). "
        "All currency figures must be numeric USD amounts. "
        "Keep monthly_projection exactly horizon_months rows."
    )
    user_content = (
        "Build an execution plan JSON using this exact schema and field names:\n"
        "{"
        "\"meta\":{\"report_version\":\"string\",\"generated_at\":\"ISO-8601\",\"currency\":\"USD\",\"horizon_months\":number},"
        "\"decision\":{\"winner\":{\"run_id\":number,\"model_id\":\"string\",\"title\":\"string\"},\"thesis\":\"string\",\"go_no_go\":\"go|conditional_go|no_go\",\"confidence\":number},"
        "\"execution_blueprint\":{\"phases\":[{\"name\":\"string\",\"start_month\":number,\"end_month\":number,\"workstreams\":[\"string\"],\"deliverables\":[\"string\"],\"dependencies\":[\"string\"],\"owner_roles\":[\"string\"]}],\"critical_path\":[\"string\"],\"gates\":[\"string\"],\"kill_criteria\":[\"string\"]},"
        "\"resources\":{\"roles\":[{\"role\":\"string\",\"fte_by_month\":[number],\"employment_type\":\"string\",\"cost_monthly\":[number]}],\"tooling\":[{\"name\":\"string\",\"category\":\"string\",\"monthly_cost\":number}],\"external_dependencies\":[\"string\"]},"
        "\"costs\":{\"setup_cost\":{\"engineering\":number,\"legal_compliance\":number,\"launch_marketing\":number,\"other\":number,\"total\":number},\"monthly_opex\":[{\"month\":number,\"payroll\":number,\"infra\":number,\"ai_inference\":number,\"tools\":number,\"sales_marketing\":number,\"other\":number,\"total\":number}],\"unit_cogs\":{\"per_customer_monthly\":number,\"components\":[{\"name\":\"string\",\"amount\":number}]}},"
        "\"revenue_profit\":{\"pricing\":{\"model\":\"string\",\"arpu_monthly\":number},\"funnel_assumptions\":{\"traffic_to_lead\":number,\"lead_to_sql\":number,\"sql_to_customer\":number},\"monthly_projection\":[{\"month\":number,\"customers\":number,\"revenue\":number,\"cogs\":number,\"gross_profit\":number,\"opex\":number,\"net_profit\":number,\"cumulative_net_profit\":number}],\"break_even_month\":number},"
        "\"scenarios\":[{\"name\":\"conservative|base|aggressive\",\"probability\":number,\"key_assumptions\":[\"string\"],\"year_1_revenue\":number,\"year_1_net_profit\":number}],"
        "\"risks\":[{\"category\":\"string\",\"description\":\"string\",\"impact\":\"low|medium|high\",\"probability\":\"low|medium|high\",\"mitigation\":\"string\",\"owner_role\":\"string\",\"trigger\":\"string\"}],"
        "\"stakeholder_ask\":{\"budget_required\":number,\"team_required\":[\"string\"],\"decision_required\":\"string\",\"next_30_days\":[\"string\"]},"
        "\"assumptions\":[{\"key\":\"string\",\"value\":number|\"string\",\"unit\":\"string\",\"source\":\"string\",\"confidence\":\"low|medium|high\"}],"
        "\"provenance\":{\"source_artifacts\":[{\"type\":\"string\",\"id\":number}],\"formula_version\":\"string\",\"generator_version\":\"string\"}"
        "}\n\n"
        "Hard requirements:\n"
        f"- horizon_months is {horizon_months}; all month-indexed arrays must match that horizon where applicable.\n"
        "- setup_cost.total must equal the sum of engineering + legal_compliance + launch_marketing + other.\n"
        "- monthly_projection must have monotonic month values starting at 1.\n"
        "- probabilities in scenarios should approximately sum to 1.0.\n"
        "- Use pragmatic, investor-grade language and realistic numbers.\n\n"
        f"Context JSON:\n{json.dumps(context_payload, ensure_ascii=False)}"
    )

    total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    first_text, first_usage, used_model = await _generate_execution_plan_text(
        system_instruction=system_instruction,
        user_content=user_content,
        model_chain=model_chain,
    )
    for key in total_usage.keys():
        total_usage[key] += int((first_usage or {}).get(key, 0) or 0)

    parsed = _extract_json_object(first_text)
    normalized, errors = _validate_execution_plan_dossier(parsed or {}, horizon_months, currency, source_ctx)
    if not errors and normalized:
        grounded = _apply_execution_plan_financial_baseline(
            llm_dossier=normalized,
            baseline_dossier=baseline_dossier,
            baseline_assumptions=baseline_assumptions,
            source_ctx=source_ctx,
            horizon_months=horizon_months,
            currency=currency,
        )
        assumptions_list = grounded.get("assumptions") if isinstance(grounded.get("assumptions"), list) else []
        return grounded, assumptions_list, used_model, total_usage

    repair_system = (
        "You repair invalid JSON for an execution plan schema. "
        "Return ONLY one valid JSON object matching the required schema and fixing all listed errors."
    )
    repair_user = (
        f"Validation errors:\n- " + "\n- ".join(errors[:20]) + "\n\n"
        "Original JSON candidate:\n"
        f"{first_text[:12000]}"
    )
    repair_text, repair_usage, repair_model = await _generate_execution_plan_text(
        system_instruction=repair_system,
        user_content=repair_user,
        model_chain=[used_model] + [m for m in model_chain if m != used_model],
        temperature=0.1,
        top_p=0.9,
    )
    for key in total_usage.keys():
        total_usage[key] += int((repair_usage or {}).get(key, 0) or 0)

    parsed_repair = _extract_json_object(repair_text)
    normalized_repair, repair_errors = _validate_execution_plan_dossier(
        parsed_repair or {},
        horizon_months,
        currency,
        source_ctx,
    )
    if repair_errors or not normalized_repair:
        detail = "Execution plan generation failed schema validation."
        if repair_errors:
            detail = f"{detail} First issue: {repair_errors[0]}"
        raise HTTPException(status_code=502, detail=detail)

    grounded_repair = _apply_execution_plan_financial_baseline(
        llm_dossier=normalized_repair,
        baseline_dossier=baseline_dossier,
        baseline_assumptions=baseline_assumptions,
        source_ctx=source_ctx,
        horizon_months=horizon_months,
        currency=currency,
    )
    assumptions_list = grounded_repair.get("assumptions") if isinstance(grounded_repair.get("assumptions"), list) else []
    return grounded_repair, assumptions_list, repair_model, total_usage



# --- API Endpoints ---
# index.py (agentic /api replacement)
# index.py - updated /api endpoint using FALLBACK_CHAINS + agentic generation + partial success


@app.get("/api/subscription")
async def subscription(creds=Depends(clerk_guard)):
    decoded = getattr(creds, "decoded", {}) or {}
    user_id = decoded.get("sub")
    plan = decoded.get("pla") or "u:free_user"

    db.ensure_user(user_id, plan)
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


@app.delete("/api/saved-results")
async def delete_all_saved_results(creds: HTTPAuthorizationCredentials = Depends(clerk_guard)):
    user_id = creds.decoded.get("sub")
    deleted_count = db.delete_all_saved_results(user_id)
    return {"status": "deleted", "count": deleted_count}


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
        return {
            "industry": str(run.get("industry") or "").strip().lower(),
            "tone": str(run.get("tone") or "").strip().lower(),
            "constraints": sorted(constraints),
        }

    if normalized_config(run_a) != normalized_config(run_b):
        raise HTTPException(
            status_code=400,
            detail="Diff analysis requires the same industry, persona, and constraints.",
        )

    cached = db.get_saved_comparison(user_id, request.run_a_id, request.run_b_id)
    if cached:
        comparison = cached.get("comparison", {}) or {}
        top_outputs = comparison.get("top_outputs") if isinstance(comparison.get("top_outputs"), dict) else {}
        run_a_top = top_outputs.get("run_a") if isinstance(top_outputs.get("run_a"), dict) else {}
        run_b_top = top_outputs.get("run_b") if isinstance(top_outputs.get("run_b"), dict) else {}
        needs_top_output_backfill = (
            not run_a_top.get("output_html")
            or not run_b_top.get("output_html")
            or "score" not in run_a_top
            or "score" not in run_b_top
        )
        if needs_top_output_backfill:
            def select_cached_top(run: Dict[str, Any]) -> Dict[str, Any]:
                results = run.get("results") or {}
                if not results:
                    return {
                        "selected_model_id": "",
                        "selected_model_label": "",
                        "selected_title": "Untitled result",
                        "selected_output": "",
                        "selected_score": None,
                    }
                rank_result = run.get("rank_result") if isinstance(run.get("rank_result"), dict) else None
                selected_model_id = None
                selected_score = None
                ranked = rank_result.get("ranked_models") if isinstance(rank_result, dict) else None
                if isinstance(ranked, list):
                    ranked_sorted = sorted(ranked, key=lambda item: int(item.get("rank", 9999)))
                    for item in ranked_sorted:
                        model_id = str(item.get("model_id", "")).strip()
                        if model_id and model_id in results:
                            selected_model_id = model_id
                            raw_score = item.get("score")
                            if isinstance(raw_score, (int, float)):
                                selected_score = raw_score
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
                    "selected_score": selected_score,
                }

            cached_a = select_cached_top(run_a)
            cached_b = select_cached_top(run_b)
            comparison["top_outputs"] = {
                "run_a": {
                    "title": cached_a.get("selected_title") or "Untitled result",
                    "model_label": cached_a.get("selected_model_label") or "Model",
                    "model_id": cached_a.get("selected_model_id") or "",
                    "output_html": cached_a.get("selected_output") or "",
                    "score": cached_a.get("selected_score"),
                },
                "run_b": {
                    "title": cached_b.get("selected_title") or "Untitled result",
                    "model_label": cached_b.get("selected_model_label") or "Model",
                    "model_id": cached_b.get("selected_model_id") or "",
                    "output_html": cached_b.get("selected_output") or "",
                    "score": cached_b.get("selected_score"),
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
                "selected_score": None,
            }
        selected_model_id = None
        selected_score = None
        ranked = rank_result.get("ranked_models") if isinstance(rank_result, dict) else None
        if isinstance(ranked, list):
            ranked_sorted = sorted(ranked, key=lambda item: int(item.get("rank", 9999)))
            for item in ranked_sorted:
                model_id = str(item.get("model_id", "")).strip()
                if model_id and model_id in results:
                    selected_model_id = model_id
                    raw_score = item.get("score")
                    if isinstance(raw_score, (int, float)):
                        selected_score = raw_score
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
            "selected_score": selected_score,
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
            "score": selected_a.get("selected_score"),
        },
        "run_b": {
            "title": selected_b.get("selected_title") or "Untitled result",
            "model_label": selected_b.get("selected_model_label") or "Model",
            "model_id": selected_b.get("selected_model_id") or "",
            "output_html": selected_b.get("selected_output") or "",
            "score": selected_b.get("selected_score"),
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


@app.delete("/api/compare-results")
async def delete_all_compare_results(creds: HTTPAuthorizationCredentials = Depends(clerk_guard)):
    user_id = creds.decoded.get("sub")
    deleted_count = db.delete_all_saved_comparisons(user_id)
    return {"status": "deleted", "count": deleted_count}


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
    run_a_top = top_outputs.get("run_a") if isinstance(top_outputs.get("run_a"), dict) else {}
    run_b_top = top_outputs.get("run_b") if isinstance(top_outputs.get("run_b"), dict) else {}
    need_backfill = (
        not run_a_top.get("output_html")
        or not run_b_top.get("output_html")
        or "score" not in run_a_top
        or "score" not in run_b_top
    )

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
                    "selected_score": None,
                }
            rank_result = run.get("rank_result") if isinstance(run.get("rank_result"), dict) else None
            selected_model_id = None
            selected_score = None
            ranked = rank_result.get("ranked_models") if isinstance(rank_result, dict) else None
            if isinstance(ranked, list):
                ranked_sorted = sorted(ranked, key=lambda item: int(item.get("rank", 9999)))
                for item in ranked_sorted:
                    model_id = str(item.get("model_id", "")).strip()
                    if model_id and model_id in results:
                        selected_model_id = model_id
                        raw_score = item.get("score")
                        if isinstance(raw_score, (int, float)):
                            selected_score = raw_score
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
                "selected_score": selected_score,
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
                    "score": selected_a.get("selected_score"),
                },
                "run_b": {
                    "title": selected_b.get("selected_title") or "Untitled result",
                    "model_label": selected_b.get("selected_model_label") or "Model",
                    "model_id": selected_b.get("selected_model_id") or "",
                    "output_html": selected_b.get("selected_output") or "",
                    "score": selected_b.get("selected_score"),
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
    run_a_top = top_outputs.get("run_a") if isinstance(top_outputs.get("run_a"), dict) else {}
    run_b_top = top_outputs.get("run_b") if isinstance(top_outputs.get("run_b"), dict) else {}
    need_backfill = (
        not run_a_top.get("output_html")
        or not run_b_top.get("output_html")
        or "score" not in run_a_top
        or "score" not in run_b_top
    )

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
                    "selected_score": None,
                }
            rank_result = run.get("rank_result") if isinstance(run.get("rank_result"), dict) else None
            selected_model_id = None
            selected_score = None
            ranked = rank_result.get("ranked_models") if isinstance(rank_result, dict) else None
            if isinstance(ranked, list):
                ranked_sorted = sorted(ranked, key=lambda item: int(item.get("rank", 9999)))
                for item in ranked_sorted:
                    model_id = str(item.get("model_id", "")).strip()
                    if model_id and model_id in results:
                        selected_model_id = model_id
                        raw_score = item.get("score")
                        if isinstance(raw_score, (int, float)):
                            selected_score = raw_score
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
                "selected_score": selected_score,
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
                    "score": selected_a.get("selected_score"),
                },
                "run_b": {
                    "title": selected_b.get("selected_title") or "Untitled result",
                    "model_label": selected_b.get("selected_model_label") or "Model",
                    "model_id": selected_b.get("selected_model_id") or "",
                    "output_html": selected_b.get("selected_output") or "",
                    "score": selected_b.get("selected_score"),
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


@app.delete("/api/rank-reports")
async def delete_all_rank_reports(creds: HTTPAuthorizationCredentials = Depends(clerk_guard)):
    user_id = creds.decoded.get("sub")
    deleted_count = db.delete_all_saved_rank_reports(user_id)
    return {"status": "deleted", "count": deleted_count}


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


@app.delete("/api/rank-reports/{report_id}")
async def delete_rank_report(report_id: int, creds: HTTPAuthorizationCredentials = Depends(clerk_guard)):
    user_id = creds.decoded.get("sub")
    deleted = db.delete_saved_rank_report(user_id, report_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Report not found.")
    return {"status": "deleted"}


def _validate_stakeholder_request_options(request: StakeholderReportRequest) -> Dict[str, str]:
    output = (request.output or "").strip().lower()
    if output != "json":
        raise HTTPException(status_code=400, detail="Execution Plan supports output=json only.")

    scenario_profile = (request.scenario_profile or "base").strip().lower()
    if scenario_profile not in {"conservative", "base", "aggressive", "all"}:
        raise HTTPException(status_code=400, detail="scenario_profile must be conservative, base, aggressive, or all.")

    finance_mode = (request.finance_mode or "grounded_v2").strip().lower()
    if finance_mode not in {"grounded_v2", "llm_v1"}:
        raise HTTPException(status_code=400, detail="finance_mode must be grounded_v2 or llm_v1.")

    currency = (request.currency or "USD").strip().upper()
    if currency != "USD":
        raise HTTPException(status_code=400, detail="Only USD is currently supported.")

    region = (request.region or "US").strip().upper()
    if region != "US":
        raise HTTPException(status_code=400, detail="Only US region assumptions are currently supported.")

    return {
        "output": output,
        "scenario_profile": scenario_profile,
        "finance_mode": finance_mode,
        "currency": currency,
        "region": region,
    }


async def _generate_stakeholder_dossier(
    *,
    source_ctx: Dict[str, Any],
    options: Dict[str, str],
    horizon_months: int,
) -> Tuple[Dict[str, Any], List[Dict[str, Any]], str, Dict[str, int]]:
    common_kwargs = {
        "source_ctx": source_ctx,
        "scenario_profile": options["scenario_profile"],
        "horizon_months": horizon_months,
        "currency": options["currency"],
        "region": options["region"],
    }
    if options["finance_mode"] == "llm_v1":
        return await _build_execution_plan_llm(**common_kwargs)
    return await _build_execution_plan_grounded_v2(**common_kwargs)


def _persist_stakeholder_report(
    *,
    user_id: str,
    source_ctx: Dict[str, Any],
    options: Dict[str, str],
    horizon_months: int,
    dossier: Dict[str, Any],
    assumptions: List[Dict[str, Any]],
    model: str,
) -> Dict[str, Any]:
    return db.save_stakeholder_report(
        user_id=user_id,
        source_type=source_ctx["source_type"],
        source_id=source_ctx["source_id"],
        scenario_profile=options["scenario_profile"],
        horizon_months=horizon_months,
        currency=options["currency"],
        region=options["region"],
        dossier=dossier,
        assumptions=assumptions,
        model=model,
    )


@app.post("/api/stakeholder-report")
async def create_stakeholder_report(request: StakeholderReportRequest, creds: HTTPAuthorizationCredentials = Depends(clerk_guard)):
    user_id = creds.decoded.get("sub")
    plan = get_user_plan(creds)
    allowed, msg = db.check_and_increment_api_call(user_id, plan)
    if not allowed:
        return JSONResponse(content={"error": msg}, status_code=429)
    options = _validate_stakeholder_request_options(request)
    source_ctx = _resolve_stakeholder_source(user_id, request.source)
    dossier, assumptions, used_model, usage = await _generate_stakeholder_dossier(
        source_ctx=source_ctx,
        options=options,
        horizon_months=request.horizon_months,
    )
    if usage.get("total_tokens", 0):
        db.track_token_usage(user_id, int(usage["total_tokens"]))

    saved = _persist_stakeholder_report(
        user_id=user_id,
        source_ctx=source_ctx,
        options=options,
        horizon_months=request.horizon_months,
        dossier=dossier,
        assumptions=assumptions,
        model=used_model,
    )
    return {
        "id": saved.get("id"),
        "created_at": saved.get("created_at"),
        "status": "ready",
        "model": used_model,
        "usage": usage,
        "dossier": dossier,
    }


@app.get("/api/stakeholder-reports")
async def list_stakeholder_reports(limit: int = 6, creds: HTTPAuthorizationCredentials = Depends(clerk_guard)):
    user_id = creds.decoded.get("sub")
    return {"reports": db.list_saved_stakeholder_reports(user_id, limit=limit)}


@app.get("/api/stakeholder-reports/{report_id}")
async def get_stakeholder_report(report_id: int, creds: HTTPAuthorizationCredentials = Depends(clerk_guard)):
    user_id = creds.decoded.get("sub")
    saved = db.get_saved_stakeholder_report_by_id(user_id, report_id)
    if not saved:
        raise HTTPException(status_code=404, detail="Stakeholder report not found.")
    return saved


@app.get("/api/stakeholder-reports/{report_id}/pdf")
async def download_stakeholder_report_pdf(report_id: int, creds: HTTPAuthorizationCredentials = Depends(clerk_guard)):
    user_id = creds.decoded.get("sub")
    saved = db.get_saved_stakeholder_report_by_id(user_id, report_id)
    if not saved:
        raise HTTPException(status_code=404, detail="Execution plan not found.")
    html = create_execution_plan_report_html(saved)
    pdf_bytes = html_to_pdf_bytes(html)
    created_at = saved.get("created_at")
    created_dt = None
    if isinstance(created_at, str):
        try:
            created_dt = datetime.fromisoformat(created_at)
        except ValueError:
            created_dt = None
    filename = build_execution_plan_filename(created_dt)
    headers = {"Content-Disposition": f"attachment;filename={filename}"}
    return StreamingResponse(io.BytesIO(pdf_bytes), media_type="application/pdf", headers=headers)


@app.get("/api/stakeholder-reports/{report_id}/presentation")
async def download_stakeholder_report_presentation(report_id: int, creds: HTTPAuthorizationCredentials = Depends(clerk_guard)):
    user_id = creds.decoded.get("sub")
    saved = db.get_saved_stakeholder_report_by_id(user_id, report_id)
    if not saved:
        raise HTTPException(status_code=404, detail="Execution plan not found.")
    html = create_execution_plan_presentation_html(saved)
    pdf_bytes = html_to_pdf_bytes(html)
    created_at = saved.get("created_at")
    created_dt = None
    if isinstance(created_at, str):
        try:
            created_dt = datetime.fromisoformat(created_at)
        except ValueError:
            created_dt = None
    filename = build_execution_plan_presentation_filename(created_dt)
    headers = {"Content-Disposition": f"attachment;filename={filename}"}
    return StreamingResponse(io.BytesIO(pdf_bytes), media_type="application/pdf", headers=headers)


@app.delete("/api/stakeholder-reports/{report_id}")
async def delete_stakeholder_report(report_id: int, creds: HTTPAuthorizationCredentials = Depends(clerk_guard)):
    user_id = creds.decoded.get("sub")
    deleted = db.delete_saved_stakeholder_report(user_id, report_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Stakeholder report not found.")
    return {"status": "deleted"}


@app.delete("/api/stakeholder-reports")
async def delete_all_stakeholder_reports(creds: HTTPAuthorizationCredentials = Depends(clerk_guard)):
    user_id = creds.decoded.get("sub")
    deleted_count = db.delete_all_saved_stakeholder_reports(user_id)
    return {"status": "deleted", "count": deleted_count}


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
    if output in {"email", "both"}:
        allowed, msg = db.check_and_increment_email(user_id, plan)
        if not allowed:
            raise HTTPException(status_code=429, detail=msg)
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
            cached_snapshot = cached.get("runs_snapshot") or []
            needs_snapshot = not cached_snapshot
            if not needs_snapshot:
                # Backfill legacy snapshots that were stored without rank_result metadata.
                for run in cached_snapshot:
                    if not isinstance(run, dict) or not isinstance(run.get("rank_result"), dict):
                        needs_snapshot = True
                        break
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
        client=deepseek_client,
        model=DEEPSEEK_MODEL,
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
