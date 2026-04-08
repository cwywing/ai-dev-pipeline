# Harness 自动化系统

AI 驱动的开发自动化框架，通过三阶段质量保证系统实现高质量代码生成。

**支持任意技术栈**：React、Vue、Next.js、Laravel、Django 等，开箱即用。
**统一 Python 架构**：全部核心脚本已从 Shell/BAT 迁移为原生 Python 模块。

---

## 快速开始

### 第一步：安装依赖

```bash
pip install -r .harness/requirements.txt
```

### 第二步：配置环境

```bash
# 复制环境配置（首次使用）
cp .harness/.env.example .harness/.env
```

### 第三步：初始化系统

```bash
# 对话式初始化（推荐）
在 Claude Code 对话中说："帮我初始化 Harness 系统"
```

### 第四步：创建任务

```bash
python .harness/scripts/add_task.py \
  --id FE_Component_001 \
  --desc "创建用户头像组件" \
  --acceptance \
    "src/components/UserAvatar/UserAvatar.tsx 存在" \
    "npm test 通过"
```

### 第五步：启动自动化

```bash
# 启动自动化（连续循环）
python .harness/scripts/run_automation.py

# 单次执行（调试用）
python .harness/scripts/run_automation.py --once

# 启用详细日志
python .harness/scripts/run_automation.py --once -v
```

---

## 目录结构

```
.harness/
├── README.md                    # 本文件
├── task-index.json              # 任务索引（自动管理）
├── .env.example                 # 环境配置模板
├── requirements.txt             # Python 依赖
│
├── scripts/                     # 核心脚本（统一 Python 架构）
│   ├── config.py                # 配置中心（路径、环境变量、超时、项目配置加载）
│   ├── logger.py                # 日志系统（loguru / stdlib 双后端）
│   ├── run_automation.py        # 主引擎（智能调度、依赖注入、知识同步）
│   ├── task_storage.py          # 任务存储引擎（O(1) 存取、阶段管理）
│   ├── next_stage.py            # 调度器（P0~P3 优先级、依赖阻断）
│   ├── detect_stage_completion.py  # 阶段完成检测器
│   ├── dual_timeout.py          # 双重超时执行器（Unix PTY / Windows threading）
│   ├── validate_satisfaction.py # LLM 裁判（满意度验证、CodeReader）
│   ├── knowledge.py             # 知识库管理（自动同步、契约/约束去重合并）
│   ├── api_flow_test.py         # API 全流程测试
│   ├── add_task.py              # 创建新任务
│   ├── harness-tools.py         # 任务管理工具
│   ├── artifacts.py             # 产出记录
│   ├── task_utils.py            # TaskCodec 编解码
│   ├── reset_harness.py         # 系统重置
│   └── ...                      # 其他辅助脚本
│
├── tasks/                       # 任务存储
│   ├── pending/                 # 待处理任务 *.json
│   └── completed/YYYY/MM/       # 已完成任务归档
│
├── templates/                   # Agent 提示词模板
│   ├── init_prompt.md           # 初始化向导
│   ├── dev_prompt.md            # Dev 阶段
│   ├── test_prompt.md           # Test 阶段
│   ├── review_prompt.md         # Review 阶段
│   └── validation_prompt.md     # 验证阶段
│
├── knowledge/                   # 全局知识库
│   ├── contracts.json           # Service 接口契约
│   ├── constraints.json         # 全局约束存储
│   ├── api_standards.json       # API 响应格式与状态码规范
│   └── model_contracts.json      # Model 层数据契约
│
├── docs/                        # 详细文档
│   ├── stages_guide.md          # 三阶段系统详解
│   ├── ai_agent_quickstart.md   # AI Agent 快速入门
│   ├── task_file_storage_quickstart.md  # 单文件存储系统
│   ├── troubleshooting.md       # 故障排查指南
│   └── initialization_guide.md  # 初始化指引
│
├── examples/                    # 示例和模板
│   └── task_examples.json       # 验收标准示例
│
├── logs/                        # 运行日志（按月归档）
├── cli-io/                      # CLI 会话管理
├── artifacts/                   # 任务产出记录
└── reports/                     # 测试报告
```

---

## 三阶段系统

每个任务依次通过三个独立 Agent 处理：

