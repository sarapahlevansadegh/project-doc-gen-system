# DocGen System — Project Manager

## Architecture Overview

### Stack
- **Backend**: Python 3.11+ / FastAPI / async SQLAlchemy / PostgreSQL + pgvector
- **Frontend**: React 19 / TypeScript / Vite / Tailwind CSS 4 / React Router 7 / TanStack Query 5
- **LLM**: Anthropic (default) / Groq / OpenAI / Ollama abstraction layer
- **RAG**: sentence-transformers (all-MiniLM-L6-v2) / pgvector cosine similarity
- **Container**: Docker Compose (db+backend+frontend), nginx reverse proxy
- **Auth**: JWT (python-jose) / bcrypt / role-based (admin, engineer, viewer)

### Backend Structure
```
backend/
├── app.py                    # FastAPI app entry, lifespan, CORS, scalar docs
├── config.py                 # Pydantic Settings (env-based)
├── api/
│   ├── deps.py               # FastAPI deps: get_db, get_current_user, require_role
│   └── routes/
│       ├── health.py         # GET /health
│       ├── auth.py           # POST /login, /register, GET /me
│       ├── devices.py        # CRUD /devices
│       ├── documents.py      # POST /generate, GET /{job_id}, /download, /history
│       ├── rag.py            # CRUD /rag/reference, activate, sections
│       └── ws.py             # WS /documents/{job_id}/progress
├── core/
│   ├── database.py           # Async engine + session factory (lazy init)
│   └── security.py           # JWT encode/decode, bcrypt hash/verify
├── models/
│   ├── device.py             # Device, DeviceSpec, DeviceAlarm, SerialCommand
│   ├── document.py           # GeneratedDocument
│   ├── template.py           # ReferenceDocument, DocumentTemplate (=DocumentSection)
│   └── user.py               # User
├── schemas/
│   ├── auth.py               # LoginRequest, RegisterRequest, TokenResponse, UserOut
│   └── device.py             # DeviceCreate/Update/Out, sub-schemas
├── services/
│   ├── auth.py               # authenticate_user, build_tokens
│   ├── device_service.py     # CRUD + get_device_data
│   ├── generation_service.py # Job lifecycle: create_job, run_generation
│   ├── agent_service.py      # Legacy: get_device_data, generate_section, generate_document
│   ├── docx_builder.py       # DOCX generation (cover page, sections, alarms table)
│   ├── figure_builder.py     # SVG → PNG diagrams (5 figures, cairosvg)
│   └── rag_service.py        # Legacy: split_document, embed_text, store, retrieve
├── agent/
│   ├── llm.py                # LLMClient abstraction (Anthropic/Groq/OpenAI/Ollama)
│   ├── prompts.py            # build_section_prompt
│   └── workflow.py           # generate_document, discover_reference_sections
├── rag/
│   ├── extractor.py          # DOCX → ExtractedSection (heading-aware parsing)
│   ├── splitter.py           # ExtractedSection → RagSection (type inference)
│   ├── embeddings.py         # Singleton HuggingFaceEmbeddings, embed_text
│   └── retriever.py          # store_sections, retrieve_similar_sections, CRUD
├── db/migrations/
│   ├── env.py
│   └── versions/
│       ├── 0001_initial.py   # All tables except users
│       ├── 0002_generation_job.py  # Generation job fields
│       ├── 0003_document_version.py # Version column
│       └── 0004_users.py     # Users table
└── tests/
    ├── test_app.py           # Health + route existence
    ├── test_auth.py          # Register/login/me/inactive/protected (Postgres-gated)
    ├── test_devices.py       # CRUD, nested update, eager load, delete cascade
    ├── test_rag.py           # Reference upload, activate, delete, sections
    ├── test_agent.py         # Workflow, job status, failure, WS, history (in-memory + DB)
    ├── test_llm_providers.py # Provider selection, model resolution, request formatting
    ├── test_journey.py       # Full E2E with mocked LLM+embeddings
    └── test_agent.py (root)  # Legacy manual test script
```

