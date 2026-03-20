#!/bin/bash
# =============================================================================
# API Flow Test Script - 用户端 API 全流程测试
# =============================================================================
# 功能：按流程顺序调用所有用户端接口，自动处理 token 存储
# 用法：./api_flow_test.sh [BASE_URL]
# =============================================================================

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 配置
BASE_URL="${1:-http://localhost:8000}"
TOKEN_FILE=".harness/.api_token"
RESULTS=()
PASS_COUNT=0
FAIL_COUNT=0

# 输出函数
print_header() {
    echo ""
    echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
    echo -e "${BLUE}  $1${NC}"
    echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
}

print_test() {
    echo -e "\n${YELLOW}▶ $1${NC}"
    echo -e "  URL: $2"
}

print_result() {
    local status=$1
    local message=$2
    if [ "$status" == "success" ]; then
        echo -e "  ${GREEN}✓ $message${NC}"
        ((PASS_COUNT++))
    else
        echo -e "  ${RED}✗ $message${NC}"
        ((FAIL_COUNT++))
    fi
}

# 初始化 token 文件目录
mkdir -p .harness

# 存储token
save_token() {
    local response=$1
    # 尝试从登录响应中提取 token
    token=$(echo "$response" | grep -o '"token":"[^"]*"' | sed 's/"token":"//;s/"$//')
    if [ -n "$token" ]; then
        echo "$token" > "$TOKEN_FILE"
        echo -e "  ${GREEN}✓ Token 已存储到 $TOKEN_FILE${NC}"
    fi
}

# 获取存储的token
get_token() {
    if [ -f "$TOKEN_FILE" ]; then
        cat "$TOKEN_FILE"
    else
        echo ""
    fi
}

# HTTP 请求函数
http_get() {
    local url=$1
    local auth=$2
    local cmd="curl -s -w '\n%{http_code}' -X GET '$url' -H 'Accept: application/json'"

    if [ -n "$auth" ]; then
        cmd="$cmd -H 'Authorization: Bearer $auth'"
    fi

    eval "$cmd"
}

http_post() {
    local url=$1
    local data=$2
    local auth=$3
    local cmd="curl -s -w '\n%{http_code}' -X POST '$url' -H 'Accept: application/json' -H 'Content-Type: application/json'"

    if [ -n "$auth" ]; then
        cmd="$cmd -H 'Authorization: Bearer $auth'"
    fi

    if [ -n "$data" ]; then
        cmd="$cmd -d '$data'"
    fi

    eval "$cmd"
}

# 解析响应
parse_response() {
    local response=$1
    local http_code=$(echo "$response" | tail -1)
    local body=$(echo "$response" | sed '$d')

    echo "$http_code|$body"
}

# =============================================================================
# 开始测试
# =============================================================================
print_header "API 全流程测试"

echo -e "${BLUE}测试环境:${NC} $BASE_URL"
echo -e "${BLUE}Token 文件:${NC} $TOKEN_FILE"
echo ""

# =============================================================================
# 阶段 1: 公共接口测试（无需认证）
# =============================================================================
print_header "阶段 1: 公共接口测试"

# 1.1 首页配置
print_test "GET /api/v1/app/home/index - 首页配置" "$BASE_URL/api/v1/app/home/index"
response=$(http_get "$BASE_URL/api/v1/app/home/index")
parsed=$(parse_response "$response")
http_code=$(echo "$parsed" | cut -d'|' -f1)
body=$(echo "$parsed" | cut -d'|' -f2-)

if [ "$http_code" == "200" ]; then
    print_result "success" "HTTP $http_code - 首页配置获取成功"
    # 检查返回数据结构
    if echo "$body" | grep -q '"categories"'; then
        echo -e "    ${GREEN}└ 返回数据包含 categories${NC}"
    fi
else
    print_result "fail" "HTTP $http_code - 请求失败"
fi

# 1.2 预约时间段
print_test "GET /api/v1/app/booking-days - 预约时间段" "$BASE_URL/api/v1/app/booking-days"
response=$(http_get "$BASE_URL/api/v1/app/booking-days")
parsed=$(parse_response "$response")
http_code=$(echo "$parsed" | cut -d'|' -f1)
body=$(echo "$parsed" | cut -d'|' -f2-)

if [ "$http_code" == "200" ]; then
    print_result "success" "HTTP $http_code - 预约时间段获取成功"
    if echo "$body" | grep -q '"dateStr"'; then
        echo -e "    ${GREEN}└ 返回数据包含预约日期${NC}"
    fi
else
    print_result "fail" "HTTP $http_code - 请求失败"
fi

# =============================================================================
# 阶段 2: 认证接口测试
# =============================================================================
print_header "阶段 2: 认证接口测试"

# 2.1 登录
print_test "POST /api/v1/app/auth/login - 用户登录" "$BASE_URL/api/v1/app/auth/login"
# 使用 Alipay 平台测试模式（platform=2）
login_data='{"code":"test_code_13111111111","platform":2}'
response=$(http_post "$BASE_URL/api/v1/app/auth/login" "$login_data")
parsed=$(parse_response "$response")
http_code=$(echo "$parsed" | cut -d'|' -f1)
body=$(echo "$parsed" | cut -d'|' -f2-)

