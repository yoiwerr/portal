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
    read -rp "  DashScope API Key (必填): " DASHSCOPE_KEY
    read -rp "  PostgreSQL 密码 (必填): " PG_PASS
    read -rp "  DeepSeek API Key (可选): " DS_KEY
    read -rp "  OpenAI API Key (可选): " OAI_KEY

    cat > .env <<EOF
# LLM
DASHSCOPE_API_KEY=${DASHSCOPE_KEY}
LLM_PROVIDER=auto
LLM_MODEL=qwen-plus

# DeepSeek (可选)
DEEPSEEK_API_KEY=${DS_KEY}
DEEPSEEK_MODEL=deepseek-chat

# OpenAI (可选)
OPENAI_API_KEY=${OAI_KEY}
OPENAI_MODEL=gpt-4o

# PostgreSQL
PGSQLPASSWORD=${PG_PASS}
DB_HOST=postgres
DB_PORT=5432

# Agent
MEMORY_ENABLED=true
SANDBOX_ENABLED=false
MAX_TOOL_ROUNDS=10

# Rerank (复用 DashScope key)
RERANK_ENABLED=true
EOF
    ok ".env 已创建"
else
    ok ".env 已存在"
fi

# ── 拉取镜像 & 构建 ──
echo ""
echo "==== 构建镜像 ===="
docker compose build

# ── 启动 ──
echo ""
echo "==== 启动服务 ===="
docker compose up -d

# ── 等待就绪 ──
echo ""
echo "==== 等待服务就绪 ===="
for i in $(seq 1 20); do
    if curl -sf http://localhost/api/health >/dev/null 2>&1; then
        ok "ChatLab API 就绪"
        break
    fi
    if [ "$i" -eq 20 ]; then warn "ChatLab API 未就绪，请检查日志"; fi
    sleep 3
done

for i in $(seq 1 15); do
    if curl -sf http://localhost/specific/api/health >/dev/null 2>&1; then
        ok "MakeItSpecific API 就绪"
        break
    fi
    if [ "$i" -eq 15 ]; then warn "MakeItSpecific API 未就绪，请检查日志"; fi
    sleep 3
done

# ── 导入 ChatLab 知识库 ──
echo ""
echo "==== 导入知识库 ===="
docker compose exec -T api python import_knowledge.py 2>/dev/null || warn "跳过（可能已导入）"

# ── 完成 ──
echo ""
echo "========================================"
echo " 部署完成"
echo ""
echo " https://yoiwerr.site          — 首页"
echo " https://yoiwerr.site/chatlab   — ChatLab"
echo " https://yoiwerr.site/specific  — MakeItSpecific"
echo " https://yoiwerr.site/api/docs  — API 文档"
echo ""
echo " docker compose logs -f          — 实时日志"
echo " docker compose ps               — 服务状态"
echo " ./scripts/update.sh             — 日常更新"
echo "========================================"