### Frontend Structure
```
frontend/
├── src/
│   ├── main.tsx              # Entry: QueryClient, AuthProvider, App
│   ├── App.tsx               # RouterProvider
│   ├── api/axios.ts          # Axios instance with auth interceptor
│   ├── hooks/useAuth.tsx     # AuthContext + provider with login/register/logout
│   ├── services/
│   │   ├── api.ts            # devicesApi, referencesApi, documentsApi, healthApi
│   │   └── auth.ts           # authApi (login, register, me)
│   ├── types/auth.ts         # User, LoginRequest, RegisterRequest, TokenResponse
│   ├── types/index.ts        # Device, DeviceSpec, ReferenceDocument, etc.
│   ├── routes/index.tsx      # BrowserRouter: /login, / (protected, children)
│   ├── components/ProtectedRoute.tsx
│   ├── layouts/
│   │   ├── AppLayout.tsx     # TopNavbar + Sidebar + Outlet
│   │   ├── Sidebar.tsx       # Nav links: Dashboard, Devices, References, Generate, History, Settings
│   │   └── TopNavbar.tsx     # User info, role badge, logout
│   └── pages/
│       ├── Login.tsx         # Login/Register form with toggle
│       ├── Dashboard.tsx     # Stats cards: devices, references, active ref, API health
│       ├── Devices.tsx       # Table + create/edit modal with specs/alarms/commands
│       ├── References.tsx    # Table + upload/activate/delete + sections drawer
│       ├── Generate.tsx      # Device + reference select, WS progress, download
│       ├── History.tsx       # Device selector → generation history table + download
│       └── Settings.tsx      # Placeholder
```

### Database Schema
- **devices**: id(UUID), name, model, document_code, safety_class, driver_version, gui_version, created_at
- **device_specs**: id(UUID), device_id(FK), category, spec_key, spec_value, spec_unit
- **device_alarms**: id(UUID), device_id(FK), priority, condition, text_shown, indicator_light, indicator_sound, required_action, alarm_order
- **serial_commands**: id(UUID), device_id(FK), direction, command_name, description, laser_a_mapping, laser_b_mapping, command_order
- **generated_documents**: id(UUID), device_id(FK), reference_doc_id(FK), status, progress_pct, current_section, result_sections(JSONB), file_path, generation_log, error_message, created_at, completed_at, version
- **reference_documents**: id(UUID), filename, template_name, storage_path, section_count, version, is_active, embedding_model, embedding_dimension, created_at
- **document_templates**: id(UUID), template_name, source_doc_id(FK), section_name, section_type, heading_level, parent_section, section_order, content, figure_refs(JSONB), embedding(Vector(384)), embedding_model, embedding_dimension, meta_data(JSONB), created_at
- **users**: id(UUID), email(unique), hashed_password, full_name, role, is_active, created_at

### Current State Assessment

#### Strengths
- Clean layered architecture (API → Services → Models/Agent/RAG)
- Good test coverage (unit, integration, E2E with mocks)
- Solid RAG pipeline (heading-aware extraction, no blind chunking)
- Multi-provider LLM abstraction
- JWT auth with role-based access control
- Section discovery from reference (not hardcoded)
- WebSocket progress streaming
- Docker Compose deployment

#### Issues
1. **Root directory clutter**: ~50 `_agent*.txt` files, `_*.txt` artifacts, `output.docx`
2. **Dead code**: `backend/services/agent_service.py` (duplicates `agent/workflow.py`), `backend/services/rag_service.py` (duplicates `rag/retriever.py`), `backend/test_agent.py` (manual test script)
3. **Persian comments**: Mixed Persian/English comments in `docx_builder.py`, `figure_builder.py`, `agent_service.py`, `rag_service.py`
4. **No linting/formatting**: No ruff config, no mypy config, no pre-commit hooks
5. **No CI/CD**: No GitHub Actions or CI config
6. **No monitoring/logging**: No structured logging, no health check depth, no metrics
7. **Security**: `SECRET_KEY=change-me-in-production` default, no CORS hardening, no rate limiting
8. **Frontend UX**: No loading skeletons, no error boundaries, no responsive sidebar (mobile), Settings page is placeholder
9. **Missing features**: No refresh token rotation, no document regeneration, no batch operations, no search/filter
10. **No API docs config**: Scalar docs optional, no OpenAPI metadata
11. **Docker**: Dev-only defaults, no staging/prod profiles, no healthcheck on backend
12. **No migration seeding**: No seed data script for demo
13. **Dependency**: `xai-sdk` in pyproject.toml but never used
14. **`uv.lock` + `.venv/`**: Committed virtual environment

---

## Work Plan (Independent Modules)

### Module 1: Housekeeping & Cleanup
- Remove all `_agent*.txt`, `_*.txt`, `output.docx` artifacts from root
- Remove dead code: `backend/services/agent_service.py`, `backend/services/rag_service.py`, `backend/test_agent.py`
- Remove unused dependency `xai-sdk` from pyproject.toml
- Remove committed `.venv/` and `uv.lock` (add to `.gitignore`)
- Replace Persian comments with English in all source files
- Organize `.gitignore` properly

