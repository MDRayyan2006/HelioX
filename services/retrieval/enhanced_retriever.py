"""
Enhanced Retriever: Improved context retrieval with semantic understanding,
adaptive hybrid scoring, and intent-aware processing.
"""

from typing import List, Dict, Any, Tuple, Optional, Set
import re
from concurrent.futures import ThreadPoolExecutor
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
            # Never recreate automatically in runtime paths. Recreate can wipe uploaded docs.
            self.vector_store.init_collection(recreate=False, force_recreate=False)

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
            try:
                self.elastic_store = ElasticStore(host=host, port=port)
            except Exception as e:
                self.logger.warning(f"Elasticsearch unavailable; continuing with dense retrieval only: {e}")
                self.elastic_store = None

    def _extract_lexical_signals(
        self,
        raw_query: str,
        keywords: List[str],
        entities: List[str]
    ) -> Tuple[Set[str], List[str], Set[str]]:
        """
        Extract deterministic lexical signals for exact-match boosting.

        Returns:
            (required_terms, phrase_candidates, numeric_terms)
        """
        required_terms: Set[str] = set()

        for term in keywords + entities:
            term_l = term.lower().strip()
            if not term_l:
                continue
            if term_l.isdigit() or len(term_l) >= 3:
                required_terms.add(term_l)
            parts = re.findall(r"[a-z]+|\d+", term_l)
            if len(parts) > 1:
                for part in parts:
                    if part.isdigit() or len(part) >= 3:
                        required_terms.add(part)

        if not required_terms:
            query_terms = re.findall(r"\w+", raw_query.lower())
            for term in query_terms:
                if term.isdigit() or len(term) >= 4:
                    required_terms.add(term)
                parts = re.findall(r"[a-z]+|\d+", term)
                if len(parts) > 1:
                    for part in parts:
                        if part.isdigit() or len(part) >= 3:
                            required_terms.add(part)

        tokens: List[str] = []
        for token in re.findall(r"\w+", raw_query.lower()):
            tokens.append(token)
            parts = re.findall(r"[a-z]+|\d+", token)
            if len(parts) > 1:
                tokens.extend(parts)

        tokens = [t for t in tokens if t.isdigit() or len(t) >= 3]
        phrase_candidates: List[str] = []
        for n in (3, 2):
            for i in range(0, max(0, len(tokens) - n + 1)):
                phrase = " ".join(tokens[i:i + n]).strip()
                if phrase and len(phrase) >= 6:
                    phrase_candidates.append(phrase)

        numeric_terms = {t for t in required_terms if t.isdigit()}
        return required_terms, phrase_candidates, numeric_terms

    def _compute_lexical_score(
        self,
        text: str,
        required_terms: Set[str],
        phrase_candidates: List[str],
        numeric_terms: Set[str]
    ) -> float:
        """
        Compute lexical relevance for exact-term and phrase anchoring.
        """
        if not text:
            return 0.0

        text_lower = text.lower()
        raw_terms = re.findall(r"\w+", text_lower)
        text_terms = set(raw_terms)

        # Expand mixed alpha-numeric tokens (e.g., "observation2" -> "observation", "2")
        for token in raw_terms:
            parts = re.findall(r"[a-z]+|\d+", token)
            if len(parts) > 1:
                text_terms.update(parts)

        compact_text = re.sub(r"[^a-z0-9]+", "", text_lower)

        if required_terms:
            matched = required_terms.intersection(text_terms)
            coverage = len(matched) / len(required_terms)
        else:
            coverage = 0.0

        phrase_hit = 0.0
        if phrase_candidates:
            hits = 0
            for p in phrase_candidates:
                if p in text_lower:
                    hits += 1
                    continue
                compact_phrase = re.sub(r"[^a-z0-9]+", "", p)
                if compact_phrase and compact_phrase in compact_text:
                    hits += 1
            phrase_hit = min(1.0, hits / max(1, min(len(phrase_candidates), 3)))

        numeric_score = 0.0
        if numeric_terms:
            matched_numeric = numeric_terms.intersection(text_terms)
            numeric_score = len(matched_numeric) / len(numeric_terms)

        lexical = 0.6 * coverage + 0.25 * phrase_hit + 0.15 * numeric_score
        return max(0.0, min(1.0, lexical))

    def _is_anchor_query(self, raw_query: str) -> bool:
        """Detect reference-style queries that need strict exact retrieval."""
        q = raw_query.lower()
        return bool(
            re.search(
                r"\b(?:observation|section|table|figure|appendix|clause|item|point)\s*[-:#]?\s*\d+\b",
                q,
            )
        )

    def _should_bias_recent_source(self, raw_query: str) -> bool:
        """Return True when query likely targets the currently uploaded document."""
        q = raw_query.lower()
        if self._is_anchor_query(raw_query):
            return True
        triggers = (
            "provided pdf",
            "this pdf",
            "uploaded pdf",
            "in the pdf",
            "this document",
            "provided document",
            "the document",
        )
        return any(t in q for t in triggers)

    def _get_preferred_source(self, raw_query: str) -> Optional[str]:
        """Get last ingested source when the query context suggests source affinity."""
        if not self._should_bias_recent_source(raw_query):
            return None
        try:
            from core.cache.cache_service import get_last_ingested_source
            source = get_last_ingested_source()
            return source.strip() if source else None
        except Exception:
            return None

    def _extract_source_hints(self, query: StructuredQuery) -> List[str]:
        """Extract source hints from query constraints, preserving order and uniqueness."""
        constraints = getattr(query, "constraints", {}) or {}
        hints: List[str] = []

        direct_hint = constraints.get("source_hint")
        if direct_hint:
            hint_clean = str(direct_hint).strip()
            if hint_clean:
                hints.append(hint_clean)

        list_hints = constraints.get("source_hints")
        if isinstance(list_hints, list):
            for item in list_hints:
                if not item:
                    continue
                hint_clean = str(item).strip()
                if hint_clean and hint_clean not in hints:
                    hints.append(hint_clean)

        return hints

    def _build_query_variants(self, raw_query: str) -> List[str]:
        """Build lexical query variants for robust BM25 matching."""
        variants: List[str] = []
        base = (raw_query or "").strip()
        if base:
            variants.append(base)

        split_alpha_num = re.sub(r"([A-Za-z])(\d)", r"\1 \2", base)
        split_alpha_num = re.sub(r"(\d)([A-Za-z])", r"\1 \2", split_alpha_num)
        if split_alpha_num and split_alpha_num != base:
            variants.append(split_alpha_num)

        q_lower = base.lower()
        obs_match = re.search(r"\bobservation\s*[-:]?\s*(\d+)\b", q_lower)
        if not obs_match:
            obs_match = re.search(r"\bobservation(\d+)\b", q_lower)
        if obs_match:
            n = obs_match.group(1)
            variants.extend([
                f"observation {n}",
                f"observation-{n}",
                f"observation:{n}",
                f"observation{n}",
            ])

        seen = set()
        deduped: List[str] = []
        for item in variants:
            key = item.lower().strip()
            if not key or key in seen:
                continue
            seen.add(key)
            deduped.append(item)
        return deduped

    def _fuse_hits_rrf(
        self,
        hit_lists: List[List[Dict[str, Any]]],
        top_k: int,
        k_constant: int = 60,
    ) -> List[Dict[str, Any]]:
        """Fuse multiple ranked hit lists using Reciprocal Rank Fusion."""
        fused: Dict[str, Dict[str, Any]] = {}

        for hits in hit_lists:
            ranked = sorted(hits or [], key=lambda h: float(h.get("score", 0.0)), reverse=True)
            for rank, hit in enumerate(ranked, start=1):
                chunk_id = hit.get("chunk_id")
                if not chunk_id:
                    continue
                entry = fused.setdefault(chunk_id, {
                    "chunk_id": chunk_id,
                    "text": hit.get("text", ""),
                    "payload": hit.get("payload", hit.get("metadata", {})),
                    "metadata": hit.get("metadata", hit.get("payload", {})),
                    "rrf": 0.0,
                    "raw_score": float(hit.get("score", 0.0)),
                })
                entry["rrf"] += 1.0 / (k_constant + rank)
                entry["raw_score"] = max(entry["raw_score"], float(hit.get("score", 0.0)))
                if not entry.get("text") and hit.get("text"):
                    entry["text"] = hit.get("text")
                if not entry.get("metadata"):
                    entry["metadata"] = hit.get("metadata", hit.get("payload", {}))

        if not fused:
            return []

        max_rrf = max(v["rrf"] for v in fused.values()) or 1.0
        merged: List[Dict[str, Any]] = []
        for entry in fused.values():
            out = {
                "chunk_id": entry["chunk_id"],
                "text": entry.get("text", ""),
                "payload": entry.get("payload", {}),
                "metadata": entry.get("metadata", {}),
                "score": entry["rrf"] / max_rrf,
            }
            merged.append(out)

        merged.sort(key=lambda h: h.get("score", 0.0), reverse=True)
        return merged[:top_k]

    def _search_source_lexical(
        self,
        source: str,
        required_terms: Set[str],
        phrase_candidates: List[str],
        numeric_terms: Set[str],
        top_k: int,
    ) -> List[Dict[str, Any]]:
        """Run deterministic lexical retrieval over chunks from one source."""
        if not source:
            return []

        try:
            candidates = self.vector_store.get_chunks_by_source(source, limit=max(300, top_k * 40))
        except Exception as e:
            self.logger.debug(f"Source lexical scan unavailable for '{source}': {e}")
            return []

        scored: List[Dict[str, Any]] = []
        for hit in candidates:
            text = hit.get("text", "")
            score = self._compute_lexical_score(text, required_terms, phrase_candidates, numeric_terms)
            if score <= 0.0:
                continue
            payload = hit.get("payload", {})
            scored.append({
                "chunk_id": hit.get("chunk_id"),
                "text": text,
                "payload": payload,
                "metadata": dict(payload),
                "score": score,
            })

        scored.sort(key=lambda h: h.get("score", 0.0), reverse=True)
        return scored[:top_k]

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
        top_k: int = 50
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

        keywords_to_use = getattr(enhanced_query, 'expanded_keywords', getattr(enhanced_query, 'keywords', []))
        entities_to_use = getattr(enhanced_query, 'entities', [])
        kw_lower_set = {k.lower() for k in keywords_to_use}
        ent_lower_set = {e.lower() for e in entities_to_use}

        required_terms, phrase_candidates, numeric_terms = self._extract_lexical_signals(
            enhanced_query.raw_query,
            list(keywords_to_use),
            list(entities_to_use),
        )

        anchor_query = self._is_anchor_query(enhanced_query.raw_query)
        preferred_sources = self._extract_source_hints(enhanced_query)
        if not preferred_sources:
            fallback_source = self._get_preferred_source(enhanced_query.raw_query)
            if fallback_source:
                preferred_sources = [fallback_source]
        preferred_source = preferred_sources[0] if preferred_sources else None
        query_variants = self._build_query_variants(enhanced_query.raw_query)

        from core.cache.redis_client import get_redis_client

        # Build cache key
        client = None
        cache_key = None
        vector_hits = None
        elastic_hits = None
        try:
            client = get_redis_client()
            if client:
                from core.cache.cache_service import get_corpus_version
                query_hash = hashlib.sha256(enhanced_query.raw_query.lower().strip().encode('utf-8')).hexdigest()
                corpus_version = get_corpus_version()
                source_key = "|".join(sorted(s.lower().strip() for s in preferred_sources)) or "none"
                source_hash = hashlib.sha1(source_key.encode('utf-8')).hexdigest()[:10]
                cache_key = f"enhanced_retrieval:v{corpus_version}:{query_hash}:k{top_k}:s{source_hash}"
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

        # Step 1-3: Run dense+BM25 retrieval concurrently when cache miss
        def _run_vector_search() -> List[Dict[str, Any]]:
            self.logger.info("Generating query embedding")
            query_embedding = self.embedder.embed(enhanced_query.raw_query)
            self.logger.info(f"Generated embedding of dimension {len(query_embedding)}")
            self.logger.info(f"Searching vector store (top_k={top_k})")
            return self.vector_store.search(
                query_embedding,
                top_k=top_k,
                source_hints=preferred_sources if preferred_sources else None,
            )

        def _run_elastic_search() -> List[Dict[str, Any]]:
            if not self.elastic_store:
                return []
            lexical_lists: List[List[Dict[str, Any]]] = []
            for variant in query_variants[:4]:
                self.logger.info(f"Searching Elasticsearch for keywords variant: {variant[:60]}...")
                hits = self.elastic_store.search_keywords(
                    variant,
                    top_k=top_k,
                    source_hints=preferred_sources if preferred_sources else None,
                )
                if hits:
                    lexical_lists.append(hits)
            return self._fuse_hits_rrf(lexical_lists, top_k=max(top_k, min(120, top_k * 2)))

        vector_future = None
        elastic_future = None
        with ThreadPoolExecutor(max_workers=2) as executor:
            if vector_hits is None:
                vector_future = executor.submit(_run_vector_search)
            if elastic_hits is None:
                elastic_future = executor.submit(_run_elastic_search)

            if vector_future is not None:
                try:
                    vector_hits = vector_future.result()
                    self.logger.info(f"Retrieved {len(vector_hits)} vector hits")
                except Exception as e:
                    self.logger.warning(f"Vector retrieval failed: {e}")
                    vector_hits = []

            if elastic_future is not None:
                try:
                    elastic_hits = elastic_future.result()
                    self.logger.info(f"Retrieved {len(elastic_hits)} Elasticsearch hits")
                except Exception as e:
                    self.logger.warning(f"Elasticsearch retrieval failed: {e}")
                    elastic_hits = []

        vector_hits = vector_hits or []
        elastic_hits = elastic_hits or []

        # Source-anchored lexical fallback improves exact references like "Observation 2".
        if preferred_sources and (anchor_query or not elastic_hits):
            source_hit_lists: List[List[Dict[str, Any]]] = []
            for source_name in preferred_sources[:3]:
                source_hits = self._search_source_lexical(
                    source_name,
                    required_terms,
                    phrase_candidates,
                    numeric_terms,
                    top_k=max(20, top_k),
                )
                if source_hits:
                    self.logger.info(
                        f"Source lexical fallback added {len(source_hits)} hits from '{source_name}'"
                    )
                    source_hit_lists.append(source_hits)

            if source_hit_lists:
                elastic_hits = self._fuse_hits_rrf(
                    [elastic_hits] + source_hit_lists,
                    top_k=max(top_k, min(150, top_k * 2)),
                )

        # Cache the hits if possible
        try:
            if client and cache_key:
                client.setex(cache_key, 300, json.dumps({
                    'vector_hits': vector_hits,
                    'elastic_hits': elastic_hits
                }))
        except Exception as e:
            self.logger.debug(f"Cache storage failed: {e}")

        # Compute adaptive weights based on query intent
        vector_weight, entity_weight, keyword_weight = self._compute_adaptive_weights(enhanced_query)
        # For BM25, we'll use the keyword_weight as the elastic weight
        elastic_weight = keyword_weight
        # Reserve score mass for metadata, lexical anchoring, source affinity and fusion.
        metadata_weight = 0.07
        lexical_weight = 0.22 if anchor_query else 0.16
        source_weight = 0.2 if preferred_sources else 0.0
        fusion_weight = 0.1
        core_budget = max(0.0, 1.0 - metadata_weight - lexical_weight - source_weight - fusion_weight)

        core_sum = vector_weight + entity_weight + elastic_weight
        if core_sum > 0:
            scale = core_budget / core_sum
            vector_weight *= scale
            entity_weight *= scale
            elastic_weight *= scale
        else:
            vector_weight = core_budget
            entity_weight = 0.0
            elastic_weight = 0.0

        self.logger.info(
            f"Adaptive weights - Vector: {vector_weight:.2f}, Entity: {entity_weight:.2f}, "
            f"Elastic: {elastic_weight:.2f}, Metadata: {metadata_weight:.2f}, "
            f"Lexical: {lexical_weight:.2f}, Source: {source_weight:.2f}, Fusion: {fusion_weight:.2f}"
        )

        # Step 5: Normalize scores from each source using min-max normalization
        def normalize_scores(hits: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
            if not hits:
                return []
            scores = [hit.get('score', 0.0) for hit in hits]
            min_s = min(scores)
            max_s = max(scores)
            range_s = max_s - min_s if max_s > min_s else None
            normalized = []
            for hit in hits:
                if range_s is None:
                    norm_score = 1.0
                else:
                    norm_score = (hit['score'] - min_s) / range_s
                hit_copy = hit.copy()
                hit_copy['norm_score'] = norm_score
                normalized.append(hit_copy)
            return normalized

        norm_vector = normalize_scores(vector_hits)
        norm_elastic = normalize_scores(elastic_hits)

        def build_rrf_map(hits: List[Dict[str, Any]]) -> Dict[str, float]:
            ranked = sorted(hits, key=lambda h: h.get('norm_score', 0.0), reverse=True)
            rrf_scores: Dict[str, float] = {}
            for rank, hit in enumerate(ranked, start=1):
                chunk_id = hit.get('chunk_id')
                if not chunk_id:
                    continue
                rrf_scores[chunk_id] = 1.0 / (50 + rank)
            if not rrf_scores:
                return {}
            max_rrf = max(rrf_scores.values())
            return {k: (v / max_rrf) for k, v in rrf_scores.items()}

        rrf_vector = build_rrf_map(norm_vector)
        rrf_elastic = build_rrf_map(norm_elastic)

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
                'metadata': dict(hit.get('payload', {})),
                'vector_score': hit['norm_score'],
                'entity_score': entity_score,
                'elastic_score': 0.0,  # Not from elastic
                'metadata_score': 0.0,  # Will compute later
                'lexical_score': 0.0,
                'source_score': 0.0,
                'fusion_score': rrf_vector.get(chunk_id, 0.0),
            }

        for hit in norm_elastic:
            chunk_id = hit['chunk_id']
            # Compute entity score for this elastic hit as well
            entity_score = self._keyword_score_jaccard(hit['text'], kw_lower_set, ent_lower_set)
            if chunk_id in unified_hits:
                # Already exists from vector; add elastic score and update entity if needed? Keep original entity
                unified_hits[chunk_id]['elastic_score'] = hit['norm_score']
                if not unified_hits[chunk_id].get('metadata'):
                    unified_hits[chunk_id]['metadata'] = hit.get('metadata', {})
            else:
                unified_hits[chunk_id] = {
                    'chunk_id': chunk_id,
                    'text': hit['text'],
                    'payload': hit.get('metadata', {}),
                    'metadata': hit.get('metadata', {}),
                    'vector_score': 0.0,  # Not from vector
                    'entity_score': entity_score,
                    'elastic_score': hit['norm_score'],
                    'metadata_score': 0.0,
                    'lexical_score': 0.0,
                    'source_score': 0.0,
                    'fusion_score': rrf_elastic.get(chunk_id, 0.0),
                }

            if chunk_id in unified_hits:
                unified_hits[chunk_id]['fusion_score'] = max(
                    unified_hits[chunk_id].get('fusion_score', 0.0),
                    rrf_vector.get(chunk_id, 0.0),
                    rrf_elastic.get(chunk_id, 0.0),
                )

        # Step 7: Compute metadata scores for all unified hits
        # Use the same metadata scoring as in ranker.py for consistency
        from services.retrieval.ranker import _compute_metadata_score as ranker_metadata_score
        for hit in unified_hits.values():
            hit['metadata_score'] = ranker_metadata_score(hit)
            hit['lexical_score'] = self._compute_lexical_score(
                hit.get('text', ''),
                required_terms,
                phrase_candidates,
                numeric_terms,
            )
            source_value = str((hit.get('metadata', {}) or {}).get('source', '')).strip().lower()
            preferred_values = [s.strip().lower() for s in preferred_sources if s and str(s).strip()]
            if preferred_values and source_value:
                score = 0.0
                for preferred_value in preferred_values:
                    if source_value == preferred_value:
                        score = max(score, 1.0)
                    elif preferred_value in source_value or source_value in preferred_value:
                        score = max(score, 0.85)
                hit['source_score'] = score
            else:
                hit['source_score'] = 0.0

        # Step 8: Compute final scores using adaptive weights
        merged_results = []
        for hit in unified_hits.values():
            vs = hit['vector_score']
            es = hit['entity_score']
            els = hit['elastic_score']
            ms = hit['metadata_score']
            ls = hit['lexical_score']
            ss = hit.get('source_score', 0.0)
            fs = hit.get('fusion_score', 0.0)

            final_score = (
                vector_weight * vs +
                entity_weight * es +
                elastic_weight * els +
                metadata_weight * ms +
                lexical_weight * ls +
                source_weight * ss +
                fusion_weight * fs
            )
            final_score = max(0.0, min(1.0, final_score))

            merged_results.append({
                'chunk_id': hit['chunk_id'],
                'text': hit['text'],
                'score': round(final_score, 4),  # Add score for downstream merge_rank compatibility
                'final_score': round(final_score, 4),
                'vector_score': round(vs, 4),
                'entity_score': round(es, 4),
                'elastic_score': round(els, 4),
                'metadata_score': round(ms, 4),
                'lexical_score': round(ls, 4),
                'source_score': round(ss, 4),
                'fusion_score': round(fs, 4),
                'metadata': hit.get('metadata', {}),
                'payload': hit['payload']
            })

        # Sort by final_score descending
        merged_results.sort(key=lambda x: x['final_score'], reverse=True)

        self.logger.info(f"Returning {len(merged_results)} merged results")

        # Return merged results as first element, vector_hits as second for compatibility
        return merged_results, vector_hits


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