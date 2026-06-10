#!/usr/bin/env bash
# ============================================================================
# AI-Care 孕产妇智能护理平台 — 一键启动脚本
#
# 用法:
#   bash start.sh              # 启动所有服务
#   bash start.sh --no-ai      # 跳过 AI 服务 (LLM/TTS/ASR/Embedding)
#   bash start.sh --init-db    # 启动前初始化数据库
#   bash start.sh stop         # 停止所有服务
#   bash start.sh status       # 查看服务状态
#   bash start.sh restart      # 重启所有服务
#
# 端口分配:
#   5432  - PostgreSQL (Docker)
#   6379  - Redis (Docker)
#   8080  - LLM (llama-server, Qwen3.6)
#   8081  - BGE-M3 Embedding
#   9880  - TTS (CosyVoice2)
#   9999  - Backend (FastAPI)
#   3000  - Frontend (Vite)
# ============================================================================

set -euo pipefail

# ── 目录定义 ──
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="${SCRIPT_DIR}"
WORKSPACE="$(cd "${PROJECT_DIR}/../.." && pwd)"
AI_SERVICES_SCRIPT="${WORKSPACE}/start_services_safe.sh"

# ── 服务端口 ──
BACKEND_PORT=9999
FRONTEND_PORT=3000
POSTGRES_PORT=5432
REDIS_PORT=6379

# ── PID 文件目录 ──
PID_DIR="${PROJECT_DIR}/.pids"
mkdir -p "${PID_DIR}"

# ── 日志目录 ──
LOG_DIR="${PROJECT_DIR}/logs"
mkdir -p "${LOG_DIR}"

# ── 颜色 ──
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

log_info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }
log_step()  { echo -e "${BLUE}[STEP]${NC}  $*"; }
log_svc()   { echo -e "${CYAN}[SVC]${NC}   $*"; }

# ── 端口检查 ──
check_port() {
    local port=$1
    if ss -tlnp 2>/dev/null | grep -q ":${port} " || \
       lsof -i :"${port}" &>/dev/null; then
        return 0
    fi
    return 1
}

wait_for_port() {
    local port=$1
    local name=$2
    local timeout=${3:-120}
    local elapsed=0
    log_info "等待 ${name} 就绪 (端口 ${port})..."
    while ! check_port "${port}"; do
        sleep 2
        elapsed=$((elapsed + 2))
        if [ ${elapsed} -ge ${timeout} ]; then
            log_error "${name} 启动超时 (${timeout}s)"
            return 1
        fi
    done
    log_info "${name} 已就绪 (${elapsed}s)"
    return 0
}

# ── 健康检查 ──
health_check() {
    local url=$1
    local name=$2
    local timeout=${3:-30}
    local elapsed=0
    while [ ${elapsed} -lt ${timeout} ]; do
        if curl -sf "${url}" > /dev/null 2>&1; then
            return 0
        fi
        sleep 2
        elapsed=$((elapsed + 2))
    done
    return 1
}

# ============================================================================
# 停止项目服务 (不含 AI 服务)
# ============================================================================
stop_project() {
    log_step "停止项目服务..."

    # 停止 Backend / Frontend 进程
    for name in backend frontend; do
        local pidfile="${PID_DIR}/${name}.pid"
        if [ -f "${pidfile}" ]; then
            local pid
            pid=$(cat "${pidfile}")
            if kill -0 "${pid}" 2>/dev/null; then
                log_info "停止 ${name} (PID: ${pid})"
                kill "${pid}" 2>/dev/null || true
                local wait_count=0
                while kill -0 "${pid}" 2>/dev/null && [ ${wait_count} -lt 15 ]; do
                    sleep 1
                    wait_count=$((wait_count + 1))
                done
                if kill -0 "${pid}" 2>/dev/null; then
                    log_warn "强制杀死 ${name} (PID: ${pid})"
                    kill -9 "${pid}" 2>/dev/null || true
                fi
            fi
            rm -f "${pidfile}"
        fi
    done

    # 停止 Docker 容器 (仅项目内的)
    log_info "停止 Docker 容器..."
    cd "${PROJECT_DIR}"
    if [ -f docker-compose.yml ]; then
        docker compose down 2>/dev/null || docker-compose down 2>/dev/null || true
    fi

    log_info "项目服务已停止"
}

