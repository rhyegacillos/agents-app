import inspect
import json
import logging
import os
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

from observability import TRACE_ID, log_event
from otel_observability import (
    get_tracer as get_otel_tracer,
    set_current_span_attributes,
)
from services.canonical_renderer import render_high_risk_output
from services.output_truth_gate import (
    apply_truth_gate,
    extract_tool_failures,
    find_pdf_input_invalid_error,
    normalize_truth_context,
    persist_truth_context,
    persist_truth_gate_verdict,
)
from services.storage import load_approved_memory
from services.truth_fix_loop import build_auto_fix_instructions, should_attempt_auto_fix
from services.chat_runtime.result_types import HighRiskChatResult


PDF_RETRY_FIX_INSTRUCTIONS = (
    "Your previous `generate_pdf_from_text` call failed with `PDF_INPUT_INVALID`. "
    "Retry exactly once. Use valid markdown or valid JSON blocks. "
    "Do not infer, summarize, omit, or add new facts. Keep content semantically identical "
    "to what the user requested (same claims, numbers, citations, and ordering). "
    "Only repair formatting/escaping/schema issues."
)

RerunFixFn = Callable[[str], Awaitable[HighRiskChatResult]]
MemoryValidatorFn = Callable[[List[Dict[str, Any]], str, str], Any]


async def _run_memory_validator(
    memory_validator: MemoryValidatorFn,
    approved: List[Dict[str, Any]],
    user_message: str,
    assistant_response: str,
) -> Dict[str, Any]:
    verdict = memory_validator(approved, user_message, assistant_response)
    if inspect.isawaitable(verdict):
        verdict = await verdict
    return verdict if isinstance(verdict, dict) else {}


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


def _log_tool_failures(tool_events: List[Dict[str, Any]], *, attempt: int) -> None:
    for failure in extract_tool_failures(tool_events):
        log_event(
            "execute.tool_failure",
            level=logging.WARNING,
            attempt=attempt,
            tool_name=failure.get("tool_name", "unknown"),
            status=failure.get("status", "error"),
            message=failure.get("message", ""),
        )


def _executed_tool_names(tool_events: List[Dict[str, Any]]) -> List[str]:
    return [
        str(evt.get("tool_name") or "").strip()
        for evt in tool_events
        if isinstance(evt, dict) and str(evt.get("tool_name") or "").strip()
    ]


def _missing_required_tools(tool_events: List[Dict[str, Any]], required_tool_names: List[str]) -> List[str]:
    executed = set(_executed_tool_names(tool_events))
    return [name for name in required_tool_names if name not in executed]


def _required_tools_in_order(tool_events: List[Dict[str, Any]], required_tool_names: List[str]) -> bool:
    if not required_tool_names:
        return True
    required_index = 0
    for tool_name in _executed_tool_names(tool_events):
        if tool_name == required_tool_names[required_index]:
            required_index += 1
            if required_index >= len(required_tool_names):
                return True
    return required_index >= len(required_tool_names)


