import os
import time
from decimal import Decimal
from typing import Any, Dict, List, Optional

import numpy as np
from openai import AsyncOpenAI

try:
    from boto3.dynamodb.conditions import Attr, Key
except ImportError:  # pragma: no cover - local fallback when boto3 is not installed yet
    Attr = None
    Key = None

class VectorStore:
    def __init__(self):
        self.table_name = os.getenv("DYNAMODB_TABLE_NAME", "").strip()
        self.endpoint_url = os.getenv("DYNAMODB_ENDPOINT_URL", "").strip() or None
        self.table = None
        self._init_dynamodb()

    def _init_dynamodb(self) -> None:
        if not self.table_name:
            raise RuntimeError("DYNAMODB_TABLE_NAME is required for the memory store")

        import boto3

        session = boto3.session.Session(
            region_name=(
                os.getenv("AWS_REGION")
                or os.getenv("AWS_DEFAULT_REGION")
                or os.getenv("DEFAULT_AWS_REGION")
            )
        )
        dynamodb = session.resource("dynamodb", endpoint_url=self.endpoint_url)
        self.table = dynamodb.Table(self.table_name)

    def _cosine_similarity(self, a: List[float], b: List[float]) -> float:
        return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))

    def _patient_pk(self, patient_name: str) -> str:
        return f"PATIENT#{patient_name.lower().strip()}"

    def _doc_sk(self, doc_id: str) -> str:
        return f"DOC#{doc_id}"

    def _dedupe_key(self, patient_name: str, metadata: Dict[str, Any], date: str) -> str:
        encounter = metadata.get("encounter_id") or ""
        return "|".join(
            [
                patient_name.lower().strip(),
                date,
                str(metadata.get("type", "")),
                str(metadata.get("template_id", "generic")),
                str(encounter),
            ]
        )

    def _serialize_for_dynamodb(self, value: Any) -> Any:
        if isinstance(value, float):
            return Decimal(str(value))
        if isinstance(value, list):
            return [self._serialize_for_dynamodb(item) for item in value]
        if isinstance(value, dict):
            return {key: self._serialize_for_dynamodb(item) for key, item in value.items()}
        return value

    def _deserialize_from_dynamodb(self, value: Any) -> Any:
        if isinstance(value, list):
            return [self._deserialize_from_dynamodb(item) for item in value]
        if isinstance(value, dict):
            return {key: self._deserialize_from_dynamodb(item) for key, item in value.items()}
        if isinstance(value, Decimal):
            if value == value.to_integral_value():
                return int(value)
            return float(value)
        return value

    def _doc_from_item(self, item: Dict[str, Any]) -> Dict[str, Any]:
        decoded = self._deserialize_from_dynamodb(item)
        return {
            "text": decoded.get("text", ""),
            "metadata": decoded.get("metadata", {}) or {},
            "embedding": decoded.get("embedding", []) or [],
            "timestamp": decoded.get("timestamp", ""),
            "payload": decoded.get("payload"),
        }

    def _item_from_doc(self, doc: Dict[str, Any]) -> Dict[str, Any]:
        metadata = doc.get("metadata", {}) or {}
        patient_name = metadata.get("patient_name", "").lower().strip()
        doc_id = metadata.get("doc_id")
        if not patient_name or not doc_id:
            raise ValueError("Document metadata must include patient_name and doc_id")

        item = {
            "pk": self._patient_pk(patient_name),
            "sk": self._doc_sk(doc_id),
            "item_type": "document",
            "doc_id": doc_id,
            "dedupe_key": self._dedupe_key(patient_name, metadata, doc.get("timestamp", "")),
            "timestamp": doc.get("timestamp", ""),
            "text": doc.get("text", ""),
            "embedding": doc.get("embedding", []),
            "metadata": metadata,
            "payload": doc.get("payload"),
        }
        return self._serialize_for_dynamodb(item)

    def _scan_all_items(self) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        response = self.table.scan(FilterExpression=Attr("item_type").eq("document"))
        items.extend(response.get("Items", []))
        while "LastEvaluatedKey" in response:
            response = self.table.scan(
                FilterExpression=Attr("item_type").eq("document"),
                ExclusiveStartKey=response["LastEvaluatedKey"],
            )
            items.extend(response.get("Items", []))
        return items

    def _query_patient_items(self, patient_name: str) -> List[Dict[str, Any]]:
        response = self.table.query(KeyConditionExpression=Key("pk").eq(self._patient_pk(patient_name)))
        items = response.get("Items", [])
        while "LastEvaluatedKey" in response:
            response = self.table.query(
                KeyConditionExpression=Key("pk").eq(self._patient_pk(patient_name)),
                ExclusiveStartKey=response["LastEvaluatedKey"],
            )
            items.extend(response.get("Items", []))
        return items

    def _find_item_by_doc_id(self, doc_id: str) -> Optional[Dict[str, Any]]:
        response = self.table.scan(
            FilterExpression=Attr("item_type").eq("document") & Attr("doc_id").eq(doc_id)
        )
        items = response.get("Items", [])
        while not items and "LastEvaluatedKey" in response:
            response = self.table.scan(
                FilterExpression=Attr("item_type").eq("document") & Attr("doc_id").eq(doc_id),
                ExclusiveStartKey=response["LastEvaluatedKey"],
            )
            items = response.get("Items", [])
        return items[0] if items else None

    def get_all_documents(self) -> List[Dict[str, Any]]:
        """Loads and returns all documents from the store."""
        return [self._doc_from_item(item) for item in self._scan_all_items()]

    async def add_document(
        self,
        text: str,
        metadata: Dict[str, Any],
        client: AsyncOpenAI,
        patient_name: str,
        date: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Generates embedding and saves document, overwriting duplicates. Optional payload is stored alongside text."""
        response = await client.embeddings.create(input=text, model="text-embedding-3-small")
        embedding = response.data[0].embedding

        doc_id = metadata.get("doc_id")
        if not doc_id:
            doc_id = os.urandom(16).hex()

        key_patient = patient_name.lower().strip()
        key_date = date
        key_type = metadata.get("type", "")
        key_template = metadata.get("template_id", "generic")
        key_encounter = metadata.get("encounter_id")

        existing_docs = [self._doc_from_item(item) for item in self._query_patient_items(key_patient)]

        found_doc: Optional[Dict[str, Any]] = None
        for existing_doc in existing_docs:
            meta = existing_doc.get("metadata", {}) or {}
            if meta.get("deleted"):
                continue
            if (
                meta.get("patient_name") == key_patient
                and meta.get("date") == key_date
                and meta.get("type", "") == key_type
                and meta.get("template_id", "generic") == key_template
                and (key_encounter is None or meta.get("encounter_id") == key_encounter)
            ):
                found_doc = existing_doc
                break

        if found_doc is not None:
            doc_id = found_doc.get("metadata", {}).get("doc_id") or doc_id

        metadata = {
            **metadata,
            "doc_id": doc_id,
            "patient_name": key_patient,
            "date": key_date,
            "template_id": key_template,
        }

        doc = {
            "text": text,
            "metadata": metadata,
            "embedding": embedding,
            "timestamp": date,
            "payload": payload or None,
        }

        self.table.put_item(Item=self._item_from_doc(doc))

    async def search(
        self,
        query: str,
        client: AsyncOpenAI,
        filter_metadata: Optional[Dict[str, Any]] = None,
        limit: int = 3,
    ) -> List[Dict[str, Any]]:
        """Semantic search with optional metadata filtering."""
        response = await client.embeddings.create(input=query, model="text-embedding-3-small")
        query_vec = response.data[0].embedding

        if filter_metadata and filter_metadata.get("patient_name"):
            candidates = [
                self._doc_from_item(item)
                for item in self._query_patient_items(filter_metadata["patient_name"])
            ]
        else:
            candidates = self.get_all_documents()

        if not candidates:
            return []

        if filter_metadata:
            for key, value in filter_metadata.items():
                candidates = [doc for doc in candidates if doc["metadata"].get(key) == value]

        if not candidates:
            return []

        scored = []
        for doc in candidates:
            score = self._cosine_similarity(query_vec, doc["embedding"])
            scored.append((score, doc))

        scored.sort(key=lambda x: x[0], reverse=True)

        results = []
        for score, doc in scored[:limit]:
            result_doc = doc.copy()
            result_doc.pop("embedding", None)
            result_doc["score"] = score
            results.append(result_doc)

        return results

    def save_all(self, docs: List[Dict[str, Any]]) -> None:
        """Persist provided docs (used for admin/maintenance updates)."""
        existing_items = self._scan_all_items()
        with self.table.batch_writer() as batch:
            for item in existing_items:
                batch.delete_item(Key={"pk": item["pk"], "sk": item["sk"]})
            for doc in docs:
                batch.put_item(Item=self._item_from_doc(doc))

    def rename_patient(self, old_name: str, new_name: str) -> int:
        old_key = old_name.lower().strip()
        new_key = new_name.lower().strip()
        items = self._query_patient_items(old_key)
        if not items:
            return 0

        updated = 0
        with self.table.batch_writer() as batch:
            for item in items:
                doc = self._doc_from_item(item)
                doc["metadata"]["patient_name"] = new_key
                batch.put_item(Item=self._item_from_doc(doc))
                batch.delete_item(Key={"pk": item["pk"], "sk": item["sk"]})
                updated += 1
        return updated

    def soft_delete_doc(self, doc_id: str) -> int:
        item = self._find_item_by_doc_id(doc_id)
        if not item:
            return 0

        metadata = self._deserialize_from_dynamodb(item.get("metadata", {}))
        metadata["deleted"] = True
        metadata["deleted_at"] = time.time()
        item["metadata"] = self._serialize_for_dynamodb(metadata)
        self.table.put_item(Item=item)
        return 1

    def restore_doc(self, doc_id: str) -> int:
        item = self._find_item_by_doc_id(doc_id)
        if not item:
            return 0

        metadata = self._deserialize_from_dynamodb(item.get("metadata", {}))
        if not metadata.get("deleted"):
            return 0
        metadata.pop("deleted", None)
        metadata.pop("deleted_at", None)
        item["metadata"] = self._serialize_for_dynamodb(metadata)
        self.table.put_item(Item=item)
        return 1


# Singleton instance
store = VectorStore()
