"""
Vector Store Service: Qdrant-based vector storage and retrieval.

Provides clean interface for upserting chunks with embeddings and performing similarity search.
Supports both local (in-memory) and remote Qdrant instances.
"""

import uuid
from typing import List, Dict, Any, Optional, TYPE_CHECKING
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchValue, MatchAny
from models.schemas.chunk import Chunk
from core.logger import get_logger
from core.config import get_config
from qdrant_client.http.exceptions import UnexpectedResponse

if TYPE_CHECKING:
    from services.embedding.embedder import Embedder

# Vector size mappings for known embedding models
MODEL_VECTOR_SIZES = {
    "BAAI/bge-m3": 1024,
    "BAAI/bge-large-en": 1024,
    "BAAI/bge-base-en": 768,
    "sentence-transformers/all-MiniLM-L6-v2": 384,
    "all-MiniLM-L6-v2": 384,
    "text-embedding-ada-002": 1536,  # OpenAI
    "embedding-001": 1536,  # Generic
}


class VectorStore:
    """
    Vector database interface using Qdrant.

    Manages collection lifecycle and provides similarity search operations.
    Stores chunks with their embeddings and metadata as payload.
    """

    def __init__(
        self,
        collection_name: str = None,
        vector_size: int = None,
        url: str = None,
        api_key: str = None,
        location: str = ":memory:",
        embedder: 'Embedder' = None  # Optional embedder to auto-derive vector_size
    ):
        """
        Initialize vector store connection.

        Args:
            collection_name: Name of the Qdrant collection (default from config)
            vector_size: Dimension of embedding vectors (if None, derived from embedder or config)
            url: Remote Qdrant URL (if None, uses local/in-memory)
            api_key: API key for remote Qdrant (required if url is provided)
            location: Local Qdrant location (default ":memory:")
            embedder: Optional Embedder instance to auto-derive vector_size from model
        """
        config = get_config()
        self.logger = get_logger("VECTORSTORE")

        self.collection_name = collection_name or config.qdrant_collection_name

        # Determine vector_size: use provided, or from embedder, or default to 1024
        if vector_size is not None:
            self.vector_size = vector_size
        elif embedder is not None:
            # Derive from embedder's model
            self.vector_size = self._get_embedder_vector_size(embedder)
        else:
            # Try to determine from config's embedding model
            model_name = getattr(config, 'embedding_model', 'intfloat/multilingual-e5-small')
            self.vector_size = self._get_model_vector_size(model_name)

        # Determine connection type: use remote if url is provided and non-empty
        if url:
            # Remote connection
            if api_key is None:
                # Try config as fallback
                api_key = config.qdrant_api_key

            self.client = QdrantClient(
                url=url,
                api_key=api_key
            )
            self.logger.info(f"Connected to remote Qdrant at {url}")
            self.is_local = False
        else:
            # Local/in-memory connection
            self.client = QdrantClient(location=location)
            self.logger.info(f"Using local Qdrant at {location}")
            self.is_local = True

        # Tracks whether payload indexes used by server-side filters are ready.
        self._payload_indexes_ready = False

    @staticmethod
    def _is_missing_payload_index_error(error: Exception, field_name: str) -> bool:
        """Return True when Qdrant reports a missing payload index for the given field."""
        message = str(error).lower()
        if "index required but not found" not in message:
            return False
        return field_name.lower() in message

    def _create_payload_index(self, field_name: str, field_schema: str) -> None:
        """Create a payload index with compatibility fallback for qdrant-client signatures."""
        try:
            self.client.create_payload_index(
                collection_name=self.collection_name,
                field_name=field_name,
                field_schema=field_schema,
            )
            self.logger.info(
                f"Ensured payload index for '{field_name}' ({field_schema}) on '{self.collection_name}'."
            )
            return
        except TypeError:
            # Older clients may use field_type instead of field_schema.
            try:
                self.client.create_payload_index(
                    collection_name=self.collection_name,
                    field_name=field_name,
                    field_type=field_schema,
                )
                self.logger.info(
                    f"Ensured payload index for '{field_name}' ({field_schema}) on '{self.collection_name}'."
                )
                return
            except UnexpectedResponse as error:
                if error.status_code == 409 or "already exists" in str(error).lower():
                    return
                raise
        except UnexpectedResponse as error:
            if error.status_code == 409 or "already exists" in str(error).lower():
                return
            raise

    def _ensure_payload_indexes(self, force: bool = False) -> None:
        """Ensure payload indexes needed for filtered retrieval are available in Qdrant."""
        if self._payload_indexes_ready and not force:
            return

        self._create_payload_index("source", "keyword")
        self._create_payload_index("chunk_index", "integer")
        self._payload_indexes_ready = True

    def _prepare_filter_indexes(self, force: bool = False) -> None:
        """Best-effort payload index preparation that does not break retrieval flow."""
        try:
            self._ensure_payload_indexes(force=force)
        except Exception as error:
            self._payload_indexes_ready = False
            self.logger.warning(
                f"Could not ensure payload indexes for filtered retrieval: {error}"
            )

    def _get_embedder_vector_size(self, embedder) -> int:
        """
        Determine vector size from an embedder instance by inspecting its model.

        Args:
            embedder: Embedder instance

        Returns:
            Vector dimension size (int)
        """
        try:
            # The embedder should already have the model loaded
            # Access the class-level _model which holds the SentenceTransformer
            from services.embedding.embedder import Embedder as RealEmbedder
            if isinstance(embedder, RealEmbedder):
                # Access class variable directly
                model = RealEmbedder._model
                if model and hasattr(model, 'get_sentence_embedding_dimension'):
                    dim = model.get_sentence_embedding_dimension()
                    self.logger.info(f"Determined vector size from embedder: {dim}")
                    return dim
                # Fallback: embed a test string and check length
                if model:
                    test_emb = model.encode("test")
                    dim = test_emb.shape[-1] if hasattr(test_emb, 'shape') else len(test_emb)
                    self.logger.info(f"Determined vector size from embedder test: {dim}")
                    return dim
        except Exception as e:
            self.logger.warning(f"Could not determine vector size from embedder: {e}. Using default 1024.")
        return 1024

    def _get_model_vector_size(self, model_name: str) -> int:
        """
        Get vector size from known model name mappings.

        Args:
            model_name: Name of the embedding model

        Returns:
            Vector dimension size (int)
        """
        # Check known mappings
        for known_name, size in MODEL_VECTOR_SIZES.items():
            if model_name.lower() == known_name.lower() or model_name.endswith(known_name):
                return size

        # Unknown model, try to load it to get dimension (expensive)
        self.logger.warning(f"Unknown embedding model '{model_name}'. Attempting to load to determine vector size...")
        try:
            from sentence_transformers import SentenceTransformer
            test_model = SentenceTransformer(model_name)
            test_emb = test_model.encode("test")
            vector_size = test_emb.shape[-1] if hasattr(test_emb, 'shape') else len(test_emb)
            # Cache this result for future use
            MODEL_VECTOR_SIZES[model_name] = vector_size
            self.logger.info(f"Determined vector size for {model_name}: {vector_size}")
            return vector_size
        except Exception as e:
            self.logger.error(f"Failed to determine vector size for model '{model_name}': {e}. Using default 1024.")
            return 1024

    def init_collection(self, recreate: bool = False, force_recreate: bool = False) -> None:
        """
        Create or initialize collection with specified parameters.

        Args:
            recreate: If True, delete existing collection first (useful for testing)
                     Default False to preserve data on remote instances
            force_recreate: If True, will recreate even if collection exists, regardless of settings.
                           Useful for fixing dimension mismatches.
        """
        should_recreate = recreate or force_recreate

        # If recreate requested, attempt to delete existing collection first
        if should_recreate:
            try:
                self.client.delete_collection(collection_name=self.collection_name)
                self.logger.info(f"Deleted existing collection '{self.collection_name}'")
            except UnexpectedResponse as e:
                if e.status_code == 404:
                    pass  # Collection didn't exist, continue
                else:
                    self.logger.warning(f"Error deleting collection during recreate: {e}. Will attempt to create anyway.")
            except Exception as e:
                self.logger.warning(f"Unexpected error deleting collection: {e}. Will attempt to create anyway.")

        created_collection = False

        # Try to create the collection
        try:
            self._create_collection()
            created_collection = True
        except UnexpectedResponse as e:
            if e.status_code == 409:
                # Collection already exists - this is okay, we'll validate it below
                self.logger.info(f"Collection '{self.collection_name}' already exists, validating configuration...")
            else:
                raise
        except Exception:
            raise

        # Collection exists (either from before or after 409). Validate dimensions.
        if not created_collection:
            self._validate_collection_dimensions(force_recreate)

        # Ensure payload indexes used by source/chunk metadata filters are available.
        self._prepare_filter_indexes(force=True)

    def _create_collection(self) -> None:
        """Helper method to create the collection with proper configuration."""
        self.client.create_collection(
            collection_name=self.collection_name,
            vectors_config=VectorParams(
                size=self.vector_size,
                distance=Distance.COSINE
            )
        )
        self.logger.info(f"Created collection '{self.collection_name}' with vector size {self.vector_size}")

    def _validate_collection_dimensions(self, force_recreate: bool = False) -> None:
        """
        Validate that the existing collection has compatible vector dimensions.
        If mismatch and (local or force_recreate), delete and recreate.
        Otherwise, raise ValueError.

        Args:
            force_recreate: If True, auto-recreate even for remote (use cautiously)
        """
        try:
            existing_info = self.client.get_collection(collection_name=self.collection_name)
        except Exception as e:
            self.logger.error(f"Failed to retrieve collection info for validation: {e}")
            raise

        try:
            config = existing_info.config
            if not (hasattr(config, 'params') and hasattr(config.params, 'vectors')):
                self.logger.warning("Collection config missing vector parameters. Assuming compatible.")
                return

            vectors_config = config.params.vectors
            # Determine existing vector size
            if hasattr(vectors_config, 'size'):
                existing_size = vectors_config.size
            elif isinstance(vectors_config, dict):
                first_key = next(iter(vectors_config.keys()))
                existing_size = vectors_config[first_key].size
            else:
                existing_size = None

            if existing_size is None:
                self.logger.warning("Could not determine existing vector size. Skipping validation.")
                return

            if existing_size != self.vector_size:
                error_msg = (f"Vector dimension mismatch: Collection '{self.collection_name}' expects "
                            f"dimension {existing_size}, but embedding model produces {self.vector_size}. ")
                error_msg += "Please either: (1) Use a different collection name, (2) Use a different embedding model, or (3) Delete and recreate the collection with recreate=True."

                if self.is_local or force_recreate:
                    self.logger.warning(f"Dimension mismatch detected. Recreating collection with correct dimension ({self.vector_size}).")
                    try:
                        self.client.delete_collection(collection_name=self.collection_name)
                        self.logger.info(f"Deleted collection '{self.collection_name}' due to dimension mismatch.")
                        self._create_collection()
                    except Exception as e:
                        self.logger.error(f"Failed to delete/recreate collection: {e}")
                        raise
                else:
                    raise ValueError(error_msg)
            else:
                self.logger.info(f"Collection '{self.collection_name}' has compatible vector size ({self.vector_size}).")
        except Exception as e:
            self.logger.error(f"Error during collection validation: {e}")
            raise

    def upsert(
        self,
        chunks: List[Chunk],
        embeddings: List[List[float]]
    ) -> None:
        """
        Insert or update chunks with their embeddings.

        Args:
            chunks: List of Chunk objects
            embeddings: Corresponding list of embedding vectors
        """
        if len(chunks) != len(embeddings):
            raise ValueError(
                f"Mismatch: {len(chunks)} chunks but {len(embeddings)} embeddings"
            )

        points = []
        for chunk, embedding in zip(chunks, embeddings):
            # Prepare payload: store chunk_id, text, and all metadata
            payload = {
                "chunk_id": chunk.chunk_id,
                "text": chunk.text,
                **chunk.metadata  # Merge metadata into payload
            }

            # Generate deterministic UUID from chunk_id (required by Qdrant)
            point_id = uuid.uuid5(uuid.NAMESPACE_DNS, chunk.chunk_id)

            point = PointStruct(
                id=point_id,
                vector=embedding,
                payload=payload
            )
            points.append(point)

        # Batch upsert
        self.client.upsert(
            collection_name=self.collection_name,
            points=points
        )

    def search(
        self,
        query_embedding: List[float],
        top_k: int = 5,
        source_hints: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Perform similarity search for a query embedding.

        Args:
            query_embedding: Embedding vector of the query
            top_k: Number of top results to return

        Returns:
            List of result dictionaries with chunk_id, score, text, and payload
        """
        normalized_sources: List[str] = []
        if source_hints:
            for src in source_hints:
                if not src:
                    continue
                src_clean = str(src).strip()
                if src_clean and src_clean not in normalized_sources:
                    normalized_sources.append(src_clean)

        query_filter = None
        if normalized_sources:
            self._prepare_filter_indexes()
            if len(normalized_sources) == 1:
                source_match = MatchValue(value=normalized_sources[0])
            else:
                source_match = MatchAny(any=normalized_sources)
            query_filter = Filter(
                must=[
                    FieldCondition(key="source", match=source_match),
                ]
            )

        # Use query_points for this version of qdrant-client.
        # Keep a graceful fallback in case query_filter is not supported by runtime version.
        search_limit = max(top_k, top_k * 3) if normalized_sources else top_k
        try:
            response = self.client.query_points(
                collection_name=self.collection_name,
                query=query_embedding,
                limit=search_limit,
                query_filter=query_filter,
            )
        except TypeError:
            response = self.client.query_points(
                collection_name=self.collection_name,
                query=query_embedding,
                limit=search_limit,
            )
        except Exception as e:
            if normalized_sources and self._is_missing_payload_index_error(e, "source"):
                self.logger.warning(
                    "Missing Qdrant payload index for 'source'; creating indexes and retrying filtered vector query once."
                )
                self._prepare_filter_indexes(force=True)
                try:
                    response = self.client.query_points(
                        collection_name=self.collection_name,
                        query=query_embedding,
                        limit=search_limit,
                        query_filter=query_filter,
                    )
                except Exception as retry_error:
                    e = retry_error

            # Remote collections may reject filter queries when payload indexes are not created.
            # Fallback to unfiltered ANN and apply source filtering client-side.
            if normalized_sources:
                self.logger.warning(
                    f"Source-filtered vector query failed ({e}); falling back to client-side filtering."
                )
                response = self.client.query_points(
                    collection_name=self.collection_name,
                    query=query_embedding,
                    limit=search_limit,
                )
            else:
                raise

        # The response contains a list of points in the 'points' attribute
        results = response.points if hasattr(response, 'points') else []

        # Format results
        formatted = []
        for hit in results:
            payload = hit.payload or {}
            result = {
                "chunk_id": payload.get("chunk_id", str(hit.id)),  # Use stored chunk_id
                "score": hit.score,
                "text": payload.get("text", ""),
                "payload": payload  # Full metadata payload
            }
            formatted.append(result)

        if normalized_sources:
            normalized_set = {s.lower() for s in normalized_sources}
            formatted = [
                item for item in formatted
                if str((item.get("payload") or {}).get("source", "")).strip().lower() in normalized_set
            ]

        return formatted[:top_k]

    def get_chunks_by_metadata(
        self,
        source: str,
        chunk_indices: List[int]
    ) -> List[Dict[str, Any]]:
        """
        Retrieve chunks by matching metadata fields source and chunk_index.

        Uses scroll with filter for exact match. Useful for fetching neighboring
        chunks for context expansion.

        Args:
            source: Source document identifier (matches payload['source'])
            chunk_indices: List of chunk indices to retrieve

        Returns:
            List of chunk dictionaries with chunk_id, text, payload.
        """
        if not chunk_indices:
            return []

        self._prepare_filter_indexes()

        # Build filter: source == source AND chunk_index IN indices
        filter_obj = Filter(
            must=[
                FieldCondition(key="source", match=MatchValue(value=source)),
                FieldCondition(key="chunk_index", match=MatchAny(any=chunk_indices))
            ]
        )

        # Use scroll to retrieve all matching points
        results = []
        next_offset = None
        use_server_filter = True
        chunk_index_set = set(chunk_indices)
        try:
            while True:
                params = {
                    "collection_name": self.collection_name,
                    "limit": 100,
                    "offset": next_offset,
                    "with_payload": True,
                    "with_vectors": False,
                }
                if use_server_filter:
                    params["scroll_filter"] = filter_obj

                try:
                    records, next_offset = self.client.scroll(**params)
                except Exception as e:
                    if use_server_filter:
                        self.logger.warning(
                            f"Metadata scroll filter unavailable ({e}); falling back to client-side filtering."
                        )
                        use_server_filter = False
                        next_offset = None
                        continue
                    raise

                for record in records:
                    payload = record.payload or {}
                    if not use_server_filter:
                        source_value = str(payload.get("source", "")).strip()
                        chunk_index_value = payload.get("chunk_index")
                        if source_value != source or chunk_index_value not in chunk_index_set:
                            continue
                    results.append({
                        "chunk_id": payload.get("chunk_id", str(record.id)),
                        "text": payload.get("text", ""),
                        "payload": payload
                    })
                if next_offset is None:
                    break
        except Exception as e:
            self.logger.error(f"Error fetching chunks by metadata: {e}")
            return []

        return results

    def get_chunks_by_source(
        self,
        source: str,
        limit: int = 2000
    ) -> List[Dict[str, Any]]:
        """
        Retrieve chunks for a specific source document.

        Args:
            source: Source document identifier (payload['source'])
            limit: Maximum number of chunks to return

        Returns:
            List of chunk dictionaries with chunk_id, text, and payload.
        """
        if not source:
            return []

        self._prepare_filter_indexes()

        filter_obj = Filter(
            must=[
                FieldCondition(key="source", match=MatchValue(value=source)),
            ]
        )

        results = []
        next_offset = None
        use_server_filter = True
        try:
            while True:
                params = {
                    "collection_name": self.collection_name,
                    "limit": min(256, max(1, limit - len(results))),
                    "offset": next_offset,
                    "with_payload": True,
                    "with_vectors": False,
                }
                if use_server_filter:
                    params["scroll_filter"] = filter_obj

                try:
                    records, next_offset = self.client.scroll(**params)
                except Exception as e:
                    if use_server_filter:
                        self.logger.warning(
                            f"Source scroll filter unavailable ({e}); falling back to client-side filtering."
                        )
                        use_server_filter = False
                        next_offset = None
                        continue
                    raise

                for record in records:
                    payload = record.payload or {}
                    if not use_server_filter:
                        source_value = str(payload.get("source", "")).strip()
                        if source_value != source:
                            continue
                    results.append({
                        "chunk_id": payload.get("chunk_id", str(record.id)),
                        "text": payload.get("text", ""),
                        "payload": payload,
                    })

                if next_offset is None or len(results) >= limit:
                    break
        except Exception as e:
            self.logger.error(f"Error fetching chunks by source '{source}': {e}")
            return []

        return results

    def get_info(self) -> Dict[str, Any]:
        """
        Get collection information (count, status).

        Returns:
            Dictionary with collection info
        """
        info = self.client.get_collection(
            collection_name=self.collection_name
        )
        return {
            "points_count": info.points_count,
            "status": info.status
        }
