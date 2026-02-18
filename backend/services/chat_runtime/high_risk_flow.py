import json
import logging
import os
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

from observability import TRACE_ID, log_event
from services.canonical_renderer import render_high_risk_output
from services.output_truth_gate import (
    apply_truth_gate,
    extract_tool_events,
    find_pdf_input_invalid_error,
    normalize_truth_context,
    persist_truth_context,
    persist_truth_gate_verdict,
)
from services.storage import load_approved_memory
from services.truth_fix_loop import build_auto_fix_instructions, should_attempt_auto_fix
from services.chat_runtime.grok_runner import usage_total_tokens
from validator_agent import validate_memory_compliance_grok


PDF_RETRY_FIX_INSTRUCTIONS = (
    "Your previous `generate_pdf_from_text` call failed with `PDF_INPUT_INVALID`. "
    "Retry exactly once. Use valid markdown or valid JSON blocks. "
    "Do not infer, summarize, omit, or add new facts. Keep content semantically identical "
    "to what the user requested (same claims, numbers, citations, and ordering). "
    "Only repair formatting/escaping/schema issues."
)

RerunFixFn = Callable[[str], Awaitable[Any]]


def _merge_truth_context(previous: Dict[str, Any], latest: Dict[str, Any]) -> Dict[str, Any]:
    def _dedupe(rows: List[Dict[str, Any]], key_fn) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        seen = set()
        for row in rows:
            if not isinstance(row, dict):
                continue
            key = key_fn(row)
            if not key or key in seen:
                continue
            seen.add(key)
            out.append(row)
        return out

    merged_artifacts = _dedupe(
        (previous.get("artifacts", []) or []) + (latest.get("artifacts", []) or []),
        lambda r: str(r.get("artifact_id") or r.get("download_url") or ""),
    )
    merged_outcomes = _dedupe(
        (previous.get("outcomes", []) or []) + (latest.get("outcomes", []) or []),
        lambda r: str(r.get("tool") or "")
        + "|"
        + str(r.get("status") or "")
        + "|"
        + str(r.get("email_id") or "")
        + "|"
        + str(r.get("message") or ""),
    )
    merged_search = _dedupe(
        (previous.get("search_results", []) or []) + (latest.get("search_results", []) or []),
        lambda r: str(r.get("url") or ""),
    )
    return {
        "artifacts": merged_artifacts,
        "outcomes": merged_outcomes,
        "search_results": merged_search,
    }


