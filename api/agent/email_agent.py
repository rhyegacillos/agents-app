import os
import json
import resend
from typing import Optional, Dict, Any, List
from fastapi import HTTPException
from openai import AsyncOpenAI

from .models import SendEmailRequest
from .utils import generate_with_fallback, get_logger

logger = get_logger(__name__)

# --- Tool Implementations ---

async def _translate_html_impl(html: str, target_language: str, client: AsyncOpenAI) -> str:
    """Internal implementation of the translation logic."""
    if not html.strip():
        return html
    
    system = (
        "You translate HTML email content. "
        "Translate only the human-readable text, not the HTML tags or attributes. "
        "Preserve formatting, links, emails, numbers, medication names, and proper nouns. "
        "Return HTML only, no extra commentary."
    )
    user = f"Target language: {target_language}\n\nHTML:\n{html}"

    try:
        # We use a simple generation call here, effectively a sub-agent
        response = await generate_with_fallback(
            client=client,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            models=[os.getenv("OPENAI_TRANSLATE_MODEL", "gpt-4o-mini"), "gpt-3.5-turbo"],
            temperature=0,
        )
        translated = (response.choices[0].message.content or "").strip()
        return translated
    except Exception as exc:
        logger.error(f"Translation tool failed: {exc}")
        raise exc


async def _send_email_impl(
    to: str,
    subject: str,
    html: str,
    reply_to: str,
    clinic_name: str
) -> Dict[str, Any]:
    api_key = os.getenv("RESEND_API_KEY")
    if not api_key:
        raise Exception("Missing RESEND_API_KEY")

    sender = os.getenv("RESEND_FROM", "no-reply@agentairg.site")
    sender_email = sender
    if "<" in sender and ">" in sender:
        sender_email = sender.split("<", 1)[1].split(">", 1)[0].strip()

    clean_clinic_name = clinic_name.strip().replace("\n", " ").replace("\r", " ").replace("<", "").replace(">", "")
    from_header = f"{clean_clinic_name} <{sender_email}>"
    resend.api_key = api_key

    try:
        response = resend.Emails.send({
            "from": from_header,
            "to": to,
            "subject": subject,
            "html": html,
            "reply_to": reply_to,
        })
        email_id = response.get("id") if isinstance(response, dict) else None
        return {"status": "sent", "id": email_id}
    except Exception as exc:
        logger.error(f"Resend failed: {exc}")
        raise exc


# --- Tool Definitions (Schema) ---

TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "translate_email",
            "description": "Translate the HTML content of an email into a target language.",
            "parameters": {
                "type": "object",
                "properties": {
                    "html_content": {
                        "type": "string",
                        "description": "The full HTML content of the email."
                    },
                    "target_language": {
                        "type": "string",
                        "description": "The language to translate into (e.g., 'Spanish', 'French')."
                    }
                },
                "required": ["html_content", "target_language"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "send_email_final",
            "description": "Send the final (possibly translated) email to the recipient.",
            "parameters": {
                "type": "object",
                "properties": {
                    "to_email": {"type": "string"},
                    "subject": {"type": "string"},
                    "html_body": {"type": "string"},
                    "reply_to": {"type": "string"},
                    "clinic_name": {"type": "string"}
                },
                "required": ["to_email", "subject", "html_body", "reply_to", "clinic_name"]
            }
        }
    }
]


# --- Agent Router ---

async def run_email_agent(
    payload: SendEmailRequest,
    client: AsyncOpenAI,
) -> Dict[str, Any]:
    """
    Fully agentic router:
    1. Analyzes the request.
    2. Decides if translation is needed.
    3. Calls translation tool if so.
    4. Calls send tool.
    """
    
    # 1. System Prompt
    system_prompt = (
        "You are an intelligent email dispatch agent. Your goal is to ensure an email is sent in the correct language."
        "You must follow these steps:"
        "1. Examine the user's request to determine the target language."
        "2. If the language is anything other than 'English', you MUST first call the `translate_email` tool to translate the `html` content."
        "3. After translation (or if no translation was needed), you MUST call the `send_email_final` tool with the final HTML content."
        "   - If you translated the content, use the translated HTML from the `translate_email` tool's output for the `html_body`."
        "   - If you did not translate, use the original `html` from the user's request."
        "4. Return only the result of the `send_email_final` operation."
    )

    # 2. User Context
    user_content = json.dumps(payload.model_dump())

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Execute this request: {user_content}"}
    ]

    # 3. Agent Loop (Max steps to prevent infinite loops)
    MAX_STEPS = 3
    
    for step in range(MAX_STEPS):
        try:
            # Call LLM with Tools
            response = await generate_with_fallback(
                client=client,
                messages=messages,
                tools=TOOLS_SCHEMA,
                tool_choice="auto",
                temperature=0, # Deterministic routing
                models=["gpt-4o", "gpt-3.5-turbo"] # Use smarter models for routing
            )
            
            message = response.choices[0].message
            tool_calls = message.tool_calls

            if not tool_calls:
                logger.warning("Agent did not call any tools. It might be finished or confused.")
                return {"status": "agent_stopped_without_sending", "reason": message.content}

            messages.append(message)

            for tool_call in tool_calls:
                fn_name = tool_call.function.name
                fn_args = json.loads(tool_call.function.arguments)
                
                logger.info(f"Agent calling tool: {fn_name}")

                result_content = ""
                
                if fn_name == "translate_email":
                    translated_html = await _translate_html_impl(
                        fn_args["html_content"],
                        fn_args["target_language"],
                        client
                    )
                    # The result is the raw HTML string
                    result_content = translated_html
                
                elif fn_name == "send_email_final":
                    send_result = await _send_email_impl(
                        to=fn_args["to_email"],
                        subject=fn_args["subject"],
                        html=fn_args["html_body"],
                        reply_to=fn_args["reply_to"],
                        clinic_name=fn_args["clinic_name"]
                    )
                    return send_result
                
                else:
                    result_content = json.dumps({"error": f"Unknown tool {fn_name}"})

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result_content
                })

        except Exception as e:
            logger.error(f"Agent loop error at step {step}: {e}")
            raise HTTPException(status_code=500, detail=f"Agent failed: {str(e)}")

    raise HTTPException(status_code=500, detail="Agent exceeded maximum steps without sending email.")
