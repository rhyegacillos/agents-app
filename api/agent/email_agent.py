import os, json, re
from typing import Any, Dict, Optional
import resend
from fastapi import HTTPException
from openai import AsyncOpenAI

from .utils import generate_with_fallback, get_logger

logger = get_logger(__name__)

# Tool schemas aligned to SendEmailRequest field names
TOOLS = [
    {"type": "function", "function": {
        "name": "translate_email",
        "description": "Translate the HTML email content into a target language (preserve HTML tags/attrs).",
        "parameters": {"type": "object", "properties": {
            "html": {"type": "string"},
            "language": {"type": "string"},
        }, "required": ["html", "language"]}
    }},
    {"type": "function", "function": {
        "name": "send_email_final",
        "description": "Send the final email.",
        "parameters": {"type": "object", "properties": {
            "to": {"type": "string"},
            "subject": {"type": "string"},
            "html": {"type": "string"},
            "reply_to": {"type": "string"},
            "clinic_name": {"type": "string"},
        }, "required": ["to", "subject", "html", "reply_to", "clinic_name"]}
    }},
]

_TRANSLATE_SYS = (
    "Translate only visible text in the HTML. Do not change tags/attributes/links/emails/numbers. "
    "Preserve medication names and proper nouns. Return HTML only. "
    "Never output the two-character sequence \\n or \\r\\n. "
    "If a line break is needed, use proper HTML (<br>, <p>, <div>) or real newlines."
)



_sender = os.getenv("RESEND_FROM", "no-reply@agentairg.site")
_sender_email = re.search(r"<([^>]+)>", _sender).group(1) if "<" in _sender else _sender

def _normalize_html(s: str) -> str:
    if not s:
        return s
    # Convert literal backslash sequences to real newlines (common when JSON-encoded text leaks through).
    s = s.replace("\\r\\n", "\n").replace("\\n", "\n").replace("\\r", "\n")
    # Normalize CRLF/CR
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    return s

async def tool_translate_email(
    client: AsyncOpenAI,
    *,
    html: str,
    language: str,
) -> str:
    html = _normalize_html(html)
    if not html.strip():
        return html

    resp = await client.chat.completions.create(
        model=os.getenv("OPENAI_TRANSLATE_MODEL", "gpt-4o-mini"),
        temperature=0,
        messages=[
            {"role": "system", "content": _TRANSLATE_SYS},
            {"role": "user", "content": f"Target language: {language}\n\nHTML:\n{html}"},
        ],
    )
    return _normalize_html((resp.choices[0].message.content or "").strip())


async def tool_send_email_final(*, to: str, subject: str, html: str, reply_to: str, clinic_name: str) -> Dict[str, Any]:
    api_key = os.getenv("RESEND_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="Missing RESEND_API_KEY")

    resend.api_key = api_key
    clean_name = re.sub(r"[<>\r\n]+", " ", (clinic_name or "")).strip() or "Clinic"
    from_header = f"{clean_name} <{_sender_email}>"
    html = _normalize_html(html)

    try:
        resp = resend.Emails.send({
            "from": from_header,
            "to": to,
            "subject": subject,
            "html": html,
            "reply_to": reply_to,
        })
        return {"status": "sent", "id": resp.get("id") if isinstance(resp, dict) else None}
    except Exception as exc:
        logger.error(f"Resend failed: {exc}")
        raise HTTPException(status_code=502, detail="Email provider failed")


TOOL_DISPATCH = {
    "translate_email": tool_translate_email,   # returns str
    "send_email_final": tool_send_email_final, # returns dict
}


async def run_email_agent(payload, client: AsyncOpenAI) -> Dict[str, Any]:
    system = """You are an email dispatch agent.
        You receive a JSON payload with fields: to, subject, html, reply_to, clinic_name, language.

        Rules:
        1) If payload.language is not 'English' (case-insensitive), you MUST call translate_email with:
        - html = payload.html
        - language = payload.language
        2) Then you MUST call send_email_final using the final HTML (translated if step 1 ran, otherwise original).
        3) If payload.language is 'English', skip translation.
        4) It is an error to call send_email_final before translate_email when payload.language != 'English'.

        You must finish by calling send_email_final. Do not output explanations.
        """

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(payload.model_dump())},
    ]

    for step in range(4):
        try:
            resp = await generate_with_fallback(
                client=client,
                messages=messages,
                tools=TOOLS,
                tool_choice="auto",
                temperature=0,
                models=["gpt-4o-mini", "gpt-4o-mini"],
            )

            msg = resp.choices[0].message
            tool_calls = getattr(msg, "tool_calls", None) or []
            if not tool_calls:
                return {"status": "agent_stopped", "reason": (msg.content or "").strip()}

            messages.append(msg)

            for call in tool_calls:
                name = call.function.name
                args = json.loads(call.function.arguments or "{}")

                impl = TOOL_DISPATCH.get(name)
                if not impl:
                    raise HTTPException(status_code=500, detail=f"Unknown tool: {name}")

                if name == "translate_email":
                    out = await impl(client=client, **args)   # str
                    tool_content = out
                else:
                    out = await impl(**args)           # dict
                    tool_content = json.dumps(out)

                messages.append({"role": "tool", "tool_call_id": call.id, "content": tool_content})

                if name == "send_email_final":
                    return out

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Agent error step={step}: {e}")
            raise HTTPException(status_code=500, detail="Agent failed")

    raise HTTPException(status_code=500, detail="Agent exceeded steps without sending")
