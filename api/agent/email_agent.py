# email_agent.py

from openai import AsyncOpenAI
from typing import Dict, Any
import json
import logging

logger = logging.getLogger("email_agent")

client = AsyncOpenAI()

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
Deliver a professional transactional email with a business idea report attached.

RULES (NON-NEGOTIABLE):
- You MUST call send_email exactly once.
- You MUST call log_action exactly once.
- Salutation MUST be: "Hi There,"
- Signature MUST be: "Ideagen"
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

def agent_user_prompt(industry: str, constraints_text: str, to_email: str) -> str:
    return f"""
        Context:
        - Recipient: {to_email}
        - Product: IdeaGen
        - Industry: {industry}
        - Constraints: {constraints_text}

        Task:
        Draft and send the email with the attached report.
        """.strip()



# ---------- AGENT RUNNER (ASYNC + RETRY) ----------

async def run_email_agent(
    *,
    to_email: str,
    industry: str,
    constraints_text: str,
    max_retries: int = 2,
) -> Dict[str, Any]:
    last_error = None

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
            logger.info(
                "email_agent.audit",
                extra={
                    "industry": industry,
                    "to": to_email,
                    "summary": audit_payload.get("summary") if audit_payload else None,
                    "risk_notes": audit_payload.get("risk_notes") if audit_payload else None,
                },
            )

            return send_email_payload

        except Exception as e:
            last_error = e
            logger.warning(f"Email agent attempt {attempt + 1} failed: {e}")

    # ---------- FALLBACK ----------
    logger.error("Email agent failed, using fallback email")

    return {
        "to": to_email,
        "subject": f"IdeaGen Report: {industry}",
        "html_body": (
            "<p>Please find your IdeaGen report attached.</p>"
            "<p>This report was generated automatically.</p>"
        ),
    }
