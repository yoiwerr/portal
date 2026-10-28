#!/usr/bin/env bash
# ============================================================
# Portal 首次部署脚本
# 用法: chmod +x scripts/deploy.sh && ./scripts/deploy.sh
# ============================================================
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
ok()   { echo -e "${GREEN}[OK]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
err()  { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

echo "========================================"
echo " Portal — 首次部署"
echo " $(date '+%Y-%m-%d %H:%M:%S')"
echo "========================================"

# ── 前置检查 ──
command -v docker &>/dev/null  || err "Docker 未安装"
docker compose version &>/dev/null 2>&1 || err "docker compose 插件未安装"

cd "$(dirname "$0")/.."
ROOT=$(pwd)
echo "工作目录: $ROOT"

# ── .env ──
if [ ! -f .env ]; then
    echo ""
    echo "==== 配置环境变量 ===="
    echo "（按 Enter 跳过可选项）"
    echo ""
    read -rp "  PostgreSQL 密码 (必填): " PG_PASS
    if [ -z "$PG_PASS" ]; then err "PostgreSQL 密码不能为空"; fi

    read -rp "  DashScope API Key (Embedding + Rerank，必填): " DASHSCOPE_KEY
    read -rp "  DeepSeek API Key (dude LLM): " DS_KEY
    read -rp "  OpenAI API Key (可选): " OAI_KEY

    cat > .env <<EOF
# ============================================================
# Portal — 环境变量
# 生成于 $(date '+%Y-%m-%d %H:%M:%S')
# ============================================================

# --- LLM Provider ---
LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=${DS_KEY}
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
DEEPSEEK_MODEL=deepseek-chat
DASHSCOPE_API_KEY=${DASHSCOPE_KEY}
OPENAI_API_KEY=${OAI_KEY}
OPENAI_MODEL=gpt-4o

# --- PostgreSQL ---
PGSQLPASSWORD=${PG_PASS}
DB_HOST=postgres
DB_PORT=5432
DB_NAME=alfred

# --- Agent (dude) ---
MEMORY_ENABLED=true
SANDBOX_ENABLED=false
MAX_TOOL_ROUNDS=10
AGENT_TIMEOUT=180.0

# --- RAG ---
RAG_TOP_K=3
SIMILARITY_THRESHOLD=0.6
RERANK_ENABLED=true
RERANK_MODEL=qwen3-rerank
RERANK_TOP_K=5
RERANK_COARSE_K=20
EOF
    ok ".env 已创建"
else
    ok ".env 已存在"
fi

# ── 检查 HTTPS 证书 ──
CERT_PATH="/etc/letsencrypt/live/yoiwerr.site/fullchain.pem"
CERT_OK=false
if [ -f "$CERT_PATH" ]; then
    ok "SSL 证书已存在"
    CERT_OK=true
else
    warn "SSL 证书未找到 ($CERT_PATH)"
    echo "  nginx HTTPS 端口不会启动，先完成 HTTP 验证再配证书。"
    echo "  部署后运行: sudo certbot certonly --standalone -d your-domain.com"
fi

# ── 拉取镜像 & 构建 ──
echo ""
echo "==== 构建镜像 ===="
docker compose build 2>&1 | tail -20

# ── 启动 ──
echo ""
echo "==== 启动服务 ===="
docker compose up -d 2>&1

# ── 等待就绪 ──
echo ""
echo "==== 等待服务就绪 ===="

# dude API
echo "  等待 dude API..."
for i in $(seq 1 20); do
    if docker compose exec -T dude-api curl -sf http://localhost:8000/api/health >/dev/null 2>&1; then
        ok "dude API 就绪"
        break
    fi
    if [ "$i" -eq 20 ]; then warn "dude API 未就绪，请检查: docker compose logs dude-api"; fi
    sleep 3
done

# nginx
echo "  等待 nginx..."
for i in $(seq 1 10); do
    if curl -sf http://localhost/ >/dev/null 2>&1; then
        ok "nginx 就绪"
        break
    fi
    if [ "$i" -eq 10 ]; then warn "nginx 未就绪（可能是 SSL 证书缺失）"; fi
    sleep 2
done

# ── 完成 ──
echo ""
echo "========================================"
echo " 部署完成"
echo ""
echo " 外网访问:"
echo "   http://<服务器IP>              — 首页"
echo "   http://<服务器IP>/journal/     — Journal"
echo "   http://<服务器IP>/dude      — dude"
echo ""
echo " 常用命令:"
echo "   docker compose logs -f          — 实时日志"
echo "   docker compose ps               — 服务状态"
echo "   ./scripts/update.sh             — 日常更新"
echo ""
if [ "$CERT_OK" = false ]; then
    echo " ⚠ 下一步: 配置域名和 HTTPS 证书"
    echo "   参考 CONTROLWEB.md 第二部分"
    echo ""
fi
echo "========================================"