if [ "$http_code" == "200" ]; then
    print_result "success" "HTTP $http_code - 登录成功"
    save_token "$body"
elif [ "$http_code" == "422" ]; then
    print_result "fail" "HTTP $http_code - 验证失败（可能需要真实登录凭证）"
    # 创建模拟 token 以便后续测试
    echo "mock_test_token_for_api_flow_test" > "$TOKEN_FILE"
    echo -e "  ${YELLOW}⚠ 使用模拟 token 继续测试${NC}"
else
    print_result "fail" "HTTP $http_code - 登录失败"
    # 创建模拟 token 以便后续测试
    echo "mock_test_token_for_api_flow_test" > "$TOKEN_FILE"
    echo -e "  ${YELLOW}⚠ 使用模拟 token 继续测试${NC}"
fi

# 获取 token
TOKEN=$(get_token)
if [ -z "$TOKEN" ]; then
    echo -e "${RED}错误: 无法获取 token，后续认证测试将失败${NC}"
    exit 1
fi
echo -e "${GREEN}当前 Token: ${TOKEN:0:20}...${NC}"

# =============================================================================
# 阶段 3: 地址接口测试（需要认证）
# =============================================================================
print_header "阶段 3: 地址接口测试"

# 3.1 地址列表
print_test "GET /api/v1/app/address/list - 地址列表" "$BASE_URL/api/v1/app/address/list"
response=$(http_get "$BASE_URL/api/v1/app/address/list" "$TOKEN")
parsed=$(parse_response "$response")
http_code=$(echo "$parsed" | cut -d'|' -f1)
body=$(echo "$parsed" | cut -d'|' -f2-)

if [ "$http_code" == "200" ]; then
    print_result "success" "HTTP $http_code - 地址列表获取成功"
elif [ "$http_code" == "401" ]; then
    print_result "fail" "HTTP $http_code - 认证失败（token 无效）"
else
    print_result "fail" "HTTP $http_code - 请求失败"
fi

# 3.2 保存地址
print_test "POST /api/v1/app/address/save - 保存地址" "$BASE_URL/api/v1/app/address/save"
address_data='{"name":"测试用户","phone":"13800138000","province":"广东省","city_id":440100,"city":"广州市","district":"天河区","detail":"天河路123号","is_default":1}'
response=$(http_post "$BASE_URL/api/v1/app/address/save" "$address_data" "$TOKEN")
parsed=$(parse_response "$response")
http_code=$(echo "$parsed" | cut -d'|' -f1)
body=$(echo "$parsed" | cut -d'|' -f2-)

if [ "$http_code" == "200" ]; then
    print_result "success" "HTTP $http_code - 地址保存成功"
    # 提取地址ID用于后续订单测试
    ADDRESS_ID=$(echo "$body" | grep -o '"id":[0-9]*' | head -1 | sed 's/"id"://')
    if [ -n "$ADDRESS_ID" ]; then
        echo -e "    ${GREEN}└ 地址ID: $ADDRESS_ID${NC}"
    fi
elif [ "$http_code" == "401" ]; then
    print_result "fail" "HTTP $http_code - 认证失败"
elif [ "$http_code" == "422" ]; then
    print_result "fail" "HTTP $http_code - 验证失败"
    echo -e "    ${YELLOW}└ 响应: $body${NC}"
else
    print_result "fail" "HTTP $http_code - 请求失败"
fi

# =============================================================================
# 阶段 4: 订单接口测试（需要认证）
# =============================================================================
print_header "阶段 4: 订单接口测试"

# 4.1 提交订单
print_test "POST /api/v1/app/order/submit - 提交订单" "$BASE_URL/api/v1/app/order/submit"
# 使用当前日期生成预约时间
RESERVE_DATE=$(date -d "+1 day" +"%Y-%m-%d" 2>/dev/null || date -v+1d +"%Y-%m-%d" 2>/dev/null || date +"%Y-%m-%d")
RESERVE_TIME="${RESERVE_DATE} 08:00-11:00"

# 如果没有地址ID，使用默认值1
if [ -z "$ADDRESS_ID" ]; then
    ADDRESS_ID=1
fi

order_data="{\"address_id\":$ADDRESS_ID,\"category_id\":1,\"est_weight\":\"1-5kg\",\"reserve_time\":\"$RESERVE_TIME\",\"remark\":\"API流程测试订单\"}"
response=$(http_post "$BASE_URL/api/v1/app/order/submit" "$order_data" "$TOKEN")
parsed=$(parse_response "$response")
http_code=$(echo "$parsed" | cut -d'|' -f1)
body=$(echo "$parsed" | cut -d'|' -f2-)

if [ "$http_code" == "200" ]; then
    print_result "success" "HTTP $http_code - 订单提交成功"
    # 提取订单ID用于后续测试
    ORDER_ID=$(echo "$body" | grep -o '"order_id":[0-9]*' | sed 's/"order_id"://')
    if [ -n "$ORDER_ID" ]; then
        echo -e "    ${GREEN}└ 订单ID: $ORDER_ID${NC}"
    fi
