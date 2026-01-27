import asyncio
import json
import re
import hashlib
from collections import OrderedDict
from pathlib import Path
from typing import AsyncGenerator, Dict, Any, Callable, Awaitable, Optional

from openai import AsyncOpenAI
from .models import Visit
from .utils import generate_with_fallback, get_logger
from .utils.templates import get_template
from .utils.html_sections import ensure_html_summary, html_to_text
from .utils import guardrails as guardrails_util
from . import extraction_agent, coordinator_agent, memory_agent, research_agent, critic_agent, evidence_agent

logger = get_logger(__name__)

SUMMARY_CACHE: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()
SUMMARY_CACHE_MAX = 10
MEMORY_DB_PATH = Path("data/memory_db.json")

MEDICATION_HINT_RE = re.compile(
    r"\b(?:mg|mcg|g|ml|units|tablet|tab|capsule|cap|injection|iv|po|bid|tid|qid|qd|prn|rx|prescribed|medication|medications)\b",
    re.IGNORECASE,
)
DOSAGE_RE = re.compile(r"\b\d+(?:\.\d+)?\s?(?:mg|mcg|g|ml|units)\b", re.IGNORECASE)
CONDITION_HINT_RE = re.compile(
    r"\b(?:diagnosis|diagnosed|dx|impression|assessment|condition|disease|syndrome|infection|hypertension|diabetes|asthma|pneumonia|cancer|fracture)\b",
    re.IGNORECASE,
)

BASE_SYSTEM_PROMPT = """
You are an expert Clinical Medical Scribe and Physician Assistant.
Your goal is to generate a professional, accurate, and concise clinical summary based ONLY on the provided doctor's notes, patient history, research findings, and ALL attached files (documents, audio transcripts, prescription images).

# CORE RESPONSIBILITIES
1. ACCURACY: Do not invent, hallucinate, or assume information not present in the source text. If a detail is missing, omit it or state "Not documented."
2. INTEGRATION: You must synthesize information from ALL sources. If a prescription image is provided, list its medications. If an audio transcript is provided, include its details. Do not ignore attachments.
3. PROFESSIONALISM: Use standard medical terminology (e.g., "patient reports" instead of "patient said"). Use abbreviations only if standard (e.g., HTN, DM2, BP).
4. SAFETY: Explicitly highlight any drug interactions or guideline warnings provided in the context.

# OUTPUT STRUCTURE
You must output strict HTML with exactly these three sections:

<section data-section="summary">
  <h3>Summary of visit for the doctor's records</h3>
  [Content: A comprehensive medical note. Include Subjective (HPI, ROS), Objective (Vitals, PE, Labs), Assessment (Diagnoses), and Plan (Treatment, Follow-up). Integrate safety/guideline notes here.]
</section>

<section data-section="next_steps">
  <h3>Next steps for the doctor</h3>
  <ul>
    <li>[Actionable item 1]</li>
    <li>[Actionable item 2]</li>
  </ul>
</section>

<section data-section="patient_email">
  <h3>Draft Email for Patient</h3>
  <p>[Patient-friendly language. 6th-grade reading level. Clear instructions. No medical jargon without explanation.]</p>
</section>

# CRITICAL INSTRUCTIONS
- Do not sign the email.
- Do not include text outside the sections.
- If Research/Guideline findings are provided, you MUST incorporate them into the 'Assessment' or 'Plan' as a "Clinical Safety Note" or "Guideline Note".
"""


def _build_system_prompt() -> str:
    guardrails = guardrails_util.get_guardrails()
    if not guardrails:
        return BASE_SYSTEM_PROMPT
    lines = "\n- ".join(guardrails)
    return f"{BASE_SYSTEM_PROMPT}\n\nFormat guardrails:\n- {lines}"

