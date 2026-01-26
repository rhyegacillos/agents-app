import json
import re
from typing import AsyncGenerator, Dict, Any

from openai import AsyncOpenAI
from .models import Visit
from .utils import generate_with_fallback, get_logger
from .utils.templates import get_template
from .utils.html_sections import ensure_html_summary, html_to_text
from . import extraction_agent, coordinator_agent, memory_agent, research_agent

logger = get_logger(__name__)

MEDICATION_HINT_RE = re.compile(
    r"\b(?:mg|mcg|g|ml|units|tablet|tab|capsule|cap|injection|iv|po|bid|tid|qid|qd|prn|rx|prescribed|medication|medications)\b",
    re.IGNORECASE,
)
DOSAGE_RE = re.compile(r"\b\d+(?:\.\d+)?\s?(?:mg|mcg|g|ml|units)\b", re.IGNORECASE)
CONDITION_HINT_RE = re.compile(
    r"\b(?:diagnosis|diagnosed|dx|impression|assessment|condition|disease|syndrome|infection|hypertension|diabetes|asthma|pneumonia|cancer|fracture)\b",
    re.IGNORECASE,
)

system_prompt = """
You are provided with notes written by a doctor from a patient's visit.
Your job is to summarize the visit for the doctor and provide an email.
You may receive extracted text from uploaded files, audio transcripts, or prescription images.
Use that material to improve accuracy, but do not invent details that are not explicitly present.
Reply with exactly three sections in HTML only using this structure:
<section data-section="summary"><h3>Summary of visit for the doctor's records</h3>...</section>
<section data-section="next_steps"><h3>Next steps for the doctor</h3><ul><li>...</li></ul></section>
<section data-section="patient_email"><h3>Draft Email for Patient</h3><p>...</p></section>
Do not include any signature or sign-off in the draft email.
Do not include any text outside the three sections.
"""

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

    research_block = ""
    if context.get("research_findings"):
        findings_value = context["research_findings"]
        if isinstance(findings_value, str):
            findings_list = [findings_value]
        else:
            findings_list = findings_value
        findings = "\n- ".join(findings_list)
        research_block = f"\n\nSafety Check / Research Findings:\n- {findings}"

    guidelines_block = ""
    if context.get("guideline_findings"):
        guidelines_value = context["guideline_findings"]
        if isinstance(guidelines_value, str):
            guidelines_list = [guidelines_value]
        else:
            guidelines_list = guidelines_value
        guidelines = "\n- ".join(guidelines_list)
        guidelines_block = f"\n\nGuideline Findings:\n- {guidelines}"

    template = get_template(visit)

    return f"""Create the summary, next steps and draft email for:
Patient Name: {visit.patient_name}
Date of Visit: {visit.date_of_visit}
Notes:
{context["notes_text"]}{attachment_block}{history_block}{research_block}{guidelines_block}

Template: {template["label"]}
{template["summary_html"]}
Follow the template exactly and do not add or remove headings.
If two or more medications are mentioned, call the check_drug_interactions tool with a list of medication names.
If a condition or diagnosis is mentioned, call search_medical_guidelines with the condition name.
After drafting the summary, call extract_actions with the full HTML summary.
If there are any safety findings, incorporate a 'Clinical Safety Note' into the 'Assessment' or 'Plan' section of your summary.
If there are guideline findings, incorporate a short 'Guideline Note' into the 'Assessment' or 'Plan' section.
For the Next steps section, use a <ul> list with clear, actionable items.
For the patient email section, use short <p> paragraphs in patient-friendly language."""


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


async def generate_summary_stream(
    visit: Visit,
    context: Dict[str, Any],
    doctor_info: Dict[str, Any],
    client: AsyncOpenAI,
) -> AsyncGenerator[str, None]:
    
    user_prompt = summary_prompt_for(visit, context)
    prompt = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    try:
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
        message = response.choices[0].message
        tool_calls = message.tool_calls
        actions_from_tool = None
        if tool_calls:
            prompt.append(message)
            for tool_call in tool_calls:
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
    
    # Memory Agent: Remember this visit
    # Store a plain-text summary so retrieval does not leak HTML into chat.
    try:
        summary_text = html_to_text(final_html)
        await memory_agent.remember_visit(
            summary_text,
            visit.patient_name, 
            visit.date_of_visit, 
            client
        )
    except Exception as e:
        logger.warning(f"Failed to save memory: {e}")

    # Coordinator Agent: Extract actions
    actions = actions_from_tool
    if actions is None:
        actions = await coordinator_agent.extract_actions(final_html, client)
    
    # Metadata event
    metadata = json.dumps(
        {
            **doctor_info,
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
        yield f"data: {line}\n\n"
        yield "data:  \n"
    if lines:
        yield f"data: {lines[-1]}\n\n"


async def run_summary_pipeline(
    visit: Visit,
    client: AsyncOpenAI,
) -> AsyncGenerator[str, None]:
    """
    Orchestrates the full summary generation pipeline:
    1. Extract text/data from visit files.
    2. Extract doctor info.
    3. Recall patient history (RAG).
    4. Generate and stream summary.
    """
    logger.info(f"Starting summary pipeline for patient: {visit.patient_name}")
    
    # 1. Extraction Phase
    context = await extraction_agent.build_visit_context(visit, client)
    doctor_info = await extraction_agent.extract_doctor_info(context["combined_text"], client)

    # 2. Memory Recall Phase
    # We use the current visit notes/transcripts as the query to find relevant past history
    history = await memory_agent.recall_patient_history(
        patient_name=visit.patient_name,
        query=context["combined_text"],
        client=client
    )
    context["patient_history"] = history

    # 3. Generation Phase
    async for chunk in generate_summary_stream(visit, context, doctor_info, client):
        yield chunk
