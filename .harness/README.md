# Harness 自动化系统

AI 驱动的开发自动化框架，通过三阶段质量保证系统实现高质量代码生成。

**支持任意技术栈**：React、Vue、Next.js、Laravel、Django 等，开箱即用。

---

## 快速开始

### 第一步：初始化系统（首次使用必需）

```bash
# 对话式初始化（推荐）
在 Claude Code 对话中说："帮我初始化 Harness 系统"

# 或手动触发（未来实现）
python3 .harness/scripts/init_harness.py
```

初始化向导会自动：
- ✅ 清空历史数据
- ✅ 识别项目技术栈（React/Vue/Laravel/等）
- ✅ 检查开发环境
- ✅ 生成项目配置
- ✅ 更新提示词模板
- ✅ 创建验收标准示例

### 第二步：创建任务

```bash
# 查看验收标准示例
cat .harness/examples/task_examples.json

# 创建任务
python3 .harness/scripts/add_task.py \
  --id FE_Component_001 \
  --desc "创建用户头像组件" \
  --acceptance \
    "src/components/UserAvatar/UserAvatar.tsx 存在" \
    "npm test 通过"
```

### 第三步：启动自动化

```bash
# 启动自动化
./.harness/run-automation.sh

# 查看当前任务
python3 .harness/scripts/harness-tools.py --action current

# 查看所有任务
python3 .harness/scripts/harness-tools.py --action list
```

---

## 目录结构

```
.harness/
├── README.md                    # 本文件（核心入口）
├── task-index.json              # 任务索引（禁止手动编辑）
├── project-config.json          # 【新增】项目配置（技术栈、路径、命令）
├── .env                         # 环境配置
├── run-automation.sh            # 自动化启动脚本
│
├── tasks/                       # 任务存储
│   ├── pending/                 # 待处理任务 *.json
│   └── completed/YYYY/MM/       # 已完成任务归档
│
├── scripts/                     # 自动化脚本
│   ├── harness-tools.py         # 核心工具（任务管理）
│   ├── next_stage.py            # 下一阶段检测
│   ├── add_task.py              # 创建新任务
│   ├── dual_timeout.py          # 超时控制
│   └── ...
│
├── templates/                   # Agent 提示词模板
│   ├── init_prompt.md           # 【新增】初始化向导提示词
│   ├── dev_prompt.md            # Dev 阶段
│   ├── test_prompt.md           # Test 阶段
│   ├── review_prompt.md         # Review 阶段
│   └── validation_prompt.md     # 验证阶段
│
├── examples/                    # 【新增】示例和模板
│   └── task_examples.json       # 验收标准示例
│
├── docs/                        # 详细文档
│   ├── stages_guide.md          # 三阶段系统详解
│   ├── ai_agent_quickstart.md   # AI Agent 快速入门
│   ├── task_file_storage_quickstart.md  # 单文件存储系统
│   └── troubleshooting.md       # 故障排查指南
│
├── logs/                        # 运行日志
│   └── progress.md              # 开发进度
│
├── cli-io/                      # CLI 会话管理
├── artifacts/                   # 任务产出记录
└── reports/                     # 执行报告
```

---

## 三阶段系统

每个任务依次通过三个独立 Agent 处理：

| 阶段 | 职责 | 输出 |
|------|------|------|
| **Dev** | 实现功能 | 代码文件 + 基础测试 |
| **Test** | 发现问题 | 测试报告 + 问题列表 |
| **Review** | 代码审查 | 质量评估 + 改进建议 |

**核心优势**：职责分离，独立审查，Bug 发现率从 ~60% 提升到 ~90%

---

## 任务创建

### 方式一：使用脚本（推荐）

#### React/Vue 项目示例

```bash
python3 .harness/scripts/add_task.py \
  --id FE_Component_001 \
  --category feature \
  --desc "创建用户头像组件" \
  --acceptance \
    "src/components/UserAvatar/UserAvatar.tsx 存在" \
    "支持三种尺寸: small, medium, large" \
    "npm test 通过"
```

#### Laravel 项目示例

