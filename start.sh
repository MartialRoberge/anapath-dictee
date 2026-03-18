#!/bin/bash
set -e

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Kill any existing processes on our ports
echo "Nettoyage des ports 5173 et 8000..."
lsof -ti:5173,8000 2>/dev/null | xargs kill -9 2>/dev/null || true
sleep 1

# Start backend
echo "Lancement du backend (FastAPI) sur http://localhost:8000"
cd "$ROOT_DIR/backend"
python3 -m uvicorn main:app --reload --port 8000 &
BACKEND_PID=$!

# Start frontend
echo "Lancement du frontend (Vite) sur http://localhost:5173"
cd "$ROOT_DIR/frontend"
npm run dev -- --port 5173 &
FRONTEND_PID=$!

echo ""
echo "Backend  : http://localhost:8000"
echo "Frontend : http://localhost:5173"
echo ""
echo "Appuyez sur Ctrl+C pour tout arreter."

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit" INT TERM
wait
