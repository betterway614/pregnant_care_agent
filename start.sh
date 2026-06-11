#!/usr/bin/env bash
# ============================================================================
# AI-Care 孕产妇智能护理平台 — 一键启动脚本
#
# 用法:
#   bash start.sh                  # 启动所有服务
#   bash start.sh --no-ai          # 跳过 AI 服务
#   bash start.sh --init-db        # 启动前初始化数据库
#   bash start.sh stop             # 停止所有服务
#   bash start.sh status           # 查看服务状态（含 PID + CPU/MEM）
#   bash start.sh restart          # 重启所有服务
#   bash start.sh monitor          # 后台监控守护进程
#   bash start.sh monitor --auto-restart  # 监控 + 异常自动重启
#   bash start.sh dashboard        # 实时仪表盘
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

# ══════════════════════════════════════════════════════════════════════════════
# 全局常量 & 初始化
# ══════════════════════════════════════════════════════════════════════════════

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="${SCRIPT_DIR}"
WORKSPACE="$(cd "${PROJECT_DIR}/../.." && pwd)"
AI_SERVICES_SCRIPT="${WORKSPACE}/start_services_safe.sh"

# 端口
BACKEND_PORT=9999
FRONTEND_PORT=3000
POSTGRES_PORT=5432
REDIS_PORT=6379

# 目录
PID_DIR="${PROJECT_DIR}/.pids"
LOG_DIR="${PROJECT_DIR}/logs"
mkdir -p "${PID_DIR}" "${LOG_DIR}"

# 监控文件
MONITOR_STATE="${PID_DIR}/.monitor_state"
MONITOR_LOG="${LOG_DIR}/monitor.log"

# 颜色
C_RED='\033[0;31m'; C_GREEN='\033[0;32m'; C_YELLOW='\033[1;33m'
C_BLUE='\033[0;34m';  C_CYAN='\033[0;36m';  C_NC='\033[0m'

log_info()  { echo -e "${C_GREEN}[INFO]${C_NC}  $*"; }
log_warn()  { echo -e "${C_YELLOW}[WARN]${C_NC}  $*"; }
log_error() { echo -e "${C_RED}[ERROR]${C_NC} $*"; }
log_step()  { echo -e "${C_BLUE}[STEP]${C_NC}  $*"; }

# ══════════════════════════════════════════════════════════════════════════════
# 基础工具函数
# ══════════════════════════════════════════════════════════════════════════════

check_port() {
    local port=$1
    ss -tlnp 2>/dev/null | grep -q ":${port} " || lsof -i :"${port}" &>/dev/null
}