```bash
python3 .harness/scripts/add_task.py \
  --id SIM_API_001 \
  --category feature \
  --desc "实现用户列表接口" \
  --acceptance \
    "app/Http/Controllers/Api/App/UserController.php 存在" \
    "包含 index 方法" \
    "php artisan test 通过"
```

**💡 提示**：查看更多示例
```bash
cat .harness/examples/task_examples.json
```

### 方式二：手动创建

```bash
cat > .harness/tasks/pending/FE_Component_001.json << 'EOF'
{
  "id": "FE_Component_001",
  "category": "feature",
  "complexity": "medium",
  "description": "创建用户头像组件",
  "acceptance": [
    "src/components/UserAvatar/UserAvatar.tsx 存在",
    "支持三种尺寸",
    "npm test 通过"
  ],
  "stages": {
    "dev": {"completed": false, "completed_at": null, "issues": []},
    "test": {"completed": false, "completed_at": null, "issues": [], "test_results": {}},
    "review": {"completed": false, "completed_at": null, "issues": [], "risk_level": null}
  }
}
EOF

# 重建索引
python3 .harness/scripts/task_file_storage.py --action rebuild-index
```

---

## 任务格式规范

```json
{
  "id": "SIM_Feature_001",           // 必填：唯一标识
  "category": "feature",             // 必填：controller/model/migration/feature/fix/test/style
  "complexity": "medium",            // 可选：simple/medium/complex
  "description": "任务描述",          // 必填：清晰描述
  "acceptance": ["标准1", "标准2"],   // 必填：可验证的验收标准
  "validation": {                    // 可选：满意度验证
    "enabled": true,
    "threshold": 0.8,
    "max_retries": 3
  },
  "stages": {...}                    // 系统自动管理
}
```

---

## 常用命令

### 任务管理

```bash
# 查看当前任务
python3 .harness/scripts/harness-tools.py --action current

# 查看阶段状态
python3 .harness/scripts/harness-tools.py --action stage-status --id TASK_ID

# 标记阶段完成
python3 .harness/scripts/harness-tools.py --action mark-stage \
  --id TASK_ID --stage dev --files file1.php file2.php

# 标记任务完成
python3 .harness/scripts/harness-tools.py --action mark-done --id TASK_ID

# 验证任务
python3 .harness/scripts/harness-tools.py --action verify --id TASK_ID
```

### 问题排查

```bash
# 查看日志
tail -f .harness/logs/automation/$(date +%Y/%m)/*.log

# 检查下一阶段
python3 .harness/scripts/next_stage.py

# 检测阶段完成状态
python3 .harness/scripts/detect_stage_completion.py --id TASK_ID --stage test
```

---

## 配置项

编辑 `.harness/.env`：

| 配置 | 默认值 | 说明 |
|------|--------|------|
| `CLAUDE_CMD` | claude | Claude CLI 命令 |
| `PERMISSION_MODE` | bypassPermissions | 权限模式 |
| `MAX_RETRIES` | 3 | 最大重试次数 |
| `LOOP_SLEEP` | 2 | 循环间隔（秒） |
| `BASE_SILENCE_TIMEOUT` | 60 | 活性超时（秒）- 无输出检测 |
| `MAX_SILENCE_TIMEOUT` | 180 | 最大活性超时（秒） |
| `TIMEOUT_BACKOFF_FACTOR` | 1.3 | 超时递增因子 |
| `MAX_TIMEOUT_RETRIES` | 3 | 最大超时重试次数 |

### 性能优化建议

如果任务执行太慢，可以调整以下参数：

```bash
# .harness/.env

# 降低活性超时（更快检测卡死）
BASE_SILENCE_TIMEOUT=60

# 降低最大超时（防止长时间卡住）
MAX_SILENCE_TIMEOUT=180

# 更快的循环间隔
LOOP_SLEEP=2
```

**硬超时配置**（在 `run-automation-stages.sh` 中）：
- `simple` 任务：300 秒（5 分钟）
- `medium` 任务：480 秒（8 分钟）
- `complex` 任务：600 秒（10 分钟）

---

