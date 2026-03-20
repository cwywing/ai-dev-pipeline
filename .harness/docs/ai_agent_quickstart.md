# SIM-Laravel 自动化系统快速入门指南

## 🤖 专为 AI 助手设计

本指南帮助 AI 助手理解自动化系统的结构、配置和执行流程。

---

## 📋 系统概述

### 项目结构
```
sim-laravel/
├── .harness/                      # 自动化系统
│   ├── task-index.json            # 任务索引（核心文件）
│   ├── tasks/                     # 任务存储目录
│   │   ├── pending/               # 待处理任务
│   │   └── completed/             # 已完成任务（按年月归档）
│   │       └── YYYY/MM/
│   ├── scripts/                   # Python/Bash 脚本
│   │   ├── harness-tools.py      # 工具函数（核心）
│   │   ├── task_file_storage.py  # 单文件存储系统
│   │   ├── artifacts.py          # 任务产物追踪
│   │   ├── check_php8.sh         # PHP 8 环境检查
│   │   ├── verify_auth_001.sh    # 任务验收脚本
│   │   └── verify_migrations.php # 迁移验证脚本
│   ├── templates/                 # Agent 提示词模板
│   │   ├── dev_prompt.md         # 开发阶段
│   │   ├── test_prompt.md        # 测试阶段
│   │   └── review_prompt.md      # 审查阶段
│   ├── docs/                      # 自动化系统文档
│   │   └── STAGES_GUIDE.md       # 三阶段指南
│   ├── logs/                      # 运行日志（按年月归档）
│   │   └── YYYY/MM/
│   ├── cli-io/                    # CLI 会话管理
│   │   ├── current.json          # 当前会话元数据
│   │   └── sessions/             # 会话输出文件
│   ├── artifacts/                 # 任务产物（代码、报告等）
│   ├── backups/                   # 系统备份
│   ├── run-automation-stages.sh   # 三阶段自动化启动脚本（推荐）
│   └── run-automation.sh          # 旧版单阶段脚本（保留）
├── docs/                          # 业务文档
├── app/Http/Controllers/          # Laravel 代码
└── CLAUDE.md                      # 开发规范
```

### 三阶段质量保证
1. **Dev 阶段**: 实现功能
2. **Test 阶段**: 发现问题
3. **Review 阶段**: 代码审查