# 从端口反查真实监听 PID（解决 npm run dev / python 等 fork 子进程后 $! 不准的问题）
resolve_port_pid() {
    local port=$1 pid
    # 兼容 gawk 和 mawk：用 gensub/sub 提取 pid=NUM，避免 GNU-only 的 match 三参数
    pid=$(ss -tlnp 2>/dev/null | awk -v p=":${port}" '
        $0 ~ p { sub(/.*pid=/, ""); sub(/[, ].*/, ""); print; exit }')
    [ -z "${pid}" ] && pid=$(lsof -ti :"${port}" 2>/dev/null | head -1)
    echo "${pid}"
}

# 获取服务最佳 PID：real.pid > pid 文件 > 端口反查
get_service_pid() {
    local svc=$1
    local real_pf="${PID_DIR}/${svc}.real.pid"
    local pf="${PID_DIR}/${svc}.pid"
    local pid=""
    [ -f "${real_pf}" ] && pid=$(cat "${real_pf}")
    [ -z "${pid}" ] && [ -f "${pf}" ] && pid=$(cat "${pf}")
    [ -z "${pid}" ] && pid=$(resolve_port_pid "${2:-0}")
    echo "${pid}"
}

# 获取进程资源: CPU%|MEM%|RSS_KB|ELAPSED
proc_stats() {
    local pid=$1
    [ -z "${pid}" ] || ! kill -0 "${pid}" 2>/dev/null && { echo "N/A|N/A|N/A|N/A"; return; }
    local stats
    stats=$(ps -p "${pid}" -o pcpu=,pmem=,rss=,etime= --no-headers 2>/dev/null) || { echo "N/A|N/A|N/A|N/A"; return; }
    echo "${stats}" | awk '{printf "%s|%s|%s|%s", $1, $2, $3, $4}'
}

wait_for_port() {
    local port=$1 name=$2 timeout=${3:-120} elapsed=0
    log_info "等待 ${name} 就绪 (端口 ${port})..."
    while ! check_port "${port}"; do
        sleep 2; elapsed=$((elapsed + 2))
        [ ${elapsed} -ge ${timeout} ] && { log_error "${name} 启动超时 (${timeout}s)"; return 1; }
    done
    log_info "${name} 已就绪 (${elapsed}s)"
}

health_check() {
    local url=$1 name=$2 timeout=${3:-30} elapsed=0
    while [ ${elapsed} -lt ${timeout} ]; do
        curl -sf "${url}" >/dev/null 2>&1 && return 0
        sleep 2; elapsed=$((elapsed + 2))
    done
    return 1
}

# 优雅杀进程：先 SIGTERM，超时后 SIGKILL
graceful_kill() {
    local pid=$1 label=${2:-进程}
    if [ -z "${pid}" ] || ! kill -0 "${pid}" 2>/dev/null; then return 0; fi
    log_info "停止 ${label} (PID: ${pid})"
    kill "${pid}" 2>/dev/null || true
    local waited=0
    while kill -0 "${pid}" 2>/dev/null && [ ${waited} -lt 15 ]; do
        sleep 1; waited=$((waited + 1))
    done
    if kill -0 "${pid}" 2>/dev/null; then
        log_warn "强制杀死 ${label} (PID: ${pid})"
        kill -9 "${pid}" 2>/dev/null || true
    fi
}

# 保存 PID：写入 .pid 文件，端口就绪后再写 .real.pid
save_pids() {
    local svc=$1 shell_pid=$2 port=$3
    echo "${shell_pid}" > "${PID_DIR}/${svc}.pid"
    local real_pid
    real_pid=$(resolve_port_pid "${port}")
    if [ -n "${real_pid}" ]; then
        echo "${real_pid}" > "${PID_DIR}/${svc}.real.pid"
        [ "${real_pid}" != "${shell_pid}" ] && log_info "${svc} 实际监听 PID: ${real_pid}"
    fi
}

# ══════════════════════════════════════════════════════════════════════════════
# 服务启动 / 停止
# ══════════════════════════════════════════════════════════════════════════════

# 通用服务启动器
# 参数: name dir_cmd port timeout logfile extra_setup_fn
launch_service() {
    local name=$1 dir=$2 cmd=$3 port=$4 timeout=${5:-30} logfile=${6:-} setup=${7:-}

    if check_port "${port}"; then
        local existing_pid
        existing_pid=$(resolve_port_pid "${port}")
        log_warn "${name} 已在运行 (端口 ${port}, PID: ${existing_pid:-unknown})"
        # 补写 PID 文件
        [ -n "${existing_pid}" ] && echo "${existing_pid}" > "${PID_DIR}/${name}.real.pid"
        return 0
    fi

    log_step "启动 ${name} (端口 ${port})..."
    cd "${dir}"

    # 可选的准备工作（如 npm install）
    [ -n "${setup}" ] && eval "${setup}"

    # 确保日志文件存在
    [ -n "${logfile}" ] && touch "${logfile}" 2>/dev/null

    ${cmd} > "${logfile:-/dev/null}" 2>&1 &
    local shell_pid=$!
    log_info "${name} 启动 (shell PID: ${shell_pid})"

    wait_for_port "${port}" "${name}" "${timeout}" || {
        log_error "${name} 启动失败，查看日志: ${logfile:-无}"
        return 1
    }

    save_pids "${name}" "${shell_pid}" "${port}"
}

# ── 基础设施 (PostgreSQL + Redis via Docker) ──

start_infra() {
    log_step "启动基础设施 (PostgreSQL + Redis)..."

    cd "${PROJECT_DIR}"
    [ ! -f docker-compose.yml ] && { log_error "docker-compose.yml 不存在"; return 1; }

    # 捕获错误输出以便诊断
    local compose_err
    compose_err=$(mktemp)
    if ! docker compose up -d postgres redis 2>"${compose_err}"; then
        if ! docker-compose up -d postgres redis 2>"${compose_err}"; then
            log_error "Docker 启动失败:"
            cat "${compose_err}" | while IFS= read -r line; do log_error "  ${line}"; done
            rm -f "${compose_err}"
            log_error "请检查: 1) Docker 是否运行  2) docker compose 是否可用"
            return 1
        fi
    fi
    rm -f "${compose_err}"

    wait_for_port ${POSTGRES_PORT} "PostgreSQL" 30 || return 1
    wait_for_port ${REDIS_PORT} "Redis" 15 || return 1
    log_info "基础设施就绪"
}

# ── 数据库初始化 ──

init_database() {
    log_step "初始化数据库..."
    cd "${PROJECT_DIR}/backend"

    local python_bin="python3"
    [ -n "${PYTHON_ENV:-}" ] && [ -x "${PYTHON_ENV}" ] && python_bin="${PYTHON_ENV}"

    local flags=""
    [ "${INIT_DB_FORCE:-0}" = "1" ] && flags="--force"
    [ "${INIT_DB_INGEST:-0}" = "1" ] && flags="${flags} --ingest"

    ${python_bin} init_db.py ${flags} || { log_error "数据库初始化失败"; return 1; }
    log_info "数据库初始化完成"
}

# ── Backend ──

start_backend() {
    launch_service "backend" \
        "${PROJECT_DIR}/backend" \
        "python run.py" \
        ${BACKEND_PORT} 30 \
        "${LOG_DIR}/backend.log" \
        "[ ! -f .env ] && log_warn '.env 不存在，使用默认配置'; export RELOAD=${RELOAD:-0}; export PORT=${BACKEND_PORT}"
}

# ── Frontend ──

start_frontend() {
    launch_service "frontend" \
        "${PROJECT_DIR}/frontend" \
        "npm run dev" \
        ${FRONTEND_PORT} 45 \
        "${LOG_DIR}/frontend.log" \
        "[ ! -d node_modules ] && { log_info '安装前端依赖...'; npm install --legacy-peer-deps; }"
}

# ── AI 服务 ──

start_ai_services() {
    if [ ! -f "${AI_SERVICES_SCRIPT}" ]; then
        log_warn "AI 服务启动脚本不存在: ${AI_SERVICES_SCRIPT}"
        log_warn "跳过 AI 服务 (LLM/TTS/ASR/Embedding)"
        return 0
    fi
    log_step "启动 AI 服务..."
    bash "${AI_SERVICES_SCRIPT}" start
}

# ── 停止 ──

stop_project() {
    log_step "停止项目服务..."

    for name in backend frontend; do
        for suffix in real.pid pid; do
            local pf="${PID_DIR}/${name}.${suffix}"
            [ -f "${pf}" ] && graceful_kill "$(cat "${pf}")" "${name}" && rm -f "${pf}"
        done
    done

    cd "${PROJECT_DIR}"
    if [ -f docker-compose.yml ]; then
        log_info "停止 Docker 容器..."
        docker compose down 2>/dev/null || docker-compose down 2>/dev/null || true
    fi
    log_info "项目服务已停止"
}

stop_all() {
    stop_monitor
    stop_project
    if [ -f "${AI_SERVICES_SCRIPT}" ]; then
        log_step "停止 AI 服务..."
        bash "${AI_SERVICES_SCRIPT}" stop 2>/dev/null || true
    fi
}

# ══════════════════════════════════════════════════════════════════════════════
# 服务状态 & 仪表盘
# ══════════════════════════════════════════════════════════════════════════════

# 显示单个应用服务行 (复用於 status + dashboard)
print_service_row() {
    local name=$1 port=$2 url=$3 svc=$4 fmt=${5:-status}

    local pid
    pid=$(get_service_pid "${svc}" "${port}")

    if check_port "${port}"; then
        local http_status cpu mem rss uptime
        http_status=$(curl -sf -o /dev/null -w "%{http_code}" "${url}" 2>/dev/null || echo "N/A")
        IFS='|' read -r cpu mem rss uptime <<< "$(proc_stats "${pid}")"

        case "${fmt}" in
            dashboard)
                printf "║ ${C_GREEN}●${C_NC} %-12s │ 端口 %-5s │ PID %-8s │ CPU %5s │ MEM %5s │ UP %-10s │ HTTP %-3s ║\n" \
                    "${name}" "${port}" "${pid:-N/A}" "${cpu}" "${mem}" "${uptime}" "${http_status}"
                ;;
            *)
                printf "    ${C_GREEN}●${C_NC} %-12s  端口 %-6s  PID %-8s  HTTP %-4s  CPU %-5s  MEM %-5s  RSS %-8s  UP %s\n" \
                    "${name}" "${port}" "${pid:-N/A}" "${http_status}" "${cpu}" "${mem}" "${rss}" "${uptime}"
                local shell_pid=""
                [ -f "${PID_DIR}/${svc}.pid" ] && shell_pid=$(cat "${PID_DIR}/${svc}.pid")
                if [ -n "${pid}" ] && [ -n "${shell_pid}" ] && [ "${pid}" != "${shell_pid}" ]; then
                    printf "    ${C_CYAN}↳${C_NC} shell PID: %-8s (包装进程)\n" "${shell_pid}"
                fi
                ;;
        esac
    else
        case "${fmt}" in
            dashboard) printf "║ ${C_RED}○${C_NC} %-12s │ 端口 %-5s │ %-44s ║\n" "${name}" "${port}" "未运行" ;;
            *)         printf "    ${C_RED}○${C_NC} %-12s  端口 %-6s  未运行\n" "${name}" "${port}" ;;
        esac
    fi
}