RESEARCH_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "check_drug_interactions",
            "description": "Checks for potential interactions between a list of 2 or more medications.",
            "parameters": {
                "type": "object",
                "properties": {
                    "medications": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "A list of medication names to check.",
                    }
                },
                "required": ["medications"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_medical_guidelines",
            "description": "Finds guideline recommendations for a clinical condition.",
            "parameters": {
                "type": "object",
                "properties": {
                    "condition": {
                        "type": "string",
                        "description": "The condition to research.",
                    }
                },
                "required": ["condition"],
            },
        },
    }
]

COORDINATOR_TOOL = [
    {
        "type": "function",
        "function": {
            "name": "extract_actions",
            "description": "Extracts structured next-step actions from a clinical summary.",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary_html": {
                        "type": "string",
                        "description": "The full HTML summary to analyze.",
                    }
                },
                "required": ["summary_html"],
            },
        },
    }
]

def summary_prompt_for(visit: Visit, context: dict) -> str:
    attachment_block = ""
    if context.get("attachments"):
        attachment_block = "\n\n" + "\n\n".join(
            f"{label}:\n{text}" for label, text in context["attachments"]
        )
    
    history_block = ""
    if context.get("patient_history"):
        history_block = f"\n\n{context['patient_history']}"

    research_block = _format_findings_block(
        "Safety Check / Research Findings",
        context.get("research_findings"),
    )

    guidelines_block = _format_findings_block(
        "Guideline Findings",
        context.get("guideline_findings"),
    )

    doctor_block = ""
    doctor_info = context.get("doctor_info") or {}
    doctor_name = (doctor_info.get("doctor_name") or "").strip()
    if doctor_name:
        doctor_block = f"\n\nAttending Physician: {doctor_name}"

    template = get_template(visit)

    return f"""Create the summary, next steps and draft email for:
Patient Name: {visit.patient_name}
Date of Visit: {visit.date_of_visit}
Notes:
{context["notes_text"]}{attachment_block}{history_block}{research_block}{guidelines_block}{doctor_block}

Template: {template["label"]}
{template["summary_html"]}
Follow the template exactly and do not add or remove headings.
If two or more medications are mentioned, call the check_drug_interactions tool with a list of medication names.
If a condition or diagnosis is mentioned, call search_medical_guidelines with the condition name.
After drafting the summary, call extract_actions with the full HTML summary.
If there are any safety findings, incorporate a 'Clinical Safety Note' into the 'Assessment' or 'Plan' section of your summary.
If there are guideline findings, incorporate a short 'Guideline Note' into the 'Assessment' or 'Plan' section.
If an attending physician is provided, include a line "Attending Physician: <name>" in the Summary section (sentence only, not a heading).
For the Next steps section, use a <ul> list with clear, actionable items.
For the patient email section, use short <p> paragraphs in patient-friendly language."""


def _format_findings_block(label: str, value: Any) -> str:
    if not value:
        return ""
    items = value if isinstance(value, list) else [value]
    lines = []
    for item in items:
        if isinstance(item, dict):
            text = item.get("summary") or item.get("text") or ""
        else:
            text = str(item)
        text = text.strip()
        if text:
            lines.append(text)
    if not lines:
        return ""
    formatted = "\n- ".join(lines)
    return f"\n\n{label}:\n- {formatted}"


def correction_prompt_for(
    visit: Visit,
    context: dict,
    summary_html: str,
    review: Dict[str, Any],
) -> str:
    attachment_block = ""
    if context.get("attachments"):
        attachment_block = "\n\n" + "\n\n".join(
            f"{label}:\n{text}" for label, text in context["attachments"]
        )

    history_block = ""
    if context.get("patient_history"):
        history_block = f"\n\n{context['patient_history']}"

    research_block = _format_findings_block("Safety Check / Research Findings", context.get("research_findings"))
    guidelines_block = _format_findings_block("Guideline Findings", context.get("guideline_findings"))

    template = get_template(visit)
    issues = critic_agent.format_issue_lines(review)
    issues_text = "\n- ".join(issues) if issues else "No issues reported."

    return f"""Revise the clinical summary to fix the issues below.
Do not introduce new facts. Use only the provided source text.
Keep the exact HTML structure with three sections.

Issues to fix:
- {issues_text}

Current summary (HTML):
{summary_html}

Source notes:
{context["notes_text"]}{attachment_block}{history_block}{research_block}{guidelines_block}

Template: {template["label"]}
{template["summary_html"]}
Follow the template exactly and do not add or remove headings.
Return only the three HTML sections."""


