FROM python:3.11-slim

WORKDIR /app


# ============================================================
# System dependencies
# ============================================================

RUN apt-get update && apt-get install -y \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*


# ============================================================
# Install uv
# ============================================================

RUN curl -LsSf https://astral.sh/uv/install.sh | sh \
    && mv /root/.local/bin/uv /usr/local/bin/uv \
    && uv --version


# ============================================================
# Environment
# ============================================================

ENV UV_HTTP_TIMEOUT=600
ENV UV_LINK_MODE=copy

# PyTorch CPU wheels
ENV UV_EXTRA_INDEX_URL=https://download.pytorch.org/whl/cpu

# Application
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH=/app/backend

# HuggingFace cache
ENV HF_HOME=/root/.cache/huggingface


# ============================================================
# Dependency layer
#
# IMPORTANT:
# Keep this layer BEFORE copying application code.
#
# If pyproject.toml and uv.lock do not change,
# Docker can reuse this entire layer.
# ============================================================

COPY pyproject.toml uv.lock README.md alembic.ini ./

RUN --mount=type=cache,target=/root/.cache/uv,sharing=locked \
    uv sync --frozen --no-dev


# ============================================================
# Application code layer
#
# Changes here should NOT reinstall dependencies.
# ============================================================

COPY backend ./backend


# ============================================================
# Runtime directories
# ============================================================

RUN mkdir -p \
    generated_docs \
    reference_templates


# ============================================================
# Runtime
# ============================================================

EXPOSE 8000

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]