show_status() {
    echo ""
    echo "=========================================="
    echo "  AI-Care 服务状态"
    echo "=========================================="

    echo ""
    echo "  ── 基础设施 ──"
    for entry in "PostgreSQL|${POSTGRES_PORT}" "Redis|${REDIS_PORT}"; do
        IFS='|' read -r name port <<< "${entry}"
        if check_port "${port}"; then
            printf "    ${C_GREEN}●${C_NC} %-12s  端口 %s\n" "${name}" "${port}"
        else
            printf "    ${C_RED}○${C_NC} %-12s  端口 %s  未运行\n" "${name}" "${port}"
        fi
    done

    echo ""
    echo "  ── 应用服务 ──"
    print_service_row "Backend"  ${BACKEND_PORT}  "http://127.0.0.1:${BACKEND_PORT}/docs" "backend"
    print_service_row "Frontend" ${FRONTEND_PORT} "http://127.0.0.1:${FRONTEND_PORT}"       "frontend"

    if [ -f "${AI_SERVICES_SCRIPT}" ]; then
        echo ""
        echo "  ── AI 服务 ──"
        bash "${AI_SERVICES_SCRIPT}" status 2>/dev/null | grep -E "^\s*(●|○)" | sed 's/^/  /' || true
    fi

    echo ""
    echo "  PID 目录: ${PID_DIR}/"
    echo "  日志目录: ${LOG_DIR}/"
    echo ""
}

