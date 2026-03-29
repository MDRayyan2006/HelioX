import re
from typing import List

def semantic_chunker(
    text: str, 
    max_chunk_size: int = 1000, 
    overlap_size: int = 200
) -> List[str]:
    """
    Splits a document into high-quality semantic chunks.
    
    Strategy:
    1. Splits the document primarily by paragraphs to preserve semantic boundaries.
    2. If a paragraph exceeds the max_chunk_size, it falls back to sentence splitting.
    3. Builds chunks up to the target max_chunk_size.
    4. Creates overlaps between chunks by preserving the trailing sequence of sentences 
       (or whole paragraphs) from the previous chunk.
    
    Args:
        text (str): The document text to be chunked.
        max_chunk_size (int): Maximum allowed characters in a chunk.
        overlap_size (int): Target number of overlapping characters between chunks.
        
    Returns:
        List[str]: A list of document chunks.
    """
    if not text or not text.strip():
        return []

    # 1. Split text into paragraphs
    paragraphs = re.split(r'\n\s*\n', text.strip())
    
    # 2. Refine large paragraphs into sentences to avoid breaking semantic context
    segments = []
    sentence_endings = re.compile(r'(?<=[.!?])\s+')
    
    for para in paragraphs:
        if len(para) <= max_chunk_size:
            segments.append(para)
        else:
            # Fallback: Split long paragraphs by sentence boundaries
            sentences = sentence_endings.split(para)
            segments.extend(sentences)

    # 3. Build chunks with overlap
    chunks = []
    current_chunk = []
    current_length = 0
    
    for segment in segments:
        segment_len = len(segment)
        
        if current_length + segment_len + (1 if current_length > 0 else 0) <= max_chunk_size:
            current_chunk.append(segment)
            current_length += segment_len + (1 if current_length > 0 else 0)
        else:
            # Finalize the current chunk
            if current_chunk:
                chunks.append(" ".join(current_chunk))
            
            # Start new chunk with overlap
            # We backtrack from the end of the current_chunk to fill the overlap limit
            overlap_chunk = []
            overlap_length = 0
            
            for prev_segment in reversed(current_chunk):
                if overlap_length + len(prev_segment) <= overlap_size:
                    overlap_chunk.insert(0, prev_segment)
                    overlap_length += len(prev_segment) + 1
                else:
                    break
            
            # Initialize the next chunk
            if overlap_chunk:
                current_chunk = overlap_chunk + [segment]
                current_length = sum(len(s) for s in current_chunk) + len(current_chunk) - 1
            else:
                # If a single sentence exceeds overlap significantly or current_chunk was empty
                current_chunk = [segment]
                current_length = segment_len
                
    # Append the last remaining chunk
    if current_chunk:
        chunks.append(" ".join(current_chunk))
        
    return chunks

# Example Usage
if __name__ == "__main__":
    sample_text = (
        "Semantic chunking is crucial for modern Retrieval-Augmented Generation systems. "
        "It focuses on preserving the integrity of concepts rather than blindly cutting text by token counts.\n\n"
        "By enforcing hard boundaries at the paragraph level first, chunks contain entire unified thoughts. "
        "If a specific paragraph runs extremely long, the chunker intelligently degrades its splitting criteria to the sentence level. "
        "This prevents critical sentences from being chopped in half. "
        "Furthermore, implementing an overlap window ensures context is stitched seamlessly between adjacent chunks."
    )
    
    for i, c in enumerate(semantic_chunker(sample_text, max_chunk_size=150, overlap_size=50)):
        print(f"--- Chunk {i+1} ---\n{c}\n")
