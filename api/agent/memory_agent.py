import time
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
    doc_id: str | None = None,
    encounter_id: str | None = None,
    template_id: str | None = None,
):
    """
    Stores a generated clinical summary into long-term memory.
    """
    logger.info(f"Memorizing visit for patient: {patient_name} on {date}")
    
    metadata = {
        "patient_name": patient_name.lower().strip(),
        "date": date,
        "type": doc_type,
        "doc_id": doc_id or None,
        "encounter_id": encounter_id,
        "template_id": template_id or "generic",
        "time": time.strftime("%H:%M:%S"),
        "saved_at": time.time(),
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


def rename_patient(old_name: str, new_name: str) -> int:
    """Rename patient across stored documents. Returns count updated."""
    return store.rename_patient(old_name, new_name)


def soft_delete_doc(doc_id: str) -> int:
    """Soft delete by doc_id; marks metadata.deleted flag."""
    return store.soft_delete_doc(doc_id)

def restore_doc(doc_id: str) -> int:
    """Restore a soft-deleted doc by doc_id."""
    return store.restore_doc(doc_id)

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
        if doc.get("metadata", {}).get("deleted"):
            continue
        if name and isinstance(name, str):
            # Sanitize before adding to the set
            patient_names.add(name.lower().strip().title())
            
    return sorted(list(patient_names))


def list_patients_paginated(
    limit: int = 50,
    offset: int = 0,
    query: str | None = None,
    sort: str = "name",
    order: str = "asc",
) -> Dict[str, Any]:
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
        if meta.get("deleted"):
            continue  # exclude soft-deleted from counts/last_visit
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

    # Sorting
    sort_key = (sort or "name").lower()
    order_key = (order or "asc").lower()
    reverse = order_key == "desc"
    if sort_key == "last_visit":
        names.sort(
            key=lambda n: (
                meta_map.get(n, {}).get("last_visit") is None,
                meta_map.get(n, {}).get("last_visit") or "",
                n,
            ),
            reverse=reverse,
        )
    else:
        names.sort(reverse=reverse)

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
    include_deleted: bool = False,
) -> Dict[str, Any]:
    """
    Returns visit documents for a patient, sorted by date desc.
    """
    if not patient_name:
        return []
    key = patient_name.lower().strip()
    docs = store.get_all_documents()
    filtered = []
    evidence_by_encounter: Dict[str, Any] = {}
    for doc in docs:
        meta = doc.get("metadata", {}) or {}
        deleted_flag = meta.get("deleted")
        if deleted_flag and not include_deleted:
            continue
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
            enc_key = meta.get("encounter_id") or meta.get("doc_id") or doc_date
            evidence_by_encounter[enc_key] = doc.get("payload")
        filtered.append(doc)
    # Sort by date (ISO strings sort lexicographically) then timestamp fallback
    filtered.sort(key=lambda d: d.get("metadata", {}).get("date") or d.get("timestamp") or "", reverse=True)
    sliced = filtered[offset: offset + limit]
    next_offset = offset + limit if (offset + limit) < len(filtered) else None
    results: List[Dict[str, Any]] = []
    for doc in sliced:
        meta = doc.get("metadata", {}) or {}
        doc_date = meta.get("date", "")
        enc_key = meta.get("encounter_id") or meta.get("doc_id") or doc_date
        evidence = evidence_by_encounter.get(enc_key)
        deleted_flag = meta.get("deleted")
        results.append({
            "date": doc_date,
            "time": meta.get("time"),
            "type": meta.get("type", "visit_summary"),
            "summary": doc.get("text", ""),
            "evidence": evidence,
            "has_evidence": evidence is not None,
            "doc_id": meta.get("doc_id") or f"{doc_date}:{meta.get('type','')}",
            "encounter_id": meta.get("encounter_id"),
            "template_id": meta.get("template_id", "generic"),
            "deleted": bool(deleted_flag),
            "deleted_at": meta.get("deleted_at"),
        })
    return {"items": results, "count": len(filtered), "next_offset": next_offset}