# ── 实时仪表盘 ──

live_dashboard() {
    local interval=${1:-3}
    echo ""
    log_info "实时仪表盘已启动 (刷新 ${interval}s, Ctrl+C 退出)"
    sleep 1

    trap 'echo ""; log_info "仪表盘已退出"; return 0' INT

    while true; do
        clear 2>/dev/null || true
        echo "╔══════════════════════════════════════════════════════════════╗"
        echo "║           AI-Care 实时服务仪表盘  ($(date '+%H:%M:%S'))          ║"
        echo "╠══════════════════════════════════════════════════════════════╣"

        print_service_row "Backend"  ${BACKEND_PORT}  "http://127.0.0.1:${BACKEND_PORT}/docs" "backend"  dashboard
        print_service_row "Frontend" ${FRONTEND_PORT} "http://127.0.0.1:${FRONTEND_PORT}"       "frontend" dashboard

        for entry in "PostgreSQL|${POSTGRES_PORT}" "Redis|${REDIS_PORT}"; do
            IFS='|' read -r name port <<< "${entry}"
            if check_port "${port}"; then
                printf "║ ${C_GREEN}●${C_NC} %-12s │ 端口 %-5s │ %-44s ║\n" "${name}" "${port}" "正常"
            else
                printf "║ ${C_RED}○${C_NC} %-12s │ 端口 %-5s │ %-44s ║\n" "${name}" "${port}" "未运行"
            fi
        done

        # 监控行
        local mon_line="监控: 未启动"
        if [ -f "${MONITOR_STATE}" ]; then
            local mon_pid
            mon_pid=$(grep -E '^mon_pid=' "${MONITOR_STATE}" 2>/dev/null | cut -d= -f2 || true)
            if [ -n "${mon_pid}" ] && kill -0 "${mon_pid}" 2>/dev/null; then
                mon_line="监控: ${C_GREEN}运行中${C_NC} (PID: ${mon_pid})"
            else
                mon_line="监控: ${C_RED}已停止${C_NC}"
            fi
        fi
        printf "║ %-58s ║\n" "${mon_line}"

        echo "╚══════════════════════════════════════════════════════════════╝"
        echo "  q=退出 | m=启动监控 | s=状态 | 刷新=${interval}s"

        read -t "${interval}" -n 1 key 2>/dev/null || true
        case "${key}" in
            q|Q) break ;;
            m|M) start_monitor 10 false ;;
            s|S) break; show_status ;;
        esac
    done
    trap - INT
}

