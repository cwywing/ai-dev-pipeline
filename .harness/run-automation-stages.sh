#!/bin/bash
# SIM-Laravel 自动化循环脚本（三阶段质量保证系统）
# Dev Agent → Test Agent → Review Agent

set -e

# Load environment variables from .harness/.env if it exists
if [ -f .harness/.env ]; then
    set -a
    source .harness/.env 2>/dev/null || true
    set +a
fi

# Default values
CLAUDE_CMD="${CLAUDE_CMD:-claude}"
PYTHON_CMD="${PYTHON_CMD:-python3}"
MAX_RETRIES="${MAX_RETRIES:-3}"
LOOP_SLEEP="${LOOP_SLEEP:-5}"
VERBOSE="${VERBOSE:-false}"

# Claude Code CLI 权限模式（用于非交互式自动化）
PERMISSION_MODE="${PERMISSION_MODE:-bypassPermissions}"

# ═══════════════════════════════════════════════════════════════
#                   超时优化配置（性能优先 2026-03）
# ═══════════════════════════════════════════════════════════════
MAX_TIMEOUT_RETRIES="${MAX_TIMEOUT_RETRIES:-3}"    # 最大超时重试次数
TIMEOUT_BACKOFF_FACTOR="${TIMEOUT_BACKOFF_FACTOR:-1.3}"  # 超时递增因子
BASE_SILENCE_TIMEOUT="${BASE_SILENCE_TIMEOUT:-60}"  # 基础活性超时（秒）
MAX_SILENCE_TIMEOUT="${MAX_SILENCE_TIMEOUT:-180}"  # 最大活性超时（秒）- 防止无限递增

# Setup logging
# 日志文件输出到 logs/automation/ 目录，按年/月组织
LOG_DIR=".harness/logs/automation"
CURRENT_YEAR=$(date +%Y)
CURRENT_MONTH=$(date +%m)
mkdir -p "$LOG_DIR/$CURRENT_YEAR/$CURRENT_MONTH"
LOG_FILE="$LOG_DIR/$CURRENT_YEAR/$CURRENT_MONTH/automation_$(date +%Y%m%d_%H%M%S).log"
PROGRESS_FILE=".harness/logs/progress.md"

# Helper functions
log() {
    local msg="[$(date '+%Y-%m-%d %H:%M:%S')] $1"
    echo "$msg"
    echo "$msg" >> "$LOG_FILE"
}

log_verbose() {
    if [ "$VERBOSE" = "true" ]; then
        local msg="[$(date '+%Y-%m-%d %H:%M:%S')] [VERBOSE] $1"
        echo "$msg"
        echo "$msg" >> "$LOG_FILE"
    fi
}

log_error() {
    local msg="[$(date '+%Y-%m-%d %H:%M:%S')] [ERROR] $1"
    echo "$msg" >&2
    echo "$msg" >> "$LOG_FILE"
}

# Check dependencies
check_dependencies() {
    log "🔍 检查依赖..."
    if ! command -v "$PYTHON_CMD" &> /dev/null; then
        log_error "$PYTHON_CMD 未安装"
        exit 1
    fi

    if [ ! -f ".harness/task-index.json" ]; then
        log_error ".harness/task-index.json 不存在"
        exit 1
    fi

    if [ ! -d ".harness/tasks/pending" ]; then
        log_error ".harness/tasks/pending/ 目录不存在"
        exit 1
    fi

    log "✅ 依赖检查通过"
}

# Get artifacts list for a task
get_artifacts_list() {
    local task_id=$1
    local artifacts_file=".harness/artifacts/${task_id}.json"

    if [ ! -f "$artifacts_file" ]; then
        echo "（暂无产出记录）"
        return
    fi

    echo "$artifacts_file" | grep -q '\.json$' && {
        artifacts_json="$artifacts_file"
    } || {
        # Fallback to generating JSON from files list
        artifacts_json=""
    }

    if [ -n "$artifacts_json" ]; then
        "$PYTHON_CMD" -c "
import json
import sys
try:
    with open('$artifacts_json', 'r') as f:
        data = json.load(f)
    files = data.get('files', [])
    if files:
        for file in files:
            print(f'  - {file}')
    else:
        print('  （暂无产出）')
except Exception as e:
    print(f'  （无法读取产出记录: {e}）', file=sys.stderr)
" 2>/dev/null || echo "  （无法读取产出记录）"
    else
        echo "  （暂无产出记录）"
    fi
}

# Get issues from previous stage
get_stage_issues() {
    local task_id=$1
    local stage=$2

    "$PYTHON_CMD" -c "
import sys
sys.path.insert(0, '.harness/scripts')
from task_utils import load_tasks
try:
    data = load_tasks()
    for task in data['tasks']:
        if task['id'] == '$task_id' and 'stages' in task:
            issues = task['stages']['$stage'].get('issues', [])
            if issues:
                for i, issue in enumerate(issues, 1):
                    print(f'{i}. {issue}')
            break
except Exception as e:
    print(f'Error: {e}', file=sys.stderr)
" 2>/dev/null || echo ""
}

