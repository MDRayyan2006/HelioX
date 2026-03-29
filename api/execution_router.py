"""
FastAPI endpoint for Execution Router

Provides a single POST endpoint /route that accepts a query and returns
the answer along with execution mode and metadata.
"""

from typing import Dict, Any
from fastapi import APIRouter, HTTPException, Body
from pydantic import BaseModel, Field

from core.execution_router import execute_query, analyze_complexity, ExecutionRouter

router = APIRouter(prefix="/router", tags=["execution"])


class QueryRequest(BaseModel):
    """Request model for query execution."""
    query: str = Field(..., min_length=1, description="User query string")
    include_analysis: bool = Field(False, description="Include complexity analysis in response")


class RouteResponse(BaseModel):
    """Response model for query routing."""
    answer: str = Field(..., description="Generated answer")
    mode: str = Field(..., description="Execution mode: LIGHTWEIGHT or MULTI_AGENT")
    confidence: float = Field(..., description="Confidence score (0-1)")
    citations: list = Field(default_factory=list, description="List of citation objects")
    metrics: Dict[str, Any] = Field(default_factory=dict, description="Execution metrics")
    analysis: Dict[str, Any] = Field(default_factory=dict, description="Complexity analysis (if requested)")


@router.post("/execute", response_model=RouteResponse)
async def execute(request: QueryRequest = Body(...)):
    """
    Execute query with automatic mode routing.

    Analyzes query complexity and routes to either:
    - LIGHTWEIGHT: Fast single-pass retrieval + answer composition
    - MULTI_AGENT: Full adaptive multi-agent pipeline with retry logic

    Returns answer with mode, confidence, and citations.
    """
    try:
        # Execute query through router
        result = execute_query(request.query)

        # If analysis requested, include it
        if request.include_analysis:
            result["analysis"] = analyze_complexity(request.query)

        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Execution failed: {str(e)}")


@router.post("/analyze")
async def analyze(request: QueryRequest = Body(...)):
    """
    Analyze query complexity without execution.

    Returns complexity score, suggested mode, and detailed metrics.
    Useful for debugging and understanding routing decisions.
    """
    try:
        analysis = analyze_complexity(request.query)
        return analysis
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")


@router.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy", "service": "execution-router"}


# For direct testing
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(router, host="0.0.0.0", port=8000)
