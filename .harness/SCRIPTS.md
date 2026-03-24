# Harness 脚本清单

> 按层级和用途分类的完整脚本清单

## Shell 层 (入口层)

| 脚本 | 用途 | 入口命令 |
|------|------|----------|
| `run-automation.sh` | 主自动化入口 | `./run-automation.sh` |
| `run-automation-stages.sh` | 多阶段自动化 | `./run-automation-stages.sh` |

### scripts/ 子目录

| 脚本 | 用途 |
|------|------|
| `check-memory-usage.sh` | 检查内存使用 |
| `check_php8.sh` | 检查 PHP8 环境 |
| `cleanup.sh` | 清理临时文件 |
| `generate-swagger.sh` | 生成 Swagger 文档 |
| `reset_harness.sh` | 重置 Harness |
| `test_cli_capture.sh` | 测试 CLI 捕获 |
| `verify-database-optimization.sh` | 验证数据库优化 |
| `verify_auth_001.sh` | 验证认证模块 |

---

## Python 层 (核心层)

### 核心脚本

| 脚本 | 用途 | 主要 action |
|------|------|-------------|
| `harness-tools.py` | 任务状态管理 | mark-stage, mark-done, list, current, verify |
| `next_stage.py` | 阶段检测和路由 | (无 CLI，直接被调用) |
| `add_task.py` | 添加新任务 | (通过 argparse) |

### 工具脚本

| 脚本 | 用途 |
|------|------|
| `knowledge.py` | 知识库管理 |
| `artifacts.py` | 产出追踪记录 |
| `validate_satisfaction.py` | 满意度验证 |
| `check_code_standards.py` | 代码规范检查 |
| `check_naming_standards.py` | 命名规范检查 |
| `detect_stage_completion.py` | 阶段完成检测 |
| `auto_detect_completion.py` | 自动完成检测 |
| `mark_done.py` | 标记任务完成 |
| `verify_output.py` | 验证输出 |

### 库脚本 (被其他模块调用)

| 脚本 | 用途 |
|------|------|
| `task_utils.py` | 任务编解码工具 |
| `task_file_storage.py` | 单文件存储 |
| `console_output.py` | 统一输出格式化 |
| `dual_timeout.py` | 双超时处理 |

### Agent CPU 集成脚本

| 脚本 | 用途 |
|------|------|
| `run-agent-cpu.py` | Python 调用 Node.js 的桥接脚本 |
| `test-agent-cpu.py` | Agent CPU 集成测试 |

### 其他

| 脚本 | 用途 |
|------|------|
| `laravel-agent.py` | Laravel Agent |
| `test_pipeline_prompt.py` | 测试管道 Prompt |
| `test_cleanup_logic.py` | 测试清理逻辑 |

---

## Node.js 层 (Agent CPU)

### 核心

| 脚本 | 用途 |
|------|------|
| `runtime.js` | Agent CPU 核心运行时 |
| `cli.js` | 命令行入口 |
| `index.js` | 统一导出 |

### 内置函数

| 脚本 | 用途 |
|------|------|
| `builtins/llmcall.js` | 确定性任务调用 |
| `builtins/agentcall.js` | 复杂任务调用 |
| `builtins/metacall.js` | 断言验证 |
| `builtins/index.js` | 统一导出 |

### 核心模块

| 脚本 | 用途 |
|------|------|
| `scope.js` | 作用域管理器 |
| `self-healing.js` | 自愈引擎 |
| `human-review.js` | 人工审查机制 |
| `knowledge-base.js` | 知识库管理 |
| `errors.js` | 自定义错误类 |

### 示例

| 脚本 | 用途 |
|------|------|
| `examples/basic-demo.js` | 基础演示 |
| `examples/basic-flow.js` | 基础流程示例 |
| `examples/self-heal-demo.js` | 自愈机制演示 |
| `examples/task-demo.js` | 任务处理演示 |

### 配置

| 文件 | 用途 |
|------|------|
| `package.json` | Node.js 依赖 |
| `config.json` | Agent CPU 配置 |
| `README.md` | 使用文档 |

---

## 调用关系图

```
Shell 入口
    │
    ├── run-automation.sh ──────→ Python 核心
    │                                  │
    └── run-automation-stages.sh ─────→├─ harness-tools.py ──→ 工具脚本
                                           │                    │
                                           │                    ├── knowledge.py
                                           │                    ├── artifacts.py
                                           │                    ├── check_code_standards.py
                                           │                    └── ...
                                           │
                                           ├─ next_stage.py
                                           │
                                           └─ run-agent-cpu.py ──→ Node.js Agent CPU
                                                                   │
                                                                   ├── runtime.js
                                                                   ├── builtins/
                                                                   ├── scope.js
                                                                   └── knowledge-base.js
```

---

## 快速命令参考

### 任务管理

```bash
# 查看任务列表
python3 .harness/scripts/harness-tools.py --action list

# 查看当前任务
python3 .harness/scripts/harness-tools.py --action current

# 标记阶段完成
python3 .harness/scripts/harness-tools.py --action mark-stage --id TASK_ID --stage dev

# 添加任务
python3 .harness/scripts/add_task.py --id TASK_001 --desc "任务描述"
```

### Agent CPU

```bash
# 执行代码
node .harness/agent-cpu/cli.js run --code "console.log('hello')"

# 知识库统计
node .harness/agent-cpu/cli.js kb --stats

# 列出审查
node .harness/agent-cpu/cli.js review --list
```

### Python 工具

```bash
# 知识库管理
python3 .harness/scripts/knowledge.py --action sync --task-id TASK_ID

# 代码规范检查
python3 .harness/scripts/check_code_standards.py

# 产出记录
python3 .harness/scripts/artifacts.py --action record --id TASK_ID file1.php file2.php
```

### 自动化

```bash
# 启动自动化
./harness/run-automation.sh

# 多阶段自动化
./harness/run-automation-stages.sh
```
