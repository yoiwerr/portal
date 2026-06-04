#!/bin/bash
# ============================================================
# Portal — Local Dev Launcher
# Starts: FastAPI (8000) + Streamlit (8501) + Homepage (8080)
# Ctrl+C to stop all
# ============================================================

set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"
APP_DIR="$ROOT/ChatHistoryAnalyst"

# Colors
GREEN='\033[0;32m'
CYAN='\033[0;36m'
NC='\033[0m'

cleanup() {
    echo ""
    echo -e "${CYAN}[STOP] Shutting down...${NC}"
    kill $API_PID $STREAMLIT_PID $STATIC_PID 2>/dev/null
    wait $API_PID $STREAMLIT_PID $STATIC_PID 2>/dev/null
    echo -e "${GREEN}All services stopped.${NC}"
    exit 0
}
trap cleanup SIGINT SIGTERM

# ── Check prerequisites ──────────────────────────────
if ! command -v python3 &>/dev/null && ! command -v python &>/dev/null; then
    echo "Error: Python not found. Install Python 3.12+"
    exit 1
fi
PYTHON=$(command -v python3 || command -v python)

if [ ! -f "$APP_DIR/.env" ]; then
    echo -e "${CYAN}[SETUP] Creating .env from .env.example (edit it with your API keys)${NC}"
    cp "$APP_DIR/.env.example" "$APP_DIR/.env"
    echo "  →  Edit $APP_DIR/.env and re-run"
    exit 1
fi

# ── Ensure local DB connection ────────────────────────
export DB_HOST=localhost
export DB_PORT=5432
export API_BASE_URL=http://localhost:8000/api/v1

# ── Start FastAPI ─────────────────────────────────────
echo -e "${GREEN}[API] Starting FastAPI on http://localhost:8000${NC}"
cd "$APP_DIR"
$PYTHON -m uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload &
API_PID=$!
sleep 2

# ── Start Streamlit ───────────────────────────────────
echo -e "${GREEN}[UI]  Starting Streamlit on http://localhost:8501${NC}"
$PYTHON -m streamlit run front/frontend.py \
    --server.port 8501 \
    --server.headless true \
    --browser.gatherUsageStats false &
STREAMLIT_PID=$!

# ── Start Homepage ────────────────────────────────────
echo -e "${GREEN}[WWW] Starting Homepage on http://localhost:8080${NC}"
cd "$ROOT/static"
$PYTHON -m http.server 8080 &
STATIC_PID=$!

echo ""
echo -e "=============================================="
echo -e "  ${GREEN}✓ All services running${NC}"
echo -e "  Homepage → ${CYAN}http://localhost:8080${NC}"
echo -e "  ChatLab  → ${CYAN}http://localhost:8501${NC}"
echo -e "  API Docs → ${CYAN}http://localhost:8000/api/docs${NC}"
echo -e "  Press Ctrl+C to stop all"
echo -e "=============================================="

wait
