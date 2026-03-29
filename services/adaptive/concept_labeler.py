"""
Concept Labeler: Deterministic semantic naming for entity clusters.

Converts raw entity clusters (e.g. ["docker", "kubernetes", "helm"])
into meaningful concept labels (e.g. "container orchestration") using
a keyword signature voting algorithm.

No LLM, no hallucination, fully deterministic.
"""

from dataclasses import dataclass
from typing import Dict, List, Set, Optional
from core.logger import get_logger

logger = get_logger("CONCEPT_LABELER")

# ---------------------------------------------------------------------------
# Tuning
# ---------------------------------------------------------------------------
MIN_MATCH_COUNT = 2           # minimum keyword matches to activate a signature
MIN_CONFIDENCE = 0.4          # minimum confidence to use semantic label


# ---------------------------------------------------------------------------
# Output type
# ---------------------------------------------------------------------------

@dataclass
class ConceptLabel:
    """Result of labeling a cluster."""
    name: str               # semantic label or fallback
    confidence: float       # 0.0-1.0
    is_inferred: bool       # True if semantic, False if fallback


# ---------------------------------------------------------------------------
# Semantic Signature Table
# ---------------------------------------------------------------------------

@dataclass
class SemanticSignature:
    """Maps a set of keywords to a concept label."""
    label: str
    keywords: Set[str]
    min_match: int = MIN_MATCH_COUNT


SIGNATURES: List[SemanticSignature] = [
    # Infrastructure & DevOps
    SemanticSignature(
        label="container orchestration",
        keywords={"docker", "kubernetes", "helm", "k8s", "pod", "container",
                  "swarm", "compose", "kubectl", "istio", "envoy"},
    ),
    SemanticSignature(
        label="cloud infrastructure",
        keywords={"aws", "gcp", "azure", "terraform", "cloudformation",
                  "pulumi", "cdk", "ec2", "s3", "lambda", "cloud"},
    ),
    SemanticSignature(
        label="ci/cd pipeline",
        keywords={"jenkins", "github actions", "gitlab ci", "circleci",
                  "argocd", "tekton", "ci/cd", "pipeline", "deploy"},
    ),
    SemanticSignature(
        label="monitoring and observability",
        keywords={"prometheus", "grafana", "datadog", "alertmanager",
                  "metrics", "opentelemetry", "jaeger", "zipkin", "tracing"},
    ),

    # Data & ML
    SemanticSignature(
        label="data pipeline",
        keywords={"airflow", "spark", "kafka", "flink", "beam", "dag",
                  "etl", "dbt", "prefect", "dagster", "batch"},
    ),
    SemanticSignature(
        label="ml ops",
        keywords={"mlflow", "kubeflow", "wandb", "tensorboard", "sagemaker",
                  "vertex ai", "model registry", "experiment", "training"},
    ),
    SemanticSignature(
        label="data storage",
        keywords={"postgres", "mysql", "mongodb", "redis", "cassandra",
                  "dynamodb", "sqlite", "mariadb", "database", "sql"},
    ),
    SemanticSignature(
        label="message queue",
        keywords={"rabbitmq", "kafka", "sqs", "nats", "pulsar",
                  "activemq", "zeromq", "broker", "queue", "pub/sub"},
    ),
    SemanticSignature(
        label="search engine",
        keywords={"elasticsearch", "solr", "opensearch", "lucene",
                  "typesense", "meilisearch", "full-text", "search"},
    ),

    # Security & Auth
    SemanticSignature(
        label="authentication",
        keywords={"oauth", "jwt", "saml", "sso", "keycloak", "auth0",
                  "oidc", "token", "ldap", "authentication"},
    ),
    SemanticSignature(
        label="security",
        keywords={"tls", "ssl", "encryption", "vault", "certificate",
                  "firewall", "rbac", "iam", "policy", "secret"},
    ),

    # AI & NLP
    SemanticSignature(
        label="natural language processing",
        keywords={"tokenizer", "ner", "spacy", "nltk", "bert", "transformer",
                  "embedding", "pos tagging", "sentiment", "text classification"},
    ),
    SemanticSignature(
        label="retrieval augmented generation",
        keywords={"rag", "retrieval", "generation", "grounding", "context window",
                  "prompt", "chain", "langchain", "llamaindex"},
    ),

    # Web & API
    SemanticSignature(
        label="api framework",
        keywords={"fastapi", "flask", "django", "express", "rest", "graphql",
                  "grpc", "websocket", "endpoint", "api"},
    ),
    SemanticSignature(
        label="frontend framework",
        keywords={"react", "vue", "angular", "svelte", "nextjs", "nuxt",
                  "tailwind", "css", "component", "spa"},
    ),

    # Testing
    SemanticSignature(
        label="testing framework",
        keywords={"pytest", "jest", "mocha", "cypress", "selenium",
                  "unittest", "mock", "coverage", "integration test"},
    ),
]


# ---------------------------------------------------------------------------
# Labeling algorithm
# ---------------------------------------------------------------------------

def label_cluster(members: List[str]) -> ConceptLabel:
    """
    Infer a semantic label for an entity cluster.

    Algorithm:
      1. For each signature, count keyword matches (exact + substring)
      2. Score = matched / max(cluster_size, signature_size)
      3. Pick highest score with matched >= min_match
      4. If score >= MIN_CONFIDENCE → use semantic label
      5. Otherwise → fallback to raw member list

    Args:
        members: List of entity names in the cluster (already lowered).

    Returns:
        ConceptLabel with name, confidence, and is_inferred flag.
    """
    if not members:
        return ConceptLabel(
            name="unknown",
            confidence=0.0,
            is_inferred=False,
        )

    members_lower = [m.lower().strip() for m in members]
    members_set = set(members_lower)

    best_label: Optional[str] = None
    best_score: float = 0.0
    best_matched: int = 0

    for sig in SIGNATURES:
        matched = 0
        for member in members_lower:
            for kw in sig.keywords:
                # Exact match or substring match (bidirectional)
                if member == kw or kw in member or member in kw:
                    matched += 1
                    break  # count each member at most once

        if matched < sig.min_match:
            continue

        # Score: what fraction of the cluster is explained by this signature
        score = matched / len(members)

        if score > best_score:
            best_score = score
            best_label = sig.label
            best_matched = matched

    # Apply confidence threshold
    if best_label and best_score >= MIN_CONFIDENCE:
        confidence = round(best_score, 4)
        logger.info(
            f"Labeled cluster {members_lower} → '{best_label}' "
            f"(confidence={confidence}, matched={best_matched}/{len(members)})"
        )
        return ConceptLabel(
            name=best_label,
            confidence=confidence,
            is_inferred=True,
        )

    # Fallback: use raw member list
    fallback_name = f"learned:{'+'.join(sorted(members_lower))}"
    logger.info(
        f"No semantic match for {members_lower} "
        f"(best: '{best_label}' at {best_score:.3f}) → fallback: {fallback_name}"
    )
    return ConceptLabel(
        name=fallback_name,
        confidence=0.0,
        is_inferred=False,
    )