| 阶段 | 职责 | 检测方式 |
|------|------|----------|
| **Dev** | 实现功能 | Git diff + Artifacts 文件 |
| **Test** | 发现问题 | 测试执行痕迹（assert / pass / fail） |
| **Review** | 代码审查 | 关键词命中 + 文本量 |

可选第四阶段 **Validation**（LLM-as-a-Judge 满意度验证）：
- `SatisfactionValidator` 作为独立裁判，只读取任务变更的文件（Token 优化）
- 逐条验收标准对比，输出 `<score>0~100</score>`
- 未达标（<80 分）自动回滚到 Dev 阶段并注入评审反馈
- 最多重试 `max_retries` 次

**核心优势**：职责分离，独立审查，Bug 发现率从 ~60% 提升到 ~90%

---

## 智能调度与知识沉淀（Phase 5）

### 项目约定注入

在项目根目录放置 `project-config.json`，定义技术栈、命名规范、API 约定、代码风格等。自动化引擎启动时会自动读取并注入到每个 Agent 的 Prompt 顶部：

```
Prompt 注入顺序:
0.  [SYSTEM DIRECTORY CONTEXT]  ← 工作区路径 + 引擎路径
0.5 [PROJECT GLOBAL CONVENTIONS] ← project-config.json
1.  CLAUDE.md
1.5 [DEPENDENCY CONTEXT]         ← 前置任务的产出
2.  {stage}_prompt.md
3.  Task Context
```

### 优先级与依赖调度

- **P0~P3 优先级排序**：高优先级任务优先调度
- **依赖阻断**：任务的 `depends_on` 字段中未完成的前置任务会挂起当前任务
- **依赖上下文注入**：前置任务的接口契约、设计决策、约束自动注入当前任务 Prompt

### 知识库自动同步

当 Dev / Review 阶段完成时，引擎自动从任务产出中提取接口契约和约束，合并写入全局知识库：

```
Task 完成 → sync_task_artifacts()
  ├─ interface_contracts → knowledge/contracts.json（去重合并）
  └─ constraints         → knowledge/constraints.json（去重合并）
```

后续任务通过依赖上下文注入机制自动获取这些知识。

### LLM 裁判（Validation 阶段）

`validate_satisfaction.py` 实现完整的 LLM-as-a-Judge 验证：

```bash
# 手动对指定任务执行验证
python .harness/scripts/validate_satisfaction.py --task-id Model_001
```

- `CodeReader` 精准提取：只读 artifact 中记录的变更文件（50KB 封顶）
- 严厉审查官 Prompt：逐条 AC 对比，YES / PARTIAL / NO 状态
- 复用 `DualTimeoutExecutor`，超时自动返回 0 分
- 缺失 `<score>` 标签时自动补 0 分

---

## 核心命令

### 自动化引擎

```bash
# 启动连续自动化循环
python .harness/scripts/run_automation.py

# 单次执行（处理一个阶段后退出）
python .harness/scripts/run_automation.py --once

# 启用详细日志（调试模式）
python .harness/scripts/run_automation.py --once -v
```

### 任务管理

```bash
# 创建任务
python .harness/scripts/add_task.py \
  --id TASK_ID --desc "描述" --acceptance "标准1" "标准2"

# 创建带依赖的任务
python .harness/scripts/add_task.py \
  --id TASK_002 --desc "描述" \
  --depends-on TASK_001 \
  --acceptance "标准1"

# 查看当前任务
python .harness/scripts/harness-tools.py --action current

# 查看所有任务
python .harness/scripts/harness-tools.py --action list

# 查看阶段状态
python .harness/scripts/harness-tools.py --action stage-status --id TASK_ID

# 标记阶段完成
python .harness/scripts/harness-tools.py --action mark-stage \
  --id TASK_ID --stage dev --files file1.php file2.php

# 标记任务完成
python .harness/scripts/harness-tools.py --action mark-done --id TASK_ID
```

### 知识库 & API 测试

```bash
# 从任务产出同步到知识库
python .harness/scripts/knowledge.py --action sync --task-id Model_001

# 列出所有知识
python .harness/scripts/knowledge.py --action list

# 查询服务契约
python .harness/scripts/knowledge.py --action query --service UserService

# 手动执行 LLM 裁判验证
python .harness/scripts/validate_satisfaction.py --task-id Model_001

# API 全流程测试
python .harness/scripts/api_flow_test.py http://localhost:8000

# 带 Token 的 API 测试
python .harness/scripts/api_flow_test.py http://localhost:8000 \
  --token "Bearer xxx"
```

