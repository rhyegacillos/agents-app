# email_agent.py

import os
from openai import AsyncOpenAI
from typing import Dict, Any, Optional
import json
import logging
import resend

logger = logging.getLogger("email_agent")

client = AsyncOpenAI()
resend.api_key = os.getenv("RESEND_API_KEY")

# ---------- TOOLS ----------

SEND_EMAIL_TOOL = {
    "type": "function",
    "function": {
        "name": "send_email",
        "description": "Prepare an email payload to be sent via Resend",
        "parameters": {
            "type": "object",
            "properties": {
                "to": {"type": "string"},
                "subject": {"type": "string"},
                "html_body": {"type": "string"},
            },
            "required": ["to", "subject", "html_body"],
        },
    },
}

LOG_ACTION_TOOL = {
    "type": "function",
    "function": {
        "name": "log_action",
        "description": "Log an audit record describing why an action was taken",
        "parameters": {
            "type": "object",
            "properties": {
                "summary": {"type": "string"},
                "risk_notes": {"type": "string"},
            },
            "required": ["summary"],
        },
    },
}

# ---------- PROMPTS ----------

AGENT_SYSTEM_PROMPT = """
You are an autonomous email-sending agent for IdeaGen.

GOAL:
Deliver a professional transactional email with a report attached.

RULES (NON-NEGOTIABLE):
- You MUST call send_email exactly once.
- You MUST call log_action exactly once.
- Salutation MUST be: "Hi There,"
- Signature MUST be: "Ideagen" and must be bold format
- You MUST include this disclaimer verbatim:
  "This is an auto-generated email. Please do not reply."
- Output HTML only inside the send_email tool.
- Do NOT mention AI, agents, or models.
- Keep email under 120 words.

AGENTIC BEHAVIOR:
- Decide wording.
- Take action.
- Explain why via log_action.
"""

def agent_user_prompt(
    industry: str,
    constraints_text: str,
    to_email: str,
    report_type: str,
    subject_hint: Optional[str],
    email_brief: Optional[Dict[str, Any]],
) -> str:
    subject_line = subject_hint or f"IdeaGen {report_type}"
    brief_summary = ""
    brief_highlights = ""
    if isinstance(email_brief, dict):
        if email_brief.get("summary"):
            brief_summary = f"\n        - Brief summary: {email_brief.get('summary')}"
        highlights = email_brief.get("highlights")
        if isinstance(highlights, list) and highlights:
            joined = "; ".join(str(h) for h in highlights)
            brief_highlights = f"\n        - Brief highlights: {joined}"
    return f"""
        Context:
        - Recipient: {to_email}
        - Product: IdeaGen
        - Report type: {report_type}
        - Industry: {industry}
        - Constraints: {constraints_text}
        - Subject line: {subject_line}
        {brief_summary}{brief_highlights}

        Task:
        Draft and send the email with the attached report. The subject line must be exactly as provided.
        """.strip()



# ---------- AGENT RUNNER (ASYNC + RETRY) ----------

async def run_email_agent(
    *,
    to_email: str,
    industry: str,
    constraints_text: str,
    report_type: str = "Report",
    subject_hint: Optional[str] = None,
    email_brief: Optional[Dict[str, Any]] = None,
    max_retries: int = 2,
) -> Dict[str, Any]:
    last_error = None
    if not subject_hint and isinstance(email_brief, dict) and email_brief.get("subject"):
        subject_hint = str(email_brief.get("subject"))

    for attempt in range(max_retries + 1):
        try:
            response = await client.chat.completions.create(
                model="gpt-5-nano",
                messages=[
                    {"role": "system", "content": AGENT_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": agent_user_prompt(
                            industry=industry,
                            constraints_text=constraints_text,
                            to_email=to_email,
                            report_type=report_type,
                            subject_hint=subject_hint,
                            email_brief=email_brief,
                        ),
                    },
                ],
                tools=[SEND_EMAIL_TOOL, LOG_ACTION_TOOL],
                tool_choice="required",
            )

            msg = response.choices[0].message
            tool_calls = msg.tool_calls or []

            send_email_payload = None
            audit_payload = None

            for call in tool_calls:
                args = json.loads(call.function.arguments)
                if call.function.name == "send_email":
                    send_email_payload = args
                elif call.function.name == "log_action":
                    audit_payload = args

            if not send_email_payload:
                raise RuntimeError("send_email tool not called")

            # log audit trail (structured)
            summary = audit_payload.get("summary") if audit_payload else None
            risk_notes = audit_payload.get("risk_notes") if audit_payload else None
            logger.info(
                "email_agent.audit industry=%s to=%s summary=%s risk_notes=%s",
                industry,
                to_email,
                summary,
                risk_notes,
            )

            if subject_hint and send_email_payload.get("subject") != subject_hint:
                send_email_payload["subject"] = subject_hint

            return send_email_payload

        except Exception as e:
            last_error = e
            logger.warning(f"Email agent attempt {attempt + 1} failed: {e}")

    # ---------- FALLBACK ----------
    logger.error("Email agent failed, using fallback email")

    return {
        "to": to_email,
        "subject": subject_hint or f"IdeaGen {report_type}: {industry}",
        "html_body": (
            "<p>Please find your IdeaGen report attached.</p>"
            "<p>This report was generated automatically.</p>"
        ),
    }


async def send_report_email(
    *,
    to_email: str,
    industry: str,
    constraints_text: str,
    report_type: str,
    subject_hint: Optional[str],
    email_brief: Optional[Dict[str, Any]] = None,
    attachment_filename: str,
    attachment_bytes: bytes,
) -> Dict[str, Any]:
    agent_result = await run_email_agent(
        to_email=to_email,
        industry=industry,
        constraints_text=constraints_text,
        report_type=report_type,
        subject_hint=subject_hint,
        email_brief=email_brief,
    )

    final_html = f"""
    <div style="font-family: Arial, sans-serif; font-size:14px; color:#111;">
      {agent_result["html_body"]}
    </div>
    """

    from_address = os.getenv("EMAIL_FROM", "IdeaGen Reports <no-reply@agentairg.site>")
    resend.Emails.send({
        "from": from_address,
        "to": agent_result["to"],
        "subject": agent_result["subject"],
        "html": final_html,
        "attachments": [{
            "filename": attachment_filename,
            "content": list(attachment_bytes),
        }],
    })

    return {
        "status": "sent",
        "subject": agent_result["subject"],
    }
