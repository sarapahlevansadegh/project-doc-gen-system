#!/usr/bin/env bash
# Demo environment setup script for DocGen System.
# Run this script to initialize the demo environment from scratch.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "=== DocGen Demo Environment Setup ==="
echo ""

# 1. Copy .env.example if .env does not exist
if [ ! -f "$PROJECT_DIR/.env" ]; then
    cp "$PROJECT_DIR/.env.example" "$PROJECT_DIR/.env"
    echo "Created .env from .env.example"
    echo "  >> Edit .env to add your API keys (ANTHROPIC_API_KEY, GROQ_API_KEY, etc.)"
    echo ""
fi

# 2. Create Python virtual environment
if [ ! -d "$PROJECT_DIR/.venv" ]; then
    echo "Creating Python virtual environment..."
    python3 -m venv "$PROJECT_DIR/.venv"
    echo "Virtual environment created at .venv/"
fi

# 3. Install dependencies
echo "Installing Python dependencies..."
"$PROJECT_DIR/.venv/bin/pip" install --upgrade pip
"$PROJECT_DIR/.venv/bin/pip" install -e "$PROJECT_DIR"

# 4. Start Docker services
echo "Starting Docker services (PostgreSQL + pgvector)..."
cd "$PROJECT_DIR"
docker compose up -d db
echo "Waiting for database to be ready..."
sleep 5

# 5. Run database migrations
echo "Running database migrations..."
"$PROJECT_DIR/.venv/bin/python" -m alembic upgrade head

# 6. Seed demo data
echo "Seeding demo data..."
"$PROJECT_DIR/.venv/bin/python" -m backend.scripts.seed_demo

# 7. Start all services
echo "Starting all Docker services..."
docker compose up -d

echo ""
echo "=== Demo Environment Ready ==="
echo "  Frontend: http://localhost"
echo "  Backend API: http://localhost:8000"
echo "  API Docs: http://localhost:8000/scalar"
echo ""
echo "  Demo accounts:"
echo "    admin@docgen.demo / admin123"
echo "    engineer@docgen.demo / engineer123"
echo ""
echo "  Upload a reference .docx document via the References page,"
echo "  then select a device and generate a document."