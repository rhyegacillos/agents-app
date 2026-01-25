import json
from typing import List, Dict, Any
from openai import AsyncOpenAI
from .utils import generate_with_fallback, get_logger

logger = get_logger(__name__)

async def extract_actions(summary_text: str, client: AsyncOpenAI) -> List[Dict[str, Any]]:
    """
    Analyzes the clinical summary (especially Next Steps) to extract structured, actionable items.
    Returns a list of actions like:
    [
        {"type": "schedule", "label": "Follow up visit", "details": "2 weeks"},
        {"type": "prescribe", "label": "Amoxicillin", "details": "500mg tid"},
        {"type": "referral", "label": "Cardiology", "details": "Dr. Smith"}
    ]
    """
    if not summary_text.strip():
        return []

    system_prompt = (
        "You are a clinical coordinator agent. "
        "Your job is to read a clinical summary and extract actionable 'Next Steps' into structured JSON. "
        "Focus on: Follow-ups, Prescriptions, Referrals, and Labs. "
        "Return a JSON object with a key 'actions' containing a list of objects. "
        "Each object must have: 'type' (schedule|prescribe|referral|lab|other), 'label' (short title), and 'details' (context). "
        "Do not invent actions not present in the text."
    )

    try:
        response = await generate_with_fallback(
            client=client,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Summary:\n{summary_text}"}
            ],
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content or "{}"
        data = json.loads(content)
        actions = data.get("actions", [])
        return actions
    except Exception as e:
        logger.error(f"Failed to extract actions: {e}")
        return []