# ══════════════════════════════════════════════════════════════════════════════
# 日志终端
# ══════════════════════════════════════════════════════════════════════════════

open_logs() {
    local services=("backend" "frontend")
    local names=("Backend" "Frontend")
    local ai_log_dir="${WORKSPACE}/logs"

    for ai_svc in llm tts asr embed; do
        [ -f "${ai_log_dir}/${ai_svc}.log" ] && services+=("ai_${ai_svc}") && names+=("AI-${ai_svc}")
    done

    log_step "打开日志终端..."

    # 检测终端
    local terminal=""
    for t in gnome-terminal xfce4-terminal xterm konsole; do
        command -v "${t}" &>/dev/null && { terminal="${t}"; break; }
    done
    if [ -z "${terminal}" ]; then
        log_error "未检测到终端模拟器 (gnome-terminal/xfce4-terminal/xterm/konsole)"
        log_info "请手动: tail -f ${LOG_DIR}/backend.log"
        log_info "        tail -f ${LOG_DIR}/frontend.log"
        return 1
    fi

    for i in "${!services[@]}"; do
        local svc="${services[$i]}" name="${names[$i]}" logfile
        [[ "${svc}" == ai_* ]] && logfile="${ai_log_dir}/${svc#ai_}.log" || logfile="${LOG_DIR}/${svc}.log"
        touch "${logfile}" 2>/dev/null || true

        case "${terminal}" in
            gnome-terminal) gnome-terminal --title="${name} 日志" -- bash -c "tail -f '${logfile}'; exec bash" & ;;
            xfce4-terminal) xfce4-terminal --title="${name} 日志" --hold -e "tail -f '${logfile}'" & ;;
            xterm)           xterm -title "${name} 日志" -e "tail -f '${logfile}'" & ;;
            konsole)         konsole --new-tab -e "tail -f '${logfile}'" & ;;
        esac
        log_info "已打开 ${name} 日志终端"
    done
}

# ══════════════════════════════════════════════════════════════════════════════
# 服务监控 (后台 watchdog)
# ══════════════════════════════════════════════════════════════════════════════

# 从监控状态文件读取键值
monitor_state_get() {
    local key=$1 default=${2:-}
    local val
    val=$(grep -E "^${key}=" "${MONITOR_STATE}" 2>/dev/null | head -1 | cut -d= -f2-)
    echo "${val:-${default}}"
}

