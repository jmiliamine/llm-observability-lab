# syntax=docker/dockerfile:1.7
# Image of the RAG service (API + ingest job share it; only the command differs).
#
# 2026 baseline applied here:
#   - multi-stage: build tools and caches never reach the runtime image
#   - dependencies installed from the lock file, not resolved at build time
#   - slim Debian 13 (trixie) base, pinned minor version; security updates applied at build
#   - no pip in the runtime image
#   - non-root numeric UID (runAsNonRoot can be verified by Kubernetes), no shell login
#   - no secrets baked in; config comes from env at runtime
#   - OCI labels so a running image can be traced back to its source commit
ARG PYTHON_VERSION=3.14

# ── Stage 1: build a self-contained virtualenv ─────────────────────────────────
FROM python:${PYTHON_VERSION}-slim-trixie AS build
# uv installs exactly what uv.lock says (hashes included): the image runs the dependency versions
# that the tests ran, and the build fails if the lock file is out of date.
COPY --from=ghcr.io/astral-sh/uv:0.12.21 /uv /bin/uv
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_PYTHON_DOWNLOADS=never \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1
WORKDIR /src
# Dependencies first: this layer is reused until pyproject.toml or uv.lock change.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project
COPY README.md LICENSE ./
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable

# ── Stage 2: runtime ───────────────────────────────────────────────────────────
FROM python:${PYTHON_VERSION}-slim-trixie AS runtime
ARG VCS_REF=unknown
LABEL org.opencontainers.image.title="obslab" \
      org.opencontainers.image.description="LangGraph RAG instrumented with OpenTelemetry GenAI conventions" \
      org.opencontainers.image.revision="${VCS_REF}" \
      org.opencontainers.image.licenses="MIT"

# Security updates published since the base image was built, and no package installer at
# runtime: pip (with the libraries it vendors) is not needed to run the app.
ARG PYTHON_VERSION
RUN apt-get update \
    && apt-get -y upgrade \
    && rm -rf /var/lib/apt/lists/* \
    && python -m pip uninstall -y pip \
    && rm -rf "/usr/local/lib/python${PYTHON_VERSION}/site-packages/"setuptools* "/usr/local/lib/python${PYTHON_VERSION}/ensurepip"

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
