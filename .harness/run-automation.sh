#!/bin/bash
# SIM-Laravel 自动化循环脚本
# 基于 Long-running Agent Harness，针对 Laravel 项目定制

set -e

# Load environment variables from .harness/.env if it exists
if [ -f .harness/.env ]; then
    set -a
    source .harness/.env 2>/dev/null || true
    set +a
fi

# Default values
# 使用 Claude Code CLI 作为 AI Agent
CLAUDE_CMD="${CLAUDE_CMD:-claude}"
MAX_RETRIES="${MAX_RETRIES:-3}"
LOOP_SLEEP="${LOOP_SLEEP:-5}"
VERBOSE="${VERBOSE:-false}"

# Claude Code CLI 权限模式（用于非交互式自动化）
# acceptEdits: 自动接受所有编辑操作
# bypassPermissions: 绕过所有权限检查（仅用于可信环境）
# dontAsk: 不询问，自动执行
PERMISSION_MODE="${PERMISSION_MODE:-acceptEdits}"

# 加统一的日志配置
source .harness/scripts/logging_config.sh

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
    if ! command -v python3 &> /dev/null; then
        log_error "python3 未安装"
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

# Main loop
log "🚀 启动 SIM-Laravel 自动化循环..."
log "日志文件: $LOG_FILE"
log "配置:"
log "  - CLAUDE_CMD: $CLAUDE_CMD"
log "  - MAX_RETRIES: $MAX_RETRIES"
log "  - LOOP_SLEEP: ${LOOP_SLEEP}s"
log "  - PERMISSION_MODE: $PERMISSION_MODE"
log ""

# Run initial checks
check_dependencies

# Task retry tracking
RETRY_DIR=".harness/.automation_retries"
SKIP_DIR=".harness/.automation_skip"
mkdir -p "$RETRY_DIR" "$SKIP_DIR"

current_task_id=""
consecutive_failures=0
MAX_CONSECUTIVE_FAILURES=5