# Get test results
get_test_results() {
    local task_id=$1

    "$PYTHON_CMD" -c "
import sys
sys.path.insert(0, '.harness/scripts')
from task_utils import load_tasks
try:
    data = load_tasks()
    for task in data['tasks']:
        if task['id'] == '$task_id' and 'stages' in task:
            test_results = task['stages']['test'].get('test_results', {})
            if test_results:
                for test_name, result in test_results.items():
                    status = '✅' if result.get('passed') else '❌'
                    msg = result.get('message', 'N/A')
                    print(f'{status} {test_name}: {msg}')
            break
except Exception as e:
    print(f'Error: {e}', file=sys.stderr)
" 2>/dev/null || echo "（暂无测试结果）"
}

# Get task complexity
get_task_complexity() {
    local task_id=$1
    local complexity=$("$PYTHON_CMD" -c "
import sys
sys.path.insert(0, '.harness/scripts')
from task_utils import load_tasks
try:
    data = load_tasks()
    for task in data['tasks']:
        if task['id'] == '$task_id':
            print(task.get('complexity', 'unknown'))
            break
except Exception as e:
    print('unknown', file=sys.stderr)
" 2>/dev/null)

    echo "${complexity:-unknown}"
}

# Get hard timeout based on complexity
# 优化后的硬超时（性能优先）
get_hard_timeout() {
    local complexity=$1
    case "$complexity" in
        simple)
            echo 300   # 5分钟
            ;;
        medium)
            echo 480   # 8分钟
            ;;
        complex)
            echo 600   # 10分钟
            ;;
        *)
            echo 300   # 默认 5分钟
            ;;
    esac
}

# Main loop
log "🚀 启动 SIM-Laravel 三阶段自动化循环..."
log "日志文件: $LOG_FILE"
log "配置:"
log "  - CLAUDE_CMD: $CLAUDE_CMD"
log "  - PYTHON_CMD: $PYTHON_CMD"
log "  - MAX_RETRIES: $MAX_RETRIES"
log "  - LOOP_SLEEP: ${LOOP_SLEEP}s"
log "  - PERMISSION_MODE: $PERMISSION_MODE"
log "  - 质量保证: 三阶段 (Dev → Test → Review)"
log ""

# Run initial checks
check_dependencies

# Task retry tracking
RETRY_DIR=".harness/.automation_retries"
SKIP_DIR=".harness/.automation_skip"
TIMEOUT_DIR=".harness/.automation_timeouts"  # 超时计数器目录
mkdir -p "$RETRY_DIR" "$SKIP_DIR" "$TIMEOUT_DIR"

current_task_id=""
current_stage=""
consecutive_failures=0
MAX_CONSECUTIVE_FAILURES=5

while true; do
    # Get the next pending stage
    log "📋 获取下一个待处理阶段..."

    # 🔧 修复：使用临时文件避免变量赋值覆盖退出码（2026-02-16）
    temp_output_file=$(mktemp)
    "$PYTHON_CMD" .harness/scripts/next_stage.py 2>&1 > "$temp_output_file"
    exit_code=$?
    stage_output=$(cat "$temp_output_file")
    rm -f "$temp_output_file"

    if [ $exit_code -eq 1 ]; then
        log "✅ 所有阶段已完成！退出循环。"
        log "📊 完成统计："
        log "  - 总任务数: $("$PYTHON_CMD" -c "import json; print(len(json.load(open('.harness/task-index.json'))['tasks']))")"
        log "  - 日志文件: $LOG_FILE"
        exit 0
    elif [ $exit_code -ne 0 ]; then
        log_error "获取阶段失败: $stage_output"
        consecutive_failures=$((consecutive_failures + 1))
        if [ $consecutive_failures -ge $MAX_CONSECUTIVE_FAILURES ]; then
            log_error "连续失败次数过多 ($consecutive_failures)，停止执行"
            exit 1
        fi
        sleep $LOOP_SLEEP
        continue
    fi

    # Reset consecutive failures on successful stage fetch
    consecutive_failures=0

    log "当前任务和阶段:"
    echo "$stage_output"
    echo ""

    # Extract task ID and stage from output
    # 修复：使用 awk 提取最后一列，避免复杂的 sed 转义
    current_task_id=$(echo "$stage_output" | grep "Task ID:" | awk '{print $NF}')
    current_stage=$(echo "$stage_output" | grep "Current Stage:" | awk '{print $NF}' | tr '[:upper:]' '[:lower:]')

    log_verbose "任务 ID: $current_task_id"
    log_verbose "当前阶段: $current_stage"

    # Check if task was permanently skipped
    if [ -f "$SKIP_DIR/${current_task_id}" ]; then
        log "⏭️  跳过任务 $current_task_id (之前已达到最大重试次数)"
        sleep $LOOP_SLEEP
        continue
    fi

    # Check retry count
    retry_file="$RETRY_DIR/${current_task_id}_${current_stage}.count"
    if [ -f "$retry_file" ]; then
        current_retry_count=$(cat "$retry_file")
        if [ "$current_retry_count" -ge "$MAX_RETRIES" ]; then
            log_error "任务 $current_task_id 的 $current_stage 阶段已达到最大重试次数 ($MAX_RETRIES)"
            log_error "将跳过此任务并继续处理其他任务"
            touch "$SKIP_DIR/${current_task_id}"
            sleep $LOOP_SLEEP
            continue
        fi

        # 🔧 重试前清理该任务的产出（仅 dev 阶段）
        if [ "$current_stage" = "dev" ]; then
            log "🧹 清理任务 $current_task_id 的残留产出..."
            "$PYTHON_CMD" .harness/scripts/artifacts.py --action clean --id "$current_task_id" 2>/dev/null || true
        fi
    else
        current_retry_count=0
    fi

    # Assemble the prompt based on stage
    log "📝 组装 Prompt（$current_stage 阶段）..."

    prompt_file=$(mktemp) || { log_error "无法创建临时文件"; exit 1; }

    # Get progress output
    if [ -f ".harness/logs/progress.md" ]; then
        progress_output=$(tail -n 30 .harness/logs/progress.md)
    else
        progress_output="暂无进度记录（这是第一个任务）"
    fi

    # Get artifacts list (for test/review stages)
    artifacts_list="（暂无产出）"
    if [ "$current_stage" = "test" ] || [ "$current_stage" = "review" ]; then
        artifacts_list=$(get_artifacts_list "$current_task_id")
    fi

    # Get previous issues
    previous_issues=""
    if [ "$current_stage" = "test" ]; then
        dev_issues=$(get_stage_issues "$current_task_id" "dev")
        if [ -n "$dev_issues" ]; then
            previous_issues="Dev 阶段遗留问题:
$dev_issues"
        fi
    elif [ "$current_stage" = "review" ]; then
        test_issues=$(get_stage_issues "$current_task_id" "test")
        if [ -n "$test_issues" ]; then
            previous_issues="Test 阶段发现的问题:
$test_issues"
        fi
    fi

    # Get test results (for review stage)
    test_results=""
    if [ "$current_stage" = "review" ]; then
        test_results=$(get_test_results "$current_task_id")
    fi

    # Select template based on stage
    template_file="${HARNESS_DIR:-.harness}/templates/${current_stage}_prompt.md"

    if [ ! -f "$template_file" ]; then
        log_error "模板文件不存在: $template_file"
        log_error "当前目录: $(pwd)"
        log_error "模板目录内容:"
        ls -la "${HARNESS_DIR:-.harness}/templates/" >> "$LOG_FILE" 2>&1 || true
        exit 1
    fi

    # Build the complete prompt
    {
        echo "# ═══════════════════════════════════════════════════════════════"
        echo "#                    SYSTEM INSTRUCTIONS (SOP)                  "
        echo "#              Laravel 开发规范 - 必须严格遵循                   "
        echo "# ═══════════════════════════════════════════════════════════════"
        echo ""
        # 🔧 优化：直接读取并嵌入 CLAUDE.md 内容，防止管道模式下 @ 标记失效
        # 与 Windows 版本保持一致
        if [ -f CLAUDE.md ]; then
            cat CLAUDE.md
            echo ""
            echo "⚠️ **CRITICAL: You MUST strictly follow the SOP / coding standards provided above.**"
        else
            echo "⚠️ Warning: CLAUDE.md not found"
        fi
        echo ""
        echo ""
        echo "# ═══════════════════════════════════════════════════════════════"
        echo "#                    RECENT PROGRESS                            "
        echo "#                    最近 30 行进度记录                          "
        echo "# ═══════════════════════════════════════════════════════════════"
        echo ""
        echo "$progress_output"
        echo ""
        echo ""
        echo "# ═══════════════════════════════════════════════════════════════"
        echo "#                    CURRENT TASK & STAGE                       "
        echo "# ═══════════════════════════════════════════════════════════════"
        echo ""
        echo "$stage_output"
        echo ""
        echo ""
        echo "# ═══════════════════════════════════════════════════════════════"
        echo "#                    ARTIFACTS & ISSUES                        "
        echo "# ═══════════════════════════════════════════════════════════════"
        echo ""
        if [ "$current_stage" = "test" ] || [ "$current_stage" = "review" ]; then
            echo "**Artifacts to test/review:**"
            echo "$artifacts_list"
            echo ""
        fi
        if [ -n "$previous_issues" ]; then
            echo "**Previous stage issues:**"
            echo "$previous_issues"
            echo ""
        fi
        if [ "$current_stage" = "review" ] && [ -n "$test_results" ]; then
            echo "**Test Results:**"
            echo "$test_results"
            echo ""
        fi
        echo ""
        # Now load the template (without variable substitution for large vars)

        # For validation stage, replace additional placeholders
        if [ "$current_stage" = "validation" ]; then
            # Get validation config
            validation_config=$("$PYTHON_CMD" -c "
import sys
sys.path.insert(0, '.harness/scripts')
from task_utils import load_tasks
data = load_tasks()
for task in data['tasks']:
    if task['id'] == '$current_task_id':
        val = task.get('validation', {})
        print(f'enabled {val.get(\"enabled\", False)}')
        print(f'threshold {val.get(\"threshold\", 0.8)}')
        print(f'max_retries {val.get(\"max_retries\", 3)}')
        break
" 2>/dev/null || echo "enabled False
threshold 0.8
max_retries 3")

            # Parse validation config
            val_enabled=$(echo "$validation_config" | grep "^enabled " | awk '{print $2}')
            val_threshold=$(echo "$validation_config" | grep "^threshold " | awk '{print $2}')
            val_max_retries=$(echo "$validation_config" | grep "^max_retries " | awk '{print $2}')

            # Get retry count
            validation_retry_file="$TIMEOUT_DIR/${current_task_id}_validation_retry.count"
            current_retry=$(cat "$validation_retry_file" 2>/dev/null || echo "0")

            # Calculate threshold percentage
            threshold_percent=$(echo "$val_threshold * 100" | bc 2>/dev/null || echo "80")

            # Get acceptance criteria (format as numbered list, use <br> for newlines)
            acceptance_criteria=$("$PYTHON_CMD" -c "
import sys
sys.path.insert(0, '.harness/scripts')
from task_utils import load_tasks
data = load_tasks()
for task in data['tasks']:
    if task['id'] == '$current_task_id':
        items = []
        for i, acc in enumerate(task.get('acceptance', []), 1):
            # 将换行符替换为 <br> 以便在 markdown 中显示
            acc_escaped = acc.replace('\n', '<br>').replace('|', '\\|')
            items.append(f'{i}. {acc_escaped}')
        sys.stdout.write('<br>'.join(items))
        break
" 2>/dev/null || echo "(无验收标准)")
            acceptance_criteria=$(echo "$acceptance_criteria" | tr -d '\n')

            # Get artifacts list (convert to single line with <br> for markdown)
            artifacts_list=$("$PYTHON_CMD" -c "
import sys
import json
artifacts_file = '.harness/artifacts/${current_task_id}.json'
try:
    with open(artifacts_file, 'r') as f:
        data = json.load(f)
    files = data.get('files', [])
    if files:
        items = [f'  - {f}' for f in files]
        sys.stdout.write('<br>'.join(items))
    else:
        sys.stdout.write('  （暂无产出）')
except Exception:
    sys.stdout.write('  （暂无产出）')
" 2>/dev/null || printf '（暂无产出）')

            # Get test results (convert to single line with <br> for markdown)
            test_results=$("$PYTHON_CMD" -c "
import sys
sys.path.insert(0, '.harness/scripts')
from task_utils import load_tasks
data = load_tasks()
for task in data['tasks']:
    if task['id'] == '$current_task_id' and 'stages' in task and 'test' in task['stages']:
        test_data = task['stages']['test'].get('test_results', {})
        if test_data:
            summary = test_data.get('summary', '无测试结果')
            passed = test_data.get('passed', 0)
            failed = test_data.get('failed', 0)
            total = test_data.get('total', 0)
            result = f'{summary}<br>Passed: {passed}, Failed: {failed}, Total: {total}'
            sys.stdout.write(result)
        break
" 2>/dev/null || printf '（暂无测试结果）')

            # Get description
            task_desc=$("$PYTHON_CMD" -c "
import sys
sys.path.insert(0, '.harness/scripts')
from task_utils import load_tasks
data = load_tasks()
for task in data['tasks']:
    if task['id'] == '$current_task_id':
        import sys
        sys.stdout.write(task.get('description', ''))
        break
" 2>/dev/null || printf '任务描述')

            # Replace all placeholders - using printf to avoid adding newlines
            printf '%s' "$(sed -e "s|{TASK_ID}|$current_task_id|g" \
                -e "s|{DESCRIPTION}|$task_desc|g" \
                -e "s|{ACCEPTANCE_CRITERIA}|$acceptance_criteria|g" \
                -e "s|{ARTIFACTS_LIST}|$artifacts_list|g" \
                -e "s|{TEST_RESULTS}|$test_results|g" \
                -e "s|{VALIDATION_THRESHOLD}|$val_threshold|g" \
                -e "s|{VALIDATION_THRESHOLD_PERCENT}|$threshold_percent%|g" \
                -e "s|{CURRENT_RETRY}|$current_retry|g" \
                -e "s|{MAX_RETRIES}|$val_max_retries|g" \
                "$template_file")"
        else
            # For dev/test/review stages, use simple replacement
            sed -e "s|{TASK_ID}|$current_task_id|g" \
                "$template_file"
        fi
    } > "$prompt_file"

    log_verbose "Prompt 已组装到: $prompt_file"

    # Execute Claude Code CLI Agent
    log "🤖 调用 Claude Code CLI ($current_stage Agent)..."
    log "────────────────────────────────────────"

    # ═══════════════════════════════════════════════════════════════
    #                   双重超时机制（优化版）
    # ═══════════════════════════════════════════════════════════════
    # 1. 活性超时：基于重试次数递增（180s → 270s → 405s ...）
    # 2. 硬超时：基于任务复杂度（simple: 15分钟, medium: 20分钟, complex: 30分钟）

    # 获取任务复杂度
    task_complexity=$(get_task_complexity "$current_task_id")
    hard_timeout=$(get_hard_timeout "$task_complexity")

    # 🔧 获取超时计数并计算动态活性超时（与 Windows 版本一致）
    timeout_count_file="$TIMEOUT_DIR/${current_task_id}_${current_stage}.count"
    timeout_count=$(cat "$timeout_count_file" 2>/dev/null || echo "0")

    # 获取 prompt 文件大小（用于动态计算）
    prompt_size_bytes=$(wc -c < "$prompt_file" 2>/dev/null || echo "0")
    prompt_size_kb=$((prompt_size_bytes / 1024))

    # 阶段产出时间 (秒) - 与 Windows 版本 calculate_dynamic_timeout 一致
    case "$current_stage" in
        dev)        stage_time=240 ;;
        test)       stage_time=180 ;;
        review)     stage_time=120 ;;
        validation) stage_time=90 ;;
        *)          stage_time=120 ;;
    esac

    # 动态超时计算: 基础60s + prompt阅读时间 + 阶段产出时间 × 退避因子
    # 算法: 60 + (prompt_size_kb * 1.5) + stage_time * (factor ^ count)
    # 注意: bc 使用 ^ 表示指数，需使用 -l 选项加载数学库
    silence_timeout=$(echo "60 + $prompt_size_kb * 1.5 + $stage_time * ($TIMEOUT_BACKOFF_FACTOR ^ $timeout_count)" | bc -l 2>/dev/null || echo "$BASE_SILENCE_TIMEOUT")
    silence_timeout=${silence_timeout%.*}  # 取整

    # 安全边界: min 120s, max MAX_SILENCE_TIMEOUT
    if [ "$silence_timeout" -lt 120 ]; then
        silence_timeout=120
    fi
    if [ "$silence_timeout" -gt "$MAX_SILENCE_TIMEOUT" ]; then
        silence_timeout=$MAX_SILENCE_TIMEOUT
    fi

    log "任务复杂度: $task_complexity"
    log "硬超时限制: ${hard_timeout}秒 ($((hard_timeout / 60))分钟)"
    log "活性超时: ${silence_timeout}秒 (第 $timeout_count 次超时，已递增)"

    # ═══════════════════════════════════════════════════════════════
    #                   CLI I/O 捕获（监控面板）
    # ═══════════════════════════════════════════════════════════════
    # 创建 CLI 会话记录
    io_session_id="$(date +%Y%m%d_%H%M%S)_$$"
    io_meta_file=".harness/cli-io/current.json"
    io_output_file=".harness/cli-io/sessions/${io_session_id}_output.txt"
    io_input_file=".harness/cli-io/sessions/${io_session_id}_input.txt"
    io_start_time=$(date -Iseconds)

    # 创建目录
    mkdir -p "$(dirname "$io_output_file")"

    # 写入会话元数据
    cat > "$io_meta_file" <<EOF
{
  "session_id": "$io_session_id",
  "task_id": "$current_task_id",
  "stage": "$current_stage",
  "start_time": "$io_start_time",
  "prompt_file": "$prompt_file",
  "active": true
}
EOF

    log "📹 CLI I/O 捕获已启用 (session: $io_session_id)"

    # 使用双重超时机制执行（带 I/O 捕获）
    # 临时禁用 set -e，因为超时会返回非零退出码，但我们希望继续处理
    set +e

    # 使用 tee 捕获 CLI 输出（更可靠的方法）
    (
        cat "$prompt_file" | "$PYTHON_CMD" .harness/scripts/dual_timeout.py \
            --hard-timeout "$hard_timeout" \
            --silence-timeout "$silence_timeout" \
            --claude-cmd "$CLAUDE_CMD" \
            --permission-mode "$PERMISSION_MODE" \
            --verbose
    ) 2>&1 | tee "$io_output_file"

    # 保存 dual_timeout.py 的退出码（PIPESTATUS[0]），而不是 tee 的退出码
    dual_timeout_exit_code=${PIPESTATUS[0]}

    set -e

    # 更新会话元数据（标记完成）
    cat > "$io_meta_file" <<EOF
{
  "session_id": "$io_session_id",
  "task_id": "$current_task_id",
  "stage": "$current_stage",
  "start_time": "$io_start_time",
  "end_time": "$(date -Iseconds)",
  "exit_code": $dual_timeout_exit_code,
  "completed": true,
  "active": false
}
EOF

    log "📹 CLI I/O 已保存到: $io_output_file"

    # ═══════════════════════════════════════════════════════════════
    #                  高级方案：超时不计入失败次数
    # ═══════════════════════════════════════════════════════════════
    # 检测是否为超时失败（退出码 14 或 124 表示超时）
    is_timeout_failure=false

    if [ "$dual_timeout_exit_code" -eq 14 ] || [ "$dual_timeout_exit_code" -eq 124 ]; then
        is_timeout_failure=true
        log "⚠️  检测到超时退出（退出码 $dual_timeout_exit_code），本次不计入逻辑失败次数"
    elif [ "$dual_timeout_exit_code" -ne 0 ]; then
        # 检查日志中是否有超时关键字（兜底机制）
        if tail -n 5 "$LOG_FILE" | grep -q "Agent 卡死\|硬超时\|无输出"; then
            is_timeout_failure=true
            log "⚠️  检测到超时退出（日志匹配），本次不计入逻辑失败次数"
        fi
    fi

    log "────────────────────────────────────────"
    echo ""

    # Clean up temp file
    rm -f "$prompt_file"

    # 🔧 清理重复的迁移文件（保留每个表的最新版本）
    if [ "$current_stage" = "dev" ] && [[ "$current_task_id" == *"Migration"* ]] || [[ "$current_task_id" == *"Foundation"* ]]; then
        log "🧹 检查并清理重复的迁移文件..."
        "$PYTHON_CMD" -c "
