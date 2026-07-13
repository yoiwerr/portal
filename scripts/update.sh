#!/usr/bin/env bash
# ============================================================
# Portal 日常更新脚本
# 用法:
#   本地 push 代码后, SSH 到服务器:
#     cd ~/portal && git pull && ./scripts/update.sh
#
#   或一键:
#     cd ~/portal && git pull && ./scripts/update.sh
# ============================================================
set -euo pipefail

# ── 参数处理 ──
FORCE_REBUILD=false
case "${1:-}" in
    --rebuild|-f) FORCE_REBUILD=true; shift ;;
esac

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
ok()   { echo -e "${GREEN}[OK]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
err()  { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

echo "========================================"
echo " Portal — 更新"
echo " $(date '+%Y-%m-%d %H:%M:%S')"
echo "========================================"

cd "$(dirname "$0")/.."
ROOT=$(pwd)
echo "工作目录: $ROOT"

# ── 检查 git 状态 ──
if ! git rev-parse --git-dir >/dev/null 2>&1; then
    err "不是 git 仓库"
fi

BRANCH=$(git branch --show-current)
COMMIT=$(git rev-parse --short HEAD)
echo "分支: $BRANCH | 提交: $COMMIT"

# 抓取远程最新，然后对比与本地 HEAD 的差异
git fetch origin 2>/dev/null || true

# 保存远程 ORIG，pull / merge 后 diff
REMOTE_HEAD=$(git rev-parse origin/"$BRANCH" 2>/dev/null || echo "")
LOCAL_HEAD=$(git rev-parse HEAD)

if [ "$LOCAL_HEAD" != "$REMOTE_HEAD" ] && [ -n "$REMOTE_HEAD" ]; then
    echo ""
    echo "远程有新提交: $(git log --oneline "$LOCAL_HEAD".."$REMOTE_HEAD" | head -3)"
    read -rp "是否现在 git pull? [Y/n] " ANS
    if [ "${ANS:-Y}" != "n" ] && [ "${ANS:-Y}" != "N" ]; then
        git pull
        ok "git pull 完成"
    else
        warn "跳过 git pull，使用当前代码"
    fi
else
    ok "已是最新"
fi

# ── 检查 .env ──
if [ ! -f .env ]; then
    err ".env 不存在 — 请先运行 ./scripts/deploy.sh 完成首次部署"
fi

# ── 检测哪些子项目有代码变更 ──
# 用 pull 前的 HEAD 对比当前 HEAD，准确捕获本次更新范围
CHANGED_FILES=$(git diff --name-only "$LOCAL_HEAD" HEAD 2>/dev/null || echo "")

rebuild_all=false
rebuild_chatlab=false
rebuild_specific=false

if $FORCE_REBUILD; then
    rebuild_all=true
    echo "→ --rebuild: 强制全部重建"
elif [ -z "$CHANGED_FILES" ]; then
    # 无法通过 git diff 检测（如首次更新或 shallow clone）
    echo ""
    echo "无法检测变更范围。"
    echo "  [A] 全部重建 (安全)"
    echo "  [S] 仅重建 MakeItSpecific"
    echo "  [C] 仅重建 ChatLab"
    echo "  [N] 不重建，仅重启"
    read -rp "选择 [A/s/c/n]: " CHOICE
    case "${CHOICE:-A}" in
        [Aa]) rebuild_all=true ;;
        [Ss]) rebuild_specific=true ;;
        [Cc]) rebuild_chatlab=true ;;
        *)    rebuild_all=false ;;
    esac
else
    echo "检测到以下变更:"
    echo "$CHANGED_FILES" | head -20
    echo ""

    if echo "$CHANGED_FILES" | grep -q "^MakeItSpecific/"; then
        rebuild_specific=true
        echo "  → MakeItSpecific 有变更，将重建"
    fi
    if echo "$CHANGED_FILES" | grep -q "^ChatHistoryAnalyst/"; then
        rebuild_chatlab=true
        echo "  → ChatLab 有变更，将重建"
    fi
    if echo "$CHANGED_FILES" | grep -qE "^(nginx/|static/|docker-compose.yml|\.env)"; then
        rebuild_all=true
        echo "  → Portal 基础设施有变更，将重建 nginx"
    fi
    if ! $rebuild_specific && ! $rebuild_chatlab && ! $rebuild_all; then
        echo ""
        ok "无镜像需要重建（仅文档/脚本变更）"
        echo "如需强制重建: ./scripts/update.sh --rebuild"
        exit 0
    fi
fi

# ── 构建 & 重启 ──
echo ""
echo "==== 构建 & 重启 ===="

# 拉取最新基础镜像
docker compose pull nginx 2>/dev/null || true

if $rebuild_all; then
    echo "→ 重建全部服务"
    docker compose build
    docker compose up -d --force-recreate
elif $rebuild_specific && $rebuild_chatlab; then
    echo "→ 重建 specific-api + api"
    docker compose build specific-api
    docker compose build api
    docker compose up -d --force-recreate specific-api api
    # 重启 nginx 以刷新 upstream 缓存
    docker compose restart nginx
elif $rebuild_specific; then
    echo "→ 重建 specific-api"
    docker compose build specific-api
    docker compose up -d --force-recreate specific-api
    docker compose restart nginx
elif $rebuild_chatlab; then
    echo "→ 重建 ChatLab (api + streamlit)"
    docker compose build api
    docker compose build streamlit
    docker compose up -d --force-recreate api streamlit
    docker compose restart nginx
fi

# ── 清理旧镜像（保留最近 2 个版本）──
echo ""
echo "==== 清理旧镜像 ===="
docker image prune -f --filter "until=24h" 2>/dev/null || true

# ── 健康检查 ──
echo ""
echo "==== 健康检查 ===="

check_url() {
    local url=$1 label=$2
    if curl -sfk -o /dev/null "$url" 2>/dev/null; then
        ok "$label ($url)"
        return 0
    else
        warn "$label 未就绪 ($url)"
        return 1
    fi
}

sleep 3  # 等容器启动
check_url "http://localhost/api/health"           "ChatLab API"
check_url "http://localhost/specific/api/health"  "MakeItSpecific API"
check_url "http://localhost"                       "Portal 首页"

# ── 显示状态 ──
echo ""
echo "==== 服务状态 ===="
docker compose ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}" 2>/dev/null || docker compose ps

# ── 最近日志（错误）──
echo ""
echo "==== 最近错误日志 ===="
docker compose logs --tail=20 2>/dev/null | grep -iE "error|fatal|traceback" | tail -10 || echo "(无错误)"

echo ""
echo "========================================"
echo " 更新完成"
echo "========================================"
echo ""
echo " 常用命令:"
echo "   docker compose logs -f specific-api   — MakeItSpecific 日志"
echo "   docker compose logs -f api            — ChatLab API 日志"
echo "   docker compose logs -f nginx          — nginx 日志"
echo "   docker compose ps                     — 服务状态"
echo "   docker compose restart specific-api   — 单独重启"
echo ""
