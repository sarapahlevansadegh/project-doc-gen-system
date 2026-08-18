# DocGen System

Medical device software documentation generation system. Generates IEC 62304-compliant Software Architectural Design documents from device specifications using LLM and RAG.

## Architecture

- **Backend**: Python 3.11+ / FastAPI / async SQLAlchemy / PostgreSQL + pgvector
- **Frontend**: React 19 / TypeScript / Vite / Tailwind CSS 4 / React Router 7 / TanStack Query 5
- **LLM**: Anthropic Claude (default) / Groq / OpenAI / Ollama
- **RAG**: sentence-transformers all-MiniLM-L6-v2 / pgvector cosine similarity
- **Auth**: JWT (python-jose) / bcrypt / role-based (admin, engineer, viewer)

## Quick Start

### Prerequisites

- Docker & Docker Compose
- Python 3.11+
- Node.js 20+

### Setup

```bash
# 1. Clone and configure
cp .env.example .env
# Edit .env to add your LLM API keys (ANTHROPIC_API_KEY, GROQ_API_KEY, etc.)

# 2. Start with Docker Compose
docker compose up -d

# 3. Seed demo data
python -m backend.scripts.seed_demo
```

### Access

- **Frontend**: http://localhost
- **API**: http://localhost:8000
- **API Docs**: http://localhost:8000/scalar

### Demo Accounts

| Email | Password | Role |
|-------|----------|------|
| admin@docgen.demo | admin123 | admin |
| engineer@docgen.demo | engineer123 | engineer |

## Development

### Backend

```bash
python -m venv .venv
.venv\Scripts\activate  # Windows
source .venv/bin/activate  # Linux/Mac
pip install -e .
alembic upgrade head
uvicorn app:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm ci
npm run dev
```

### Linting

```bash
ruff check backend/
```

### Testing

```bash
pytest backend/tests/ -v
```

## API Endpoints

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| GET | /health | Health check | No |
| GET | /health/ready | Deep health check (DB) | No |
| POST | /auth/login | Login | No |
| POST | /auth/refresh | Refresh token | No |
| POST | /auth/register | Register (first = admin) | Optional |
| GET | /auth/me | Current user | Yes |
| GET/POST/PATCH/DELETE | /devices | Device CRUD | Yes |
| POST | /documents/generate | Generate document | engineer+ |
| GET | /documents/{id} | Job status | Yes |
| GET | /documents/{id}/download | Download DOCX | Yes |
| GET | /documents/history/{device_id} | Generation history | Yes |
| WS | /documents/{id}/progress | WebSocket progress | Yes |
| POST/GET | /rag/reference | Reference CRUD | Yes |
| GET | /settings | System settings | Yes |
| GET | /scalar | API docs UI | No |

## Project Structure

```
├── backend/
│   ├── app.py              # FastAPI entry point
│   ├── config.py           # Settings (env-based)
│   ├── api/routes/         # API route handlers
│   ├── core/               # Database, security, middleware
│   ├── models/             # SQLAlchemy models
│   ├── schemas/            # Pydantic schemas
│   ├── services/           # Business logic
│   ├── agent/              # LLM workflow
│   ├── rag/                # RAG pipeline
│   └── tests/              # Test suite
├── frontend/
│   └── src/
│       ├── pages/          # Route pages
│       ├── components/     # Shared components
│       ├── hooks/          # React hooks
│       ├── services/       # API clients
│       └── layouts/        # Layout components
└── scripts/
    └── setup_demo.sh       # Demo environment setup
```

## Configuration

Key environment variables in `.env`:

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | postgresql+asyncpg://... | PostgreSQL connection |
| `ANTHROPIC_API_KEY` | - | Anthropic API key |
| `DOCGEN_LLM_PROVIDER` | anthropic | LLM provider |
| `SECRET_KEY` | auto-generated | JWT signing key |
| `CORS_ORIGINS` | http://localhost:5173,... | Allowed origins |