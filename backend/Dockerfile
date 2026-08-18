FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*


RUN curl -LsSf https://astral.sh/uv/install.sh | sh \
    && mv /root/.local/bin/uv /usr/local/bin/uv \
    && uv --version


ENV UV_HTTP_TIMEOUT=600

ENV UV_EXTRA_INDEX_URL=https://download.pytorch.org/whl/cpu


COPY pyproject.toml uv.lock README.md alembic.ini ./


RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev


COPY backend ./backend


RUN mkdir -p generated_docs reference_templates


ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH=/app/backend


# HuggingFace cache directory
ENV HF_HOME=/root/.cache/huggingface


EXPOSE 8000


CMD ["uvicorn","app:app","--host","0.0.0.0","--port","8000"]