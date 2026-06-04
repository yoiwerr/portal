#!/usr/bin/env bash
set -euo pipefail

echo "========================================"
echo " Portal Deployment Script"
echo "========================================"

# ---- Prerequisites check ----
if ! command -v docker &> /dev/null; then
    echo "[ERROR] Docker is not installed."
    echo "  Install: curl -fsSL https://get.docker.com | bash"
    exit 1
fi

if ! docker compose version &> /dev/null 2>&1; then
    echo "[ERROR] docker compose plugin not found."
    echo "  Install: sudo apt install docker-compose-plugin"
    exit 1
fi

# ---- .env setup ----
if [ ! -f .env ]; then
    echo ""
    echo "[SETUP] .env file not found. Let's create one."
    echo ""
    read -rp "  DashScope API Key: " DASHSCOPE_KEY
    read -rp "  Tavily API Key: " TAVILY_KEY
    read -rp "  LangSmith API Key (press Enter to skip): " LANGSMITH_KEY
    read -rp "  PostgreSQL Password (set a strong one): " PG_PASS

    cat > .env <<EOF
DASHSCOPE_API_KEY=${DASHSCOPE_KEY}
TAVILY_API_KEY=${TAVILY_KEY}
LANGSMITH_API_KEY=${LANGSMITH_KEY}
PGSQLPASSWORD=${PG_PASS}
EOF
    echo ""
    echo "[OK] .env created."
else
    echo "[OK] .env already exists."
fi

# ---- Build & Start ----
echo ""
echo "[BUILD] Building images..."
docker compose build

echo ""
echo "[START] Starting all services..."
docker compose up -d

echo ""
echo "[WAIT] Waiting for API to be ready..."
for i in $(seq 1 12); do
    if curl -s http://localhost:80/api/v1/imported_files > /dev/null 2>&1; then
        echo "[OK] API is ready."
        break
    fi
    echo "  ... waiting ($i/12)"
    sleep 5
done

# ---- Import knowledge base ----
echo ""
echo "[IMPORT] Importing psychology knowledge base..."
docker compose exec -T api python import_knowledge.py || echo "  (import may have partially completed, check above)"

echo ""
echo "========================================"
echo " Deployment complete!"
echo ""
echo " Homepage:   http://<server-ip>"
echo " ChatLab:    http://<server-ip>/chatlab"
echo " API:        http://<server-ip>/api/v1/"
echo " API Docs:   http://<server-ip>/api/docs"
echo ""
echo " Management:"
echo "   docker compose logs -f              # tail all logs"
echo "   docker compose restart api          # restart API only"
echo "   docker compose down                 # stop everything"
echo "   docker compose up -d                # start everything"
echo "   docker compose up -d --build        # rebuild & start"
echo "========================================"
