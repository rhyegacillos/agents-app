def _tool_header(title: str) -> str:
    return f"### {title}\n"


def build_tool_intro() -> str:
    return (
        "## Tool Use Contract\n\n"
        "Use tools for actions. Do not invent execution results.\n"
    )


def build_read_uploaded_file_instructions() -> str:
    return _tool_header("read_uploaded_file") + (
        "- Use when the user asks to inspect or summarize an uploaded file.\n"
        "- Pass the exact `file_id` provided in context.\n\n"
    )


def build_send_resend_email_instructions() -> str:
    return _tool_header("send_resend_email") + (
        "- Use only when the user asks to send/resend email.\n"
        "- Never claim email success unless the tool returns success.\n\n"
    )


def build_generate_pdf_instructions() -> str:
    return _tool_header("generate_pdf_from_text") + (
        "- Use only when the user explicitly asks for PDF/export/download.\n"
        "- Keep PDF content semantically aligned with the user request.\n\n"
    )


def build_download_pdf_instructions() -> str:
    return _tool_header("download_pdf") + (
        "- Use to fetch/resolve a provided PDF URL.\n"
        "- Use returned fields as canonical output for any response.\n\n"
    )


def build_web_search_instructions() -> str:
    return _tool_header("brave_web_search") + (
        "- Use for current events/news/latest/research lookups.\n"
        "- Treat tool-returned URLs as the only canonical sources.\n\n"
    )


def build_intent_rules() -> str:
    return (
        "Intent rules:\n"
        "- Conversational requests: answer directly without tools.\n"
        "- Action requests (PDF/email/file/search): call the required tool.\n"
        "- If required action inputs are missing, ask a focused follow-up question.\n\n"
    )


def build_truth_rules() -> str:
    return (
        "Truth rules:\n"
        "- Never output placeholder/template links.\n"
        "- Never fabricate URLs, IDs, page counts, or delivery status.\n"
        "- Only claim completed actions when backed by tool output.\n"
        "- For PDF links, use tool-returned `download_url` or `public_url`; fallback to `/downloads/<filename>` only when filename is present in tool output.\n\n"
    )


def build_source_rules() -> str:
    return (
        "Source rules (search/news/research only):\n"
        "- Never invent URLs.\n"
        "- Citations must be references to tool-returned sources only.\n"
        "- Include a final 'Sources' section for search/news/research answers.\n"
        "- If you cannot cite a claim with available sources, say verification is incomplete or omit the claim.\n\n"
    )


def build_retry_rules() -> str:
    return (
        "Retry policy:\n"
        "- If `generate_pdf_from_text` returns `PDF_INPUT_INVALID`, retry once.\n"
        "- Retry may repair formatting/schema only; do not change facts.\n"
        "- If retry fails, return the structured tool error and stop.\n\n"
    )


def build_tool_call_formatting_rules() -> str:
    return (
        "Tool-call formatting:\n"
        "- If calling tools in a turn, output only tool calls.\n"
        "- Produce user-facing text after tool results are available.\n\n"
    )


def build_common_rules() -> str:
    return "".join(
        [
            build_intent_rules(),
            build_truth_rules(),
            build_source_rules(),
            build_retry_rules(),
            build_tool_call_formatting_rules(),
        ]
    )


def build_tool_instructions() -> str:
    return "".join(
        [
            build_tool_intro(),
            build_read_uploaded_file_instructions(),
            build_send_resend_email_instructions(),
            build_generate_pdf_instructions(),
            build_download_pdf_instructions(),
            build_web_search_instructions(),
            build_common_rules(),
        ]
    )


def build_tool_instructions_by_tool() -> dict[str, str]:
    base = build_tool_intro()
    common_rules = build_common_rules()
    tool_sections = {
        "read_uploaded_file": build_read_uploaded_file_instructions(),
        "send_resend_email": build_send_resend_email_instructions(),
        "generate_pdf_from_text": build_generate_pdf_instructions(),
        "download_pdf": build_download_pdf_instructions(),
        "brave_web_search": build_web_search_instructions(),
    }
    by_tool: dict[str, str] = {}
    for tool_name, section in tool_sections.items():
        by_tool[tool_name] = base + section + common_rules
    by_tool["extract_memory_candidates"] = base + common_rules
    by_tool["check_memory_conflict"] = base + common_rules
    return by_tool


def tool_instructions_for(tool_name: str) -> str:
    return build_tool_instructions_by_tool().get(tool_name, build_tool_instructions())
