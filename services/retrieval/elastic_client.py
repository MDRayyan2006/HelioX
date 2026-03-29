"""
Elasticsearch client for keyword-based retrieval.
"""

from typing import List, Dict, Any, Optional
from elasticsearch import Elasticsearch
from core.logger import get_logger
from core.config import get_config


class ElasticStore:
    """
    Elasticsearch wrapper for storing and searching document chunks.
    """

    def __init__(self, host: str = "localhost", port: int = 9200):
        """
        Initialize Elasticsearch client.

        Args:
            host: Elasticsearch host
            port: Elasticsearch port
        """
        self.logger = get_logger("ELASTIC_STORE")
        self.es_host = host
        self.es_port = port
        self.index_name = "heliox_chunks"

        # Initialize client
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        
        url = f"https://{host}:{port}"
        self.es = Elasticsearch(
            url,
            basic_auth=("elastic", "CjRL0vg1D2yulxlEAKWk"),
            verify_certs=False,
            request_timeout=30
        )

        # Create index if it doesn't exist
        self._create_index()

    def _populate_sample_data(self):
        """
        Populate Elasticsearch with sample document chunks.

        Uses same sample data as in retriever.py for consistency.
        """
        # Import Chunk here to avoid circular dependency
        from models.schemas.chunk import Chunk

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

        # Convert Chunk objects to dictionaries for indexing
        chunks_to_index = []
        for chunk in sample_chunks:
            chunks_to_index.append({
                "chunk_id": chunk.chunk_id,
                "text": chunk.text,
                "metadata": chunk.metadata
            })

        self.index_chunks(chunks_to_index)
        self.logger.info(f"Populated Elasticsearch with {len(chunks_to_index)} sample chunks")

    def _create_index(self):
        """Create the chunks index with appropriate mapping if it doesn't exist."""
        if self.es.indices.exists(index=self.index_name):
            self.logger.info(f"Index '{self.index_name}' already exists")
            return

        # Define mapping for chunks
        mapping = {
            "mappings": {
                "properties": {
                    "chunk_id": {"type": "keyword"},
                    "text": {"type": "text"},
                    "metadata": {"type": "object"}
                }
            }
        }

        try:
            self.es.indices.create(index=self.index_name, body=mapping)
            self.logger.info(f"Created index '{self.index_name}' with mapping")
        except Exception as e:
            self.logger.error(f"Failed to create index: {e}")
            raise

    def index_chunk(self, chunk_id: str, text: str, metadata: Dict[str, Any] = None):
        """
        Index a single chunk in Elasticsearch.

        Args:
            chunk_id: Unique identifier for the chunk
            text: Text content of the chunk
            metadata: Additional metadata dictionary
        """
        doc = {
            "chunk_id": chunk_id,
            "text": text,
            "metadata": metadata or {}
        }

        try:
            self.es.index(
                index=self.index_name,
                id=chunk_id,
                body=doc
            )
            self.logger.debug(f"Indexed chunk {chunk_id}")
        except Exception as e:
            self.logger.error(f"Failed to index chunk {chunk_id}: {e}")
            raise

    def index_chunks(self, chunks: List[Dict[str, Any]]):
        """
        Index multiple chunks in Elasticsearch using bulk API.

        Args:
            chunks: List of dictionaries with keys: chunk_id, text, metadata
        """
        operations = []
        for chunk in chunks:
            operations.append({"index": {"_index": self.index_name, "_id": chunk["chunk_id"]}})
            operations.append({
                "chunk_id": chunk["chunk_id"],
                "text": chunk["text"],
                "metadata": chunk.get("metadata", {})
            })

        if operations:
            try:
                self.es.bulk(body=operations, refresh=True)
                self.logger.info(f"Indexed {len(chunks)} chunks")
            except Exception as e:
                self.logger.error(f"Failed to bulk index chunks: {e}")
                raise

    def search_keywords(self, query: str, top_k: int = 10) -> List[Dict[str, Any]]:
        """
        Search for chunks using keyword matching (BM25).

        Args:
            query: Search query string
            top_k: Number of top results to return

        Returns:
            List of dictionaries with keys: chunk_id, text, score
        """
        try:
            # Elasticsearch query using match (BM25 by default for text field)
            body = {
                "query": {
                    "match": {
                        "text": {
                            "query": query
                        }
                    }
                },
                "size": top_k,
                "_source": ["chunk_id", "text"]  # We don't need metadata for scoring
            }

            response = self.es.search(index=self.index_name, body=body)

            hits = []
            for hit in response["hits"]["hits"]:
                source = hit["_source"]
                hits.append({
                    "chunk_id": source["chunk_id"],
                    "text": source["text"],
                    "score": hit["_score"]  # BM25 score from Elasticsearch
                })

            self.logger.info(f"Found {len(hits)} keyword matches for query: {query[:50]}...")
            return hits

        except Exception as e:
            self.logger.error(f"Keyword search failed: {e}")
            return []


# Singleton accessor for convenience
_elastic_store_instance = None


def get_elastic_store() -> ElasticStore:
    """
    Get default Elasticsearch store instance (singleton).

    Returns:
        Shared ElasticStore instance
    """
    global _elastic_store_instance
    if _elastic_store_instance is None:
        config = get_config()
        # Use config values if available, otherwise defaults
        host = getattr(config, 'elastic_host', 'localhost')
        port = getattr(config, 'elastic_port', 9200)
        _elastic_store_instance = ElasticStore(host=host, port=port)
    return _elastic_store_instance