### 问题排查

```bash
# 查看配置
python .harness/scripts/config.py

# 检查下一阶段
python .harness/scripts/next_stage.py

# 检测阶段完成状态
python .harness/scripts/detect_stage_completion.py --id TASK_ID --stage test

# 重置系统
python .harness/scripts/reset_harness.py
```

---

## 任务格式规范

```json
{
  "id": "Feature_001",
  "category": "feature",
  "complexity": "medium",
  "description": "任务描述",
  "acceptance": ["标准1", "标准2"],
  "depends_on": ["Infra_001"],
  "validation": {
    "enabled": true,
    "threshold": 0.8,
    "max_retries": 3
  },
  "stages": {
    "dev": {"completed": false, "completed_at": null, "issues": []},
    "test": {"completed": false, "completed_at": null, "issues": [], "test_results": {}},
    "review": {"completed": false, "completed_at": null, "issues": [], "risk_level": null},
    "validation": {"completed": false, "completed_at": null}
  }
}
```

---

## 工作区隔离（Phase 6）

引擎（控制面）与业务代码（数据面）通过 `PROJECT_ROOT` 彻底隔离：

```
引擎目录 (ENGINE_ROOT)          ← .harness/、.git、README 等
├── .harness/                   ← HARNESS_DIR: 引擎核心资产（永远不动）
│   ├── tasks/                  ← 任务存储
│   ├── knowledge/              ← 知识库
│   ├── artifacts/              ← 产出记录
│   ├── logs/                   ← 运行日志
│   └── cli-io/                 ← 会话管理
└── sandbox/                    ← PROJECT_ROOT (默认): Agent 写代码的地方

配置外部工作区后:
├── .harness/                   ← 引擎资产
└── /path/to/laravel/           ← PROJECT_ROOT: Agent 在真实项目中写代码
```

配置 `.harness/.env`：

| 配置 | 默认值 | 说明 |
|------|--------|------|
| `TARGET_WORKSPACE` | `sandbox/` | Agent 读写业务代码的绝对路径 |

- 未配置或路径不存在时自动回退到 `sandbox/`
- `project-config.json` 先在工作区查找，找不到回退到引擎根目录
- `DualTimeoutExecutor` 的子进程 `cwd` 严格指向 `PROJECT_ROOT`
- Agent Prompt 顶部注入 `[SYSTEM DIRECTORY CONTEXT]` 明确告知工作路径

---

## 配置项

编辑 `.harness/.env`：

| 配置 | 默认值 | 说明 |
|------|--------|------|
| `TARGET_WORKSPACE` | sandbox/ | 业务代码工作区绝对路径 |
| `CLAUDE_CMD` | claude | Claude CLI 命令 |
| `PERMISSION_MODE` | bypassPermissions | 权限模式 |
| `MAX_RETRIES` | 3 | 最大逻辑重试次数 |
| `LOOP_SLEEP` | 2 | 循环间隔（秒） |
| `BASE_SILENCE_TIMEOUT` | 60 | 基础活性超时（秒） |
| `MAX_SILENCE_TIMEOUT` | 180 | 最大活性超时（秒） |
| `TIMEOUT_BACKOFF_FACTOR` | 1.3 | 超时递增因子 |
| `MAX_TIMEOUT_RETRIES` | 3 | 最大超时重试次数 |
| `ENABLE_AUTO_VALIDATION` | false | 启用自动满意度验证 |
| `SKIP_PHP_CHECK` | false | 跳过 PHP 环境检查 |

### 超时计算

各阶段硬超时 = `BASE_SILENCE_TIMEOUT x 阶段系数 x 退避因子`

| 阶段 | 系数 | 默认超时 |
|------|------|----------|
| dev | 4.0x | 240s |
| test | 3.0x | 180s |
| review | 2.0x | 120s |
| validation | 1.5x | 90s |

---

## 工作流图

