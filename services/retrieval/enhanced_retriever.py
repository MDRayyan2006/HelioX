"""
Enhanced Retriever: Improved context retrieval with semantic understanding,
adaptive hybrid scoring, and intent-aware processing.
"""

from typing import List, Dict, Any, Tuple, Optional
from models.schemas.query import StructuredQuery
from services.embedding.embedder import Embedder, get_embedder
from services.vectorstore.qdrant_client import VectorStore
from core.logger import get_logger
from services.retrieval.enhanced_analyzer import analyze_query_enhanced
import hashlib
import json


class EnhancedRetriever:
    """
    Enhanced retriever that improves context retrieval through:
    1. Semantic query understanding with enhanced analyzer
    2. Adaptive hybrid scoring based on query intent
    3. Contextual expansion and reranking
    4. Improved caching strategy
    """

    def __init__(
        self,
        embedder: Embedder = None,
        vector_store: VectorStore = None,
        elastic_store: Any = None  # Optional ElasticStore for BM25 retrieval
    ):
        """
        Initialize enhanced retriever with dependencies.

        Args:
            embedder: Embedder instance (uses singleton if None)
            vector_store: VectorStore instance (creates and initializes if None)
            elastic_store: ElasticStore instance (creates and initializes if None)
        """
        from core.config import get_config

        self.embedder = embedder or get_embedder()
        self.logger = get_logger("ENHANCED_RETRIEVER")

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
            # Only recreate collection if using local memory (testing)
            # For remote, preserve existing data unless collection doesn't exist
            recreate = config.qdrant_url is None or config.qdrant_url == "http://localhost:6333"
            # Use force_recreate to auto-fix dimension mismatches in local mode
            force = recreate
            self.vector_store.init_collection(recreate=recreate, force_recreate=force)
            self._populate_sample_data(self.vector_store)

        # Initialize Elasticsearch store for BM25 retrieval
        if elastic_store is not None:
            self.elastic_store = elastic_store
        else:
            self.logger.info("Initializing Elasticsearch store")
            config = get_config()
            # Use config's Elasticsearch host and port if available
            host = getattr(config, 'elastic_host', 'localhost')
            port = getattr(config, 'elastic_port', 9200)
            from services.retrieval.elastic_client import ElasticStore
            self.elastic_store = ElasticStore(host=host, port=port)
            # Populate with sample data for consistency
            self.elastic_store._populate_sample_data()

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

    def _keyword_score_jaccard(self, text: str, kw_lower_set: set[str], ent_lower_set: set[str]) -> float:
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

    def _compute_adaptive_weights(self, query: StructuredQuery) -> Tuple[float, float, float]:
        """
        Compute adaptive weights for vector, entity, and keyword components
        based on query intent and characteristics.

        Returns:
            Tuple of (vector_weight, entity_weight, keyword_weight)
        """
        # Default weights
        vector_weight = 0.6
        entity_weight = 0.3
        keyword_weight = 0.1

        # Adjust based on intent if available
        if hasattr(query, 'constraints') and query.constraints:
            intent_weights = query.constraints.get('intent_weights')
            if intent_weights:
                vector_weight = intent_weights.get('vector', vector_weight)
                entity_weight = intent_weights.get('entity', entity_weight)
                keyword_weight = intent_weights.get('keyword', keyword_weight)

        # Further adjust based on query characteristics
        query_length = getattr(query, 'constraints', {}).get('query_length', 0) if hasattr(query, 'constraints') else 0

        # For very short queries, rely more on vector search
        if query_length < 3:
            vector_weight = min(0.8, vector_weight + 0.1)
            entity_weight = max(0.1, entity_weight - 0.05)
            keyword_weight = max(0.0, keyword_weight - 0.05)
        # For very long queries, boost entity and keyword matching
        elif query_length > 10:
            vector_weight = max(0.5, vector_weight - 0.1)
            entity_weight = min(0.4, entity_weight + 0.05)
            keyword_weight = min(0.2, keyword_weight + 0.05)

        # Normalize weights to sum to 1.0
        total = vector_weight + entity_weight + keyword_weight
        if total > 0:
            vector_weight /= total
            entity_weight /= total
            keyword_weight /= total

        return vector_weight, entity_weight, keyword_weight

    def retrieve(
        self,
        query: StructuredQuery,
        top_k: int = 50,
        vector_only: bool = False
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Retrieve relevant chunks for the query with enhanced processing.

        Steps:
            1. (Optional) Enhance query with semantic understanding if not already enhanced
            2. Embed the query text
            3. Search vector database using the embedding
            4. Search Elasticsearch for BM25 keyword matches
            5. Compute adaptive hybrid scoring based on query intent using normalized scores
            6. Merge and rerank all sources (vector, entity, elastic, metadata)

        Args:
            query: StructuredQuery with raw_query, keywords, and entities
            top_k: Number of top results to return from each search

        Returns:
            Tuple of (merged_results, vector_hits), where merged_results is a list of dicts with:
                - chunk_id, text, final_score, vector_score, entity_score, elastic_score, metadata_score
        """
        self.logger.info(f"Retrieving for query: {query.raw_query[:50]}...")
        self.logger.info(f"Extracted keywords: {getattr(query, 'keywords', [])}")
        self.logger.info(f"Extracted entities: {getattr(query, 'entities', [])}")

        # Check if query needs enhancement (backward compatibility)
        enhanced_query = query
        if not hasattr(query, 'constraints') or not query.constraints:
            self.logger.info("Enhancing query with semantic understanding")
            enhanced_query = analyze_query_enhanced(query.raw_query)

        import hashlib
        import json
        from core.cache.redis_client import get_redis_client

        # Build cache key
        client = None
        cache_key = None
        vector_hits = None
        elastic_hits = None
        try:
            client = get_redis_client()
            if client:
                query_hash = hashlib.sha256(enhanced_query.raw_query.lower().strip().encode('utf-8')).hexdigest()
                cache_key = f"enhanced_retrieval:{query_hash}"
                cached = client.get(cache_key)
                if cached:
                    cached_data = json.loads(cached)
                    vector_hits = cached_data.get('vector_hits')
                    elastic_hits = cached_data.get('elastic_hits')
                    if vector_hits is not None and elastic_hits is not None:
                        self.logger.info("Found cached vector and elastic hits.")
        except Exception as e:
            self.logger.debug(f"Cache lookup failed: {e}")
            vector_hits = None
            elastic_hits = None

        # Step 1: Embed the query
        if vector_hits is None:
            self.logger.info("Generating query embedding")
            query_embedding = self.embedder.embed(enhanced_query.raw_query)
            self.logger.info(f"Generated embedding of dimension {len(query_embedding)}")

            # Step 2: Vector search
            self.logger.info(f"Searching vector store (top_k={top_k})")
            vector_hits = self.vector_store.search(query_embedding, top_k=top_k)
            self.logger.info(f"Retrieved {len(vector_hits)} vector hits")

        if vector_only:
            self.logger.info(f"Vector only mode active. Returning {len(vector_hits)} vector hits directly.")
            formatted_hits = []
            for hit in vector_hits:
                formatted_hit = hit.copy()
                formatted_hit['final_score'] = hit.get('score', 0.0)
                formatted_hits.append(formatted_hit)
            return formatted_hits, vector_hits

        # Step 3: Elasticsearch BM25 keyword search
        if elastic_hits is None:
            self.logger.info(f"Searching Elasticsearch for keywords (top_k={top_k})")
            elastic_hits = self.elastic_store.search_keywords(enhanced_query.raw_query, top_k=top_k)
            self.logger.info(f"Retrieved {len(elastic_hits)} Elasticsearch hits")

        # Cache the hits if possible
        try:
            if client and cache_key:
                client.setex(cache_key, 300, json.dumps({
                    'vector_hits': vector_hits,
                    'elastic_hits': elastic_hits
                }))
        except Exception as e:
            self.logger.debug(f"Cache storage failed: {e}")

        # Step 4: Prepare keyword/entity sets for entity scoring
        keywords_to_use = getattr(enhanced_query, 'expanded_keywords', getattr(enhanced_query, 'keywords', []))
        entities_to_use = getattr(enhanced_query, 'entities', [])
        kw_lower_set = {k.lower() for k in keywords_to_use}
        ent_lower_set = {e.lower() for e in entities_to_use}

        # Compute adaptive weights based on query intent
        vector_weight, entity_weight, keyword_weight = self._compute_adaptive_weights(enhanced_query)
        # For BM25 (Elasticsearch), we'll use the keyword_weight as starting point
        elastic_weight = keyword_weight
        # Metadata weight is fixed small portion
        metadata_weight = 0.1

        # Dynamic adjustment: if query is keyword-rich, boost elastic (BM25) weight
        query_word_count = len(enhanced_query.raw_query.split())
        if query_word_count > 0:
            keyword_density = len(keywords_to_use) / query_word_count
            if keyword_density > 0.3:  # query has many keywords
                boost = min(0.2, (keyword_density - 0.3) * 0.5)
                elastic_weight = min(0.4, elastic_weight + boost)
                self.logger.info(f"Keyword density {keyword_density:.2f} boosted elastic weight to {elastic_weight:.2f}")

        # Re-normalize to account for metadata and ensure sum = 1.0
        total_sparse = entity_weight + elastic_weight + metadata_weight
        if total_sparse > 1.0:
            scale = 1.0 / total_sparse
            entity_weight *= scale
            elastic_weight *= scale
            metadata_weight *= scale
        # Ensure total weights sum to 1 (vector is the remainder)
        total = vector_weight + entity_weight + elastic_weight + metadata_weight
        if abs(total - 1.0) > 1e-6:
            vector_weight = 1.0 - (entity_weight + elastic_weight + metadata_weight)

        self.logger.info(f"Adaptive weights - Vector: {vector_weight:.2f}, Entity: {entity_weight:.2f}, Elastic: {elastic_weight:.2f}, Metadata: {metadata_weight:.2f}")

        # Step 5: Normalize scores from each source using min-max normalization
        def normalize_scores(hits: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
            if not hits:
                return []
            scores = [hit.get('score', 0.0) for hit in hits]
            min_s = min(scores)
            max_s = max(scores)
            range_s = max_s - min_s if max_s > min_s else 1.0
            normalized = []
            for hit in hits:
                norm_score = (hit['score'] - min_s) / range_s
                hit_copy = hit.copy()
                hit_copy['norm_score'] = norm_score
                normalized.append(hit_copy)
            return normalized

        norm_vector = normalize_scores(vector_hits)
        norm_elastic = normalize_scores(elastic_hits)

        # Step 6: Compute entity scores for all hits (both vector and elastic)
        # We'll create unified hit dicts with all source scores
        unified_hits = {}  # chunk_id -> hit dict

        for hit in norm_vector:
            chunk_id = hit['chunk_id']
            # Compute entity score (Jaccard) for this chunk
            entity_score = self._keyword_score_jaccard(hit['text'], kw_lower_set, ent_lower_set)
            unified_hits[chunk_id] = {
                'chunk_id': chunk_id,
                'text': hit['text'],
                'payload': hit.get('payload', {}),
                'vector_score': hit['norm_score'],
                'entity_score': entity_score,
                'elastic_score': 0.0,  # Not from elastic
                'metadata_score': 0.0  # Will compute later
            }

        for hit in norm_elastic:
            chunk_id = hit['chunk_id']
            # Compute entity score for this elastic hit as well
            entity_score = self._keyword_score_jaccard(hit['text'], kw_lower_set, ent_lower_set)
            if chunk_id in unified_hits:
                # Already exists from vector; add elastic score and update entity if needed? Keep original entity
                unified_hits[chunk_id]['elastic_score'] = hit['norm_score']
            else:
                unified_hits[chunk_id] = {
                    'chunk_id': chunk_id,
                    'text': hit['text'],
                    'payload': {},  # Elastic hits may not have payload
                    'vector_score': 0.0,  # Not from vector
                    'entity_score': entity_score,
                    'elastic_score': hit['norm_score'],
                    'metadata_score': 0.0
                }

        # Step 7: Compute metadata scores for all unified hits
        # Use the same metadata scoring as in ranker.py for consistency
        from services.retrieval.ranker import _compute_metadata_score as ranker_metadata_score
        for hit in unified_hits.values():
            hit['metadata_score'] = ranker_metadata_score(hit)

        # Step 8: Compute final scores using adaptive weights
        merged_results = []
        for hit in unified_hits.values():
            vs = hit['vector_score']
            es = hit['entity_score']
            els = hit['elastic_score']
            ms = hit['metadata_score']

            final_score = (
                vector_weight * vs +
                entity_weight * es +
                elastic_weight * els +
                metadata_weight * ms
            )

            merged_results.append({
                'chunk_id': hit['chunk_id'],
                'text': hit['text'],
                'score': round(final_score, 4),  # Add score for downstream merge_rank compatibility
                'final_score': round(final_score, 4),
                'vector_score': round(vs, 4),
                'entity_score': round(es, 4),
                'elastic_score': round(els, 4),
                'metadata_score': round(ms, 4),
                'payload': hit['payload']
            })

        # Sort by final_score descending
        merged_results.sort(key=lambda x: x['final_score'], reverse=True)

        # Coverage gap handling is now done at the pipeline level via sufficiency_check.py
        # This avoids recursive re-retrieval that doubles latency.
        # Log coverage info for debugging but don't re-retrieve here.
        if self._check_coverage_gap(merged_results, keywords_to_use, entities_to_use, 0.4):
            self.logger.info("Coverage gap detected — will be handled by pipeline sufficiency check")

        self.logger.info(f"Returning {len(merged_results)} merged results")

        # Return merged results as first element, vector_hits as second for compatibility
        return merged_results, vector_hits

    def _check_coverage_gap(
        self,
        results: List[Dict[str, Any]],
        keywords: List[str],
        entities: List[str],
        threshold: float = 0.4
    ) -> bool:
        """
        Check if retrieved results cover enough of the query terms.
        Returns True if coverage gap exists (needs expansion).
        """
        if not results:
            return True

        texts_lower = [r['text'].lower() for r in results[:20]]  # check top 20
        kw_covered = sum(1 for kw in keywords if any(kw.lower() in txt for txt in texts_lower))
        kw_coverage = kw_covered / max(len(keywords), 1) if keywords else 1.0

        ent_covered = sum(1 for ent in entities if any(ent.lower() in txt for txt in texts_lower))
        ent_coverage = ent_covered / max(len(entities), 1) if entities else 1.0

        avg_coverage = (kw_coverage + ent_coverage) / 2
        self.logger.debug(f"Coverage check: keywords={kw_coverage:.2f}, entities={ent_coverage:.2f}, avg={avg_coverage:.2f}")
        return avg_coverage < threshold

    def _merge_uniq_results(
        self,
        original: List[Dict[str, Any]],
        new: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Merge two result lists, deduplicating by chunk_id and keeping highest final_score.
        """
        combined = original + new
        best_by_chunk: Dict[str, Dict[str, Any]] = {}
        for hit in combined:
            cid = hit['chunk_id']
            score = hit.get('final_score', 0.0)
            if cid not in best_by_chunk or score > best_by_chunk[cid].get('final_score', 0.0):
                best_by_chunk[cid] = hit
        merged = list(best_by_chunk.values())
        merged.sort(key=lambda x: x.get('final_score', 0.0), reverse=True)
        return merged


# Singleton accessor for convenience
_retriever_instance = None


def get_enhanced_retriever() -> EnhancedRetriever:
    """
    Get default enhanced retriever instance (singleton).

    Returns:
        Shared EnhancedRetriever instance
    """
    global _retriever_instance
    if _retriever_instance is None:
        _retriever_instance = EnhancedRetriever()
    return _retriever_instance