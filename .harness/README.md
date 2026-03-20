# Harness 自动化系统

AI 驱动的 Laravel 开发自动化框架，通过三阶段质量保证系统实现高质量代码生成。

---

## 快速开始

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
│   ├── init_prompt.md           # 初始化向导
│   ├── dev_prompt.md            # Dev 阶段
│   ├── test_prompt.md           # Test 阶段
│   └── review_prompt.md         # Review 阶段
│
├── contracts/                   # 接口契约和约束
│   ├── api_standards.json       # API 响应格式、错误码
│   └── model_contracts.json     # Model 契约、关系定义
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

```bash
python3 .harness/scripts/add_task.py \
  --id SIM_Feature_001 \
  --category feature \
  --desc "实现用户列表接口" \
  --priority P1 \
  --acceptance "文件存在" "方法已实现" "测试通过"
```

### 方式二：手动创建

```bash
cat > .harness/tasks/pending/SIM_Feature_001.json << 'EOF'
{
  "id": "SIM_Feature_001",
  "category": "feature",
  "complexity": "medium",
  "description": "实现用户列表接口",
  "acceptance": [
    "app/Http/Controllers/Api/App/UserController.php 存在",
    "包含 index 方法",
    "测试通过"
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
| `LOOP_SLEEP` | 5 | 循环间隔（秒） |
| `BASE_SILENCE_TIMEOUT` | 90 | 活性超时（秒） |
| `MAX_SILENCE_TIMEOUT` | 240 | 最大活性超时（秒） |

---

## 重要规则

1. **禁止手动编辑 `task-index.json`** - 由系统自动管理
2. **创建任务后必须重建索引** - `python3 .harness/scripts/task_file_storage.py --action rebuild-index`
3. **Dev 阶段必须记录产出** - 使用 `--files` 参数
4. **验收标准必须具体可验证** - 明确文件路径、方法名、预期结果
5. **测试使用 DatabaseTransactions** - 禁止 RefreshDatabase

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

## 初始化指引

### 首次使用初始化（必须执行）

首次将 Harness 复制到新项目时，需要执行以下初始化步骤：

#### 1. 复制环境配置

```bash
# 复制环境配置示例
cp .harness/.env.example .harness/.env
```

#### 2. 创建必需的目录结构

```bash
# 创建运行时目录
mkdir -p .harness/tasks/pending
mkdir -p .harness/tasks/completed
mkdir -p .harness/logs/automation
mkdir -p .harness/cli-io/sessions
mkdir -p .harness/artifacts
mkdir -p .harness/reports
mkdir -p .harness/knowledge
```

#### 3. 初始化任务索引

```bash
# 初始化 task-index.json
cat > .harness/task-index.json << 'EOF'
{
  "version": 2,
  "storage_mode": "single_file",
  "project": "你的项目名称",
  "created_at": "2024-01-01T00:00:00",
  "updated_at": "2024-01-01T00:00:00",
  "total_tasks": 0,
  "pending": 0,
  "completed": 0,
  "index": {}
}
EOF
```

#### 4. 初始化知识库（可选，用于 Laravel 开发规范）

```bash
# 初始化 constraints.json（全局约束）
cat > .harness/knowledge/constraints.json << 'EOF'
{
  "version": 1,
  "global": [
    "所有 API 必须使用 API Resource 格式化响应",
    "所有验证必须使用 FormRequest",
    "业务逻辑必须在 Service 层"
  ],
  "per_module": {}
}
EOF

