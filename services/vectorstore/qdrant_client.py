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

        # Try to create the collection
        try:
            self._create_collection()
            # Successfully created, nothing more to do
            return
        except UnexpectedResponse as e:
            if e.status_code == 409:
                # Collection already exists - this is okay, we'll validate it below
                self.logger.info(f"Collection '{self.collection_name}' already exists, validating configuration...")
            else:
                raise
        except Exception:
            raise

        # Collection exists (either from before or after 409). Validate dimensions.
        self._validate_collection_dimensions(force_recreate)

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
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Perform similarity search for a query embedding.

        Args:
            query_embedding: Embedding vector of the query
            top_k: Number of top results to return

        Returns:
            List of result dictionaries with chunk_id, score, text, and payload
        """
        # Use query_points for this version of qdrant-client
        response = self.client.query_points(
            collection_name=self.collection_name,
            query=query_embedding,
            limit=top_k
        )

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

        return formatted

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

        # Build filter: source == source AND chunk_index IN indices
        filter = Filter(
            must=[
                FieldCondition(key="source", match=MatchValue(value=source)),
                FieldCondition(key="chunk_index", match=MatchAny(any=chunk_indices))
            ]
        )

        # Use scroll to retrieve all matching points
        results = []
        next_offset = None
        try:
            while True:
                records, next_offset = self.client.scroll(
                    collection_name=self.collection_name,
                    limit=100,  # batch size
                    offset=next_offset,
                    filter=filter,
                    with_payload=True,
                    with_vectors=False
                )
                for record in records:
                    payload = record.payload or {}
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