# ============================================================================
# 停止所有服务 (含 AI 服务)
# ============================================================================
stop_all() {
    stop_project

    # 停止 AI 服务
    if [ -f "${AI_SERVICES_SCRIPT}" ]; then
        log_step "停止 AI 服务..."
        bash "${AI_SERVICES_SCRIPT}" stop 2>/dev/null || true
    fi
}

# ============================================================================
# 启动基础设施 (PostgreSQL + Redis via Docker)
# ============================================================================
start_infra() {
    log_step "启动基础设施 (PostgreSQL + Redis)..."

    cd "${PROJECT_DIR}"

    if [ ! -f docker-compose.yml ]; then
        log_error "docker-compose.yml 不存在"
        return 1
    fi

    # 仅启动 postgres 和 redis
    docker compose up -d postgres redis 2>/dev/null || \
        docker-compose up -d postgres redis 2>/dev/null || {
            log_error "Docker 启动失败，请检查 Docker 是否运行"
            return 1
        }

    # 等待 PostgreSQL 就绪
    wait_for_port ${POSTGRES_PORT} "PostgreSQL" 30 || {
        log_error "PostgreSQL 启动失败"
        return 1
    }

    # 等待 Redis 就绪
    wait_for_port ${REDIS_PORT} "Redis" 15 || {
        log_error "Redis 启动失败"
        return 1
    }

    log_info "基础设施就绪"
}

# ============================================================================
# 初始化数据库
# ============================================================================
init_database() {
    log_step "初始化数据库..."

    cd "${PROJECT_DIR}/backend"

    # 检查 Python 环境
    local python_bin="python3"
    if [ -n "${PYTHON_ENV:-}" ] && [ -x "${PYTHON_ENV}" ]; then
        python_bin="${PYTHON_ENV}"
    fi

    local flags=""
    if [ "${INIT_DB_FORCE:-0}" = "1" ]; then
        flags="--force"
    fi
    if [ "${INIT_DB_INGEST:-0}" = "1" ]; then
        flags="${flags} --ingest"
    fi

    ${python_bin} init_db.py ${flags} || {
        log_error "数据库初始化失败"
        return 1
    }

    log_info "数据库初始化完成"
}

# ============================================================================
# 启动后端 (FastAPI)
# ============================================================================
start_backend() {
    if check_port ${BACKEND_PORT}; then
        log_warn "Backend 已在运行 (端口 ${BACKEND_PORT})"
        return 0
    fi

    log_step "启动 Backend (FastAPI, 端口 ${BACKEND_PORT})..."

    cd "${PROJECT_DIR}/backend"

    # 确保 .env 存在
    if [ ! -f .env ]; then
        log_warn ".env 文件不存在，使用默认配置"
    fi

    export RELOAD="${RELOAD:-0}"
    export PORT="${BACKEND_PORT}"

    # 使用 python run.py 启动
    python run.py > "${LOG_DIR}/backend.log" 2>&1 &
    echo $! > "${PID_DIR}/backend.pid"
    log_info "Backend PID: $(cat ${PID_DIR}/backend.pid)"

    # 等待后端就绪
    wait_for_port ${BACKEND_PORT} "Backend" 30 || {
        log_error "Backend 启动失败，查看日志: ${LOG_DIR}/backend.log"
        return 1
    }
}

# ============================================================================
# 启动前端 (Vite)
# ============================================================================
start_frontend() {
    if check_port ${FRONTEND_PORT}; then
        log_warn "Frontend 已在运行 (端口 ${FRONTEND_PORT})"
        return 0
    fi

    log_step "启动 Frontend (Vite, 端口 ${FRONTEND_PORT})..."

    cd "${PROJECT_DIR}/frontend"

    # 检查 node_modules
    if [ ! -d node_modules ]; then
        log_info "安装前端依赖..."
        npm install --legacy-peer-deps
    fi

    npm run dev > "${LOG_DIR}/frontend.log" 2>&1 &
    echo $! > "${PID_DIR}/frontend.pid"
    log_info "Frontend PID: $(cat ${PID_DIR}/frontend.pid)"

    # 等待前端就绪
    wait_for_port ${FRONTEND_PORT} "Frontend" 30 || {
        log_error "Frontend 启动失败，查看日志: ${LOG_DIR}/frontend.log"
        return 1
    }
}

# ============================================================================
# 启动 AI 服务 (复用 start_services_safe.sh)
# ============================================================================
start_ai_services() {
    if [ ! -f "${AI_SERVICES_SCRIPT}" ]; then
        log_warn "AI 服务启动脚本不存在: ${AI_SERVICES_SCRIPT}"
        log_warn "跳过 AI 服务 (LLM/TTS/ASR/Embedding)"
        return 0
    fi

    log_step "启动 AI 服务 (复用 start_services_safe.sh)..."
    bash "${AI_SERVICES_SCRIPT}" start
}