start_monitor() {
    local interval=${1:-10}
    local auto_restart=${2:-false}

    if [ -f "${MONITOR_STATE}" ]; then
        local existing_pid
        existing_pid=$(monitor_state_get "mon_pid")
        [ -z "${existing_pid}" ] && existing_pid=$(head -1 "${MONITOR_STATE}" 2>/dev/null)
        if [ -n "${existing_pid}" ] && kill -0 "${existing_pid}" 2>/dev/null; then
            log_warn "监控已在运行 (PID: ${existing_pid})"
            log_info "查看: tail -f ${MONITOR_LOG}"
            return 0
        fi
        rm -f "${MONITOR_STATE}"
    fi

    log_step "启动监控守护进程 (间隔 ${interval}s, 自动重启: ${auto_restart})"

    # 在子进程中运行监控循环
    (
        set +e  # 关闭 errexit，避免非关键命令导致子进程退出

        cat > "${MONITOR_STATE}" <<EOF
${$}
interval=${interval}
auto_restart=${auto_restart}
started=$(date +%s)
restart_backend=0
restart_frontend=0
last_tick=0
EOF

        # 监控内部状态变量（子进程隔离，无需 local）
        r_be=0; r_fe=0; down_be=0; down_fe=0

        # 重启 Backend
        restart_backend_fn() {
            r_be=$((r_be + 1))
            _now=$(date '+%Y-%m-%d %H:%M:%S')
            echo "[${_now}] ${C_YELLOW}↻${C_NC} 尝试重启 Backend (第 ${r_be} 次)..." | tee -a "${MONITOR_LOG}"
            rm -f "${PID_DIR}/backend.pid" "${PID_DIR}/backend.real.pid"
            cd "${PROJECT_DIR}/backend"
            python run.py > "${LOG_DIR}/backend.log" 2>&1 &
            echo $! > "${PID_DIR}/backend.pid"
            sleep 3
            if check_port ${BACKEND_PORT}; then
                _new_pid=$(resolve_port_pid ${BACKEND_PORT})
                [ -n "${_new_pid}" ] && echo "${_new_pid}" > "${PID_DIR}/backend.real.pid"
                echo "[${_now}] ${C_GREEN}✓${C_NC} Backend 恢复 (PID: ${_new_pid:-N/A})" | tee -a "${MONITOR_LOG}"
            else
                echo "[${_now}] ${C_RED}✗${C_NC} Backend 重启失败" | tee -a "${MONITOR_LOG}"
            fi
        }

        # 重启 Frontend
        restart_frontend_fn() {
            r_fe=$((r_fe + 1))
            _now=$(date '+%Y-%m-%d %H:%M:%S')
            echo "[${_now}] ${C_YELLOW}↻${C_NC} 尝试重启 Frontend (第 ${r_fe} 次)..." | tee -a "${MONITOR_LOG}"
            rm -f "${PID_DIR}/frontend.pid" "${PID_DIR}/frontend.real.pid"
            cd "${PROJECT_DIR}/frontend"
            npm run dev > "${LOG_DIR}/frontend.log" 2>&1 &
            echo $! > "${PID_DIR}/frontend.pid"
            sleep 5
            if check_port ${FRONTEND_PORT}; then
                _new_pid=$(resolve_port_pid ${FRONTEND_PORT})
                [ -n "${_new_pid}" ] && echo "${_new_pid}" > "${PID_DIR}/frontend.real.pid"
                echo "[${_now}] ${C_GREEN}✓${C_NC} Frontend 恢复 (PID: ${_new_pid:-N/A})" | tee -a "${MONITOR_LOG}"
            else
                echo "[${_now}] ${C_RED}✗${C_NC} Frontend 重启失败" | tee -a "${MONITOR_LOG}"
            fi
        }

        while true; do
            now=$(date '+%Y-%m-%d %H:%M:%S')
            changed=false

            # ── Backend ──
            if ! check_port ${BACKEND_PORT}; then
                was_pid=$(get_service_pid "backend" "${BACKEND_PORT}")
                echo "[${now}] ${C_RED}✗${C_NC} Backend 不可达 (端口 ${BACKEND_PORT}, PID: ${was_pid:-N/A})" | tee -a "${MONITOR_LOG}"
                changed=true; down_be=$(date +%s)
                [ "${auto_restart}" = "true" ] && restart_backend_fn
            elif [ "${down_be}" -ne 0 ]; then
                echo "[${now}] ${C_GREEN}✓${C_NC} Backend 恢复 (中断 $(( $(date +%s) - down_be ))s)" | tee -a "${MONITOR_LOG}"
                down_be=0
            fi

            # ── Frontend ──
            if ! check_port ${FRONTEND_PORT}; then
                was_pid=$(get_service_pid "frontend" "${FRONTEND_PORT}")
                echo "[${now}] ${C_RED}✗${C_NC} Frontend 不可达 (端口 ${FRONTEND_PORT}, PID: ${was_pid:-N/A})" | tee -a "${MONITOR_LOG}"
                changed=true; down_fe=$(date +%s)
                [ "${auto_restart}" = "true" ] && restart_frontend_fn
            elif [ "${down_fe}" -ne 0 ]; then
                echo "[${now}] ${C_GREEN}✓${C_NC} Frontend 恢复 (中断 $(( $(date +%s) - down_fe ))s)" | tee -a "${MONITOR_LOG}"
                down_fe=0
            fi

            # ── 心跳 (每 60s) ──
            if [ "${changed}" = false ]; then
                tick=$(date +%s)
                last_tick=$(monitor_state_get "last_tick" 0)
                if [ $((tick - last_tick)) -ge 60 ]; then
                    echo "[${now}] ${C_GREEN}♥${C_NC} 所有服务正常" | tee -a "${MONITOR_LOG}"
                    sed -i "s/^last_tick=.*/last_tick=${tick}/" "${MONITOR_STATE}" 2>/dev/null || true
                fi
            fi

            # ── 持久化计数 ──
            sed -i "s/^restart_backend=.*/restart_backend=${r_be}/" "${MONITOR_STATE}" 2>/dev/null || true
            sed -i "s/^restart_frontend=.*/restart_frontend=${r_fe}/" "${MONITOR_STATE}" 2>/dev/null || true

            sleep "${interval}"
        done
    ) &
    local mon_pid=$!
    disown "${mon_pid}" 2>/dev/null || true

    sleep 1
    if kill -0 "${mon_pid}" 2>/dev/null; then
        # 记录监控 PID 到状态文件
        sed -i "s/^mon_pid=.*/mon_pid=${mon_pid}/" "${MONITOR_STATE}" 2>/dev/null || echo "mon_pid=${mon_pid}" >> "${MONITOR_STATE}"
        log_info "监控已启动 (PID: ${mon_pid})"
        log_info "监控日志: ${MONITOR_LOG}"
        log_info "停止监控: bash start.sh monitor-stop"
    else
        log_error "监控守护进程启动失败"
        return 1
    fi
}

