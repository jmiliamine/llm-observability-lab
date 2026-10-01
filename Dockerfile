# syntax=docker/dockerfile:1.7
# Image of the RAG service (API + ingest job share it; only the command differs).
#
# 2026 baseline applied here:
#   - multi-stage: build tools and pip caches never reach the runtime image
#   - slim Debian 13 (trixie) base, pinned minor version; rebuild regularly for CVE fixes
#   - non-root numeric UID (runAsNonRoot can be verified by Kubernetes), no shell login
#   - no secrets baked in; config comes from env at runtime
#   - OCI labels so a running image can be traced back to its source commit
ARG PYTHON_VERSION=3.14

# ── Stage 1: build a self-contained virtualenv ─────────────────────────────────
FROM python:${PYTHON_VERSION}-slim-trixie AS build
ENV PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /src
# Copy only what the install needs: changing docs or tests does not bust this layer.
COPY pyproject.toml ./
COPY src ./src
# BuildKit cache mount: wheels are cached across builds on the build host, not in the image.
RUN --mount=type=cache,target=/root/.cache/pip \
    python -m venv /opt/venv && /opt/venv/bin/pip install .

# ── Stage 2: runtime ───────────────────────────────────────────────────────────
FROM python:${PYTHON_VERSION}-slim-trixie AS runtime
ARG VCS_REF=unknown
LABEL org.opencontainers.image.title="obslab" \
      org.opencontainers.image.description="LangGraph RAG instrumented with OpenTelemetry GenAI conventions" \
      org.opencontainers.image.revision="${VCS_REF}" \
      org.opencontainers.image.licenses="MIT"

# Dedicated user; UID/GID 10001 matches runAsUser/fsGroup in the Deployment.
RUN groupadd --gid 10001 app && useradd --uid 10001 --gid app --no-create-home --shell /usr/sbin/nologin app

COPY --from=build /opt/venv /opt/venv
# The notes to index ship with the image (staged in build/corpus/ by `task app:build`, from
# samples/notes/ or your own folder). The *index* is not in the image: the ingest Job writes it
# to PostgreSQL (pgvector), with the same embedding model the API uses.
COPY --chown=10001:10001 build/corpus /app/corpus

ENV PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    OBSLAB_LOG_STDOUT=true

USER 10001:10001
WORKDIR /app
EXPOSE 8000
ENTRYPOINT ["obslab"]
CMD ["serve", "--host", "0.0.0.0", "--port", "8000"]
