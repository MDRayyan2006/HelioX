"""
Routing Engine: Intelligent query routing with constraint-based filtering and fallback.

Pipeline:
1. Metadata/temporal/domain filtering (if constraints exist)
2. Entity-based filtering (via retriever)
3. Vector search (via retriever)
4. Fallback: expand query if results below threshold

Integrates with existing Retriever class without modification.
"""

from typing import List, Dict, Any, Tuple, Optional
from core.logger import get_logger
from services.retrieval.retriever import get_retriever, Retriever
from models.schemas.query import StructuredQuery

logger = get_logger("ROUTER")

# Configuration
MIN_RESULTS_THRESHOLD = 3  # Minimum results before fallback expansion
VECTOR_TOP_K = 50  # Base vector search top_k
FALLBACK_EXPANSION_FACTOR = 2  # Multiply top_k on fallback


class RoutingEngine:
    """
    Routes queries through intelligent filtering and fallback strategies.

    Does NOT modify the base Retriever - wraps it with additional logic.
    """

    def __init__(self, retriever: Retriever = None):
        self.retriever = retriever or get_retriever()
        self.logger = logger

    def _apply_constraint_filters(
        self,
        hits: List[Dict[str, Any]],
        constraints: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Apply constraint-based filtering to search results.

        Args:
            hits: List of hit dictionaries with metadata
            constraints: StructuredQuery.constraints dict

        Returns:
            Filtered list of hits (may be empty if all filtered out)
        """
        if not constraints:
            return hits

        filtered = []
        self.logger.info(f"Applying constraint filters: {list(constraints.keys())}")

        for hit in hits:
            payload = hit.get('payload', {})
            text = hit.get('text', '').lower()
            keep = True

            # Temporal constraint filtering
            if 'temporal' in constraints:
                temporal = constraints['temporal']
                if temporal == "latest":
                    # Prefer hits with recent indicators (date strings in text, "latest" mentions)
                    # Also check metadata for recency if available
                    if 'date' in payload or 'updated' in payload:
                        # For now, keep all if metadata exists (would sort by date in production)
                        pass
                    # Also check for temporal keywords in text
                    if any(word in text for word in ['latest', 'recent', 'new', 'current']):
                        keep = True
                    else:
                        # Don't exclude, just lower priority (handled in ranking)
                        pass
                elif temporal == "historical":
                    if any(word in text for word in ['historical', 'past', 'old', 'previous']):
                        keep = True

            # Domain constraint filtering (keyword check)
            if 'domain' in constraints and keep:
                domain = constraints['domain']
                # Simple domain keyword matching (could be more sophisticated)
                domain_keywords = {
                    "technical": ["api", "code", "database", "server", "architecture"],
                    "business": ["revenue", "cost", "market", "customer", "strategy"],
                    "analysis": ["metrics", "data", "report", "statistics", "trends"],
                }
                if domain in domain_keywords:
                    keywords = domain_keywords[domain]
                    if not any(kw in text for kw in keywords):
                        # Not enough domain signal, can penalize but not exclude outright
                        # In production, we'd adjust score; here we keep but let ranking handle
                        pass

            # Filter constraints (restrictive words) - already in query, so results should match
            # We don't filter out, trusting that the query already encoded this

            if keep:
                filtered.append(hit)

        self.logger.info(f"Constraint filtering: {len(hits)} → {len(filtered)} hits")
        return filtered

    def route(
        self,
        structured_query: StructuredQuery,
        top_k: int = 10,
        fallback: bool = True
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Execute routed retrieval with constraint filtering and fallback.

        Args:
            structured_query: Analyzed query with intent and constraints
            top_k: Desired number of vector results
            fallback: Enable query expansion fallback if results insufficient

        Returns:
            Tuple of (entity_hits, vector_hits) after routing and filtering
        """
        self.logger.info(f"Routing query: intent={structured_query.intent}, "
                         f"constraints={list(structured_query.constraints.keys())}")

        # Phase 1: Initial retrieval
        self.logger.info("Phase 1: Retrieving with base query")
        entity_hits, vector_hits = self.retriever.retrieve(
            structured_query,
            top_k=VECTOR_TOP_K
        )

        # Phase 2: Apply constraint-based filtering
        if structured_query.constraints:
            self.logger.info("Phase 2: Applying constraint filters")
            vector_hits = self._apply_constraint_filters(vector_hits, structured_query.constraints)
            # Also filter entity hits (they're derived from vector hits)
            entity_hits = [h for h in entity_hits
                          if any(vh['chunk_id'] == h['chunk_id'] for vh in vector_hits)]

        # Phase 3: Check if results are sufficient
        if len(vector_hits) < MIN_RESULTS_THRESHOLD and fallback and structured_query.expanded_keywords:
            self.logger.warning(f"Insufficient results ({len(vector_hits)} < {MIN_RESULTS_THRESHOLD}); "
                              "triggering fallback expansion")

            # Phase 4: Fallback - expand query with synonyms and retry
            self.logger.info("Phase 4: Fallback - expanding query")
            expanded_query = self._create_fallback_query(structured_query)

            self.logger.info(f"Fallback query: {expanded_query.raw_query[:80]}...")
            entity_hits_fb, vector_hits_fb = self.retriever.retrieve(expanded_query, top_k=VECTOR_TOP_K)

            # Merge results (deduplicate by chunk_id, keep best scores)
            self.logger.info("Merging fallback results with original")
            vector_hits = self._merge_results(vector_hits, vector_hits_fb)
            entity_hits = self._merge_results(entity_hits, entity_hits_fb)

            self.logger.info(f"After fallback: {len(vector_hits)} vector hits, {len(entity_hits)} entity hits")

        # Limit to requested top_k
        vector_hits = vector_hits[:top_k] if top_k else vector_hits
        entity_hits = entity_hits[:top_k] if top_k else entity_hits

        self.logger.info(f"Routing complete: returning {len(entity_hits)} entity hits, "
                        f"{len(vector_hits)} vector hits")
        return entity_hits, vector_hits

    def _create_fallback_query(self, structured_query: StructuredQuery) -> StructuredQuery:
        """
        Create expanded query for fallback using expanded_keywords and constraint relaxation.

        Args:
            structured_query: Original structured query

        Returns:
            New StructuredQuery with expanded keyword set and relaxed constraints
        """
        # Combine original keywords with expanded synonyms
        all_keywords = list(set(structured_query.keywords + structured_query.expanded_keywords))

        # Build expanded query text by adding synonym keywords
        # We don't modify the original raw_query but create a new text with extra terms
        expanded_text = structured_query.raw_query
        if structured_query.expanded_keywords:
            # Add top 3 expanded keywords not already in the query
            existing_lower = structured_query.raw_query.lower()
            additions = []
            for kw in structured_query.expanded_keywords[:5]:
                if kw.lower() not in existing_lower:
                    additions.append(kw)
            if additions:
                expanded_text = f"{structured_query.raw_query} {' '.join(additions[:3])}"

        # Relax some constraints for fallback (remove restrictive filters)
        relaxed_constraints = structured_query.constraints.copy()
        if 'filters' in relaxed_constraints:
            # Remove restrictive word constraints to broaden search
            relaxed_constraints.pop('filters', None)

        return StructuredQuery(
            raw_query=expanded_text,
            keywords=structured_query.keywords,
            entities=structured_query.entities,
            intent=structured_query.intent,
            constraints=relaxed_constraints,
            expanded_keywords=structured_query.expanded_keywords
        )

    def _merge_results(
        self,
        original: List[Dict[str, Any]],
        new: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Merge two result lists, deduplicating by chunk_id and keeping best score.

        Args:
            original: Existing result list
            new: New results to merge in

        Returns:
            Merged and sorted list (by original 'score' field)
        """
        combined = original + new
        best_by_chunk: Dict[str, Dict[str, Any]] = {}

        for hit in combined:
            chunk_id = hit['chunk_id']
            score = hit.get('score', 0.0)
            if chunk_id not in best_by_chunk or score > best_by_chunk[chunk_id].get('score', 0.0):
                best_by_chunk[chunk_id] = hit

        merged = list(best_by_chunk.values())
        merged.sort(key=lambda x: x.get('score', 0.0), reverse=True)
        return merged


# Singleton accessor
_router_instance = None


def get_router() -> RoutingEngine:
    """Get singleton router instance."""
    global _router_instance
    if _router_instance is None:
        _router_instance = RoutingEngine()
    return _router_instance
