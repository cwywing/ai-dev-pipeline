#!/bin/bash

###############################################################################
# Harness 系统重置脚本
# 用途：将 Harness 系统恢复到初始状态，清空所有历史数据和任务
# 使用：cd .harness && ./scripts/reset_harness.sh
###############################################################################

set -e  # 遇到错误立即退出

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 获取脚本所在目录的父目录（.harness根目录）
HARNESS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo -e "${YELLOW}=== Harness 系统重置 ===${NC}"
echo ""

# 确认操作
read -p "⚠️  此操作将清空所有任务和历史数据，是否继续？(yes/no): " confirm
if [ "$confirm" != "yes" ]; then
    echo -e "${RED}操作已取消${NC}"
    exit 1
fi

cd "$HARNESS_DIR"

# 1. 清空任务
echo -e "${YELLOW}1. 清空任务数据...${NC}"
rm -rf tasks/pending/*.json 2>/dev/null || true
rm -rf tasks/completed/* 2>/dev/null || true
echo -e "   ${GREEN}✓ 已清空 tasks/pending 和 tasks/completed${NC}"

# 2. 清空日志
echo -e "${YELLOW}2. 清空运行日志...${NC}"
rm -rf logs/automation/* 2>/dev/null || true
rm -f logs/progress.md 2>/dev/null || true
echo -e "   ${GREEN}✓ 已清空 logs 目录${NC}"

# 3. 清空CLI会话
echo -e "${YELLOW}3. 清空CLI会话...${NC}"
rm -f cli-io/current.json 2>/dev/null || true
rm -rf cli-io/sessions/* 2>/dev/null || true
echo -e "   ${GREEN}✓ 已清空 cli-io 目录${NC}"

# 4. 清空产出
echo -e "${YELLOW}4. 清空产出记录...${NC}"
rm -rf artifacts/* 2>/dev/null || true
rm -rf reports/* 2>/dev/null || true
echo -e "   ${GREEN}✓ 已清空 artifacts 和 reports 目录${NC}"

# 5. 重置索引
echo -e "${YELLOW}5. 重置任务索引...${NC}"

# 读取项目名称（如果存在旧的task-index.json）
PROJECT_NAME="新项目"
if [ -f "task-index.json" ]; then
    old_project=$(python3 -c "import json; print(json.load(open('task-index.json')).get('project', '新项目'))" 2>/dev/null || echo "新项目")
    read -p "请输入新项目名称 (当前: $old_project): " new_project
    PROJECT_NAME="${new_project:-$old_project}"
else
    read -p "请输入项目名称: " PROJECT_NAME
fi

# 使用Python生成新的task-index.json
python3 << EOF
import json
from datetime import datetime

data = {
    'version': 2,
    'storage_mode': 'single_file',
    'project': '$PROJECT_NAME',
    'created_at': datetime.now().isoformat(),
    'updated_at': datetime.now().isoformat(),
    'total_tasks': 0,
    'pending': 0,
    'completed': 0,
    'index': {}
}

with open('task-index.json', 'w', encoding='utf-8') as f:
    json.dump(data, f, indent=2, ensure_ascii=False)

print(f"✓ 已创建新的 task-index.json")
EOF

echo -e "   ${GREEN}✓ 已重置 task-index.json${NC}"

# 6. 创建必要的目录结构
echo -e "${YELLOW}6. 创建必要的目录结构...${NC}"
mkdir -p tasks/pending
mkdir -p tasks/completed/$(date +%Y/%m)
mkdir -p logs/automation/$(date +%Y/%m)
mkdir -p cli-io/sessions
mkdir -p artifacts
mkdir -p reports
echo -e "   ${GREEN}✓ 已创建必要的目录${NC}"

echo ""
echo -e "${GREEN}=== 重置完成！===${NC}"
echo -e "项目名称: ${YELLOW}$PROJECT_NAME${NC}"
echo ""
echo "下一步操作："
echo "  1. 使用 add_task.py 创建新任务"
echo "  2. 运行 ./run-automation.sh 启动自动化"
echo ""