async def finalize_high_risk_response(
    *,
    user_id: str,
    user_message: str,
    session_id: Optional[str],
    require_sources: bool,
    initial_result: HighRiskChatResult,
    rerun_with_fix: RerunFixFn,
    memory_validator: MemoryValidatorFn,
    required_tool_names: Optional[List[str]] = None,
) -> Tuple[str, int]:
    tracer = get_otel_tracer("digital_assistant.high_risk")
    result = initial_result
    output = str(result.output or "")
    total_llm_tokens = max(0, int(result.llm_tokens or 0))

    approved = load_approved_memory(user_id)
    if approved:
        with tracer.start_as_current_span("high_risk.memory_validate"):
            set_current_span_attributes({"memory.approved_count": len(approved)})
            log_event("memory_validator.running", approved=len(approved))
            verdict = await _run_memory_validator(memory_validator, approved, user_message, output)
            set_current_span_attributes(
                {
                    "memory.compliant": bool(verdict.get("compliant")),
                    "memory.reason": str(verdict.get("reason", "") or ""),
                }
            )
            if not verdict.get("compliant"):
                log_event("memory_validator.noncompliant", reason=verdict.get("reason", ""))
                result = await rerun_with_fix(verdict.get("fix_instructions", ""))
                total_llm_tokens += max(0, int(result.llm_tokens or 0))
                output = str(result.output or "")
    else:
        log_event("memory_validator.skipped", reason="no_approved_memory")

    tool_events = list(result.tool_events or [])
    pdf_input_error = find_pdf_input_invalid_error(tool_events)
    if pdf_input_error:
        with tracer.start_as_current_span("high_risk.pdf_retry"):
            set_current_span_attributes({"pdf.retry": True, "pdf.error": pdf_input_error})
            log_event("pdf_retry.retrying", reason=pdf_input_error)
            result = await rerun_with_fix(PDF_RETRY_FIX_INSTRUCTIONS)
            total_llm_tokens += max(0, int(result.llm_tokens or 0))
            output = str(result.output or "")
            tool_events = list(result.tool_events or [])
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
    required_tool_names = [name for name in (required_tool_names or []) if isinstance(name, str) and name]
    truth_fix_attempt = 0
    try:
        max_truth_fix_attempts = int(os.getenv("TRUTH_FIX_MAX_ATTEMPTS", "2"))
    except ValueError:
        max_truth_fix_attempts = 2
    max_truth_fix_attempts = max(0, min(5, max_truth_fix_attempts))

    while True:
        missing_required_tools = _missing_required_tools(current_tool_events, required_tool_names)
        if missing_required_tools:
            log_event(
                "execute.required_tools_missing",
                level=logging.WARNING,
                trace_id=trace_id,
                required_tools=",".join(required_tool_names),
                missing_tools=",".join(missing_required_tools),
                tool_events=len(current_tool_events),
            )
            return (
                "I couldn't complete that action because one or more required execution tools did not run. "
                "Please retry the action."
            ), total_llm_tokens
        if required_tool_names and not _required_tools_in_order(current_tool_events, required_tool_names):
            log_event(
                "execute.required_tools_out_of_order",
                level=logging.WARNING,
                trace_id=trace_id,
                required_tools=",".join(required_tool_names),
                tool_events=len(current_tool_events),
            )
            return (
                "I couldn't complete that action because the required tool execution order was not satisfied. "
                "Please retry the action."
            ), total_llm_tokens
        _log_tool_failures(current_tool_events, attempt=truth_fix_attempt)
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
        with tracer.start_as_current_span("high_risk.render"):
            set_current_span_attributes(
                {
                    "tool.event_count": len(current_tool_events),
                    "truth.artifact_count": len(current_truth_context.get("artifacts", []) or []),
                    "truth.outcome_count": len(current_truth_context.get("outcomes", []) or []),
                    "truth.search_result_count": len(current_truth_context.get("search_results", []) or []),
                }
            )
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
        with tracer.start_as_current_span("high_risk.validate"):
            verdict = apply_truth_gate(
                rendered_output,
                current_truth_context,
                risk_tier="high",
                require_sources=require_sources,
            )
            set_current_span_attributes({"truth_gate.status": str(verdict.get("status", "unknown"))})
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
        with tracer.start_as_current_span("high_risk.fix_loop"):
            set_current_span_attributes(
                {
                    "fix.attempt": truth_fix_attempt,
                    "fix.max_attempts": max_truth_fix_attempts,
                    "fix.issues": issue_codes_csv,
                }
            )
            result = await rerun_with_fix(fix_instructions)
            total_llm_tokens += max(0, int(result.llm_tokens or 0))
            current_output = str(result.output or "")
            current_tool_events = list(result.tool_events or [])
            retry_truth_context = normalize_truth_context(current_tool_events)
            current_truth_context = _merge_truth_context(current_truth_context, retry_truth_context)