```
┌─────────────────────────────────────────────────────────────┐
│                    自动化工作流                              │
├─────────────────────────────────────────────────────────────┤
│  1. run_automation.py 主循环启动                             │
│  2. next_stage.py → P0~P3 优先级排序 + 依赖阻断             │
│  3. 组装 Prompt (cwd=PROJECT_ROOT)                           │
│     a. [SYSTEM DIRECTORY CONTEXT] → 工作区 + 引擎路径          │
│     b. project-config.json → [PROJECT GLOBAL CONVENTIONS]   │
│     c. CLAUDE.md                                            │
│     d. _build_dependency_context() → [DEPENDENCY CONTEXT]   │
│     e. {stage}_prompt.md + 任务上下文                        │
│  4. dual_timeout.py → 调用 Claude Code CLI                  │
│     - Unix: PTY (pty/fcntl/select)                          │
│     - Windows: threading + subprocess                       │
│  5. detect_stage_completion.py → 检测完成状态               │
│  6. task_storage.py → 更新阶段状态                           │
│  7. _sync_knowledge() → 知识库自动沉淀                       │
│     - interface_contracts → contracts.json                  │
│     - constraints → constraints.json                        │
│  8. Validation: validate_satisfaction.py → LLM 裁判打分     │
│     - <score>80</score> → 通过                              │
│     - <score>45</score> → 回滚到 Dev + 注入反馈            │
│  9. 完成 → 下一阶段                                         │
│     失败 → 重试（最多 MAX_RETRIES 次）→ 跳过                 │
└─────────────────────────────────────────────────────────────┘
```

---

## 技术架构

### 原生 Python 模块

核心脚本之间使用原生 Python `import`，不再通过 subprocess 调用 Shell 脚本：

```
run_automation.py (主引擎)
    ├── import next_stage            # P0~P3 优先级调度 + 依赖阻断
    ├── import detect_stage_completion  # 阶段完成检测
    ├── import task_storage          # 任务存储读写
    ├── import knowledge             # 知识库自动同步
    ├── import validate_satisfaction # LLM 裁判（Validation 阶段）
    ├── import dual_timeout          # Claude CLI 执行
    ├── import config                # 全局配置 + project-config.json
    └── import logger                # 日志系统
```

### 跨平台超时执行

`DualTimeoutExecutor` 自动根据运行平台选择实现：

- **Linux / macOS**: `_UnixExecutor` — 基于 PTY 伪终端 + `select` 非阻塞 I/O
- **Windows**: `_WindowsExecutor` — 基于 `threading` + `subprocess.PIPE`

双重超时机制：
- **活性超时** (Silence Timeout): 无输出即判定卡死，终止进程
- **硬超时** (Hard Timeout): 绝对上限，强制 kill

退出码约定：`0`=正常, `14`=活性超时, `124`=硬超时, `1`=启动失败

---

## 初始化指引

### 何时需要初始化

- 首次将 Harness 复制到新项目
- 切换项目技术栈
- 重置所有任务和环境数据

### 执行方式

```
在 Claude Code 对话中说："帮我初始化 Harness 系统"
```

初始化向导会自动：清空历史数据、识别技术栈、检查环境、生成项目配置、更新模板提示词。

详细说明见 [docs/initialization_guide.md](docs/initialization_guide.md)。

---

## 文档索引

| 文档 | 说明 |
|------|------|
| [stages_guide.md](docs/stages_guide.md) | 三阶段系统详解 |
| [ai_agent_quickstart.md](docs/ai_agent_quickstart.md) | AI Agent 快速入门 |
| [task_file_storage_quickstart.md](docs/task_file_storage_quickstart.md) | 单文件存储系统 |
| [troubleshooting.md](docs/troubleshooting.md) | 故障排查指南 |
| [initialization_guide.md](docs/initialization_guide.md) | 初始化指引 |

---

## 知识库文件说明

| 文件 | 用途 |
|------|------|
| `contracts.json` | Service 层接口契约 |
| `constraints.json` | 全局约束条件 |
| `api_standards.json` | API 响应格式、状态码、验证规则 |
| `model_contracts.json` | Model 层数据契约、关系定义 |

---

## 重要规则

1. **首次使用必须初始化** — 在对话中说 "帮我初始化 Harness 系统"
2. **禁止手动编辑 `task-index.json`** — 由 task_storage.py 自动管理
3. **验收标准必须具体可验证** — 明确文件路径、方法名、预期结果
4. **测试隔离** — 确保测试不污染数据库或文件系统

---

## 快速参考

```bash
# 安装依赖
pip install -r .harness/requirements.txt

# 创建并启动
python .harness/scripts/add_task.py --id TASK_001 --desc "描述" --acceptance "标准"
python .harness/scripts/run_automation.py --once -v

# 持续运行
python .harness/scripts/run_automation.py
```

---

**最后更新**: 2026-04
