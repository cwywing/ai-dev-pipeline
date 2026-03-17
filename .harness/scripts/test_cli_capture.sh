#!/bin/bash
# 测试 CLI I/O 捕获功能（简化版）

set -e

echo "🧪 测试 CLI I/O 捕获功能..."
echo ""

# 清理旧的测试文件
rm -rf .harness/cli-io/sessions/test_*
mkdir -p .harness/cli-io/sessions

# 模拟自动化脚本中的 CLI I/O 捕获逻辑
io_session_id="test_$(date +%Y%m%d_%H%M%S)_$$"
io_meta_file=".harness/cli-io/current.json"
io_output_file=".harness/cli-io/sessions/${io_session_id}_output.txt"
io_start_time=$(date -Iseconds)

echo "📝 创建测试会话..."
echo "   Session ID: $io_session_id"

# 写入会话元数据（标记为活跃）
cat > "$io_meta_file" <<EOF
{
  "session_id": "$io_session_id",
  "task_id": "TEST_TASK_001",
  "stage": "test",
  "start_time": "$io_start_time",
  "active": true
}
EOF

echo "✅ 会话元数据已创建"
echo ""

# 模拟 CLI 执行并捕获输出（简单方法）
echo "📹 模拟 CLI 执行并捕获输出..."

{
    echo '🤖 Claude CLI Output Simulation'
    echo ''
    echo '✓ Analyzing task...'
    sleep 0.2
    echo '✓ Reading files...'
    sleep 0.2
    echo '✓ Writing code...'
    sleep 0.2
    echo ''
    echo '   PASS  Tests\Feature\Api\Admin\UserTest'
    echo '   ✓ test_user_list_returns_paginated'
    echo '   ✓ test_user_list_filters_by_name'
    echo ''
    echo '   Tests:  2 passed, 0 failed'
    echo '   Duration: 1.23 seconds'
    echo ''
    echo '✅ Task completed successfully'
} > "$io_output_file"

echo "✅ CLI 执行完成"
echo ""

# 更新会话元数据（标记完成）
cat > "$io_meta_file" <<EOF
{
  "session_id": "$io_session_id",
  "task_id": "TEST_TASK_001",
  "stage": "test",
  "start_time": "$io_start_time",
  "end_time": "$(date -Iseconds)",
  "exit_code": 0,
  "completed": true,
  "active": false
}
EOF

echo "📊 验证生成的文件..."
echo ""

if [ -f "$io_output_file" ]; then
    echo "✅ 输出文件已创建: $io_output_file"
    file_size=$(wc -c < "$io_output_file")
    echo "   文件大小: $file_size 字节"
    echo ""
    echo "   📄 输出内容:"
    cat "$io_output_file"
else
    echo "❌ 输出文件未创建"
    exit 1
fi

echo ""
echo "📡 测试后端 API 读取..."

# 测试 API
current_api=$(curl -s http://127.0.0.1:8001/api/cli/current)

# 使用 Python 解析 JSON
python3 <<'PYTHON_SCRIPT'
import json
import sys

try:
    data = json.loads(sys.stdin.read())

    if data.get('active'):
        print("✅ API 返回 active=True（会话进行中）")
    else:
        print("✅ API 返回 active=False（会话已完成）")

    task_id = data.get('task_id', 'N/A')
    session_id = data.get('session_id', 'N/A')
    stage = data.get('stage', 'N/A')

    print(f"   Task ID: {task_id}")
    print(f"   Session ID: {session_id}")
    print(f"   Stage: {stage}")

    output = data.get('output', '')
    if output:
        lines = output.strip().count('\n')
        print(f"   输出行数: {lines}")
    else:
        print("   ⚠️  输出为空")

except Exception as e:
    print(f"❌ API 调用失败: {e}")
    sys.exit(1)
PYTHON_SCRIPT

echo ""
echo "🎉 CLI I/O 捕获测试完成！"
echo ""
echo "📁 生成的文件:"
echo "   元数据: $io_meta_file"
echo "   输出:   $io_output_file"
echo ""
echo "💡 接下来可以:"
echo "   1. 运行自动化: ./.harness/run-automation-stages.sh"
echo "   2. 启动监控: cd .harness/monitor && ./start.sh"
