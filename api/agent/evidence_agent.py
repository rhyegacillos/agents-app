"""
Evidence Agent (V2)

This agent is responsible for creating a verifiable link between the final generated summary
and the source documents (notes, uploads, research findings). This process is also known as
"grounding" the summary in the source data.
"""

import json
import os
import re
from typing import Dict, Any, List

from openai import AsyncOpenAI

from .utils import generate_with_fallback, get_logger
from .utils.html_sections import html_to_text
from .utils import evidence

logger = get_logger(__name__)

# --- Configuration ---
EVIDENCE_MODEL = ["gemini-2.5-flash"]
MAX_EVIDENCE_CHUNKS = 40
SNIPPET_MAX_CHARS = 140
EVIDENCE_ALLOWED_SOURCES = {"Notes", "Upload", "Research", "Guidelines", "History"}

# --- Helper Functions ---

def _strip_patient_email_section(html: str) -> str:
    """Removes the patient email section to focus on clinical content."""
    if not html:
        return ""
    return re.sub(
        r"<section\s+data-section=['\"]patient_email['\"][\s\S]*?</section>",
        "",
        html,
        flags=re.IGNORECASE,
    ).strip()

def _is_heading_sentence(sentence: str) -> bool:
    """Checks if a sentence is a common section heading."""
    normalized = sentence.strip().strip(":").lower()
    if not normalized:
        return True
    # A set of common headings found in clinical notes
    headings = {
        "summary of visit for the doctor's records",
        "summary of visit for the doctor’s records",
        "next steps for the doctor",
        "draft email for patient",
        "subjective",
        "objective",
        "assessment",
        "plan",
        "history of present illness",
        "review of systems",
        "past medical history",
        "physical examination",
        "medications",
        "allergies",
        "social history",
        "family history",
        "current medications",
        "changes made",
        "issues/side effects",
        "recommendations",
    }
    return normalized in headings

def _is_meaningful_sentence(sentence: str) -> bool:
    """Checks if a sentence contains substantive clinical information."""
    s_lower = sentence.lower()
    
    # Reject boilerplate
    if s_lower.startswith("attending physician:") or s_lower.startswith("patient name:"):
        return False
        
    # Reject if it's just a heading that was missed
    if _is_heading_sentence(s_lower):
        return False

    # Must contain at least one clinical keyword to be considered meaningful
    clinical_keywords = [
        'reports', 'states', 'denies', 'complains of', 'history of',
        'diagnosed with', 'presents with', 'admitted for',
        'vitals', 'bp', 'hr', 'rr', 'temp', 'spo2',
        'exam', 'revealed', 'showed', 'normal', 'abnormal',
        'assessment', 'impression', 'diagnosis', 'rule out',
        'plan', 'continue', 'start', 'discontinue', 'monitor', 'advise',
        'medication', 'prescribed', 'increase', 'decrease',
        'allergy', 'allergic to', 'nka', 'nkda',
        'finding', 'guideline', 'interaction'
    ]
    if not any(keyword in s_lower for keyword in clinical_keywords):
        return False
        
    return True

def _build_prompt(sentence_items: List[Dict], chunk_items: List[Dict]) -> str:
    """Constructs the detailed prompt for the evidence mapping LLM call."""
    return (
        "You are an expert clinical auditor. Your task is to link each sentence from a clinical summary "
        "to the single best source chunk that supports it. Your work is critical for ensuring the "
        "summary is grounded and verifiable.\n\n"
        "INSTRUCTIONS:\n"
        "1.  For each `sentence`, find the single most relevant `source chunk` that provides evidence for it.\n"
        "2.  Use only the provided IDs for sentences and chunks.\n"
        "3.  If no chunk directly supports a sentence, return an empty `chunk_id` for that sentence.\n"
        "4.  Create an `evidence_snippet` by extracting an EXACT quote from the chosen chunk's `text` field (max 140 characters). DO NOT include any URLs in the snippet.\n"
        "5.  CRITICAL SAFETY CHECK: If a sentence mentions a 'Clinical Safety Note' or 'Guideline Note', you MUST link it to a chunk with `source` type 'Research' or 'Guidelines'.\n\n"
        "RESPONSE FORMAT:\n"
        "Return a valid JSON array `[...]` of objects, where each object has these keys: `sentence_id`, `chunk_id`, `evidence_snippet`.\n\n"
        f"SENTENCES TO VERIFY:\n{json.dumps(sentence_items, indent=2)}\n\n"
        f"SOURCE CHUNKS:\n{json.dumps(chunk_items, indent=2)}"
    )