### 单文件存储系统
- **task-index.json**: O(1) 查找性能的任务索引
- **tasks/pending/*.json**: 待处理任务文件
- **tasks/completed/YYYY/MM/*.json**: 已完成任务归档

---

## 🎯 任务定义格式

### 任务结构
```json
{
  "id": "SIM_Feature_001",
  "category": "controller",        // controller/migration/model/test/documentation 等
  "complexity": "medium",          // simple/medium/complex
  "description": "实现 SIM 列表查询接口",
  "acceptance": [
    "app/Http/Controllers/Api/App/SimController.php 存在",
    "包含 index 方法",
    "返回 API Resource 格式",
    "包含分页功能",
    "包含搜索功能"
  ],
  "validation": {                  // 满意度验证配置（可选）
    "enabled": true,               // 是否启用验证
    "threshold": 0.8,              // 验证通过阈值（0.0-1.0）
    "max_retries": 3                // 最大重试次数
  },
  "stages": {
    "dev": {"completed": false, "completed_at": null, "issues": []},
    "test": {"completed": false, "completed_at": null, "issues": [], "test_results": {}},
    "review": {"completed": false, "completed_at": null, "issues": [], "risk_level": null}
  }
}
```

}
```

### Category 类别说明

| Category | 说明 | 自动执行 | 适用场景 |
|----------|------|---------|---------|
| controller | 控制器开发 | ❌ 否 | 实现 API 接口 |
| model | 模型开发 | ❌ 否 | 数据表、关联关系 |
| migration | 数据库迁移 | ❌ 否 | 表结构变更 |
| feature | 综合功能开发 | ❌ 否 | 需要多步骤的任务 |
| fix | Bug 修复 | ❌ 否 | 修复现有代码问题 |
| test | 测试验证 | ✅ 是 php8 artisan test | 纯测试任务 |
| style | 代码风格 | ✅ 是 ./vendor/bin/pint | 纯代码检查任务 |

⚠️ 重要提示：
- test 和 style 类任务会自动执行命令并跳过 Dev 阶段
- 其他类别会正常执行 Dev → Test → Review → Validation 流程
- 满意度验证阶段通过 --validation-enabled 参数启用，与 category 无关
- 不要使用 category: validation，这会导致逻辑错误

**validation 字段说明**：
- `enabled`: 是否启用满意度验证（默认 `false`）
  - `false`: 不启用，Review 阶段完成后直接标记任务完成
  - `true`: 启用，Review 阶段会调用 Claude 独立评估任务完成质量
- `threshold`: 验证通过阈值（0.0-1.0，默认 0.8）
  - 计算公式：`满意度 = 通过的验收标准数 / 总验收标准数`
  - 如果 `满意度 ≥ threshold` → 验证通过，标记任务完成
  - 如果 `满意度 < threshold` → 返回 Dev 阶段重试
- `max_retries`: 验证失败后最大重试次数（默认 3）
  - 达到最大次数仍未通过 → 任务标记为失败

### 验收标准规范
- **具体**: 指明具体文件、类、方法
- **可验证**: 可以用脚本验证（如 `php artisan test`）
- **可量化**: 包含数量指标（如覆盖率 >80%）
- **完整性**: 涵盖功能的各个方面

---

## 🔧 配置检查清单

### 1. 环境准备
```bash
# 检查依赖
which claude python3 php
composer install
```

### 2. 项目配置
- [ ] `.env` 已配置数据库连接
- [ ] 数据库连接正常 (`php artisan migrate:status`)
- [ ] `CLAUDE.md` 规范已阅读
- [ ] `.harness/task-index.json` 存在且格式正确
- [ ] `.harness/tasks/pending/` 目录存在

### 3. 任务完整性
- [ ] 任务描述清晰具体
- [ ] 验收标准可验证
- [ ] 类别归属正确
- [ ] 不存在冲突任务

### 4. 自动化配置
- [ ] `run-automation-stages.sh` 权限正确（`chmod +x`）
- [ ] Python 脚本可执行
- [ ] Claude CLI 已配置

---

## 🚀 执行前确认

### 1. 任务索引检查
```bash
# 验证任务索引 JSON 格式
python3 -c "import json; json.load(open('.harness/task-index.json'))"
```

### 2. 系统可用性检查
```bash
# 查看当前待处理任务
python3 .harness/scripts/harness-tools.py --action current

# 检查下一阶段任务
python3 .harness/scripts/next_stage.py
```

### 3. 脚本权限检查
```bash
ls -la .harness/run-automation-stages.sh
```

---

## ⚡ 开始执行

### 1. 启动自动化循环
```bash
./.harness/run-automation-stages.sh
```

### 2. 监控执行状态
```bash
# 查看当前任务
python3 .harness/scripts/harness-tools.py --action current

# 查看任务详情
python3 .harness/scripts/harness-tools.py --action stage-status --id TASK_ID

# 查看实时日志（日志按年月归档）
tail -f .harness/logs/$(date +%Y/%m)/automation_*.log
```

### 3. 手动干预（如需要）
```bash
# 标记阶段完成
python3 .harness/scripts/harness-tools.py --action mark-stage --id TASK_ID --stage dev --files file1.php file2.php

# 标记任务完成
python3 .harness/scripts/harness-tools.py --action mark-done --id TASK_ID

# 更新进度记录
python3 .harness/scripts/harness-tools.py --action update-progress --id TASK_ID \
  --what-done "创建了 SimController" \
  --test-result "测试通过" \
  --next-step "继续下一个任务"
```

---

## 🛠️ 常用命令

### 任务管理
```bash
# 查看当前任务
python3 .harness/scripts/harness-tools.py --action current

# 标记阶段完成
python3 .harness/scripts/harness-tools.py --action mark-stage --id TASK_ID --stage dev --files file1.php file2.php

# 标记任务完成
python3 .harness/scripts/harness-tools.py --action mark-done --id TASK_ID

# 查看所有任务状态
python3 .harness/scripts/harness-tools.py --action list

# 查看阶段状态
python3 .harness/scripts/harness-tools.py --action stage-status --id TASK_ID

# 验证任务完成度
python3 .harness/scripts/harness-tools.py --action verify --id TASK_ID
```

### 系统维护
```bash
# 检查下一待处理阶段
python3 .harness/scripts/next_stage.py

# 运行测试
php artisan test

# 检查代码风格
./vendor/bin/pint --test

# 查看进度日志
cat .harness/logs/progress.md
```

### 产物管理
```bash
# 记录任务产物
python3 .harness/scripts/artifacts.py record --task-id TASK_ID --file-path /path/to/file

# 查看任务产物
python3 .harness/scripts/artifacts.py get --task-id TASK_ID

# 清理旧产物（保留最近 7 天）
python3 .harness/scripts/artifacts.py clean --days 7
```

---

## 📝 AI 助手使用流程

### 1. 接收开发任务
- 用户提供具体功能需求
- AI 理解业务逻辑和技术要求

### 2. 分析任务结构
- 确定 API 端点（App/Admin）
- 设计数据库结构
- 规划代码层次（Controller/Service/Model/Resource）

### 3. 创建任务文件
```bash
# 使用工具创建新任务（推荐）
python3 .harness/scripts/task_file_storage.py create \
  --id SIM_New_Feature_001 \
  --category controller \
  --complexity medium \
  --description "实现新功能" \
  --acceptance "验收标准1" "验收标准2"
```

或者手动创建：
```bash
# 在 tasks/pending/ 目录创建任务文件
cat > .harness/tasks/pending/SIM_New_Feature_001.json <<EOF
{
  "id": "SIM_New_Feature_001",
  "category": "controller",
  "complexity": "medium",
  "description": "实现新功能",
  "acceptance": ["验收标准1", "验收标准2"],
  "stages": {
    "dev": {"completed": false, "completed_at": null, "issues": []},
    "test": {"completed": false, "completed_at": null, "issues": [], "test_results": {}},
    "review": {"completed": false, "completed_at": null, "issues": [], "risk_level": null}
  }
}
EOF

# 重建索引
python3 .harness/scripts/task_file_storage.py rebuild-index
```

### 4. 验证配置
- 确认任务已添加到索引
- 验证验收标准完整性
- 检查环境准备就绪

### 5. 准备执行
- 确认 `.env` 配置正确
- 确认数据库连接正常
- 验证自动化脚本权限

### 6. 启动自动化
- 建议用户运行: `./.harness/run-automation-stages.sh`
- 说明监控方法和预期时间

### 7. 持续跟进
- 监控执行状态
- 处理异常情况
- 优化验收标准

---

## ⚠️ 注意事项

- **不要手动编辑 task-index.json** - 它是由单文件存储系统自动生成的
- **创建任务后必须重建索引** - 运行 `python3 .harness/scripts/task_file_storage.py rebuild-index`
- **确保验收标准具体可验证** - 便于自动化检查
- **保持任务粒度适中** - 每个任务 1-3 个验收标准
- **遵循 Laravel 规范** - 参考 `CLAUDE.md`
- **测试先行** - 采用 TDD 开发模式
- **使用 DatabaseTransactions** - 测试必须使用 `use DatabaseTransactions;` trait

---

## 🎯 执行确认

当你收到用户的开发任务时：

1. **[ ]** 分析需求，将其分解为具体的子任务
2. **[ ]** 检查 `.harness/tasks/pending/` 中是否已有类似任务
3. **[ ]** 创建新任务文件并重建索引
4. **[ ]** 验证自动化系统配置完整性
5. **[ ]** 确认环境和依赖已准备好
6. **[ ]** 告诉用户可以运行: `./.harness/run-automation-stages.sh`
7. **[ ]** 提供监控和问题排查指导

**一切准备就绪后，自动化系统将执行 Dev → Test → Review 三阶段流程，最终生成符合 Laravel 11 规范的高质量代码。**

---

## 📚 参考文档

- **三阶段指南**: `.harness/docs/STAGES_GUIDE.md`
- **开发规范**: `CLAUDE.md`
- **业务文档**: `docs/` 目录
- **任务存储**: `.harness/docs/task_file_storage_quickstart.md`

---

## 🆕 新增功能与改动（2026-02-26）

### 满意度验证系统 (Satisfaction Validation)

#### 功能概述

新增基于 Claude AI 的任务质量自动评估系统，在任务 Review 阶段自动评估任务完成质量。

**核心特性**：
- **AI 独立评估**: Review 阶段完成后自动调用 Claude 进行质量评估
- **满意度计算**: 根据验收标准通过率自动计算满意度
- **智能重试**: 不通过时自动返回 Dev 阶段重试
- **灵活配置**: 支持自定义阈值和重试次数

#### 任务分类与验证策略

| 任务复杂度 | validation.threshold | validation.max_retries | 示例 |
|-----------|---------------------|------------------------|------|
| 🟢 简单任务 | 不启用 validation | - | 备份文件、清除缓存、单一命令 |
| 🟡 中等任务 | 0.6 (60%) | 2 | 注册路由（5-10条）、配置修改、数据迁移 |
| 🔴 复杂任务 | 0.8-0.9 (80-90%) | 3 | 完整测试运行、项目验收、多模块集成 |

#### 评估流程

```
┌─────────────────────────────────────────────────────────────────┐
│                  满意度验证评估流程                                │
├─────────────────────────────────────────────────────────────────┤
│  1. 任务进入 Review 阶段                                     │
│  2. 系统自动调用 Claude 进行独立评估                           │
│  3. Claude 逐一验证 acceptance 标准                               │
│  4. 计算满意度 = 通过项数 / 总项数                              │
│  5. 判断是否通过：                                             │
│     ✅ 满意度 ≥ threshold → 标记任务完成                       │
│     ❌ 满意度 < threshold → 返回 Dev 阶段重试                  │
│  6. 最多重试 max_retries 次                                       │
└─────────────────────────────────────────────────────────────────┘
```

#### 使用方式

**方式 1: 使用 add_task.py 脚本（推荐）**

```bash
# 简单任务 - 无需 validation
python3 .harness/scripts/add_task.py \
  --id SIM_Simple_001 \
  --category feature \
  --desc "实现基础功能" \
  --priority P2 \
  --acceptance "文件存在" "测试通过"

# 中等任务 - 启用 validation (threshold: 0.6)
python3 .harness/scripts/add_task.py \
  --id SIM_Medium_001 \
  --category route \
  --desc "注册用户管理路由（10条）" \
  --priority P0 \
  --acceptance "routes/api.php 包含 GET /users" "routes/api.php 包含 POST /users" \
  --validation-enabled \
  --validation-threshold 0.6 \
  --validation-max-retries 2 \
  --notes "中等复杂度，10条路由需要验证映射关系"

# 复杂任务 - 启用 validation (threshold: 0.8)
python3 .harness/scripts/add_task.py \
  --id SIM_Complex_001 \
  --category test \
  --desc "运行完整测试套件" \
  --priority P0 \
  --acceptance "测试通过率 > 80%" "无 500 错误" "Allure 报告已生成" \
  --validation-enabled \
  --validation-threshold 0.8 \
  --validation-max-retries 3 \
  --notes "复杂任务，需综合评估测试结果、错误分析、报告完整性"
```

**方式 2: 手动创建任务 JSON**

```json
{
  "id": "SIM_Complex_001",
  "category": "test",
  "description": "运行完整测试套件",
  "acceptance": [
    "测试通过率 > 80%",
    "无 500 错误",
    "Allure 报告已生成"
  ],
  "validation": {
    "enabled": true,
    "threshold": 0.8,
    "max_retries": 3
  },
  "stages": {
    "dev": {"completed": false, "completed_at": null, "issues": []},
    "test": {"completed": false, "completed_at": null, "issues": [], "test_results": {}},
    "review": {"completed": false, "completed_at": null, "issues": [], "risk_level": null}
  }
}
```

#### 配置参数说明

`--validation-enabled` (默认: false)
- 启用满意度验证
- 启用后，Review 阶段会自动调用 Claude 独立评估

`--validation-threshold` (默认: 0.8)
- 验证通过阈值（0.0-1.0）
- 满意度必须 ≥ threshold 才能通过验证
- 推荐设置：
  - 简单任务：不启用
  - 中等任务：0.6（允许 40% 的容错）
  - 复杂任务：0.8-0.9（高标准严要求）

`--validation-max-retries` (默认: 3)
- 验证失败后最大重试次数
- 推荐设置：
  - 中等任务：2 次
  - 复杂任务：3 次

---

### Windows 跨平台支持

#### 新增 Python 脚本

| 脚本 | 说明 |
|------|------|
| `dual_timeout.py` | 双重超时机制执行器（跨平台） |
| `detect_stage_completion.py` | 混合模式阶段完成检测器 |
| `auto_detect_completion.py` | 自动检测任务完成状态（备用） |
| `laravel-agent.py` | Laravel 自动化 Agent（基础版） |

#### 核心改进

**1. Dual Timeout（双重超时机制）**
- **活性超时**: 180秒无输出 → 认为卡死（可递增）
- **硬超时**: 根据任务复杂度动态设置（simple: 15min, medium: 20min, complex: 30min）
- **跨平台兼容**:
  - Windows: `subprocess + threading`
  - Unix/Mac: `pty + select`
- **退出码**:
  - `14` - 活性超时（卡死）
  - `124` - 硬超时
  - `0` - 正常完成

**2. 混合模式阶段完成检测**

当 Agent 未主动调用 `mark-stage` 时，系统会自动检测：

```bash
python3 .harness/scripts/detect_stage_completion.py \
    --id TASK_ID \
    --stage test
```

**检测逻辑**:
- **Dev 阶段**: `mark-stage` 调用 + Git 变更 + 产出记录
- **Test 阶段**: `--test-results` / `--issues` 参数 + 测试执行痕迹
- **Review 阶段**: `--issues` 参数 + 审查关键词 + 完成状态文本匹配

**退出码**:
- `0` - 阶段已完成
- `1` - 阶段未完成
- `2` - 无法确定（需要人工审查）

**3. 任务文件存储系统**

- **索引文件**: `task-index.json`（O(1) 查找性能）
- **单文件模式**: 每个任务独立存储为 JSON 文件
- **目录结构**:
  ```
  .harness/tasks/
  ├── pending/          # 待处理任务 *.json
  └── completed/        # 已完成任务（按年/月归档）
      └── YYYY/MM/      # *.json
  ```

### 自动化循环改进

#### 配置项（`.harness/.env`）

| 配置 | 默认 | 说明 |
|------|------|------|
| `BASE_SILENCE_TIMEOUT` | 180 | 基础活性超时（秒） |
| `MAX_SILENCE_TIMEOUT` | 600 | 最大活性超时（秒） |
| `TIMEOUT_BACKOFF_FACTOR` | 1.5 | 超时递增因子 |
| `MAX_TIMEOUT_RETRIES` | 5 | 超时最大重试次数 |
| `PERMISSION_MODE` | bypassPermissions | Claude 权限模式 |

#### 工作流

```
┌─────────────────────────────────────────────────────────────────┐
│                        自动化循环流程                           │
├─────────────────────────────────────────────────────────────────┤
│  1. 获取下一待处理阶段 (next_stage.py)                         │
│  2. 组装 Prompt (CLAUDE.md + 进度 + 任务 + 模板)              │
│  3. 执行 Claude (dual_timeout.py with hard/silence timeout)   │
│  4. 检查阶段状态 (harness-tools.py + detect_stage_completion) │
│  5. 结算阶段状态 (重试/完成/跳过)                              │
└─────────────────────────────────────────────────────────────────┘
```

### CLI 工具增强

#### harness-tools.py

新增/改进功能：
- `--action mark-stage`: 支持 Dev/Test/Review 三阶段标记
- `--action stage-status`: 查看任务各阶段状态
- `--files` 参数: Dev 阶段必须提供，用于记录产出
- `--status failed`: 支持阶段失败回滚（Test → Dev, Review → Dev）

#### artifacts.py

```bash
# 记录任务产出
python3 .harness/scripts/artifacts.py record \
    --id TASK_ID \
    --files file1.php file2.php

# 查看任务产出
python3 .harness/scripts/artifacts.py get --id TASK_ID

# 清理旧产物（保留最近 7 天）
python3 .harness/scripts/artifacts.py clean --days 7
```

### Windows 特定修复

#### 终端编码
```python
# 自动设置 Windows 控制台输出编码为 UTF-8
sys.stdout = io.TextIOWrapper(..., encoding='utf-8', errors='replace')
```

#### 命令路径查找
```python
# 自动解析 .cmd/.bat 文件路径
cmd_exe = shutil.which(cmd[0])
if cmd_exe.lower().endswith(('.cmd', '.bat')):
    use_shell = True
```

### 目录结构更新

```
.harness/
├── task-index.json               # 索引文件（O(1) 查找）
├── tasks/
│   ├── pending/                  # 待处理任务（单文件模式）
│   └── completed/                # 已完成任务（按年/月归档）
├── scripts/
│   ├── dual_timeout.py          # 双重超时执行器（新增）
│   ├── detect_stage_completion.py  # 阶段完成检测（新增）
│   ├── auto_detect_completion.py   # 自动检测（新增）
│   ├── laravel-agent.py        # Laravel Agent（新增）
│   ├── task_file_storage.py    # 单文件存储系统
│   ├── task_utils.py           # 任务编解码器
│   └── ... (其他脚本)
├── cli-io/
│   ├── current.json            # 当前会话元数据
│   └── sessions/               # 会话输出文件（按时间戳）
├── .automation_retries/        # 重试计数文件
├── .automation_skip/           # 跳过任务列表
├── .automation_timeouts/       # 超时计数文件
├── artifacts/                  # 任务产物记录
└── logs/
    └── automation/
        └── YYYY/MM/            # 自动化日志归档
```

### 常用命令速查

```bash
# 查看当前待处理任务
python3 .harness/scripts/harness-tools.py --action current

# 标记阶段完成（Dev 阶段必须提供 --files）
python3 .harness/scripts/harness-tools.py --action mark-stage \
    --id TASK_ID --stage dev --files file1.php file2.php

# 标记测试阶段完成
python3 .harness/scripts/harness-tools.py --action mark-stage \
    --id TASK_ID --stage test \
    --test-results '{"test_name": {"passed": true, "message": "OK"}}'

# 查看阶段状态
python3 .harness/scripts/harness-tools.py --action stage-status --id TASK_ID

# 验证任务完成度
python3 .harness/scripts/harness-tools.py --action verify --id TASK_ID

# 检测阶段是否完成（混合模式）
python3 .harness/scripts/detect_stage_completion.py \
    --id TASK_ID --stage test

# 添加新任务
python3 .harness/scripts/add_task.py \
  --id SIM_New_001 \
  --category feature \
  --desc "实现新功能" \
  --priority P1 \
  --acceptance "标准1" "标准2"

# 添加中等复杂度任务（启用满意度验证）
python3 .harness/scripts/add_task.py \
  --id SIM_Route_001 \
  --category route \
  --desc "注册用户管理模块路由" \
  --priority P0 \
  --acceptance "routes/api.php 包含 GET /users" "routes/api.php 包含 POST /users" \
  --validation-enabled \
  --validation-threshold 0.6 \
  --validation-max-retries 2 \
  --notes "中等复杂度，需要验证路由映射关系"

# 添加复杂任务（启用满意度验证，高阈值）
python3 .harness/scripts/add_task.py \
  --id SIM_Final_001 \
  --category feature \
  --desc "项目最终验收" \
  --priority P0 \
  --acceptance "测试通过率 > 80%" "路由注册 > 100条" "无 500 错误" \
  --validation-enabled \
  --validation-threshold 0.8 \
  --validation-max-retries 3 \
  --notes "复杂任务，需综合评估所有目标"

# 重建索引（任务文件变更后）
python3 .harness/scripts/task_file_storage.py --action rebuild-index

# 查看存储统计
python3 .harness/scripts/task_file_storage.py --action stats
```

### 人机协作边界

遇到以下情况必须停下并输出清晰指引：

| 情况 | 需要人类操作 |
|------|--------------|
| 需要注册账号/申请 API Key | 提供账号凭证 |
| 需要 OAuth 回调配置 | 配置回调 URL |
| 需要支付/验证码 | 人间授权 |
| 需要访问私有资源 | 提供访问凭证 |
| 需要对生产环境操作 | 明确批准 |

### 注意事项

1. **不要手动编辑 task-index.json** - 它由单文件存储系统自动生成
2. **创建任务后必须重建索引** - 运行 `rebuild-index`
3. **Dev 阶段必须提供 --files** - 用于记录产出（可以是空数组 `--files ''`）
4. **测试必须使用 DatabaseTransactions** - 禁止使用 RefreshDatabase
5. **超时会递增** - 连续超时会自动延长等待时间（最多 600 秒）
6. **自动跳过机制** - 达到最大重试次数（默认 3 次）的任务会被跳过

---

**最后更新**: 2026-02-26
**维护者**: SIM-Laravel Team
