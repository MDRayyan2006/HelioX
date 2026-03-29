import time
from models.schemas.query import StructuredQuery
from services.retrieval.retriever import get_retriever


def measure_latency():
    retriever = get_retriever()
    
    query = StructuredQuery(
        raw_query="What is the architecture of the RAG system?",
        intent="informational",
        keywords=["architecture", "RAG", "system"],
        entities=["RAG"]
    )
    
    start_time = time.time()
    entity_hits, vector_hits = retriever.retrieve(query, top_k=50)
    end_time = time.time()
    
    print(f"Retrieval took {(end_time - start_time) * 1000:.2f} ms")
    print(f"Retrieved {len(vector_hits)} hits.")
    
if __name__ == "__main__":
    measure_latency()
