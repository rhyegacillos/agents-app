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
        date=date
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