### Module 2: Code Quality Tooling
- Add `ruff` config to pyproject.toml (lint + format)
- Add `mypy` config
- Add pre-commit hooks config
- Run linting and fix all issues
- Run type checking and fix all issues

### Module 3: Backend Hardening
- Add structured logging (structlog or JSON logging)
- Add request ID middleware
- Add rate limiting (slowapi)
- Add CORS hardening (allowlist from env)
- Add proper error handling middleware
- Add health check depth (DB connectivity, embedding model load)
- Add OpenAPI metadata (description, contact, license)
- Fix default SECRET_KEY to generate on first run

### Module 4: Backend Enhancements
- Add refresh token rotation endpoint
- Add pagination for devices list
- Add search/filter for devices
- Add document regeneration endpoint
- Add batch delete for references
- Add settings API endpoint (GET/PUT)
- Add `.env` validation on startup

### Module 5: Frontend Enhancement
- Add loading skeletons for all pages
- Add error boundaries
- Add responsive sidebar (mobile hamburger menu)
- Add proper Settings page with API config, LLM provider selection
- Add search bar for devices
- Add pagination for tables
- Add toast notifications for mutations
- Add document preview (text content, not just download)

### Module 6: Demo & Presentation
- Create seed data script (demo devices + reference documents)
- Create demo script (end-to-end walkthrough)
- Add production Docker Compose profile (with proper secrets, healthchecks, resource limits)
- Add Kubernetes manifests (optional: kustomize/helm)
- Add monitoring with Prometheus metrics endpoint
- Create demo environment setup script
- Add demo data (sample devices with realistic medical device specs)

### Module 7: CI/CD & Deployment
- Add GitHub Actions: lint, typecheck, test, build, Docker push
- Add Docker Compose healthchecks
- Add production configuration (nginx caching, gzip, SSL)
- Add migration CI check
- Add test coverage reporting

### Module 8: Documentation
- Update README with architecture diagram, setup instructions, API docs link
- Add deployment guide
- Add developer guide (how to add new LLM provider, new section type)
- Add API documentation (OpenAPI/Scalar config)

---

## Progress Tracking

| Module | Status | Started | Completed |
|--------|--------|---------|-----------|
| 1: Housekeeping & Cleanup | Completed | 2026-08-05 | 2026-08-05 |
| 2: Code Quality Tooling | Completed | 2026-08-05 | 2026-08-05 |
| 3: Backend Hardening | Completed | 2026-08-05 | 2026-08-05 |
| 4: Backend Enhancements | Completed | 2026-08-05 | 2026-08-05 |
| 5: Frontend Enhancement | Completed | 2026-08-05 | 2026-08-05 |
| 6: Demo & Presentation | Completed | 2026-08-05 | 2026-08-05 |
| 7: CI/CD & Deployment | Completed | 2026-08-05 | 2026-08-05 |
| 8: Documentation | Completed | 2026-08-05 | 2026-08-05 |

## Post-Completion Summary

### Critical Bugs Fixed
- `app.py`: `importlib.metadata.version()` has no `default` param — would crash on startup. Fixed with try/except wrapper.
- `docx_builder.py`: Removed dead code referencing undefined `figure_map`/`figures` variables.
- `workflow.py`: Added missing `import traceback` (was `F821` undefined name).

### Backend Changes
- Structured logging with request ID middleware
- CORS origins from env config
- Rate limiting (optional, via slowapi)
- Global exception handler with request ID propagation
- Deep health check at `/health/ready` (DB connectivity)
- OpenAPI metadata (description, contact, license)
- Pagination + search on `GET /devices` endpoint
- Refresh token rotation endpoint (`POST /auth/refresh`)
- Settings API endpoint (`GET /settings`)
- Auto-generated `SECRET_KEY` if default is used

### Frontend Changes
- Real Settings page (fetches from `/settings` API)
- ErrorBoundary component wrapping all routes
- Responsive mobile sidebar with hamburger menu
- Device search bar
- Pagination controls on Devices page
- Refresh token API client

### Demo & Infrastructure
- Seed data script (2 users, 2 devices with realistic medical laser specs)
- Docker Compose with healthchecks, resource limits, restart policies
- Setup script `scripts/setup_demo.sh`
- GitHub Actions CI (lint, test with pgvector, frontend build)

### Known Remaining Items
- `backend/services/figure_builder.py` is unused (no imports) — kept for future use
- `backend/scripts/` has `build_fixture.py`, `demo_rag.py`, `seed_reference.py` — legacy scripts
- Mypy not run (requires full type annotation pass)
- Prometheus metrics not implemented
- Kubernetes manifests not added