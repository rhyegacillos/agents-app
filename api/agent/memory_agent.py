from typing import List, Dict, Any
from openai import AsyncOpenAI
from ..memory.vector_store import store
from .utils import get_logger

logger = get_logger(__name__)

async def remember_visit(
    summary: str,
    patient_name: str, 
    date: str, 
    client: AsyncOpenAI,
    doc_type: str = "visit_summary",
    payload: Dict[str, Any] | None = None,
):
    """
    Stores a generated clinical summary into long-term memory.
    """
    logger.info(f"Memorizing visit for patient: {patient_name} on {date}")
    
    metadata = {
        "patient_name": patient_name.lower().strip(),
        "date": date,
        "type": doc_type
    }
    
    # Store chunks or the whole summary? 
    # For now, storing the whole summary context is fine for this scale.
    await store.add_document(
        text=summary,
        metadata=metadata,
        client=client,
        patient_name=patient_name,
        date=date,
        payload=payload,
    )

async def recall_patient_history(
    patient_name: str, 
    query: str, 
    client: AsyncOpenAI
) -> str:
    """
    Retrieves relevant past context for a patient based on a query.
    Returns a formatted string suitable for LLM context injection.
    """
    logger.info(f"Recalling history for: {patient_name} with query: '{query}'")
    
    try:
        results = await store.search(
            query=query,
            client=client,
            filter_metadata={"patient_name": patient_name.lower().strip()},
            limit=3
        )
    except Exception as e:
        logger.error(f"Failed to recall history: {e}")
        return "Memory retrieval unavailable due to an error."
    
    if not results:
        return "No past history found."
    
    context = f"Past Clinical History for {patient_name}:\n"
    for doc in results:
        date = doc["metadata"].get("date", "Unknown Date")
        doc_type = doc["metadata"].get("type", "visit_summary")
        context += f"- [Date: {date} | {doc_type}]: {doc['text']}\n" # No truncation
        
    return context


def list_known_patients() -> List[str]:
    """
    Scans the vector store and returns a unique, sorted list of all patient names.
    """
    logger.info("Retrieving list of all known patients.")
    
    all_docs = store.get_all_documents()
    
    patient_names = set()
    for doc in all_docs:
        name = doc.get("metadata", {}).get("patient_name")
        if name and isinstance(name, str):
            # Sanitize before adding to the set
            patient_names.add(name.lower().strip().title())
            
    return sorted(list(patient_names))


def list_patients_paginated(limit: int = 50, offset: int = 0, query: str | None = None) -> Dict[str, Any]:
    """
    Returns a paginated list of patient names with has_more flag.
    """
    names = list_known_patients()
    if query:
        q = query.lower().strip()
        names = [n for n in names if q in n.lower()]

    # Build metadata map: latest date and note count
    docs = store.get_all_documents()
    meta_map: Dict[str, Dict[str, Any]] = {}
    for doc in docs:
        meta = doc.get("metadata", {}) or {}
        patient = meta.get("patient_name")
        if not patient:
            continue
        patient_title = patient.strip().title()
        if query and patient_title.lower().find(query.lower().strip()) == -1:
            # Skip those not matching query
            continue
        date = meta.get("date")
        entry = meta_map.setdefault(patient_title, {"note_count": 0, "last_visit": None})
        entry["note_count"] += 1
        if date:
            if (entry["last_visit"] is None) or (date > entry["last_visit"]):
                entry["last_visit"] = date

    total = len(names)
    start = max(offset, 0)
    end = max(start + limit, start)
    items = names[start:end]
    has_more = end < total
    details = []
    for name in items:
        info = meta_map.get(name) or {}
        details.append({
            "name": name,
            "last_visit": info.get("last_visit"),
            "note_count": info.get("note_count", 0),
        })

    return {
        "items": items,              # backwards compatibility
        "details": details,          # enriched data for UI
        "count": len(items),
        "has_more": has_more,
        "total": total,
        "next_offset": end if has_more else None,
    }

def list_patient_visits(
    patient_name: str,
    limit: int = 10,
    offset: int = 0,
    start_date: str | None = None,
    end_date: str | None = None,
    query: str | None = None,
) -> List[Dict[str, Any]]:
    """
    Returns visit documents for a patient, sorted by date desc.
    """
    if not patient_name:
        return []
    key = patient_name.lower().strip()
    docs = store.get_all_documents()
    filtered = []
    evidence_by_date: Dict[str, Any] = {}
    for doc in docs:
        meta = doc.get("metadata", {}) or {}
        if meta.get("patient_name") != key:
            continue
        doc_date = meta.get("date")
        if start_date and doc_date and doc_date < start_date:
            continue
        if end_date and doc_date and doc_date > end_date:
            continue
        if query:
            q = query.lower().strip()
            text = (doc.get("text") or "").lower()
            if q not in text:
                continue
        if doc.get("metadata", {}).get("type") == "visit_evidence" and doc.get("payload"):
            evidence_by_date[doc_date] = doc.get("payload")
        filtered.append(doc)
    # Sort by date (ISO strings sort lexicographically) then timestamp fallback
    filtered.sort(key=lambda d: d.get("metadata", {}).get("date") or d.get("timestamp") or "", reverse=True)
    sliced = filtered[offset: offset + limit]
    results: List[Dict[str, Any]] = []
    for doc in sliced:
        meta = doc.get("metadata", {})
        doc_date = meta.get("date", "")
        evidence = evidence_by_date.get(doc_date)
        results.append({
            "date": doc_date,
            "type": meta.get("type", "visit_summary"),
            "summary": doc.get("text", ""),
            "evidence": evidence,
            "has_evidence": evidence is not None,
        })
    return results
