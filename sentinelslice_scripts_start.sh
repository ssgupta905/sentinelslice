#!/usr/bin/env bash
# SentinelSlice — Quick Start
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$SCRIPT_DIR/.."

echo ""
echo "┌─────────────────────────────────────┐"
echo "│        SentinelSlice v1.0           │"
echo "│   Operational Memory Bank + Agents  │"
echo "└─────────────────────────────────────┘"
echo ""

# Check .env
if [ ! -f "$ROOT/backend/.env" ]; then
  echo "⚠  No .env found. Copying from .env.example..."
  cp "$ROOT/backend/.env.example" "$ROOT/backend/.env"
  echo "   → Edit backend/.env with your credentials before continuing."
  echo ""
fi

# Install dependencies
echo "Installing Python dependencies..."
pip install -r "$ROOT/backend/requirements.txt" -q

echo ""
echo "Starting FastAPI backend on http://localhost:8000"
echo "API docs: http://localhost:8000/docs"
echo ""
echo "Open frontend/index.html in your browser to use the UI."
echo ""

cd "$ROOT/backend"
uvicorn main:app --reload --port 8000 --host 0.0.0.0
