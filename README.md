# HelioX RAG Pipeline

HelioX is a production-grade multi-agent RAG (Retrieval-Augmented Generation) system designed for high precision and adaptive performance.

## Prerequisites

- Python 3.10 or higher
- [Optional] Qdrant (local or cloud)
- [Optional] Redis (for caching)

## Quick Start (Windows)

To set up your project environment and install all dependencies automatically:

1.  **Clone the repository:**
    ```powershell
    git clone <your-repo-url>
    cd helioLasthope
    ```

2.  **Run the setup script:**
    ```powershell
    .\setup_venv.ps1
    ```
    This will:
    - Create a local virtual environment in `.venv/`
    - Upgrade pip
    - Install all required modules from `requirements.txt`

3.  **Run the API server:**
    ```powershell
    .\run_api.ps1
    ```
    The server will start on `http://localhost:8000`.

## Quick Start (MacOS/Linux)

1.  **Create and activate venv:**
    ```bash
    python3 -m venv .venv
    source .venv/bin/activate
    ```

2.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

3.  **Run server:**
    ```bash
    python api_server.py
    ```

## Project Structure

- `api/`: Core engine and pipeline logic.
- `api_server.py`: FastAPI server exposing RAG endpoints.
- `services/`: Specialized services for retrieval, embedding, and adaptive tuning.
- `models/`: Pydantic schemas for data validation.
- `core/`: Logging, configuration, and caching utilities.
- `.venv/`: Virtual environment folder (ignored by git).

## Key Features

- **Multi-Agent Pipeline**: Planner, Retriever, Reasoner, and Critic agents.
- **Adaptive Retrieval**: Dynamically adjusts search depth and strategy.
- **Context Packing**: Optimizes token usage and prevents "context drowning".
- **Telemetry**: Detailed logs for performance and accuracy tracking.
