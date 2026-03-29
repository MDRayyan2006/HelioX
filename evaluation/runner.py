"""
Pipeline Runner: Executes the main pipeline with a given query.
"""

import traceback
from typing import Dict, Any

from api.engine.pipeline import run_pipeline
from models.schemas.agent_output import AgentOutput


def run_query(query: str) -> Dict[str, Any]:
    """
    Execute the pipeline with a given query and return structured output.

    Args:
        query: User query string

    Returns:
        Dictionary containing:
        - query: original query
        - worker_outputs: list of WorkerOutput objects (converted to dict)
        - success: bool
        - error: str or None
    """
    try:
        result: AgentOutput = run_pipeline(query)

        # Convert Pydantic models to dict for easier evaluation
        outputs_dict = [output.model_dump() for output in result.worker_outputs]

        return {
            "query": query,
            "worker_outputs": outputs_dict,
            "success": True,
            "error": None
        }
    except Exception as e:
        return {
            "query": query,
            "worker_outputs": [],
            "success": False,
            "error": str(e) + "\n" + traceback.format_exc()
        }