# 初始化 contracts.json（接口契约）
cat > .harness/knowledge/contracts.json << 'EOF'
{
  "version": 1,
  "services": {},
  "api_responses": {
    "list": {
      "structure": {"data": "array", "meta": {"total": "integer"}}
    },
    "error": {
      "structure": {"message": "string", "errors": "object"}
    }
  }
}
EOF
```

#### 5. 初始化项目配置（可选）

```bash
# 初始化 project-config.json
cat > .harness/project-config.json << 'EOF'
{
  "tech_stack": {
    "language": "php",
    "framework": "laravel"
  },
  "paths": {
    "source": "app",
    "controllers": "app/Http/Controllers",
    "models": "app/Models",
    "tests": "tests"
  },
  "commands": {
    "test": "php artisan test",
    "lint": "php artisan pint"
  }
}
EOF
```

---

### 使用初始化向导（推荐）

参见 [templates/init_prompt.md](templates/init_prompt.md)，包含完整的初始化流程。

### 迁移到新项目时需要执行的操作

将 Harness 系统迁移到新项目时，需要清空历史数据和状态，确保系统从干净状态开始。

#### 1. 清空任务数据

```bash
# 删除所有待处理任务
rm -rf .harness/tasks/pending/*.json

# 删除所有已完成任务归档
rm -rf .harness/tasks/completed/*

# 删除任务索引（必须）
rm .harness/task-index.json
```

#### 2. 清空运行日志

```bash
# 删除自动化日志
rm -rf .harness/logs/automation/*

# 删除进度记录
rm -f .harness/logs/progress.md
```

#### 3. 清空CLI会话数据

```bash
# 删除当前会话
rm -f .harness/cli-io/current.json

# 删除历史会话记录
rm -rf .harness/cli-io/sessions/*
```

#### 4. 清空产出记录

```bash
# 删除任务产出记录
rm -rf .harness/artifacts/*

# 删除执行报告
rm -rf .harness/reports/*
```

#### 5. 重置任务索引

```bash
# 初始化 task-index.json（必须执行）
cat > .harness/task-index.json << 'EOF'
{
  "version": 2,
  "storage_mode": "single_file",
  "project": "新项目名称",
  "created_at": "$(date -Iseconds)",
  "updated_at": "$(date -Iseconds)",
  "total_tasks": 0,
  "pending": 0,
  "completed": 0,
  "index": {}
}
EOF

# 或使用Python命令初始化
python3 -c "
import json
from datetime import datetime
data = {
    'version': 2,
    'storage_mode': 'single_file',
    'project': '新项目名称',
    'created_at': datetime.now().isoformat(),
    'updated_at': datetime.now().isoformat(),
    'total_tasks': 0,
    'pending': 0,
    'completed': 0,
    'index': {}
}
with open('.harness/task-index.json', 'w', encoding='utf-8') as f:
    json.dump(data, f, indent=2, ensure_ascii=False)
"
```

#### 6. 一键重置脚本

创建初始化脚本 `.harness/scripts/reset_harness.sh`：

```bash
#!/bin/bash

echo "=== Harness 系统重置 ==="

# 1. 清空任务
echo "清空任务数据..."
rm -rf tasks/pending/*.json
rm -rf tasks/completed/*

# 2. 清空日志
echo "清空运行日志..."
rm -rf logs/automation/*
rm -f logs/progress.md

# 3. 清空CLI会话
echo "清空CLI会话..."
rm -f cli-io/current.json
rm -rf cli-io/sessions/*

# 4. 清空产出
echo "清空产出记录..."
rm -rf artifacts/*
rm -rf reports/*

# 5. 重置索引
echo "重置任务索引..."
python3 -c "
import json
from datetime import datetime
data = {
    'version': 2,
    'storage_mode': 'single_file',
    'project': '新项目名称',
    'created_at': datetime.now().isoformat(),
    'updated_at': datetime.now().isoformat(),
    'total_tasks': 0,
    'pending': 0,
    'completed': 0,
    'index': {}
}
with open('task-index.json', 'w', encoding='utf-8') as f:
    json.dump(data, f, indent=2, ensure_ascii=False)
"

echo "✓ 重置完成！"
```

使用方法：

```bash
cd .harness
chmod +x scripts/reset_harness.sh
./scripts/reset_harness.sh
```

#### 7. 修改项目配置

编辑 `.harness/task-index.json`：

```json
{
  "project": "新项目名称",  // 修改为你的项目名称
  ...
}
```

编辑 `.harness/.env`（如果需要）：

```bash
# 项目相关配置
PROJECT_NAME=新项目名称
```

#### 8. 验证初始化

```bash
# 检查任务列表（应该为空）
python3 .harness/scripts/harness-tools.py --action list

# 预期输出：
# [INFO] 项目: 新项目名称
# [INFO] 总任务数: 0
# [INFO] 待处理: 0
# [INFO] 已完成: 0
```

---

## 初始化检查清单

迁移到新项目时，按以下清单逐项检查：

- [ ] 已删除 `tasks/pending/*.json` 所有任务文件
- [ ] 已删除 `tasks/completed/*` 已完成任务归档
- [ ] 已删除 `task-index.json` 并重新初始化
- [ ] 已清空 `logs/automation/*` 运行日志
- [ ] 已删除 `logs/progress.md` 进度记录
- [ ] 已删除 `cli-io/current.json` 当前会话
- [ ] 已清空 `cli-io/sessions/*` 会话历史
- [ ] 已清空 `artifacts/*` 产出记录
- [ ] 已清空 `reports/*` 执行报告
- [ ] 已修改 `task-index.json` 中的项目名称
- [ ] 已验证任务列表为空

---

## 维护者

SIM-Laravel Team

**最后更新**: 2026-03-18