"""
Retrieval Service: Encapsulates vector search and entity retrieval.

Provides a clean interface for the pipeline to retrieve relevant chunks
using embedding-based similarity search and keyword-based search.
"""

from typing import List, Dict, Any, Tuple, Optional
from models.schemas.query import StructuredQuery
from services.embedding.embedder import Embedder, get_embedder
from services.vectorstore.qdrant_client import VectorStore
from services.retrieval.elastic_client import ElasticStore
from services.retrieval.ranker import merge_rank
from core.logger import get_logger


class Retriever:
    """
    Retrieves relevant chunks for a query using vector similarity search.

    Uses embedding model to encode queries and Qdrant for vector search.
    Entity retrieval is currently mocked (uses same results as vector search).
    """

    def __init__(
        self,
        embedder: Embedder = None,
        vector_store: VectorStore = None,
        elastic_store: ElasticStore = None
    ):
        """
        Initialize retriever with dependencies.

        Args:
            embedder: Embedder instance (uses singleton if None)
            vector_store: VectorStore instance (creates and initializes if None)
            elastic_store: ElasticStore instance (creates and initializes if None)
        """
        from core.config import get_config

        self.embedder = embedder or get_embedder()
        self.logger = get_logger("RETRIEVER")

        # Initialize vector store with sample data if not provided
        if vector_store is not None:
            self.vector_store = vector_store
        else:
            self.logger.info("Initializing vector store")
            config = get_config()
            # Use config's Qdrant URL and API key
            self.vector_store = VectorStore(
                url=config.qdrant_url,
                api_key=config.qdrant_api_key,
                embedder=self.embedder  # Auto-derive vector size from embedder
            )
            # Never recreate automatically in runtime paths. Recreate can wipe uploaded docs.
            self.vector_store.init_collection(recreate=False, force_recreate=False)

        # Initialize Elasticsearch store with sample data if not provided
        if elastic_store is not None:
            self.elastic_store = elastic_store
        else:
            self.logger.info("Initializing Elasticsearch store")
            config = get_config()
            # Use config's Elasticsearch host and port if available
            host = getattr(config, 'elastic_host', 'localhost')
            port = getattr(config, 'elastic_port', 9200)
            try:
                self.elastic_store = ElasticStore(host=host, port=port)
            except Exception as e:
                self.logger.warning(f"Elasticsearch unavailable; continuing with dense retrieval only: {e}")
                self.elastic_store = None

    def _populate_sample_data(self, vector_store: VectorStore) -> None:
        """
        Populate vector store with sample document chunks.

        Uses same sample data as pipeline._populate_sample_data.
        """
        # Import Chunk here to avoid circular dependency
        from models.schemas.chunk import Chunk

        embedder = self.embedder
        sample_chunks = [
            Chunk(
                chunk_id="vec_001",
                text="HelioX performs vector search using Qdrant for production deployments.",
                metadata={"source": "vector"}
            ),
            Chunk(
                chunk_id="vec_002",
                text="The embedding model used is intfloat/multilingual-e5-small.",
                metadata={"source": "vector"}
            ),
            Chunk(
                chunk_id="vec_003",
                text="BM25 sparse retrieval optimization uses the BM25 ranking function.",
                metadata={"source": "vector"}
            ),
            Chunk(
                chunk_id="vec_004",
                text="Vector similarity search uses cosine distance for embeddings.",
                metadata={"source": "vector"}
            ),
            Chunk(
                chunk_id="vec_005",
                text="Chunks are embedded in batches of 100 for efficiency.",
                metadata={"source": "vector"}
            ),
            Chunk(
                chunk_id="ent_001",
                text="HelioX supports both dense and sparse retrieval methods.",
                metadata={"source": "entity"}
            ),
            Chunk(
                chunk_id="ent_002",
                text="Elasticsearch is used for keyword and entity search capabilities.",
                metadata={"source": "entity"}
            ),
            Chunk(
                chunk_id="ent_003",
                text="BM25 ranking function is applied for sparse retrieval optimization.",
                metadata={"source": "entity"}
            )
        ]

        texts = [chunk.text for chunk in sample_chunks]
        self.logger.info(f"Generating embeddings for {len(texts)} sample chunks")
        embeddings = embedder.embed_batch(texts)
        vector_store.upsert(sample_chunks, embeddings)
        self.logger.info(f"Populated vector store with {len(sample_chunks)} chunks")

    def _keyword_score(self, text: str, kw_lower_set: set[str], ent_lower_set: set[str]) -> float:
        """
        Score a chunk by keyword/entity overlap using Jaccard similarity.
        """
        if not kw_lower_set and not ent_lower_set:
            return 0.0

        clean_text = text.lower().replace(".", " ").replace(",", " ")
        text_words = set(clean_text.split())

        # Jaccard for keywords
        jaccard_kw = 0.0
        if kw_lower_set:
            intersection_kw = kw_lower_set.intersection(text_words)
            union_kw = kw_lower_set.union(text_words)
            jaccard_kw = len(intersection_kw) / len(union_kw) if union_kw else 0.0

        # Jaccard for entities
        jaccard_ent = 0.0
        if ent_lower_set:
            intersection_ent = ent_lower_set.intersection(text_words)
            union_ent = ent_lower_set.union(text_words)
            jaccard_ent = len(intersection_ent) / len(union_ent) if union_ent else 0.0

        return 0.6 * jaccard_kw + 0.4 * jaccard_ent

    def retrieve(
        self,
        query: StructuredQuery,
        top_k: int = 50
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Retrieve relevant chunks for the query.

        Steps:
            1. Embed the raw query text
            2. Search vector database using the embedding
            3. Search Elasticsearch for keyword matches
            4. Compute entity scores via keyword/entity matching
            5. Merge and rank results

        Args:
            query: StructuredQuery with raw_query, keywords, and entities
            top_k: Number of top results to return from each search

        Returns:
            Tuple of (entity_hits, vector_hits), each as list of dicts with:
                - chunk_id: unique identifier
                - score: similarity score (0-1)
                - text: chunk content
                - payload: additional metadata
        """
        self.logger.info(f"Retrieving for query: {query.raw_query[:50]}...")
        self.logger.info(f"Extracted keywords: {query.keywords}")
        self.logger.info(f"Extracted entities: {query.entities}")

        import hashlib
        import json
        client = None
        cache_key = None
        vector_hits = None
        elastic_hits = None

        try:
            from core.cache.redis_client import get_redis_client
            client = get_redis_client()
            if client:
                query_hash = hashlib.sha256(query.raw_query.lower().strip().encode('utf-8')).hexdigest()
                cache_key = f"retrieval:{query_hash}"
                cached = client.get(cache_key)
                if cached:
                    vector_hits = json.loads(cached)
                    self.logger.info("Found vector hits in Redis cache.")
        except Exception as e:
            # Fallback gracefully
            pass

        # Step 1: Embed the query
        self.logger.info("Generating query embedding")
        query_embedding = self.embedder.embed(query.raw_query)
        self.logger.info(f"Generated embedding of dimension {len(query_embedding)}")

        # Step 2: Vector search (with caching)
        if vector_hits is None:
            self.logger.info(f"Searching vector store (top_k={top_k})")
            vector_hits = self.vector_store.search(query_embedding, top_k=top_k)
            self.logger.info(f"Retrieved {len(vector_hits)} vector hits")

            # Cache the retrieval results to bypass Qdrant and Embedder on duplicates
            try:
                if client and cache_key:
                    # We serialize the full hits (including payloads) to not break ranking logic downstream
                    # adhering strictly to storing the base dict structure {"chunk_id":..., "text":..., "score":...} + metadata
                    client.setex(cache_key, 300, json.dumps(vector_hits))
            except Exception as e:
                pass
        else:
            self.logger.info("Using cached vector hits")

        # Step 3: Keyword search using Elasticsearch
        if self.elastic_store is not None:
            self.logger.info(f"Searching Elasticsearch for keywords (top_k={top_k})")
            # Use the raw query for keyword search
            elastic_hits = self.elastic_store.search_keywords(query.raw_query, top_k=top_k)
            self.logger.info(f"Retrieved {len(elastic_hits)} Elasticsearch hits")
        else:
            elastic_hits = []
            self.logger.info("Elasticsearch unavailable; skipping BM25 keyword search")

        # Step 4: Entity scoring based on algorithm optimized O(1) sets
        keywords_to_use = query.expanded_keywords if query.expanded_keywords else query.keywords
        kw_lower_set = {k.lower() for k in keywords_to_use}
        ent_lower_set = {e.lower() for e in query.entities}

        # Determine weights for hybrid scoring
        # If no keywords and no entities, rely solely on vector search
        has_keywords = bool(keywords_to_use)
        has_entities = bool(ent_lower_set)
        if not has_keywords and not has_entities:
            vector_weight = 1.0
            entity_weight = 0.0
        else:
            vector_weight = 0.7
            entity_weight = 0.3

        entity_hits = []
        for hit in vector_hits:
            vector_score = hit.get('score', 0.0)
            entity_score = self._keyword_score(hit['text'], kw_lower_set, ent_lower_set)

            # Hybrid search fusion: weighted combination
            final_score = vector_weight * vector_score + entity_weight * entity_score
            entity_hits.append({**hit, 'score': final_score})

        # Sort descending so the highest scoring hybrid chunks bubble up
        entity_hits.sort(key=lambda x: x['score'], reverse=True)

        self.logger.info(f"Computed entity scores for {len(entity_hits)} hits")

        # Step 5: Merge and rank results using the existing merge_rank function
        # Note: We return the merged results as the first element, and keep vector_hits as second for compatibility
        merged_results = merge_rank(
            entity_hits=entity_hits,
            vector_hits=vector_hits,
            elastic_hits=elastic_hits  # We'll need to modify merge_rank to accept this
        )

        return merged_results, vector_hits


# Singleton accessor for convenience
_retriever_instance = None


def get_retriever() -> Retriever:
    """
    Get default retriever instance (singleton).

    Returns:
        Shared Retriever instance
    """
    global _retriever_instance
    if _retriever_instance is None:
        _retriever_instance = Retriever()
    return _retriever_instance