# ============================================================================
# 显示服务状态
# ============================================================================
show_status() {
    echo ""
    echo "=========================================="
    echo "  AI-Care 服务状态"
    echo "=========================================="

    # 基础设施
    local infra_services=(
        "PostgreSQL|${POSTGRES_PORT}"
        "Redis|${REDIS_PORT}"
    )

    # 应用服务
    local app_services=(
        "Backend|${BACKEND_PORT}|http://127.0.0.1:${BACKEND_PORT}/docs"
        "Frontend|${FRONTEND_PORT}|http://127.0.0.1:${FRONTEND_PORT}"
    )

    echo ""
    echo "  ── 基础设施 ──"
    for entry in "${infra_services[@]}"; do
        IFS='|' read -r name port <<< "${entry}"
        if check_port "${port}"; then
            printf "    ${GREEN}●${NC} %-12s  端口 %s\n" "${name}" "${port}"
        else
            printf "    ${RED}○${NC} %-12s  端口 %s  未运行\n" "${name}" "${port}"
        fi
    done

    echo ""
    echo "  ── 应用服务 ──"
    for entry in "${app_services[@]}"; do
        IFS='|' read -r name port url <<< "${entry}"
        local pidfile="${PID_DIR}/$(echo ${name} | tr '[:upper:]' '[:lower:]').pid"
        local pid=""
        if [ -f "${pidfile}" ]; then
            pid=$(cat "${pidfile}")
        fi
        if check_port "${port}"; then
            local http_status
            http_status=$(curl -sf -o /dev/null -w "%{http_code}" "${url}" 2>/dev/null || echo "N/A")
            printf "    ${GREEN}●${NC} %-12s  端口 %-6s  PID %-7s  HTTP %s\n" "${name}" "${port}" "${pid:-N/A}" "${http_status}"
        else
            printf "    ${RED}○${NC} %-12s  端口 %-6s  未运行\n" "${name}" "${port}"
        fi
    done

    # AI 服务状态 (如果脚本存在)
    if [ -f "${AI_SERVICES_SCRIPT}" ]; then
        echo ""
        echo "  ── AI 服务 ──"
        bash "${AI_SERVICES_SCRIPT}" status 2>/dev/null | grep -E "^\s*(●|○)" | sed 's/^/  /' || true
    fi

    echo ""
}

# ============================================================================
# 打开日志终端 (每个服务一个独立窗口)
# ============================================================================
open_logs() {
    local services=("backend" "frontend")
    local names=("Backend" "Frontend")

    # 如果 AI 服务日志存在也一并打开
    local ai_log_dir="${WORKSPACE}/logs"
    for ai_svc in llm tts asr embed; do
        if [ -f "${ai_log_dir}/${ai_svc}.log" ]; then
            services+=("ai_${ai_svc}")
            names+=("AI-${ai_svc}")
        fi
    done

    log_step "打开日志终端..."

    # 检测终端模拟器
    local terminal=""
    if command -v gnome-terminal &>/dev/null; then
        terminal="gnome-terminal"
    elif command -v xfce4-terminal &>/dev/null; then
        terminal="xfce4-terminal"
    elif command -v xterm &>/dev/null; then
        terminal="xterm"
    elif command -v konsole &>/dev/null; then
        terminal="konsole"
    else
        log_error "未检测到终端模拟器 (gnome-terminal/xfce4-terminal/xterm/konsole)"
        log_info "请手动打开终端运行:"
        log_info "  tail -f ${LOG_DIR}/backend.log"
        log_info "  tail -f ${LOG_DIR}/frontend.log"
        return 1
    fi

    for i in "${!services[@]}"; do
        local svc="${services[$i]}"
        local name="${names[$i]}"
        local logfile=""

        # 确定日志文件路径
        if [[ "${svc}" == ai_* ]]; then
            logfile="${ai_log_dir}/${svc#ai_}.log"
        else
            logfile="${LOG_DIR}/${svc}.log"
        fi

        # 创建日志文件 (如不存在)
        touch "${logfile}" 2>/dev/null || true

        case "${terminal}" in
            gnome-terminal)
                gnome-terminal --title="${name} 日志" -- bash -c "tail -f '${logfile}'; exec bash" &
                ;;
            xfce4-terminal)
                xfce4-terminal --title="${name} 日志" --hold -e "tail -f '${logfile}'" &
                ;;
            xterm)
                xterm -title "${name} 日志" -e "tail -f '${logfile}'" &
                ;;
            konsole)
                konsole --new-tab -e "tail -f '${logfile}'" &
                ;;
        esac
        log_info "已打开 ${name} 日志终端"
    done

    log_info "所有日志终端已打开"
}