## 重要规则

1. **首次使用必须初始化** - 在对话中说 "帮我初始化 Harness 系统"
2. **禁止手动编辑 `task-index.json`** - 由系统自动管理
3. **创建任务后必须重建索引** - `python3 .harness/scripts/task_file_storage.py --action rebuild-index`
4. **Dev 阶段必须记录产出** - 使用 `--files` 参数
5. **验收标准必须具体可验证** - 明确文件路径、方法名、预期结果
6. **测试隔离** - 确保测试不污染数据库或文件系统
7. **技术栈适配** - 如需切换技术栈，重新执行初始化流程

---

## 项目配置说明

初始化完成后，会在 `.harness/project-config.json` 中生成项目配置：

```json
{
  "tech_stack": {
    "language": "typescript",
    "framework": "react",
    "package_manager": "npm"
  },
  "paths": {
    "source": "src",
    "components": "src/components",
    "tests": "src/__tests__"
  },
  "commands": {
    "test": "npm test",
    "lint": "npm run lint",
    "build": "npm run build"
  }
}
```

此配置文件供所有脚本和模板使用，**修改此文件可影响整个系统行为**。

---

## 文档索引

| 文档 | 说明 |
|------|------|
| [stages_guide.md](docs/stages_guide.md) | 三阶段系统详解 |
| [ai_agent_quickstart.md](docs/ai_agent_quickstart.md) | AI Agent 快速入门 |
| [task_file_storage_quickstart.md](docs/task_file_storage_quickstart.md) | 单文件存储系统 |
| [troubleshooting.md](docs/troubleshooting.md) | 故障排查指南 |

---

## 工作流图

```
┌─────────────────────────────────────────────────────────────┐
│                    自动化工作流                              │
├─────────────────────────────────────────────────────────────┤
│  1. next_stage.py → 获取下一阶段                            │
│  2. 组装 Prompt（CLAUDE.md + 任务 + 模板）                  │
│  3. 调用 Claude Code CLI                                    │
│  4. Agent 执行并调用 mark-stage                             │
│  5. 检测完成状态                                            │
│  6. 完成 → Git 提交 → 下一任务                              │
│     失败 → 重试（最多3次）→ 跳过                            │
└─────────────────────────────────────────────────────────────┘
```

---

## 初始化指引（重要）

### 何时需要初始化

以下情况需要执行初始化：
- ✅ 首次将 Harness 复制到新项目
- ✅ 切换项目技术栈（如从 Laravel 切换到 React）
- ✅ 重置所有任务和环境数据
- ✅ 更新模板提示词以匹配新技术栈

### 智能初始化流程

Harness 采用**大模型驱动的智能初始化**，无需手动配置技术栈。

#### 执行方式

```
在 Claude Code 对话中说："帮我初始化 Harness 系统"
```

或（未来实现）：

```bash
python3 .harness/scripts/init_harness.py
```

#### 初始化步骤

向导会自动执行以下 8 个步骤：

**步骤 1: 清空历史数据**
- 删除所有旧任务
- 清空运行日志
- 重置 CLI 会话

**步骤 2: 识别技术栈**
- 自动读取 `package.json` / `composer.json` / `requirements.txt`
- 检测语言、框架、包管理器
- 分析目录结构
- **交互确认**检测结果

**步骤 3: 检查本地环境**
- 验证必需工具（node/php/python 等）
- 检查版本是否满足要求
- 提供缺失工具的安装建议

**步骤 4: 生成项目配置**
- 创建 `.harness/project-config.json`
- 配置路径映射（components/models/tests 等）
- 配置命令映射（test/lint/build 等）
- 配置验收标准模板

**步骤 5: 更新 CLAUDE.md**
- 检查项目根目录是否有 `CLAUDE.md`
- 如不存在，根据技术栈生成规范文档
- 包含代码风格、目录结构、测试策略

**步骤 6: 验证脚本兼容性**
- 检查 `.harness/scripts/*.py` 是否硬编码路径
- 自动适配脚本以读取 `project-config.json`