while true; do
    # Get the next pending task
    log "📋 获取下一个待处理任务..."

    if ! task_output=$(python3 .harness/scripts/harness-tools.py --action current 2>&1); then
        exit_code=$?
        if [ $exit_code -eq 1 ]; then
            log "✅ 所有任务已完成！退出循环。"
            log "📊 完成统计："
            log "  - 总任务数: $(python3 -c "import json; data=json.load(open('.harness/task-index.json')); print(len(data['tasks']))")"
            log "  - 日志文件: $LOG_FILE"
            exit 0
        else
            log_error "获取任务失败: $task_output"
            consecutive_failures=$((consecutive_failures + 1))
            if [ $consecutive_failures -ge $MAX_CONSECUTIVE_FAILURES ]; then
                log_error "连续失败次数过多 ($consecutive_failures)，停止执行"
                exit 1
            fi
            sleep $LOOP_SLEEP
            continue
        fi
    fi

    # Reset consecutive failures on successful task fetch
    consecutive_failures=0

    log "当前任务:"
    echo "$task_output"
    echo ""

    # Extract task ID from output
    current_task_id=$(echo "$task_output" | grep "^\\*\\*ID:\\*\\*" | sed 's/\*\*ID:\*\* //')
    log_verbose "任务 ID: $current_task_id"

    # Check if task was permanently skipped
    if [ -f "$SKIP_DIR/${current_task_id}" ]; then
        log "⏭️  跳过任务 $current_task_id (之前已达到最大重试次数)"
        sleep $LOOP_SLEEP
        continue
    fi

    # Check retry count
    retry_file="$RETRY_DIR/${current_task_id}.count"
    if [ -f "$retry_file" ]; then
        current_retry_count=$(cat "$retry_file")
        if [ "$current_retry_count" -ge "$MAX_RETRIES" ]; then
            log_error "任务 $current_task_id 已达到最大重试次数 ($MAX_RETRIES)"
            log_error "将跳过此任务并继续处理其他任务"
            touch "$SKIP_DIR/${current_task_id}"
            sleep $LOOP_SLEEP
            continue
        fi

        # 🔧 重试前清理该任务的产出
        log "🧹 清理任务 $current_task_id 的残留产出..."
        python3 .harness/scripts/artifacts.py --action clean --id "$current_task_id" 2>/dev/null || true
    else
        current_retry_count=0
    fi

    # Assemble the full prompt with SOP + Task + Progress
    log "📝 组装 Prompt（SOP + 任务 + 进度）..."

    prompt_file=$(mktemp) || { log_error "无法创建临时文件"; exit 1; }

    # Build the complete prompt
    {
        echo "# ═══════════════════════════════════════════════════════════════"
        echo "#                    SYSTEM INSTRUCTIONS (SOP)                  "
        echo "#              Laravel 开发规范 - 必须严格遵循                   "
        echo "# ═══════════════════════════════════════════════════════════════"
        echo ""
        if [ -f CLAUDE.md ]; then
            cat CLAUDE.md
        else
            echo "⚠️  Warning: CLAUDE.md not found"
        fi
        echo ""
        echo ""
        echo "# ═══════════════════════════════════════════════════════════════"
        echo "#                    RECENT PROGRESS                            "
        echo "#                    最近 30 行进度记录                          "
        echo "# ═══════════════════════════════════════════════════════════════"
        echo ""
        if [ -f ".harness/logs/progress.md" ]; then
            tail -n 30 .harness/logs/progress.md
        else
            echo "暂无进度记录（这是第一个任务）"
        fi
        echo ""
        echo ""
        echo "# ═══════════════════════════════════════════════════════════════"
        echo "#                    CURRENT TASK                              "
        echo "#                    当前待处理任务                              "
        echo "# ═══════════════════════════════════════════════════════════════"
        echo ""
        echo "$task_output"
        echo ""
        echo ""
        echo "# ═══════════════════════════════════════════════════════════════"
        echo "#                    INSTRUCTIONS TO AGENT                      "
        echo "#                    Agent 执行指令                              "
        echo "# ═══════════════════════════════════════════════════════════════"
        echo ""
        echo "你是 Claude AI，一位 Laravel 11 专家级开发者。"
        echo ""
        echo "## ⚠️ 重要提醒：自动化模式"
        echo ""
        echo "你当前运行在 **自动化模式**（非交互）："
        echo "  - ✅ 已自动授予文件写入权限（--permission-mode $PERMISSION_MODE）"
        echo "  - ✅ 可以直接创建/修改文件"
        echo "  - ✅ 可以运行命令"
        echo "  - ⚠️  无需等待用户批准，直接执行任务"
        echo ""
        echo "## 🎯 核心要求（必须严格遵守）"
        echo ""
        echo "### 1. 遵循开发规范"
        echo "**以上方的 System Instructions (CLAUDE.md) 为唯一权威标准**，你必须："
        echo "  - ✅ 严格按照 CLAUDE.md 中的 Laravel 规范编写代码"
        echo "  - ✅ 遵循 TDD（测试驱动开发）流程"
        echo "  - ✅ 使用 API Resources 格式化输出（禁止直接返回 Array）"
        echo "  - ✅ 使用 FormRequest 验证输入（禁止在 Controller 中验证）"
        echo "  - ✅ 业务逻辑下沉到 Service 层（Controller 保持精简）"
        echo "  - ✅ 使用 DatabaseTransactions trait（禁止 RefreshDatabase）"
        echo "  - ✅ 遵循双端 API 架构（App 端 vs Admin 端）"
        echo ""
        echo "### 2. 完成标准"
        echo "确保满足当前任务的所有 **Acceptance Criteria（验收标准）**"
        echo ""
        echo "### 3. 工具使用（必须调用）"
        echo "完成任务后，**必须**执行以下步骤："
        echo ""
        echo "#### 步骤 A: 记录产出清单"
        echo "   创建文件后，**必须**先记录产出："
        echo "   \`\`\`bash"
        echo "   python3 .harness/scripts/harness-tools.py --action mark-done --id $current_task_id \\"
        echo "     --files file1.php file2.php ..."
        echo "   \`\`\`"
        echo "   **重要**: --files 参数列出所有创建的文件（迁移、模型、控制器等）"
        echo ""
        echo "#### 步骤 B: 标记任务完成"
        echo "   如果没有创建文件，只运行："
        echo "   \`\`\`bash"
        echo "   python3 .harness/scripts/harness-tools.py --action mark-done --id $current_task_id"
        echo "   \`\`\`"
        echo ""
        echo "   **⚠️ 严禁手动编辑 task-index.json**，它由单文件存储系统自动管理"
        echo ""
        echo "### 4. 更新进度（强烈推荐）"
        echo "建议调用以下命令更新进度记录："
        echo "   \`\`\`bash"
        echo "   python3 .harness/scripts/harness-tools.py --action update-progress --id $current_task_id \\"
        echo "     --what-done \"做了什么（关键文件与改动点）\" \\"
        echo "     --test-result \"测试结果（命令与输出）\" \\"
        echo "     --next-step \"下一步建议\""
        echo "   \`\`\`"
        echo ""
        echo "### 5. 验证优先"
        echo "在标记完成前，请确保："
        echo "  - ✅ 所有验收标准中要求的文件已创建"
        echo "  - ✅ 测试已通过（运行 php8 artisan test）"
        echo "  - ✅ 代码风格符合规范（运行 ./vendor/bin/pint）"
        echo "  - ✅ 路由已正确注册（运行 php8 artisan route:list）"
        echo ""
        echo "### 6. 参考进度"
        echo "参考上方 Recent Progress 了解项目历史，避免重复工作或冲突。"
        echo ""
        echo "---"
        echo ""
        echo "🚀 现在开始执行任务... 记住：**严格遵循 CLAUDE.md 规范！**"
    } > "$prompt_file"

    log_verbose "Prompt 已组装到: $prompt_file"
    log_verbose "Prompt 预览（前 10 行）："
    log_verbose "$(head -n 10 "$prompt_file")"

    # Execute Claude Code CLI Agent
    log "🤖 调用 Claude Code CLI..."
    log "────────────────────────────────────────"

    # 使用 Claude Code CLI 执行任务（非交互模式）
    # --print: 非交互模式，打印响应后退出
    # --permission-mode: 权限模式（acceptEdits = 自动接受编辑）
    if cat "$prompt_file" | $CLAUDE_CMD --print --permission-mode "$PERMISSION_MODE" 2>&1; then
        agent_exit_code=0
        log_verbose "Claude Agent 执行成功"
    else
        agent_exit_code=$?
        log "⚠️  Claude Agent 退出，代码: $agent_exit_code"
    fi

    log "────────────────────────────────────────"
    echo ""

    # Clean up temp file
    rm -f "$prompt_file"

    # Check if task was marked as done
    log "🔍 检查任务状态..."

    if python3 .harness/scripts/harness-tools.py --action verify --id "$current_task_id" >/dev/null 2>&1; then
        # Task is complete
        log "✅ 任务 $current_task_id 已标记为完成"

        # Git commit
        if [ -d .git ] && command -v git &> /dev/null; then
            log "📦 创建 Git 提交..."

            task_desc=$(python3 .harness/scripts/harness-tools.py --action current 2>/dev/null | grep "描述:" | sed 's/描述: //')

            if git add -A . 2>/dev/null; then
                if git commit -m "$current_task_id: $task_desc" 2>/dev/null; then
                    log "✓ 已提交: $current_task_id: $task_desc"
                else
                    log "ℹ️  没有变更需要提交"
                fi
            fi
        fi

        # Reset retry count
        rm -f "$RETRY_DIR/${current_task_id}.count" 2>/dev/null || true

    else
        # Task not complete
        retry_file="$RETRY_DIR/${current_task_id}.count"
        if [ -f "$retry_file" ]; then
            current_retry_count=$(cat "$retry_file")
        else
            current_retry_count=0
        fi

        current_retry_count=$((current_retry_count + 1))
        echo "$current_retry_count" > "$retry_file"

        log "⚠️  任务 $current_task_id 尚未完成 (尝试 $current_retry_count/$MAX_RETRIES)"
        log "🔄 将在下次循环中重试"

        if [ $current_retry_count -ge $MAX_RETRIES ]; then
            log_error "任务 $current_task_id 已达到最大重试次数 ($MAX_RETRIES)"
            log_error "将跳过此任务并继续处理其他任务"
            touch "$SKIP_DIR/${current_task_id}"
        fi
    fi

    echo ""
    log "💤 等待 ${LOOP_SLEEP}秒后继续..."
    echo ""
    sleep $LOOP_SLEEP
done