def _has_medication_candidates(text: str) -> bool:
    if not text:
        return False
    if DOSAGE_RE.search(text):
        return True
    return bool(MEDICATION_HINT_RE.search(text))


def _has_condition_candidates(text: str) -> bool:
    if not text:
        return False
    return bool(CONDITION_HINT_RE.search(text))


def _memory_db_mtime() -> float:
    try:
        return MEMORY_DB_PATH.stat().st_mtime
    except FileNotFoundError:
        return 0.0


def _summary_cache_key(visit: Visit) -> str:
    payload = visit.model_dump()
    payload["_memory_db_mtime"] = _memory_db_mtime()
    raw = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _cache_get(key: str) -> Dict[str, Any] | None:
    cached = SUMMARY_CACHE.get(key)
    if cached:
        SUMMARY_CACHE.move_to_end(key)
    return cached


def _cache_set(key: str, value: Dict[str, Any]) -> None:
    SUMMARY_CACHE[key] = value
    SUMMARY_CACHE.move_to_end(key)
    while len(SUMMARY_CACHE) > SUMMARY_CACHE_MAX:
        SUMMARY_CACHE.popitem(last=False)


def _normalize_notes_text(text: str) -> str:
    if not text:
        return ""
    lines = [line.rstrip() for line in text.splitlines()]
    cleaned = []
    blank = False
    for line in lines:
        if not line.strip():
            if not blank:
                cleaned.append("")
                blank = True
            continue
        cleaned.append(line)
        blank = False
    return "\n".join(cleaned).strip()


def _format_evidence_text(evidence_map: Dict[str, Any]) -> str:
    if not evidence_map:
        return ""
    citations = evidence_map.get("citations") or []
    chunks = evidence_map.get("chunks") or []
    if not citations or not chunks:
        return ""
    chunk_lookup = {chunk.get("id"): chunk for chunk in chunks if chunk.get("id")}
    lines = ["Evidence Links:"]
    for item in citations:
        sentence = (item.get("sentence") or "").strip()
        if not sentence:
            continue
        lines.append(f"- {sentence}")
        snippets = item.get("snippets") or {}
        for chunk_id in item.get("chunk_ids") or []:
            chunk = chunk_lookup.get(chunk_id)
            if not chunk:
                continue
            source = chunk.get("source") or "Source"
            snippet = (snippets.get(chunk_id) or chunk.get("text") or "").strip()
            if len(snippet) > 140:
                snippet = snippet[:140] + "..."
            lines.append(f"  - {source}: {snippet}")
            for link in chunk.get("sources") or []:
                url = (link.get("url") or "").strip()
                if not url:
                    continue
                title = (link.get("title") or "").strip()
                if title:
                    lines.append(f"    - {title}: {url}")
                else:
                    lines.append(f"    - {url}")
    return "\n".join(lines).strip()



async def _fill_doctor_info_from_summary(
    doctor_info: Dict[str, Any],
    summary_html: str,
    client: AsyncOpenAI,
) -> Dict[str, Any]:
    summary_text = html_to_text(summary_html)
    if not summary_text:
        return doctor_info
    try:
        extracted = await extraction_agent.extract_doctor_info(summary_text, client)
    except Exception as exc:
        logger.warning(f"Failed to extract doctor info from summary: {exc}")
        return doctor_info

    for key in ("doctor_name", "doctor_phone", "clinic_name", "doctor_email"):
        existing = (doctor_info.get(key) or "").strip()
        candidate = (extracted.get(key) or "").strip()
        if not existing and candidate:
            doctor_info[key] = candidate
            logger.info("Filled %s from summary text.", key)

    return doctor_info