stop_monitor() {
    [ ! -f "${MONITOR_STATE}" ] && return 0

    local mon_pid
    mon_pid=$(monitor_state_get "mon_pid")
    [ -z "${mon_pid}" ] && mon_pid=$(head -1 "${MONITOR_STATE}" 2>/dev/null)

    if [ -n "${mon_pid}" ] && kill -0 "${mon_pid}" 2>/dev/null; then
        graceful_kill "${mon_pid}" "监控守护进程"
    fi
    rm -f "${MONITOR_STATE}"
    log_info "监控已停止"
}

show_monitor_status() {
    echo ""
    echo "=========================================="
    echo "  监控守护进程状态"
    echo "=========================================="

    if [ ! -f "${MONITOR_STATE}" ]; then
        echo -e "  状态: ${C_RED}未运行${C_NC}"
        echo ""
        echo "  启动监控: bash start.sh monitor"
        echo "=========================================="
        echo ""
        return 0
    fi

    local mon_pid interval auto_restart started r_be r_fe
    mon_pid=$(monitor_state_get "mon_pid" "N/A")
    interval=$(monitor_state_get "interval" "N/A")
    auto_restart=$(monitor_state_get "auto_restart" "N/A")
    started=$(monitor_state_get "started" "0")
    r_be=$(monitor_state_get "restart_backend" "0")
    r_fe=$(monitor_state_get "restart_frontend" "0")

    local alive uptime_str=""
    if [ -n "${mon_pid}" ] && [ "${mon_pid}" != "N/A" ] && kill -0 "${mon_pid}" 2>/dev/null; then
        alive="${C_GREEN}运行中${C_NC}"
        local elapsed=$(( $(date +%s) - started ))
        uptime_str=$(printf "%dh %dm %ds" $((elapsed/3600)) $(((elapsed%3600)/60)) $((elapsed%60)))
    else
        alive="${C_RED}已退出${C_NC}"
        uptime_str="N/A"
    fi

    echo "  守护进程 PID: ${mon_pid}  [${alive}]"
    echo "  运行时长:     ${uptime_str}"
    echo "  检查间隔:     ${interval}s"
    echo "  自动重启:     ${auto_restart}"
    echo "  Backend 重启: ${r_be} 次"
    echo "  Frontend 重启: ${r_fe} 次"
    echo "  监控日志:     ${MONITOR_LOG}"
    echo ""
    echo "  最近 10 条日志:"
    echo "  ──────────────────────────────────────────"
    if [ -f "${MONITOR_LOG}" ]; then
        tail -10 "${MONITOR_LOG}" 2>/dev/null | while IFS= read -r line; do echo "  ${line}"; done
    else
        echo "  (无日志)"
    fi
    echo "  ──────────────────────────────────────────"
    echo ""
}

