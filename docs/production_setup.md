# DocGen System - Production Setup Guide

## Prerequisites

- Docker Engine 20.10+
- Docker Compose 2.0+
- 4GB+ RAM available
- 10GB+ disk space

## Quick Start

### 1. Clone and Configure

```bash
git clone <repository-url>
cd doc-gen-system

# Copy environment file
cp .env.example .env

# IMPORTANT: Change the SECRET_KEY in .env for production
# Generate a secure key: openssl rand -hex 32
```

### 2. Start Services

```bash
docker-compose up -d
```

This starts:
- PostgreSQL with pgvector on port 5433
- Backend API on port 8000
- Frontend on port 80

### 3. Run Database Migrations

```bash
docker-compose exec backend alembic upgrade head
```

### 4. Create First Admin User

```bash
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "admin@example.com",
    "password": "YourSecurePassword123!",
    "full_name": "Admin User",
    "role": "admin"
  }'
```

### 5. Access the Application

- Frontend: http://localhost
- API: http://localhost:8000
- API Docs: http://localhost:8000/docs

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DB_PASSWORD` | PostgreSQL password | `docgen_pass_123` |
| `DATABASE_URL` | Database connection string | `postgresql+asyncpg://docgen:docgen_pass_123@db:5432/docgen` |
| `ANTHROPIC_API_KEY` | Anthropic API key for LLM | (empty) |
| `GROQ_API_KEY` | Groq API key for LLM | (empty) |
| `GENERATED_DOCS_PATH` | Path for generated documents | `./generated_docs` |
| `EMBED_MODEL` | HuggingFace embedding model | `sentence-transformers/all-MiniLM-L6-v2` |
| `EMBED_DIMENSION` | Embedding vector dimension | `384` |
| `SECRET_KEY` | JWT signing secret | `change-me-in-production` |
| `ALGORITHM` | JWT algorithm | `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Access token lifetime | `15` |
| `REFRESH_TOKEN_EXPIRE_DAYS` | Refresh token lifetime | `7` |

## Database Migrations

Migrations are stored in `backend/db/migrations/versions/`.

To apply migrations:
```bash
docker-compose exec backend alembic upgrade head
```

To create a new migration:
```bash
docker-compose exec backend alembic revision --autogenerate -m "description"
```

## Backup Instructions

### Backup PostgreSQL

```bash
docker-compose exec db pg_dump -U docgen docgen > backup_$(date +%Y%m%d_%H%M%S).sql
```

### Backup Generated Documents

```bash
tar -czf generated_docs_backup_$(date +%Y%m%d_%H%M%S).tar.gz generated_docs/
```

### Backup Reference Templates

```bash
tar -czf reference_templates_backup_$(date +%Y%m%d_%H%M%S).tar.gz reference_templates/
```

### Restore

```bash
# Restore database
docker-compose exec -T db psql -U docgen docgen < backup_20260101_000000.sql

# Restore documents
tar -xzf generated_docs_backup_20260101_000000.tar.gz
tar -xzf reference_templates_backup_20260101_000000.tar.gz
```

## User Roles

| Role | Permissions |
|------|-------------|
| `admin` | Full access to all features |
| `engineer` | Create/edit devices, upload references, generate documents |
| `viewer` | Read-only access to devices, references, history, downloads |

## Troubleshooting

### Backend won't start
```bash
# Check logs
docker-compose logs backend

# Common issue: database not ready
docker-compose restart backend
```

### Frontend shows blank page
```bash
# Check nginx logs
docker-compose logs frontend

# Verify backend is running
curl http://localhost:8000/health
```

### Database connection errors
```bash
# Verify PostgreSQL is running
docker-compose ps db

# Check database logs
docker-compose logs db
```

## Security Notes

1. **Change SECRET_KEY**: Always use a secure random key in production
2. **Use strong passwords**: Default passwords are for development only
3. **Enable HTTPS**: Use a reverse proxy (nginx/Caddy) with TLS in production
4. **Firewall**: Restrict access to ports 5433 and 8000
5. **Backups**: Schedule regular automated backups

## System Requirements

- **CPU**: 2+ cores recommended
- **RAM**: 4GB minimum, 8GB recommended
- **Storage**: 10GB minimum for OS + Docker + data
- **OS**: Linux (Ubuntu 20.04+ recommended), macOS, or Windows with WSL2