import os
import re
from pathlib import Path
from collections import defaultdict

migrations_dir = Path('database/migrations')
if not migrations_dir.exists():
    exit(0)

# 按表名分组迁移文件
tables = defaultdict(list)
for f in migrations_dir.glob('*.php'):
    match = re.search(r'create_(\w+)_table', f.stem)
    if match:
        table_name = match.group(1)
        tables[table_name].append(f)

# 删除重复文件，保留最新的
deleted_count = 0
for table_name, files in tables.items():
    if len(files) > 1:
        # 按时间戳排序，保留最新的
        files_sorted = sorted(files, key=lambda x: x.stat().st_mtime, reverse=True)
        for old_file in files_sorted[1:]:
            try:
                old_file.unlink()
                deleted_count += 1
            except:
                pass

if deleted_count > 0:
    print(f'  ✓ 清理了 {deleted_count} 个重复的迁移文件')
" 2>/dev/null || true
    fi

    # ═══════════════════════════════════════════════════════════════
    #           智能混合机制：信任但要核实 (Trust, but Verify)
    # ═══════════════════════════════════════════════════════════════
    log "🔍 检查阶段状态..."

    # 1. 非正常退出 (超时/崩溃) - 直接判失败
    if [ "$dual_timeout_exit_code" -ne 0 ]; then
        log "❌ Agent 异常退出或超时 (Exit Code: $dual_timeout_exit_code)"
        # is_completed 保持空，进入下方的失败重试逻辑
        is_completed=""
    else
        # 2. 正常退出，检查是否显式调用了 mark-stage
        stage_status_output=$(python3 .harness/scripts/harness-tools.py --action stage-status --id "$current_task_id" --stage "$current_stage" 2>/dev/null || true)
        is_completed=$(echo "$stage_status_output" | grep -c "完成" || true)

        if [ "$is_completed" -ge 1 ]; then
            log "✅ Agent 完美执行并主动调用了 mark-stage！"
        else
            log "⚠️ Agent 正常退出，但未调用 mark-stage 命令。尝试混合检测..."

            # 3. 混合模式检测（新增）
            detect_result=$(python3 .harness/scripts/detect_stage_completion.py \
                --id "$current_task_id" \
                --stage "$current_stage" \
                2>&1)
            detect_exit_code=$?

            if [ "$detect_exit_code" -eq 0 ]; then
                log "✅ 混合检测通过: $detect_result"
                # 自动调用 mark-stage（模仿 agent 行为）
                if [ "$current_stage" = "dev" ]; then
                    git_files=$(git status --porcelain 2>/dev/null | awk '{print $2}' | tr '\n' ' ')
                    python3 .harness/scripts/harness-tools.py --action mark-stage \
                        --id "$current_task_id" --stage dev --files "$git_files" >/dev/null 2>&1 || true
                else
                    # Test/Review 阶段只标记完成，不需要 files
                    python3 .harness/scripts/harness-tools.py --action mark-stage \
                        --id "$current_task_id" --stage "$current_stage" >/dev/null 2>&1 || true
                fi
                is_completed=1
            elif [ "$detect_exit_code" -eq 1 ]; then
                log "❌ 混合检测未通过: $detect_result"

                # 3.5 Validation Stage 特殊处理：提取满意度分数并自动调用
                if [ "$current_stage" = "validation" ] && [ -f "$io_output_file" ]; then
                    log "🔍 检测到 validation stage，尝试提取满意度分数..."

                    # 提取满意度分数（优先级: <score> 标签 > 旧格式兼容）
                    # 方法1 (优先): <score> 标签精确提取 - 与 validation_prompt.md 模板要求一致
                    satisfaction_score=$(grep -oE "<score>[[:space:]]*[0-9]+\.?[0-9]*[[:space:]]*</score>" "$io_output_file" 2>/dev/null | \
                        grep -oE "[0-9]+\.?[0-9]*" | head -1 || true)

                    # 方法2 (兼容): 中文格式 "满意度分数: 100.0"
                    if [ -z "$satisfaction_score" ]; then
                        satisfaction_score=$(grep -i "满意度分数" "$io_output_file" 2>/dev/null | grep -oE "[0-9]+\.[0-9]|[0-9]+" | head -1 || true)
                    fi

                    # 方法3 (兼容): JSON格式 "satisfaction_score": 85.7
                    if [ -z "$satisfaction_score" ]; then
                        satisfaction_score=$(grep -oE "satisfaction_score[\"']?:[[:space:]]*[0-9]+\.?[0-9]*" "$io_output_file" 2>/dev/null | head -1 | grep -oE "[0-9]+\.?[0-9]*" | head -1 || true)
                    fi

                    if [ -n "$satisfaction_score" ]; then
                        log "📊 提取到满意度分数: $satisfaction_score"

                        # 获取当前重试次数
                        validation_retry_file="$TIMEOUT_DIR/${current_task_id}_validation_retry.count"
                        current_retry=$(cat "$validation_retry_file" 2>/dev/null || echo "0")

                        # 调用 mark-validation
                        if python3 .harness/scripts/harness-tools.py --action mark-validation \
                            --id "$current_task_id" \
                            --score "$satisfaction_score" \
                            --tries "$current_retry" 2>&1; then
                            log "✅ 已自动调用 mark-validation (分数: $satisfaction_score)"
                            is_completed=1
                        else
                            log "❌ mark-validation 调用失败"
                            is_completed=""
                        fi
                    else
                        log "⚠️  无法提取满意度分数，使用兜底机制..."
                    fi
                fi

                # 3.6 兜底机制：检查输出中是否包含完成文本
                if [ -f "$io_output_file" ]; then
                    if grep -qiE "(review.*已完成|审查.*已完成|阶段已完成|已标记为完成|review.*complete)" "$io_output_file" 2>/dev/null; then
                        log "⚠️  检测到完成文本，尝试自动标记..."
                        python3 .harness/scripts/harness-tools.py --action mark-stage \
                            --id "$current_task_id" --stage "$current_stage" >/dev/null 2>&1 || true
                        is_completed=1
                        log "✅ 已根据完成文本自动标记为完成（兜底机制）"
                    else
                        is_completed=""
                    fi
                else
                    is_completed=""
                fi
            else
                log "⚠️ 混合检测无法确定: $detect_result"
                is_completed=""
            fi
        fi
    fi

    # 4. 结算阶段状态
    if [ "$is_completed" -gt 0 ] 2>/dev/null; then
        # Stage is complete
        log "✅ 任务 $current_task_id 的 $current_stage 阶段已完成"

        # Check if all stages are complete
        if "$PYTHON_CMD" -c "