async def finalize_high_risk_response(
    *,
    user_id: str,
    user_message: str,
    session_id: Optional[str],
    require_sources: bool,
    initial_result: Any,
    initial_output: str,
    total_llm_tokens: int,
    rerun_with_fix: RerunFixFn,
) -> Tuple[str, int]:
    result = initial_result
    output = initial_output

    approved = load_approved_memory(user_id)
    if approved:
        log_event("memory_validator.running", approved=len(approved))
        verdict = await validate_memory_compliance_grok(approved, user_message, output)
        if not verdict.get("compliant"):
            log_event("memory_validator.noncompliant", reason=verdict.get("reason", ""))
            result = await rerun_with_fix(verdict.get("fix_instructions", ""))
            total_llm_tokens += usage_total_tokens(result)
            output = str(result.final_output or "")
    else:
        log_event("memory_validator.skipped", reason="no_approved_memory")

    tool_events = extract_tool_events(result)
    pdf_input_error = find_pdf_input_invalid_error(tool_events)
    if pdf_input_error:
        log_event("pdf_retry.retrying", reason=pdf_input_error)
        result = await rerun_with_fix(PDF_RETRY_FIX_INSTRUCTIONS)
        total_llm_tokens += usage_total_tokens(result)
        output = str(result.final_output or "")
        tool_events = extract_tool_events(result)
        retry_pdf_input_error = find_pdf_input_invalid_error(tool_events)
        if retry_pdf_input_error:
            trace_id = TRACE_ID.get()
            log_event(
                "pdf_retry.exhausted",
                level=logging.WARNING,
                trace_id=trace_id,
                reason=retry_pdf_input_error,
            )
            return json.dumps(
                {
                    "status": "error",
                    "code": "PDF_INPUT_INVALID",
                    "trace_id": trace_id,
                    "retry_exhausted": True,
                    "reason": retry_pdf_input_error,
                }
            ), total_llm_tokens

    trace_id = TRACE_ID.get()
    current_output = str(output or "")
    current_tool_events = tool_events
    current_truth_context = normalize_truth_context(current_tool_events)
    truth_fix_attempt = 0
    try:
        max_truth_fix_attempts = int(os.getenv("TRUTH_FIX_MAX_ATTEMPTS", "2"))
    except ValueError:
        max_truth_fix_attempts = 2
    max_truth_fix_attempts = max(0, min(5, max_truth_fix_attempts))

    while True:
        log_event(
            "execute.tool_summary",
            tool_events=len(current_tool_events),
            artifacts=len(current_truth_context.get("artifacts", []) or []),
            outcomes=len(current_truth_context.get("outcomes", []) or []),
            search_results=len(current_truth_context.get("search_results", []) or []),
        )
        if require_sources:
            debug_samples = [
                {
                    "tool": str(evt.get("tool_name") or "unknown"),
                    "output_type": type(evt.get("output")).__name__,
                }
                for evt in current_tool_events[:5]
            ]
            log_event(
                "truth_gate.search_context",
                search_require=True,
                tool_events=len(current_tool_events),
                search_results=len(current_truth_context.get("search_results", []) or []),
                samples=debug_samples,
            )

        persist_truth_context(trace_id=trace_id, session_id=session_id, context=current_truth_context)
        rendered_output = render_high_risk_output(
            user_message=user_message,
            llm_output=current_output,
            context=current_truth_context,
            require_sources=require_sources,
        )
        log_event(
            "render.canonical",
            mode="v3_canonical",
            input_chars=len(current_output),
            output_chars=len(rendered_output),
        )
        verdict = apply_truth_gate(
            rendered_output,
            current_truth_context,
            risk_tier="high",
            require_sources=require_sources,
        )
        persist_truth_gate_verdict(trace_id, verdict)
        if verdict.get("status") == "pass":
            log_event("validate.pass", trace_id=trace_id, mode="v3_canonical")
            return str(verdict.get("output", rendered_output) or rendered_output), total_llm_tokens

        issue_code_list = sorted(
            {
                str(i.get("code", "UNKNOWN"))
                for i in (verdict.get("issues", []) or [])
                if str(i.get("code", "UNKNOWN")).strip()
            }
        )
        issue_codes_csv = ", ".join(issue_code_list) if issue_code_list else "UNKNOWN"
        log_event(
            "validate.blocked",
            level=logging.WARNING,
            trace_id=trace_id,
            issues=issue_codes_csv,
        )

        can_auto_fix = should_attempt_auto_fix(issue_code_list)
        if truth_fix_attempt >= max_truth_fix_attempts or not can_auto_fix:
            return (
                "I couldn't safely finalize that action output due to verification checks "
                f"({issue_codes_csv}). Please ask me to retry the action."
            ), total_llm_tokens

        truth_fix_attempt += 1
        fix_instructions = build_auto_fix_instructions(
            issue_codes=issue_code_list,
            issue_details=verdict.get("issues", []) or [],
            truth_context=current_truth_context,
            attempt=truth_fix_attempt,
            max_attempts=max_truth_fix_attempts,
        )
        log_event(
            "fix_loop.attempt",
            attempt=f"{truth_fix_attempt}/{max_truth_fix_attempts}",
            trace_id=trace_id,
            issues=issue_codes_csv,
        )
        result = await rerun_with_fix(fix_instructions)
        total_llm_tokens += usage_total_tokens(result)
        current_output = str(result.final_output or "")
        current_tool_events = extract_tool_events(result)
        retry_truth_context = normalize_truth_context(current_tool_events)
        current_truth_context = _merge_truth_context(current_truth_context, retry_truth_context)
