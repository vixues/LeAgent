"""Vector Search Tool - Semantic vector search using Milvus.

Provides operations for embedding generation and similarity search in vector databases.
"""

from __future__ import annotations

from typing import Any

import structlog

from leagent.tools._data import load_records
from leagent.tools._data.tool_helpers import INPUT_SCHEMA_FRAGMENT
from leagent.tools.base import BaseTool, ToolCategory, ToolContext

logger = structlog.get_logger(__name__)


class VectorSearchTool(BaseTool):
    """Semantic vector search using Milvus vector database.

    Features:
    - Generate embeddings using configurable models
    - Search across Milvus collections
    - Similarity threshold filtering
    - Hybrid search with metadata filters
    - Batch query support
    """

    name = "vector_search"
    description = (
        "Perform semantic vector search using Milvus. Generate embeddings and "
        "find similar items based on vector similarity with optional threshold filtering."
    )
    category = ToolCategory.DATA
    version = "1.0.0"
    timeout_sec = 120
    aliases = ["semantic_search", "embedding_search", "similarity_search"]
    search_hint = "vector embedding semantic similarity search Milvus nearest neighbor"
    is_concurrency_safe = True
    is_read_only = True
    interrupt_behavior = "cancel"
    max_result_size_chars = 100_000

    def _enforce_path_sandbox(
        self,
        params: dict[str, Any],
        context: ToolContext,
    ) -> None:
        from leagent.tools._sandbox.paths import PathSandbox

        request_id = context.extra.get("request_id", context.session_id or "")
        ref = params.get("documents_artifact")
        if isinstance(ref, dict):
            uri = ref.get("uri", "")
            if uri and not uri.startswith("minio://"):
                raw = uri.removeprefix("file://")
                PathSandbox.resolve_safe(
                    raw, context=context, tool_name=self.name,
                    request_id=str(request_id),
                )
        for doc in params.get("documents") or []:
            if isinstance(doc, dict):
                uri = doc.get("uri", "")
                if uri and not uri.startswith("minio://"):
                    raw = uri.removeprefix("file://")
                    PathSandbox.resolve_safe(
                        raw, context=context, tool_name=self.name,
                        request_id=str(request_id),
                    )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": ["search", "embed", "insert", "delete", "count"],
                    "description": "Operation to perform.",
                    "default": "search",
                },
                "collection_name": {
                    "type": "string",
                    "description": "Name of the Milvus collection.",
                },
                "query_text": {
                    "type": "string",
                    "description": "Text to search for (will be embedded).",
                },
                "query_texts": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Multiple texts to search for.",
                },
                "query_vector": {
                    "type": "array",
                    "items": {"type": "number"},
                    "description": "Pre-computed query vector.",
                },
                "top_k": {
                    "type": "integer",
                    "description": "Number of results to return.",
                    "default": 10,
                    "minimum": 1,
                    "maximum": 1000,
                },
                "similarity_threshold": {
                    "type": "number",
                    "description": "Minimum similarity score (0-1) for results.",
                    "minimum": 0,
                    "maximum": 1,
                },
                "filter_expression": {
                    "type": "string",
                    "description": "Milvus filter expression for metadata filtering.",
                },
                "output_fields": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Fields to include in results.",
                },
                "texts_to_embed": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "For embed operation: texts to convert to vectors.",
                },
                "documents": {
                    "description": (
                        "For insert operation: documents to add (inline array or artifact-ref)."
                    ),
                    "oneOf": [
                        {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "id": {"type": "string"},
                                    "text": {"type": "string"},
                                    "metadata": {"type": "object"},
                                },
                            },
                        },
                        {"type": "object", "properties": {"uri": {"type": "string"}}, "required": ["uri"]},
                    ],
                },
                "documents_artifact": INPUT_SCHEMA_FRAGMENT["artifact"],
                "ids_to_delete": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "For delete operation: document IDs to remove.",
                },
                "embedding_model": {
                    "type": "string",
                    "description": "Model to use for embedding generation.",
                    "default": "text-embedding-3-small",
                },
                "metric_type": {
                    "type": "string",
                    "enum": ["L2", "IP", "COSINE"],
                    "description": "Distance metric for similarity.",
                    "default": "COSINE",
                },
            },
            "required": ["operation"],
            "additionalProperties": False,
        }

    def get_activity_description(self, params: dict[str, Any] | None = None) -> str | None:
        return "Searching vectors"

    async def execute(self, params: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        """Execute vector search operation.

        Args:
            params: Tool parameters including operation type and search options.
            context: Execution context with LLM client for embeddings.

        Returns:
            Dictionary containing search results or operation status.

        Raises:
            ValueError: If parameters are invalid.
            RuntimeError: If Milvus operations fail.
        """
        operation = params.get("operation", "search")

        if operation == "embed":
            return await self._execute_embed(params, context)
        elif operation == "search":
            return await self._execute_search(params, context)
        elif operation == "insert":
            return await self._execute_insert(params, context)
        elif operation == "delete":
            return await self._execute_delete(params, context)
        elif operation == "count":
            return await self._execute_count(params, context)
        else:
            raise ValueError(f"Unknown operation: {operation}")

    async def _get_embeddings(
        self, texts: list[str], model: str, context: ToolContext
    ) -> list[list[float]]:
        """Generate embeddings for texts using the configured LLM client."""
        if not context.llm:
            raise RuntimeError("LLM client not available in context for embedding generation")

        embeddings = []
        for text in texts:
            embedding = await context.llm.embed(text, model=model)
            embeddings.append(embedding)

        return embeddings

    async def _get_milvus_client(self, context: ToolContext) -> Any:
        """Get Milvus client from context or create new connection."""
        try:
            from pymilvus import MilvusClient
        except ImportError as e:
            raise RuntimeError(
                "pymilvus is not installed. Install with: pip install pymilvus"
            ) from e

        if context.settings and hasattr(context.settings, "milvus_uri"):
            uri = context.settings.milvus_uri
        else:
            uri = "http://localhost:19530"

        client = MilvusClient(uri=uri)
        return client

    async def _execute_embed(
        self, params: dict[str, Any], context: ToolContext
    ) -> dict[str, Any]:
        """Generate embeddings for texts."""
        texts = params.get("texts_to_embed", [])
        model = params.get("embedding_model", "text-embedding-3-small")

        if not texts:
            raise ValueError("texts_to_embed is required for embed operation")

        logger.info("Generating embeddings", count=len(texts), model=model)

        embeddings = await self._get_embeddings(texts, model, context)

        return {
            "operation": "embed",
            "embeddings": embeddings,
            "count": len(embeddings),
            "dimension": len(embeddings[0]) if embeddings else 0,
            "model": model,
        }

    async def _execute_search(
        self, params: dict[str, Any], context: ToolContext
    ) -> dict[str, Any]:
        """Execute vector similarity search."""
        collection_name = params.get("collection_name")
        query_text = params.get("query_text")
        query_texts = params.get("query_texts", [])
        query_vector = params.get("query_vector")
        top_k = params.get("top_k", 10)
        similarity_threshold = params.get("similarity_threshold")
        filter_expression = params.get("filter_expression")
        output_fields = params.get("output_fields")
        model = params.get("embedding_model", "text-embedding-3-small")
        metric_type = params.get("metric_type", "COSINE")

        if not collection_name:
            raise ValueError("collection_name is required for search operation")

        if query_text:
            query_texts = [query_text]

        if query_texts and not query_vector:
            embeddings = await self._get_embeddings(query_texts, model, context)
            query_vectors = embeddings
        elif query_vector:
            query_vectors = [query_vector]
        else:
            raise ValueError("Either query_text, query_texts, or query_vector is required")

        logger.info(
            "Executing vector search",
            collection=collection_name,
            queries=len(query_vectors),
            top_k=top_k,
        )

        client = await self._get_milvus_client(context)

        try:
            search_params = {
                "metric_type": metric_type,
            }

            search_kwargs: dict[str, Any] = {
                "collection_name": collection_name,
                "data": query_vectors,
                "limit": top_k,
                "search_params": search_params,
            }

            if filter_expression:
                search_kwargs["filter"] = filter_expression

            if output_fields:
                search_kwargs["output_fields"] = output_fields

            results = client.search(**search_kwargs)

            formatted_results: list[list[dict[str, Any]]] = []
            for query_results in results:
                query_hits: list[dict[str, Any]] = []
                for hit in query_results:
                    score = hit.get("distance", 0)

                    if metric_type == "COSINE":
                        similarity = score
                    elif metric_type == "IP":
                        similarity = score
                    else:
                        similarity = 1 / (1 + score)

                    if similarity_threshold and similarity < similarity_threshold:
                        continue

                    hit_data = {
                        "id": hit.get("id"),
                        "score": score,
                        "similarity": similarity,
                    }

                    if "entity" in hit:
                        hit_data["fields"] = hit["entity"]

                    query_hits.append(hit_data)

                formatted_results.append(query_hits)

            total_results = sum(len(qr) for qr in formatted_results)

            return {
                "operation": "search",
                "collection": collection_name,
                "results": formatted_results[0] if len(formatted_results) == 1 else formatted_results,
                "total_results": total_results,
                "queries_count": len(query_vectors),
                "top_k": top_k,
                "threshold_applied": similarity_threshold,
            }

        finally:
            client.close()

    async def _execute_insert(
        self, params: dict[str, Any], context: ToolContext
    ) -> dict[str, Any]:
        """Insert documents into collection."""
        collection_name = params.get("collection_name")
        documents_raw = params.get("documents") or params.get("documents_artifact")
        model = params.get("embedding_model", "text-embedding-3-small")

        if not collection_name:
            raise ValueError("collection_name is required for insert operation")

        documents = load_records(documents_raw, context) if documents_raw is not None else []

        if not documents:
            raise ValueError("documents is required for insert operation")

        logger.info("Inserting documents", collection=collection_name, count=len(documents))

        texts = [doc.get("text", "") for doc in documents]
        embeddings = await self._get_embeddings(texts, model, context)

        client = await self._get_milvus_client(context)

        try:
            data = []
            for i, doc in enumerate(documents):
                record = {
                    "id": doc.get("id", str(i)),
                    "vector": embeddings[i],
                    "text": doc.get("text", ""),
                }
                if "metadata" in doc:
                    record.update(doc["metadata"])
                data.append(record)

            result = client.insert(collection_name=collection_name, data=data)

            return {
                "operation": "insert",
                "collection": collection_name,
                "inserted_count": len(data),
                "insert_result": result,
            }

        finally:
            client.close()

    async def _execute_delete(
        self, params: dict[str, Any], context: ToolContext
    ) -> dict[str, Any]:
        """Delete documents from collection."""
        collection_name = params.get("collection_name")
        ids_to_delete = params.get("ids_to_delete", [])
        filter_expression = params.get("filter_expression")

        if not collection_name:
            raise ValueError("collection_name is required for delete operation")

        if not ids_to_delete and not filter_expression:
            raise ValueError("Either ids_to_delete or filter_expression is required")

        logger.info(
            "Deleting documents",
            collection=collection_name,
            id_count=len(ids_to_delete) if ids_to_delete else "filter",
        )

        client = await self._get_milvus_client(context)

        try:
            if ids_to_delete:
                result = client.delete(
                    collection_name=collection_name,
                    ids=ids_to_delete,
                )
            else:
                result = client.delete(
                    collection_name=collection_name,
                    filter=filter_expression,
                )

            return {
                "operation": "delete",
                "collection": collection_name,
                "delete_result": result,
            }

        finally:
            client.close()

    async def _execute_count(
        self, params: dict[str, Any], context: ToolContext
    ) -> dict[str, Any]:
        """Count documents in collection."""
        collection_name = params.get("collection_name")

        if not collection_name:
            raise ValueError("collection_name is required for count operation")

        client = await self._get_milvus_client(context)

        try:
            stats = client.get_collection_stats(collection_name)
            row_count = stats.get("row_count", 0)

            return {
                "operation": "count",
                "collection": collection_name,
                "count": row_count,
                "stats": stats,
            }

        finally:
            client.close()
