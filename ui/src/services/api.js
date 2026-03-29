/**
 * HelioX API Service
 * Connects the frontend to the real FastAPI backend endpoints.
 */

const API_BASE = '/api';

/**
 * POST /api/query — Run the RAG pipeline and get the full response.
 */
export async function queryPipeline(query, mode = 'multi-agent') {
  const res = await fetch(`${API_BASE}/query`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query, mode }),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Query failed: ${res.status}`);
  }

  return res.json();
}

/**
 * POST /api/upload — Upload a document (PDF, TXT, MD) for ingestion.
 */
export async function uploadDocument(file) {
  const form = new FormData();
  form.append('file', file);

  const res = await fetch(`${API_BASE}/upload`, {
    method: 'POST',
    body: form,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Upload failed: ${res.status}`);
  }

  return res.json();
}

/**
 * GET /api/telemetry — Fetch aggregated telemetry trends.
 */
export async function fetchTelemetry() {
  const res = await fetch(`${API_BASE}/telemetry`);
  if (!res.ok) return null;
  return res.json();
}

/**
 * GET /api/learning — Fetch learning insights (concepts, strategies).
 */
export async function fetchLearning() {
  const res = await fetch(`${API_BASE}/learning`);
  if (!res.ok) return null;
  return res.json();
}

/**
 * GET /api/health — Check API health.
 */
export async function checkHealth() {
  try {
    const res = await fetch(`${API_BASE}/health`);
    return res.ok;
  } catch {
    return false;
  }
}