import sys
sys.path.insert(0, '.harness/scripts')
from task_utils import load_tasks
data = load_tasks()
for task in data['tasks']:
    if task['id'] == '$current_task_id' and 'stages' in task:
        all_complete = all([
            task['stages']['dev']['completed'],
            task['stages']['test']['completed'],
            task['stages']['review']['completed']
        ])
        sys.exit(0 if all_complete else 1)
sys.exit(2)
" 2>/dev/null; then
            # All stages complete, do git commit
            log "🎉 任务 $current_task_id 的所有阶段已完成！"

            if [ -d .git ] && command -v git &> /dev/null; then
                log "📦 创建 Git 提交..."

                task_desc=$("$PYTHON_CMD" -c "
import sys
sys.path.insert(0, '.harness/scripts')
from task_utils import load_tasks
data = load_tasks()
for task in data['tasks']:
    if task['id'] == '$current_task_id':
        print(task['description'])
        break
" 2>/dev/null)

                if git add -A . 2>/dev/null; then
                    # 清理提交信息，去除额外后缀
                    clean_task_desc=$(echo "$task_desc" | sed 's/ (三阶段质量保证通过)//' | sed 's/ *$//')
                    if git commit -m "$current_task_id: $clean_task_desc" 2>/dev/null; then
                        log "✓ 已提交: $current_task_id: $clean_task_desc"
                    else
                        log "ℹ️  没有变更需要提交"
                    fi
                fi
            fi
        fi

        # Reset retry count and timeout count for this stage
        rm -f "$RETRY_DIR/${current_task_id}_${current_stage}.count" 2>/dev/null || true
        rm -f "$TIMEOUT_DIR/${current_task_id}_${current_stage}.count" 2>/dev/null || true

        # ═══════════════════════════════════════════════════════════════
        #           检查是否需要执行 Satisfaction Validation
        # ═══════════════════════════════════════════════════════════════
        # 只有在 review 阶段完成且 validation 启用时才执行
        if [ "$current_stage" = "review" ]; then
            # 检查是否所有标准阶段都完成
            all_stages_complete=$("$PYTHON_CMD" -c "
import sys
sys.path.insert(0, '.harness/scripts')
from task_utils import load_tasks
data = load_tasks()
for task in data['tasks']:
    if task['id'] == '$current_task_id' and 'stages' in task:
        all_complete = all([
            task['stages']['dev']['completed'],
            task['stages']['test']['completed'],
            task['stages']['review']['completed']
        ])
        print('true' if all_complete else 'false')
        break
" 2>/dev/null)

            if [ "$all_stages_complete" = "true" ]; then
                # 检查是否启用 validation
                validation_enabled=$("$PYTHON_CMD" -c "
import sys
sys.path.insert(0, '.harness/scripts')
from task_utils import load_tasks
data = load_tasks()
for task in data['tasks']:
    if task['id'] == '$current_task_id':
        val = task.get('validation', {})
        print('true' if val.get('enabled', False) else 'false')
        break
" 2>/dev/null)

                if [ "$validation_enabled" = "true" ]; then
                    # 检查 validation 是否已完成
                    validation_completed=$("$PYTHON_CMD" -c "
import sys
sys.path.insert(0, '.harness/scripts')
from task_utils import load_tasks
data = load_tasks()
for task in data['tasks']:
    if task['id'] == '$current_task_id' and 'stages' in task:
        print(task['stages'].get('validation', {}).get('completed', False))
        break
" 2>/dev/null)

                    if [ "$validation_completed" != "True" ] && [ "$validation_completed" != "true" ]; then
                        log "🔍 检测到需要 Satisfaction Validation"

                        # 检查重试次数
                        validation_retry_file="$TIMEOUT_DIR/${current_task_id}_validation_retry.count"
                        validation_retry_count=$(cat "$validation_retry_file" 2>/dev/null || echo "0")
                        max_validation_retries=$("$PYTHON_CMD" -c "
import sys
sys.path.insert(0, '.harness/scripts')
from task_utils import load_tasks
data = load_tasks()
for task in data['tasks']:
    if task['id'] == '$current_task_id':
        val = task.get('validation', {})
        print(val.get('max_retries', 3))
        break
" 2>/dev/null || echo "3")

                        if [ "$validation_retry_count" -ge "$max_validation_retries" ]; then
                            log_error "任务 $current_task_id 的 validation 重试次数过多 ($validation_retry_count/$max_validation_retries)"
                            touch "$SKIP_DIR/${current_task_id}"
                            continue
                        fi

                        # 执行 satisfaction validator
                        log "🤖 调用 Satisfaction Validator..."
                        validator_output=$("$PYTHON_CMD" .harness/scripts/validate_satisfaction.py \
                            --task-id "$current_task_id" 2>&1)
                        validator_exit_code=$?

                        # 解析满意度评分（从 JSON 输出中提取）
                        satisfaction_score=$(echo "$validator_output" | "$PYTHON_CMD" -c "
import sys, json
try:
    data = json.loads(sys.stdin.read())
    print(data.get('satisfaction_score', 0))
except:
    print(0)
" 2>/dev/null || echo "0")

                        # 检查是否通过
                        threshold=$("$PYTHON_CMD" -c "
import sys
sys.path.insert(0, '.harness/scripts')
from task_utils import load_tasks
data = load_tasks()
for task in data['tasks']:
    if task['id'] == '$current_task_id':
        val = task.get('validation', {})
        print(val.get('threshold', 0.8))
        break
" 2>/dev/null || echo "0.8")

                        # 比较评分（乘以100转换为整数比较）
                        threshold_int=$(echo "$threshold * 100" | bc 2>/dev/null | cut -d. -f1 || echo "80")
                        if [ -z "$threshold_int" ]; then
                            threshold_int=80
                        fi

                        if [ "$validator_exit_code" -eq 0 ] && [ "$satisfaction_score" -ge "$threshold_int" ]; then
                            log "✅ Satisfaction Validation 通过 (score: $satisfaction_score)"

                            # 标记 validation 阶段完成
                            "$PYTHON_CMD" .harness/scripts/harness-tools.py --action mark-validation \
                                --id "$current_task_id" --score "$satisfaction_score" \
                                --tries "$validation_retry_count" >/dev/null 2>&1

                            # 重置重试计数
                            rm -f "$validation_retry_file"
                        else
                            log "❌ Satisfaction Validation 失败 (score: $satisfaction_score < threshold: $threshold)"

                            # 增加强试计数
                            validation_retry_count=$((validation_retry_count + 1))
                            echo "$validation_retry_count" > "$validation_retry_file"

                            # 返回 Dev 阶段
                            log "🔢 返回 Dev 阶段重修 (validation retry: $validation_retry_count/$max_validation_retries)"

                            # 更新任务状态（重置 stages）
                            "$PYTHON_CMD" -c "
import sys
sys.path.insert(0, '.harness/scripts')
from task_utils import load_tasks, save_tasks
data = load_tasks()
for task in data['tasks']:
    if task['id'] == '$current_task_id':
                        task['stages']['dev']['completed'] = False
                        task['stages']['test']['completed'] = False
                        task['stages']['review']['completed'] = False
                        task['stages']['dev']['issues'].append(f'Validation failed (score: $satisfaction_score, threshold: $threshold)')
                        break
save_tasks(data)
" 2>/dev/null || true

                            if [ "$validation_retry_count" -ge "$max_validation_retries" ]; then
                                log_error "任务 $current_task_id 的 validation 达到最大重试次数"
                                touch "$SKIP_DIR/${current_task_id}"
                            fi
                        fi
                    fi
                fi
            fi
        fi

    else
        # Stage not complete
        retry_file="$RETRY_DIR/${current_task_id}_${current_stage}.count"
        if [ -f "$retry_file" ]; then
            current_retry_count=$(cat "$retry_file")
        else
            current_retry_count=0
        fi

        # ═══════════════════════════════════════════════════════════════
        #          优化方案：超时失败独立计数 + 递增超时 + 跳过机制
        # ═══════════════════════════════════════════════════════════════
        if [ "$is_timeout_failure" = "true" ]; then
            # 超时失败：增加超时计数器
            timeout_count=$((timeout_count + 1))
            echo "$timeout_count" > "$timeout_count_file"

            if [ "$timeout_count" -ge "$MAX_TIMEOUT_RETRIES" ]; then
                log_error "❌ 任务 $current_task_id 的 $current_stage 阶段超时重试次数过多 ($timeout_count/$MAX_TIMEOUT_RETRIES)"
                log_error "⏭️  将暂时跳过此任务，继续处理其他任务"
                touch "$SKIP_DIR/${current_task_id}"
                # 清理超时计数器以便下次重试
                rm -f "$timeout_count_file"
            else
                log "⚠️  任务 $current_task_id 的 $current_stage 阶段超时 ($timeout_count/$MAX_TIMEOUT_RETRIES)"
                log "💡 下次重试将使用更长的超时时间: $(echo "$BASE_SILENCE_TIMEOUT * ($TIMEOUT_BACKOFF_FACTOR ^ $timeout_count)" | bc 2>/dev/null || echo "N/A")秒"
                log "🔄 将在下次循环中重试"
            fi
        else
            # 逻辑错误：增加重试计数
            current_retry_count=$((current_retry_count + 1))
            echo "$current_retry_count" > "$retry_file"

            log "⚠️  任务 $current_task_id 的 $current_stage 阶段尚未完成 (尝试 $current_retry_count/$MAX_RETRIES)"
            log "🔄 将在下次循环中重试"

            if [ $current_retry_count -ge "$MAX_RETRIES" ]; then
                log_error "任务 $current_task_id 的 $current_stage 阶段已达到最大重试次数 ($MAX_RETRIES)"
                log_error "将跳过此任务并继续处理其他任务"
                touch "$SKIP_DIR/${current_task_id}"
            fi
        fi
    fi

    echo ""
    log "💤 等待 ${LOOP_SLEEP}秒后继续..."
    echo ""
    sleep $LOOP_SLEEP
done