async def generate_summary_stream(
    visit: Visit,
    context: Dict[str, Any],
    doctor_info: Dict[str, Any],
    client: AsyncOpenAI,
    should_abort: Optional[Callable[[], Awaitable[bool]]] = None,
) -> AsyncGenerator[str, None]:
    async def _abort_now(stage: str) -> bool:
        if should_abort and await should_abort():
            logger.info("Summary generation aborted: %s", stage)
            return True
        return False

    if await _abort_now("before prompt assembly"):
        return
    user_prompt = summary_prompt_for(visit, context)
    system_prompt = _build_system_prompt()
    prompt = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    actions_from_tool = None
    try:
        if await _abort_now("before initial generation"):
            return
        tool_enabled = _has_medication_candidates(context.get("combined_text", ""))
        condition_enabled = _has_condition_candidates(context.get("combined_text", ""))
        research_tools: list[dict] = []
        if tool_enabled or condition_enabled:
            research_tools = RESEARCH_TOOLS
        tools = COORDINATOR_TOOL + research_tools
        if tools:
            response = await generate_with_fallback(
                client=client,
                messages=prompt,
                tools=tools,
                tool_choice="auto",
            )
        else:
            response = await generate_with_fallback(
                client=client,
                messages=prompt,
            )
        if await _abort_now("after initial generation"):
            return
        message = response.choices[0].message
        tool_calls = message.tool_calls
        if tool_calls:
            prompt.append(message)
            for tool_call in tool_calls:
                if await _abort_now("during tool execution"):
                    return
                fn_name = tool_call.function.name
                try:
                    fn_args = json.loads(tool_call.function.arguments)
                except json.JSONDecodeError:
                    logger.warning("Failed to parse tool arguments.")
                    fn_args = {}

                if fn_name == "check_drug_interactions":
                    medications = fn_args.get("medications", [])
                    findings = await research_agent.check_drug_interactions(medications)
                    if findings:
                        context["research_findings"] = findings
                        prompt[1]["content"] = summary_prompt_for(visit, context)
                    tool_result = json.dumps({"findings": findings})
                elif fn_name == "search_medical_guidelines":
                    condition = fn_args.get("condition", "")
                    guidelines = await research_agent.search_medical_guidelines(condition)
                    if guidelines:
                        context["guideline_findings"] = guidelines
                        prompt[1]["content"] = summary_prompt_for(visit, context)
                    tool_result = json.dumps({"guidelines": guidelines})
                elif fn_name == "extract_actions":
                    summary_html = fn_args.get("summary_html", "")
                    if not summary_html:
                        tool_result = json.dumps({"actions": []})
                    else:
                        actions_from_tool = await coordinator_agent.extract_actions(summary_html, client)
                        tool_result = json.dumps({"actions": actions_from_tool})
                else:
                    tool_result = json.dumps({"error": f"Unknown tool {fn_name}"})

                prompt.append(
                    {"role": "tool", "tool_call_id": tool_call.id, "content": tool_result}
                )

            if await _abort_now("before post-tool generation"):
                return
            response = await generate_with_fallback(
                client=client,
                messages=prompt,
                tools=tools,
                tool_choice="none",
            )
            raw_text = response.choices[0].message.content or ""
        else:
            raw_text = message.content or ""
    except Exception as e:
        logger.error(f"Failed to generate summary: {e}")
        raw_text = "<p>Error generating summary. Please check logs.</p>"

    template = get_template(visit)
    final_html = ensure_html_summary(raw_text, template)

    if critic_agent.critic_enabled():
        if await _abort_now("before critic review"):
            return
        logger.info("Critic review starting.")
        critic_client = critic_agent.build_critic_client(client)
        review = await critic_agent.review_summary(
            summary_html=final_html,
            source_text=context.get("combined_text", ""),
            patient_history=context.get("patient_history", ""),
            research_findings=_format_findings_block("Research", context.get("research_findings")),
            guideline_findings=_format_findings_block("Guidelines", context.get("guideline_findings")),
            client=critic_client,
        )
        await guardrails_util.record_critic_issues(review.get("issues", []), client)
        
        if critic_agent.review_requires_regen(review):
            logger.info("Critic review failed. Triggering Parallel Regeneration Tournament (N=5).")
            
            # 1. Prepare Prompt
            correction_prompt = correction_prompt_for(visit, context, final_html, review)
            
            # 2. Generate 5 Candidates in Parallel
            N_CANDIDATES = 5
            gen_tasks = []
            for _ in range(N_CANDIDATES):
                gen_tasks.append(
                    generate_with_fallback(
                        client=critic_client,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": correction_prompt},
                        ],
                        models=critic_agent.critic_models(),
                        temperature=0.7 # Slight variance for diversity
                    )
                )
            
            gen_results = await asyncio.gather(*gen_tasks, return_exceptions=True)
            
            candidates = []
            for res in gen_results:
                if isinstance(res, Exception):
                    logger.warning(f"Tournament generation failed: {res}")
                    continue
                raw = res.choices[0].message.content or ""
                if raw.strip():
                    candidates.append(ensure_html_summary(raw, template))
            
            if not candidates:
                logger.error("All tournament generations failed. Keeping original draft.")
            else:
                # 3. Critique Candidates in Parallel
                logger.info(f"Tournament Phase 2: Critiquing {len(candidates)} candidates...")
                critique_tasks = []
                for cand in candidates:
                    critique_tasks.append(
                        critic_agent.review_summary(
                            summary_html=cand,
                            source_text=context.get("combined_text", ""),
                            patient_history=context.get("patient_history", ""),
                            research_findings=_format_findings_block("Research", context.get("research_findings")),
                            guideline_findings=_format_findings_block("Guidelines", context.get("guideline_findings")),
                            client=critic_client,
                        )
                    )
                
                critique_results = await asyncio.gather(*critique_tasks, return_exceptions=True)
                
                # 4. Pick Winner
                best_cand = None
                best_review = None
                best_score = -1.0
                
                for i, (cand, rev) in enumerate(zip(candidates, critique_results)):
                    if isinstance(rev, Exception):
                        logger.warning(f"Tournament critique {i} failed: {rev}")
                        continue
                    
                    score = rev.get("score", 0.0)
                    passed = not critic_agent.review_requires_regen(rev)
                    
                    logger.info(f"Candidate {i}: score={score}, passed={passed}")
                    
                    # Immediate winner if passes
                    if passed:
                        best_cand = cand
                        best_review = rev
                        logger.info(f"Candidate {i} is the winner (Passed).")
                        break
                    
                    # Track best failing candidate
                    if score > best_score:
                        best_score = score
                        best_cand = cand
                        best_review = rev
                
                # 5. Apply Result
                if best_cand:
                    final_html = best_cand
                    if best_review:
                        review = best_review # Update review state for final log/audit
                        await guardrails_util.record_critic_issues(review.get("issues", []), client)
                    logger.info(f"Tournament finished. Selected candidate with score={best_score if best_score > -1 else 'Pass'}")
                else:
                    logger.warning("Tournament produced no valid candidates. Keeping original.")

        logger.info("Critic review finished.")

    doctor_info = await _fill_doctor_info_from_summary(doctor_info, final_html, client)
    evidence_map = await evidence_agent.build_evidence_map(final_html, context, client)
    
    if await _abort_now("before memory save"):
        return
    # Memory Agent: Remember this visit
    # Store both plain-text summary and original notes for recall.
    try:
        summary_text = html_to_text(final_html)
        await memory_agent.remember_visit(
            summary_text,
            visit.patient_name, 
            visit.date_of_visit, 
            client,
            doc_type="visit_summary",
        )
        original_notes = _normalize_notes_text(context.get("combined_text", ""))
        if original_notes:
            await memory_agent.remember_visit(
                original_notes,
                visit.patient_name,
                visit.date_of_visit,
                client,
                doc_type="visit_notes",
            )
        evidence_text = _format_evidence_text(evidence_map)
        if evidence_text:
            await memory_agent.remember_visit(
                evidence_text,
                visit.patient_name,
                visit.date_of_visit,
                client,
                doc_type="visit_evidence",
            )
    except Exception as e:
        logger.warning(f"Failed to save memory: {e}")

    if await _abort_now("before action extraction"):
        return
    # Coordinator Agent: Extract actions
    actions = actions_from_tool
    if actions is None:
        actions = await coordinator_agent.extract_actions(final_html, client)
    
    # Metadata event
    metadata = json.dumps(
        {
            **doctor_info,
            "evidence_map": evidence_map,
            "prescription_text": context.get("prescription_text", ""),
            "prescription_filename": context.get("prescription_filename", ""),
            "prescription_texts": context.get("prescription_texts", []),
            "prescription_filenames": context.get("prescription_filenames", []),
        }
    )
    yield f"event: metadata\ndata: {metadata}\n\n"

    # Actions event
    if actions:
        yield f"event: actions\ndata: {json.dumps(actions)}\n\n"
    
    # Stream the HTML
    lines = final_html.split("\n")
    for line in lines[:-1]:
        if await _abort_now("during stream"):
            return
        yield f"data: {line}\n\n"
        yield "data:  \n"
    if lines:
        if await _abort_now("during stream"):
            return
        yield f"data: {lines[-1]}\n\n"