elif [ "$http_code" == "401" ]; then
    print_result "fail" "HTTP $http_code - 认证失败"
elif [ "$http_code" == "422" ]; then
    print_result "fail" "HTTP $http_code - 验证失败"
    echo -e "    ${YELLOW}└ 响应: $body${NC}"
else
    print_result "fail" "HTTP $http_code - 请求失败"
fi

# 4.2 订单列表
print_test "GET /api/v1/app/order/list - 订单列表" "$BASE_URL/api/v1/app/order/list"
response=$(http_get "$BASE_URL/api/v1/app/order/list" "$TOKEN")
parsed=$(parse_response "$response")
http_code=$(echo "$parsed" | cut -d'|' -f1)
body=$(echo "$parsed" | cut -d'|' -f2-)

if [ "$http_code" == "200" ]; then
    print_result "success" "HTTP $http_code - 订单列表获取成功"
    # 如果没有订单ID，尝试从列表获取
    if [ -z "$ORDER_ID" ]; then
        ORDER_ID=$(echo "$body" | grep -o '"id":[0-9]*' | head -1 | sed 's/"id"://')
        if [ -n "$ORDER_ID" ]; then
            echo -e "    ${GREEN}└ 从列表获取订单ID: $ORDER_ID${NC}"
        fi
    fi
elif [ "$http_code" == "401" ]; then
    print_result "fail" "HTTP $http_code - 认证失败"
else
    print_result "fail" "HTTP $http_code - 请求失败"
fi

# =============================================================================
# 阶段 5: 用户接口测试（需要认证）
# =============================================================================
print_header "阶段 5: 用户接口测试"

# 5.1 用户信息
print_test "GET /api/v1/app/user/info - 用户信息" "$BASE_URL/api/v1/app/user/info"
response=$(http_get "$BASE_URL/api/v1/app/user/info" "$TOKEN")
parsed=$(parse_response "$response")
http_code=$(echo "$parsed" | cut -d'|' -f1)
body=$(echo "$parsed" | cut -d'|' -f2-)

if [ "$http_code" == "200" ]; then
    print_result "success" "HTTP $http_code - 用户信息获取成功"
    if echo "$body" | grep -q '"balance"'; then
        echo -e "    ${GREEN}└ 返回数据包含用户余额${NC}"
    fi
elif [ "$http_code" == "401" ]; then
    print_result "fail" "HTTP $http_code - 认证失败"
else
    print_result "fail" "HTTP $http_code - 请求失败"
fi

# 5.2 余额流水
print_test "GET /api/v1/app/user/bill_list - 余额流水" "$BASE_URL/api/v1/app/user/bill_list"
response=$(http_get "$BASE_URL/api/v1/app/user/bill_list" "$TOKEN")
parsed=$(parse_response "$response")
http_code=$(echo "$parsed" | cut -d'|' -f1)
body=$(echo "$parsed" | cut -d'|' -f2-)

if [ "$http_code" == "200" ]; then
    print_result "success" "HTTP $http_code - 余额流水获取成功"
elif [ "$http_code" == "401" ]; then
    print_result "fail" "HTTP $http_code - 认证失败"
else
    print_result "fail" "HTTP $http_code - 请求失败"
fi

# =============================================================================
# 阶段 6: 助力接口测试（需要认证）
# =============================================================================
print_header "阶段 6: 助力接口测试"

# 6.1 助力访问
print_test "POST /api/v1/app/share/visit - 助力访问" "$BASE_URL/api/v1/app/share/visit"

# 如果没有订单ID，使用默认值1
if [ -z "$ORDER_ID" ]; then
    ORDER_ID=1
fi

share_data="{\"order_id\":$ORDER_ID}"
response=$(http_post "$BASE_URL/api/v1/app/share/visit" "$share_data" "$TOKEN")
parsed=$(parse_response "$response")
http_code=$(echo "$parsed" | cut -d'|' -f1)
body=$(echo "$parsed" | cut -d'|' -f2-)

if [ "$http_code" == "200" ]; then
    print_result "success" "HTTP $http_code - 助力访问成功"
elif [ "$http_code" == "401" ]; then
    print_result "fail" "HTTP $http_code - 认证失败"
elif [ "$http_code" == "422" ]; then
    print_result "fail" "HTTP $http_code - 验证失败（订单可能不存在）"
else
    print_result "fail" "HTTP $http_code - 请求失败"
fi

# =============================================================================
# 测试总结
# =============================================================================
print_header "测试结果汇总"

TOTAL=$((PASS_COUNT + FAIL_COUNT))
echo ""
echo -e "${BLUE}总计测试: $TOTAL${NC}"
echo -e "${GREEN}通过: $PASS_COUNT${NC}"
echo -e "${RED}失败: $FAIL_COUNT${NC}"
echo ""

if [ "$FAIL_COUNT" -eq 0 ]; then
    echo -e "${GREEN}✓ 所有测试通过！${NC}"
    exit 0
else
    echo -e "${YELLOW}⚠ 部分测试失败，请检查日志${NC}"
    exit 1
fi