# ══════════════════════════════════════════════════════════════════════════════
# 帮助
# ══════════════════════════════════════════════════════════════════════════════

show_help() {
    cat <<'EOF'
用法: bash start.sh [命令] [选项]

命令:
  start          启动所有服务 (默认)
  stop           停止所有服务
  status         查看服务状态 (PID + CPU/MEM/运行时长)
  restart        重启所有服务
  logs           打开独立终端实时查看各服务日志
  monitor        启动后台监控守护进程 (watchdog)
  monitor-stop   停止监控守护进程
  monitor-status 查看监控守护进程状态
  dashboard      打开实时仪表盘 (Ctrl+C 退出)

选项:
  --no-ai           跳过 AI 服务 (LLM/TTS/ASR/Embedding)
  --init-db         启动前初始化数据库
  --force-db        强制重建数据库 (危险: 删除旧数据)
  --ingest          初始化时同时执行知识库入库
  --reload          后端开启热重载 (开发模式)
  --auto-restart    配合 monitor: 服务异常时自动重启
  --interval=N      监控/仪表盘刷新间隔秒数 (默认: 监控10s, 仪表盘3s)
  --help -h         显示此帮助

环境变量:
  PYTHON_ENV    指定 Python 解释器路径
  RELOAD=1      后端热重载

示例:
  bash start.sh                          # 启动所有服务
  bash start.sh --no-ai                  # 仅启动应用服务
  bash start.sh --init-db                # 初始化数据库后启动
  bash start.sh --init-db --ingest       # 初始化 + 知识库入库
  bash start.sh stop                     # 停止所有服务
  bash start.sh monitor                  # 启动后台监控
  bash start.sh monitor --auto-restart   # 启动监控 + 自动重启
  bash start.sh dashboard                # 实时仪表盘
EOF
}

# ══════════════════════════════════════════════════════════════════════════════
# 主流程
# ══════════════════════════════════════════════════════════════════════════════

main() {
    local cmd="start" skip_ai=false auto_restart=false
    local monitor_interval=10 dashboard_interval=3

    while [[ $# -gt 0 ]]; do
        case "$1" in
            start|stop|status|restart|logs|monitor|monitor-stop|monitor-status|dashboard)
                cmd="$1"; shift ;;
            --no-ai)       skip_ai=true; shift ;;
            --auto-restart) auto_restart=true; shift ;;
            --interval=*)  monitor_interval="${1#*=}"; dashboard_interval="${1#*=}"; shift ;;
            --init-db)     export INIT_DB_FORCE=0; export INIT_DB_INGEST=0; shift ;;
            --force-db)    export INIT_DB_FORCE=1; export INIT_DB_INGEST=0; shift ;;
            --ingest)      export INIT_DB_INGEST=1; shift ;;
            --reload)      export RELOAD=1; shift ;;
            --help|-h)     show_help; exit 0 ;;
            *)             log_error "未知参数: $1"; show_help; exit 1 ;;
        esac
    done

    # 单步命令 (不需要启动流程)
    case "${cmd}" in
        stop)            stop_all; exit 0 ;;
        status)          show_status; exit 0 ;;
        logs)            open_logs; exit 0 ;;
        monitor)         start_monitor "${monitor_interval}" "${auto_restart}"; exit 0 ;;
        monitor-stop)    stop_monitor; exit 0 ;;
        monitor-status)  show_monitor_status; exit 0 ;;
        dashboard)       live_dashboard "${dashboard_interval}"; exit 0 ;;
        restart)         stop_all; sleep 2 ;;
        start)           ;;
    esac

    # ── 启动流程 ──
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

    start_infra || exit 1

    if [ "${INIT_DB_FORCE:-0}" = "1" ] || [ "${INIT_DB_INGEST:-0}" = "1" ]; then
        init_database || exit 1
    fi

    start_backend  || exit 1
    start_frontend || exit 1

    [ "${skip_ai}" = false ] && start_ai_services

    show_status

    log_info "日志目录: ${LOG_DIR}/"
    log_info "停止服务: bash start.sh stop"
    log_info "查看状态: bash start.sh status"
    log_info "启动监控: bash start.sh monitor --auto-restart"
}

main "$@"