def _parse_llm_response(response_content: str) -> List[Dict]:
    """Safely parses the JSON array from the LLM's response string."""
    try:
        # Find the outermost JSON array
        match = re.search(r'\[\s*\{.*\}\s*\]', response_content, re.DOTALL)
        if match:
            return json.loads(match.group(0))
    except (json.JSONDecodeError, TypeError):
        logger.warning("Evidence agent failed to parse LLM response JSON.")
    return []

# --- Main Agent Function ---

async def build_evidence_map(
    summary_html: str,
    context: Dict[str, Any],
    client: AsyncOpenAI,
) -> Dict[str, Any]:
    """
    Builds the full evidence map by splitting the summary, chunking the sources,
    and using an LLM to link them.
    """
    # 2. Prepare Source Chunks
    all_chunks = [
        chunk
        for chunk in evidence.build_source_chunks(context, max_chars=260)
        if chunk.get("source") in EVIDENCE_ALLOWED_SOURCES
    ]
    if not all_chunks:
        return {"chunks": [], "citations": []}

    # Prioritize Research and Guidelines chunks to ensure they are not truncated
    priority_chunks = [c for c in all_chunks if c.get("source") in {"Research", "Guidelines"}]
    other_chunks = [c for c in all_chunks if c.get("source") not in {"Research", "Guidelines"}]
    selected_chunks = (priority_chunks + other_chunks)[:MAX_EVIDENCE_CHUNKS]

    chunk_items = [
        {
            "id": chunk["id"],
            "text": chunk["text"],
            "source": chunk["source"],
            "sources": chunk.get("sources", []),
        }
        for chunk in selected_chunks
    ]
    
    # 3. Prepare Summary Sentences
    # Strip all HTML tags to get clean text for sentence splitting.
    summary_text = re.sub(r'<[^>]+>', ' ', summary_html)
    sentences = evidence.split_sentences(summary_text)
    
    # Filter for meaningful sentences
    meaningful_sentences = [
        s.strip() for s in sentences 
        if _is_meaningful_sentence(s)
    ]

    if not meaningful_sentences:
        return {"chunks": all_chunks, "citations": []}

    sentence_items = [
        {"id": f"S{i+1}", "text": sentence}
        for i, sentence in enumerate(meaningful_sentences)
    ]

    # 4. LLM Call for Mapping
    prompt = _build_prompt(sentence_items, chunk_items)
    
    try:
        response = await generate_with_fallback(
            client=client,
            messages=[
                {"role": "system", "content": "You are a clinical auditor linking sentences to evidence chunks."},
                {"role": "user", "content": prompt},
            ],
            models=EVIDENCE_MODEL,
        )
        llm_output = response.choices[0].message.content or ""
        mappings = _parse_llm_response(llm_output)
    except Exception as exc:
        logger.error(f"Evidence mapping LLM call failed: {exc}")
        mappings = []

    # 5. Process Mappings into Final Citation Format
    sentence_lookup = {item["id"]: item["text"] for item in sentence_items}
    chunk_ids_in_prompt = {chunk["id"] for chunk in chunk_items}
    
    citations = []
    used_chunk_ids = set()

    for item in mappings:
        sentence_id = item.get("sentence_id")
        chunk_id = item.get("chunk_id")
        
        if not sentence_id or not chunk_id or chunk_id not in chunk_ids_in_prompt:
            continue
            
        sentence_text = sentence_lookup.get(sentence_id)
        if not sentence_text:
            continue

        snippet = (item.get("evidence_snippet") or "").strip().replace("\n", " ")
        if len(snippet) > SNIPPET_MAX_CHARS:
            snippet = snippet[:SNIPPET_MAX_CHARS] + "..."

        citations.append({
            "sentence": sentence_text,
            "chunk_ids": [chunk_id],
            "snippets": {chunk_id: snippet} if snippet else {},
        })
        used_chunk_ids.add(chunk_id)

    # Filter original chunks to only those that were actually used
    filtered_chunks = [chunk for chunk in all_chunks if chunk["id"] in used_chunk_ids]

    return {"chunks": filtered_chunks, "citations": citations}
