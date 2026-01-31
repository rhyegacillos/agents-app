import json
import os
import numpy as np
from typing import List, Dict, Any, Optional
from pathlib import Path
from openai import AsyncOpenAI

DB_PATH = Path("data/memory_db.json")

class VectorStore:
    def __init__(self):
        self.db_path = DB_PATH
        self._ensure_db()

    def _ensure_db(self):
        if not self.db_path.parent.exists():
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.db_path.exists():
            with open(self.db_path, "w") as f:
                json.dump([], f)

    def _load(self) -> List[Dict[str, Any]]:
        try:
            with open(self.db_path, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return []

    def _save(self, data: List[Dict[str, Any]]):
        with open(self.db_path, "w") as f:
            json.dump(data, f)

    def _cosine_similarity(self, a: List[float], b: List[float]) -> float:
        return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))

    def get_all_documents(self) -> List[Dict[str, Any]]:
        """Loads and returns all documents from the store."""
        return self._load()

    async def add_document(self, text: str, metadata: Dict[str, Any], client: AsyncOpenAI, patient_name: str, date: str, payload: Optional[Dict[str, Any]] = None):
        """Generates embedding and saves document, overwriting duplicates. Optional payload is stored alongside text."""
        response = await client.embeddings.create(
            input=text,
            model="text-embedding-3-small"
        )
        embedding = response.data[0].embedding

        # Ensure a doc_id for later targeted updates/deletes
        doc_id = metadata.get("doc_id")
        if not doc_id:
            doc_id = os.urandom(16).hex()
            metadata["doc_id"] = doc_id
        
        doc = {
            "text": text,
            "metadata": metadata,
            "embedding": embedding,
            "timestamp": date,
            "payload": payload or None,
        }
        
        db = self._load()
        
        # Deduplication logic
        key_patient = patient_name.lower().strip()
        key_date = date
        key_type = metadata.get("type", "")
        key_template = metadata.get("template_id", "generic")
        key_encounter = metadata.get("encounter_id")
        
        found_index = -1
        for i, existing_doc in enumerate(db):
            meta = existing_doc.get("metadata", {}) or {}
            if meta.get("deleted"):
                continue  # do not overwrite soft-deleted entries; create a new record instead
            if (
                meta.get("patient_name") == key_patient
                and meta.get("date") == key_date
                and meta.get("type", "") == key_type
                and meta.get("template_id", "generic") == key_template
                and (key_encounter is None or meta.get("encounter_id") == key_encounter)
            ):
                found_index = i
                break
        
        if found_index != -1:
            db[found_index] = doc # Overwrite
        else:
            db.append(doc) # Add new
            
        self._save(db)

    async def search(self, query: str, client: AsyncOpenAI, filter_metadata: Optional[Dict[str, Any]] = None, limit: int = 3) -> List[Dict[str, Any]]:
        """Semantic search with optional metadata filtering."""
        response = await client.embeddings.create(
            input=query,
            model="text-embedding-3-small"
        )
        query_vec = response.data[0].embedding
        
        db = self._load()
        if not db:
            return []

        # Filter first (e.g., only this patient_id)
        candidates = db
        if filter_metadata:
            for key, value in filter_metadata.items():
                candidates = [doc for doc in candidates if doc["metadata"].get(key) == value]

        if not candidates:
            return []

        # Calculate scores
        scored = []
        for doc in candidates:
            score = self._cosine_similarity(query_vec, doc["embedding"])
            scored.append((score, doc))

        # Sort descending
        scored.sort(key=lambda x: x[0], reverse=True)
        
        # Return top N (stripped of embedding to save bandwidth)
        results = []
        for score, doc in scored[:limit]:
            result_doc = doc.copy()
            del result_doc["embedding"]
            result_doc["score"] = score
            results.append(result_doc)
            
        return results

    def save_all(self, docs: List[Dict[str, Any]]):
        """Persist provided docs (used for admin/maintenance updates)."""
        self._save(docs)

# Singleton instance
store = VectorStore()