**步骤 7: 更新模板提示词**
- 替换 `templates/dev_prompt.md` 中的技术栈特定命令
- 替换 `templates/test_prompt.md` 测试命令
- 替换 `templates/review_prompt.md` 审查要点

**步骤 8: 创建验收标准示例**
- 在 `.harness/examples/task_examples.json` 添加示例
- 包含组件、Hook、API、页面等常见任务类型

#### 初始化示例

```
用户: 帮我初始化 Harness 系统

LLM: 我检测到这是一个 React + TypeScript 项目，使用了 Vite 作为构建工具。
     - 包管理器: npm
     - 测试框架: Vitest
     - 代码风格: ESLint + Prettier

     环境检查结果:
     ✅ Node.js v20.11.0
     ✅ npm 10.2.0

     是否继续生成配置？(Y/n)

用户: Y

LLM: 已创建 .harness/project-config.json
     已更新 CLAUDE.md（React + TypeScript 规范）
     已更新 templates/*.md（前端命令）

     ✅ 初始化完成！
     你现在可以创建任务了：
     python3 .harness/scripts/add_task.py --id FE_Component_001 --desc "创建用户头像组件"
```

#### 支持的技术栈

初始化向导可自动识别以下技术栈：

**前端框架**
- React + TypeScript/JavaScript
- Vue 3 + TypeScript/JavaScript
- Next.js (App Router/Pages Router)
- Nuxt.js
- Angular

**后端框架**
- Laravel (PHP)
- Django (Python)
- Flask (Python)
- Express (Node.js)
- NestJS (Node.js)

**其他**
- Go 项目
- Rust 项目
- 自定义技术栈（手动选择）

#### 如果检测失败

当无法自动识别技术栈时，向导会提供交互式选择：

```
⚠️  无法自动识别技术栈

请手动选择技术栈：
1. React + TypeScript
2. Vue + TypeScript
3. Next.js
4. Laravel (PHP)
5. Django (Python)
6. 其他（请描述）

请输入选项 (1-6):
```

---

## 初始化检查清单

迁移到新项目时，向导会自动完成以下检查：

- [x] 已清空历史任务和环境数据
- [x] 已识别技术栈并确认
- [x] 已检查开发环境
- [x] 已生成 `project-config.json`
- [x] 已创建或更新 `CLAUDE.md`
- [x] 已验证脚本兼容性
- [x] 已更新模板提示词
- [x] 已创建验收标准示例

---

## 初始化输出文件

初始化完成后，会生成以下文件：

| 文件 | 说明 |
|------|------|
| `.harness/project-config.json` | 项目配置（技术栈、路径、命令） |
| `CLAUDE.md` | 项目规范文档（如不存在） |
| `.harness/templates/init_prompt.md` | 初始化向导提示词 |
| `.harness/examples/task_examples.json` | 验收标准示例 |

---

## 维护者

Harness Automation Team

**最后更新**: 2026-03

**核心特性**：
- 🚀 智能技术栈识别
- 🔄 三阶段质量保证（Dev → Test → Review）
- 📦 开箱即用，支持任意技术栈
- 🤖 大模型驱动初始化

---

## 快速参考

### 必需操作

```bash
# 首次使用
对话中说："帮我初始化 Harness 系统"

# 创建任务
python3 .harness/scripts/add_task.py --id FE_Component_001 --desc "描述"

# 启动自动化
./.harness/run-automation.sh
```

### 常用命令

```bash
# 查看当前任务
python3 .harness/scripts/harness-tools.py --action current

# 查看所有任务
python3 .harness/scripts/harness-tools.py --action list

# 标记阶段完成
python3 .harness/scripts/harness-tools.py --action mark-stage --id TASK_ID --stage dev --files file1 file2

# 查看验收标准示例
cat .harness/examples/task_examples.json
```

### 关键文件

- **项目配置**: `.harness/project-config.json`
- **开发规范**: `CLAUDE.md`
- **初始化提示词**: `.harness/templates/init_prompt.md`
- **验收示例**: `.harness/examples/task_examples.json`
- **任务模板**: `.harness/templates/dev_prompt.md` 等