# ============================================================================
# 打印帮助
# ============================================================================
show_help() {
    echo "用法: bash start.sh [命令] [选项]"
    echo ""
    echo "命令:"
    echo "  start      启动所有服务 (默认)"
    echo "  stop       停止所有服务"
    echo "  status     查看服务状态"
    echo "  restart    重启所有服务"
    echo "  logs       打开独立终端实时查看各服务日志"
    echo ""
    echo "选项:"
    echo "  --no-ai       跳过 AI 服务 (LLM/TTS/ASR/Embedding)"
    echo "  --init-db     启动前初始化数据库"
    echo "  --force-db    强制重建数据库 (危险: 删除旧数据)"
    echo "  --ingest      初始化时同时执行知识库入库"
    echo "  --reload      后端开启热重载 (开发模式)"
    echo "  --help -h     显示此帮助"
    echo ""
    echo "环境变量:"
    echo "  PYTHON_ENV    指定 Python 解释器路径"
    echo "  RELOAD=1      后端热重载"
    echo ""
    echo "示例:"
    echo "  bash start.sh                     # 启动所有服务"
    echo "  bash start.sh --no-ai             # 仅启动应用服务"
    echo "  bash start.sh --init-db           # 初始化数据库后启动"
    echo "  bash start.sh --init-db --ingest  # 初始化 + 知识库入库"
    echo "  bash start.sh stop                # 停止所有服务"
}

# ============================================================================
# 主流程
# ============================================================================
main() {
    local cmd="start"
    local skip_ai=false

    # 解析参数
    while [[ $# -gt 0 ]]; do
        case "$1" in
            start|stop|status|restart|logs)
                cmd="$1"
                shift
                ;;
            --no-ai)
                skip_ai=true
                shift
                ;;
            --init-db)
                export INIT_DB_FORCE=0
                export INIT_DB_INGEST=0
                shift
                ;;
            --force-db)
                export INIT_DB_FORCE=1
                export INIT_DB_INGEST=0
                shift
                ;;
            --ingest)
                export INIT_DB_INGEST=1
                shift
                ;;
            --reload)
                export RELOAD=1
                shift
                ;;
            --help|-h)
                show_help
                exit 0
                ;;
            *)
                log_error "未知参数: $1"
                show_help
                exit 1
                ;;
        esac
    done

    case "${cmd}" in
        stop)
            stop_all
            exit 0
            ;;
        status)
            show_status
            exit 0
            ;;
        logs)
            open_logs
            exit 0
            ;;
        restart)
            stop_all
            sleep 2
            ;;
        start)
            ;;
    esac

    echo ""
    echo "=========================================="
    echo "  AI-Care 孕产妇智能护理平台"
    echo "=========================================="
    echo "  PostgreSQL : ${POSTGRES_PORT}"
    echo "  Redis      : ${REDIS_PORT}"
    echo "  Backend    : ${BACKEND_PORT}"
    echo "  Frontend   : ${FRONTEND_PORT}"
    echo "  AI 服务    : $([ "${skip_ai}" = true ] && echo '跳过' || echo '启动')"
    echo "=========================================="
    echo ""

    # ── 阶段 1: 基础设施 ──
    start_infra

    # ── 阶段 2: 数据库初始化 (可选) ──
    if [ "${INIT_DB_FORCE:-0}" = "1" ] || [ "${INIT_DB_INGEST:-0}" = "1" ]; then
        init_database
    fi

    # ── 阶段 3: 应用服务 ──
    start_backend
    start_frontend

    # ── 阶段 4: AI 服务 (可选) ──
    if [ "${skip_ai}" = false ]; then
        start_ai_services
    fi

    # ── 最终状态 ──
    show_status

    log_info "日志目录: ${LOG_DIR}/"
    log_info "查看后端日志: tail -f ${LOG_DIR}/backend.log"
    log_info "查看前端日志: tail -f ${LOG_DIR}/frontend.log"
    log_info "停止服务: bash start.sh stop"
    log_info "查看状态: bash start.sh status"
}

main "$@"
