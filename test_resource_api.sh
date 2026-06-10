#!/usr/bin/env bash
# ============================================================================
# 资源管理 API 测试脚本
# ============================================================================

set -euo pipefail

BASE_URL="http://localhost:9999/api/v1/admin/resource"
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

# 获取 JWT Token
get_token() {
    local response
    response=$(curl -s -X POST "http://localhost:9999/api/v1/auth/login" \
        -H "Content-Type: application/json" \
        -d '{"username": "admin", "password": "admin123"}')
    echo "$response" | python3 -c "import sys, json; print(json.load(sys.stdin).get('access_token', ''))" 2>/dev/null
}

# 测试函数
test_endpoint() {
    local method=$1
    local endpoint=$2
    local data=$3
    local description=$4

    echo -n "测试: $description ... "

    local response
    if [ "$method" = "GET" ]; then
        response=$(curl -s -w "\n%{http_code}" "$BASE_URL$endpoint" \
            -H "Authorization: Bearer $TOKEN")
    else
        response=$(curl -s -w "\n%{http_code}" -X "$method" "$BASE_URL$endpoint" \
            -H "Authorization: Bearer $TOKEN" \
            -H "Content-Type: application/json" \
            -d "$data")
    fi

    local http_code
    http_code=$(echo "$response" | tail -1)
    local body
    body=$(echo "$response" | head -n -1)

    if [ "$http_code" -ge 200 ] && [ "$http_code" -lt 300 ]; then
        echo -e "${GREEN}✓${NC} ($http_code)"
    else
        echo -e "${RED}✗${NC} ($http_code)"
        echo "  Response: $body"
    fi
}

# 主流程
echo "=========================================="
echo "  资源管理 API 测试"
echo "=========================================="
echo ""

# 获取 Token
echo "获取管理员 Token ..."
TOKEN=$(get_token)

if [ -z "$TOKEN" ]; then
    echo -e "${RED}无法获取 Token，请确保后端服务已启动${NC}"
    exit 1
fi

echo -e "${GREEN}Token 获取成功${NC}"
echo ""

# 测试资源监控端点
echo "=== 资源监控 ==="
test_endpoint "GET" "/status" "" "获取系统资源状态"
test_endpoint "GET" "/services" "" "获取所有服务配置"
test_endpoint "GET" "/policy" "" "获取当前策略"
test_endpoint "GET" "/adjustments" "" "获取优化建议"
test_endpoint "GET" "/history?limit=10" "" "获取历史数据"
test_endpoint "GET" "/llm-analysis?type=pattern" "" "获取 LLM 分析"

echo ""
echo "=== 监控控制 ==="
test_endpoint "POST" "/monitoring/start" '{"interval": 5}' "启动监控"
test_endpoint "POST" "/monitoring/stop" "" "停止监控"

echo ""
echo "=== 策略管理 ==="
test_endpoint "PUT" "/policy" '{"policy": "conservative"}' "切换策略"
test_endpoint "PUT" "/services/bge_m3" '{"batch_size": 128}' "更新服务配置"

echo ""
echo "=== 预警管理 ==="
test_endpoint "GET" "/alerts" "" "获取预警列表"
test_endpoint "GET" "/alerts/stats" "" "获取预警统计"

echo ""
echo "=== 报告生成 ==="
test_endpoint "POST" "/report/agent" '{"from_date": "2026-06-01", "to_date": "2026-06-10"}' "生成智能体报告"
test_endpoint "POST" "/report/device" '{"from_date": "2026-06-01", "to_date": "2026-06-10"}' "生成设备报告"
test_endpoint "GET" "/report/history" "" "获取报告历史"

echo ""
echo "=========================================="
echo "  测试完成"
echo "=========================================="
