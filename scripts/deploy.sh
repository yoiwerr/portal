#!/usr/bin/env bash
set -euo pipefail

echo "========================================"
echo " Portal Deployment Script"
echo "========================================"

if ! command -v docker &> /dev/null; then
    echo "[ERROR] Docker is not installed."
    exit 1
fi
if ! docker compose version &> /dev/null 2>&1; then
    echo "[ERROR] docker compose plugin not found."
    exit 1
fi

if [ ! -f .env ]; then
    echo ""
    echo "[SETUP] Creating .env..."
    read -rp "  DashScope API Key (ChatLab + MakeItSmooth 共用): " DASHSCOPE_KEY
    read -rp "  Tavily API Key: " TAVILY_KEY
    read -rp "  LangSmith API Key (Enter to skip): " LANGSMITH_KEY
    read -rp "  PostgreSQL Password: " PG_PASS

    cat > .env <<EOF
DASHSCOPE_API_KEY=${DASHSCOPE_KEY}
TAVILY_API_KEY=${TAVILY_KEY}
LANGSMITH_API_KEY=${LANGSMITH_KEY}
PGSQLPASSWORD=${PG_PASS}
EOF
    echo "[OK] .env created."
else
    echo "[OK] .env found."
fi

echo ""
echo "[BUILD] Building images..."
docker compose build

echo ""
echo "[START] Starting all services..."
docker compose up -d

echo ""
echo "[WAIT] Waiting for services..."
for i in $(seq 1 15); do
    if curl -s http://localhost:80/api/v1/imported_files > /dev/null 2>&1; then
        echo "[OK] ChatLab API ready."
        break
    fi
    echo "  ... ($i/15)"
    sleep 4
done

echo ""
echo "[IMPORT] Importing ChatLab knowledge base..."
docker compose exec -T api python import_knowledge.py 2>/dev/null || echo "  (skipped)"

echo ""
echo "========================================"
echo " Deployment complete!"
echo ""
echo " Portal:       http://<IP>"
echo " ChatLab:      http://<IP>/chatlab"
echo " MakeItSmooth: http://<IP>/smooth"
echo " API Docs:     http://<IP>/api/docs"
echo ""
echo " docker compose logs -f       # tail logs"
echo " docker compose ps             # status"
echo " docker compose up -d --build  # rebuild"
echo "========================================"
