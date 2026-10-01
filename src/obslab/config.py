"""All settings come from environment variables (12-factor), with local defaults.

OBSLAB_PROVIDER          ollama | fake            (fake = deterministic, for tests/CI)
OBSLAB_CHAT_MODEL        default llama3.2:3b
OBSLAB_EMBED_MODEL       default nomic-embed-text
OLLAMA_BASE_URL          default http://localhost:11434
PGHOST, PGPORT, PGDATABASE, PGUSER, PGPASSWORD    PostgreSQL connection (standard libpq variables)
OBSLAB_DB_TIMEOUT_MS     statement timeout for vector queries, default 5000
OBSLAB_TELEMETRY         otlp | console | none    (tests inject in-memory exporters directly)
OTEL_EXPORTER_OTLP_ENDPOINT  default http://localhost:4318 (the collector)
OBSLAB_CAPTURE_CONTENT   true to record prompts/answers on spans (opt-in, off by default)
OBSLAB_TOP_K / OBSLAB_MIN_SCORE   retrieval tuning (validated: 1..20 and 0..1)
OBSLAB_PRICE_IN / OBSLAB_PRICE_OUT  USD per 1M tokens, to chart an "API-equivalent" cost
OBSLAB_ENVIRONMENT       deployment.environment.name resource attribute (local, k3d, ...)
OBSLAB_LOG_STDOUT        true to also print app logs on stdout (containers: `kubectl logs`)
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

PROVIDERS = ("ollama", "fake")
MAX_TOP_K = 20


def _bool(name: str, default: bool = False) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class Settings:
    provider: str = field(default_factory=lambda: os.environ.get("OBSLAB_PROVIDER", "ollama"))
    chat_model: str = field(default_factory=lambda: os.environ.get("OBSLAB_CHAT_MODEL", "llama3.2:3b"))
    embed_model: str = field(default_factory=lambda: os.environ.get("OBSLAB_EMBED_MODEL", "nomic-embed-text"))
    ollama_url: str = field(default_factory=lambda: os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434"))
    db_timeout_ms: int = field(default_factory=lambda: int(os.environ.get("OBSLAB_DB_TIMEOUT_MS", "5000")))
    telemetry: str = field(default_factory=lambda: os.environ.get("OBSLAB_TELEMETRY", "otlp"))
    otlp_endpoint: str = field(default_factory=lambda: os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318"))
    service_name: str = field(default_factory=lambda: os.environ.get("OTEL_SERVICE_NAME", "obslab-rag"))
    capture_content: bool = field(default_factory=lambda: _bool("OBSLAB_CAPTURE_CONTENT"))
    top_k: int = field(default_factory=lambda: int(os.environ.get("OBSLAB_TOP_K", "4")))
    min_score: float = field(default_factory=lambda: float(os.environ.get("OBSLAB_MIN_SCORE", "0.6")))
    price_in: float = field(default_factory=lambda: float(os.environ.get("OBSLAB_PRICE_IN", "0")))
    price_out: float = field(default_factory=lambda: float(os.environ.get("OBSLAB_PRICE_OUT", "0")))
    environment: str = field(default_factory=lambda: os.environ.get("OBSLAB_ENVIRONMENT", "local"))
    log_stdout: bool = field(default_factory=lambda: _bool("OBSLAB_LOG_STDOUT"))

    def __post_init__(self) -> None:
        # Fail at startup with a clear message rather than serve odd answers later.
        problems = []
        if self.provider not in PROVIDERS:
            problems.append(f"OBSLAB_PROVIDER={self.provider!r} (expected one of {PROVIDERS})")
        if not 1 <= self.top_k <= MAX_TOP_K:
            problems.append(f"OBSLAB_TOP_K={self.top_k} (expected 1..{MAX_TOP_K})")
        if not 0.0 <= self.min_score <= 1.0:
            problems.append(f"OBSLAB_MIN_SCORE={self.min_score} (expected 0..1)")
        if not 100 <= self.db_timeout_ms <= 60_000:
            problems.append(f"OBSLAB_DB_TIMEOUT_MS={self.db_timeout_ms} (expected 100..60000)")
        if problems:
            raise ValueError("invalid settings: " + "; ".join(problems))

    @property
    def embed_model_id(self) -> str:
        """Identity of the embedding model, as written in the index metadata."""
        return "fake-embed" if self.provider == "fake" else self.embed_model