async def run_summary_pipeline(
    visit: Visit,
    client: AsyncOpenAI,
    request: Optional[Any] = None,
) -> AsyncGenerator[str, None]:
    """
    Orchestrates the full summary generation pipeline:
    1. Extract text/data from visit files.
    2. Extract doctor info.
    3. Recall patient history (RAG).
    4. Generate and stream summary.
    """
    logger.info(f"Starting summary pipeline for patient: {visit.patient_name}")

    async def is_disconnected() -> bool:
        if request is None:
            return False
        try:
            return await request.is_disconnected()
        except Exception:
            return False

    if await is_disconnected():
        logger.info("Client disconnected before summary start.")
        return

    cache_key = _summary_cache_key(visit)
    cached = _cache_get(cache_key)
    if cached:
        logger.info("Summary cache hit.")
        for chunk in cached["events"]:
            yield chunk
        return
    logger.info("Summary cache miss.")

    # 1. Extraction Phase
    context = await extraction_agent.build_visit_context(visit, client)
    if await is_disconnected():
        logger.info("Client disconnected after extraction.")
        return

    # 2. Memory Recall Phase (parallel with doctor info extraction)
    doctor_task = extraction_agent.extract_doctor_info(context["combined_text"], client)
    history_task = None
    if visit.patient_name and context.get("combined_text"):
        history_task = memory_agent.recall_patient_history(
            patient_name=visit.patient_name,
            query=context["combined_text"],
            client=client
        )

    if history_task:
        doctor_info, history = await asyncio.gather(doctor_task, history_task)
    else:
        doctor_info = await doctor_task
        history = "No past history found."

    context["patient_history"] = history
    context["doctor_info"] = doctor_info

    # 3. Generation Phase
    events: list[str] = []
    async for chunk in generate_summary_stream(
        visit,
        context,
        doctor_info,
        client,
        should_abort=is_disconnected,
    ):
        if await is_disconnected():
            logger.info("Client disconnected during summary stream.")
            return
        events.append(chunk)
        yield chunk

    if await is_disconnected():
        logger.info("Client disconnected before cache write.")
        return

    _cache_set(cache_key, {"events": events})
