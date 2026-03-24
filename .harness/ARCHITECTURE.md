# Harness 架构文档

> 明确各层脚本的职责边界和调用关系

## 整体架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        Shell 入口层                               │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  │
│  │ run-automation  │  │ run-automation  │  │  其他脚本        │  │
│  │    -stages     │  │     .sh         │  │                 │  │
│  └────────┬───────┘  └────────┬───────┘  └────────┬────────┘  │
└───────────┼─────────────────────┼───────────────────┼────────────┘
            │                     │                    │
            ▼                     ▼                    ▼
┌───────────────────────────────────────────────────────────────────┐
│                     Python Harness 核心层                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│  │ harness-     │  │  next_stage  │  │   其他工具    │         │
│  │   tools.py   │  │    .py       │  │              │         │
│  │ (任务状态)   │  │ (阶段检测)   │  │              │         │
│  └──────┬───────┘  └──────────────┘  └──────────────┘         │
│         │                                                        │
│  ┌─────┴──────────────────────────────────────────────────┐       │
│  │              Python 工具层                            │       │
│  │  knowledge.py | artifacts.py | validate_satisfaction.py│       │
│  │  check_code_standards.py | add_task.py | ...         │       │
│  └───────────────────────────────────────────────────────┘       │
└───────────────────────────┬─────────────────────────────────────┘
                            │ 可选调用
                            ▼
┌───────────────────────────────────────────────────────────────────┐
│                     Node.js Agent CPU 层                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │   runtime.js │  │   cli.js     │  │   内置函数    │          │
│  │  (核心引擎)  │  │  (命令行)    │  │ (llmcall等)  │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
│                                                                   │
│  Agent CPU 职责:                                                  │
│  - 执行 LLM 生成的流程代码                                         │
│  - 管理作用域和上下文                                              │
│  - 提供断言验证和自愈机制                                          │
│  - 知识库同步                                                      │
└───────────────────────────────────────────────────────────────────┘
```

## 层级职责

### 1. Shell 入口层 (`*.sh`)

**职责**：流程控制和环境检查

| 脚本 | 职责 |
|------|------|
| `run-automation.sh` | 主入口，循环调用 Python 核心 |
| `run-automation-stages.sh` | 多阶段入口，调用 Claude Code |

**调用关系**：
```
用户执行 sh → Shell 检查环境 → 调用 Python 核心
```

### 2. Python Harness 核心层

**职责**：任务管理、状态流转、持久化

| 脚本 | 职责 | 对外接口 |
|------|------|----------|
| `harness-tools.py` | 任务状态管理 | `mark-stage`, `mark-done`, `list`, `current` |
| `next_stage.py` | 阶段检测和路由 | 输出下一个待处理阶段 |
| `task_utils.py` | 任务编解码 | 供其他模块调用 |
| `task_file_storage.py` | 单文件存储 | 供其他模块调用 |

**调用关系**：
```
Shell → harness-tools.py (CLI) → task_utils.py (库)
                        ↓
              next_stage.py → 输出阶段信息
```

### 3. Python 工具层

**职责**：辅助功能，Harness 的配套工具

| 脚本 | 职责 |
|------|------|
| `knowledge.py` | 知识库管理 |
| `artifacts.py` | 产出追踪 |
| `validate_satisfaction.py` | 满意度验证 |
| `check_code_standards.py` | 代码规范检查 |
| `add_task.py` | 添加任务 |
| `detect_stage_completion.py` | 阶段完成检测 |

**调用关系**：
```
harness-tools.py (调用) → 工具层脚本
                        ↓
              工具层内部调用 Python 库
```

### 4. Node.js Agent CPU 层

**职责**：流程代码执行引擎（新增层）

| 脚本 | 职责 |
|------|------|
| `runtime.js` | 核心运行时 |
| `cli.js` | 命令行入口 |
| `builtins/` | 内置函数 (llmcall/agentcall/metacall) |
| `scope.js` | 作用域管理 |
| `self-healing.js` | 自愈引擎 |
| `human-review.js` | 人工审查 |
| `knowledge-base.js` | 知识库 |

**调用关系**：
```
Python 核心 → run-agent-cpu.py → Node.js cli.js → runtime.js
                    或
           Python 核心 → subprocess → node runtime.js
```

## 调用边界规则

### Python → Node.js 调用（跨语言）

仅在以下情况调用：
1. **Agent CPU 执行**：需要运行流程代码时
2. **特殊计算**：Node.js 更擅长的场景

调用方式：
```bash
# Python 脚本中
subprocess.run(['node', 'cli.js', 'run', '--code', '...'], ...)
```

### Node.js → Python 调用（单向）

Node.js 不应该反向调用 Python，保持单向依赖：
- Node.js 只使用 Node.js 内置函数
- 如需持久化，通过 Python 提供的 API

### Shell → Python 调用（标准）

所有自动化流程通过 Shell 调用 Python：
```bash
python3 .harness/scripts/harness-tools.py --action ...
```

## 入口命令速查

| 操作 | 命令 |
|------|------|
| 启动自动化 | `./harness/run-automation.sh` |
| 查看任务列表 | `python3 .harness/scripts/harness-tools.py --action list` |
| 查看当前任务 | `python3 .harness/scripts/harness-tools.py --action current` |
| 查看阶段状态 | `python3 .harness/scripts/harness-tools.py --action stage-status --id XXX` |
| 标记阶段完成 | `python3 .harness/scripts/harness-tools.py --action mark-stage --id XXX --stage dev` |
| 添加任务 | `python3 .harness/scripts/add_task.py --id XXX --desc "..."` |
| Agent CPU 测试 | `node .harness/agent-cpu/cli.js run --code "..."` |
| Agent CPU 知识库 | `node .harness/agent-cpu/cli.js kb --stats` |

## 环境依赖

| 组件 | 依赖 |
|------|------|
| Shell 脚本 | Bash (Linux/macOS) 或 Git Bash (Windows) |
| Python 核心 | Python 3.7+ |
| Node.js Agent CPU | Node.js 18+ |

## 注意事项

1. **不要跨层反向调用**：Node.js 不调用 Python
2. **保持单向依赖**：Shell → Python → Node.js
3. **工具层可被多个模块调用**：但必须通过 Python 核心间接调用
4. **Agent CPU 是可选层**：现有流程不依赖它，可独立运行
