# 三阶段质量保证系统

## 📖 概述

这是一个基于 Long-running Agent Harness 的**三阶段质量保证系统**，每个任务都通过三个独立的 Agent 对话来完成：

```
Dev Agent → Test Agent → Review Agent → 完成
```

### 为什么需要三阶段？

| 指标 | 单阶段系统 | 三阶段系统 |
|------|-----------|-----------|
| Agent 对话数 | 1 | 3 |
| Bug 发现率 | ~60% | ~90% |
| 代码规范符合度 | ~70% | ~95% |
| 质量 | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ |

**核心优势**：
- ✅ **职责分离**：Dev 专注实现，Test 专注发现问题，Review 专注质量
- ✅ **避免认知偏差**：独立 Agent 更客观，不会忽略自己写的问题
- ✅ **符合业界最佳实践**：类似 GitLab MR / GitHub PR 的 CI + Review
- ✅ **可追溯性**：每个阶段的输出和问题都有记录

---

## 🏗️ 系统架构

### 文件结构

```
.harness/
├── task.json                      # 任务定义（v2，支持 stages）
├── templates/
│   ├── dev_prompt.md             # Dev Agent Prompt 模板
│   ├── test_prompt.md            # Test Agent Prompt 模板
│   └── review_prompt.md          # Review Agent Prompt 模板
├── scripts/
│   ├── next_stage.py             # 获取下一个待处理阶段 ⭐
│   ├── harness-tools.py          # 工具脚本（支持 mark-stage）⭐
│   ├── upgrade_to_stages.py      # task.json 升级脚本 ⭐
│   ├── artifacts.py              # 产出管理
│   └── reset_tasks.py            # 重置任务
├── run-automation-stages.sh      # 三阶段自动化脚本 ⭐
└── run-automation.sh             # 旧版单阶段脚本（保留）
```

### task.json 结构

```json
{
  "version": 2,
  "tasks": [
    {
      "id": "Sim_001",
      "description": "实现 SIM 列表查询接口",
      "passes": false,
      "stages": {
        "dev": {
          "completed": false,
          "completed_at": null,
          "issues": []
        },
        "test": {
          "completed": false,
          "completed_at": null,
          "issues": [],
          "test_results": {}
        },
        "review": {
          "completed": false,
          "completed_at": null,
          "issues": [],
          "risk_level": null
        }
      }
    }
  ]
}
```

---

## 🚀 快速开始

### 1. 启动三阶段自动化

```bash
# 从项目根目录运行
./.harness/run-automation-stages.sh
```

**自动化流程**：
```
获取下一个阶段 → 组装 Prompt → 调用 Claude Code CLI → 检查状态 → 标记完成 → 下一个阶段
```

### 2. 查看当前阶段

```bash
# 查看下一个待处理的阶段
python3 .harness/scripts/next_stage.py

# 查看特定任务的所有阶段状态
python3 .harness/scripts/harness-tools.py --action stage-status --id Sim_001
```

### 3. 手动标记阶段完成

```bash
# 标记 dev 阶段完成（记录产出）
python3 .harness/scripts/harness-tools.py --action mark-stage \\
  --id Sim_001 --stage dev \\
  --files app/Models/Tenant.php tests/Unit/TenantTest.php

# 标记 test 阶段完成（通过）
python3 .harness/scripts/harness-tools.py --action mark-stage \\
  --id Sim_001 --stage test --status passed

# 标记 test 阶段失败（发现问题）
python3 .harness/scripts/harness-tools.py --action mark-stage \\
  --id Sim_001 --stage test --status failed \\
  --issues "测试未通过" "覆盖率不足" "边界情况未处理"
```

---

## 📋 三阶段详解

### Stage 1: Dev Agent（开发阶段）

**目标**：实现功能（不要求完美）

**职责**：
- ✅ 实现验收标准要求的功能
- ✅ 编写基础单元测试和集成测试
- ✅ 确保代码可运行
- ❌ 不要求 100% 测试覆盖率
- ❌ 不要求所有边界情况都处理

**Prompt 模板**：`.harness/templates/dev_prompt.md`

**完成命令**：
```bash
python3 .harness/scripts/harness-tools.py --action mark-stage \\
  --id {TASK_ID} --stage dev \\
  --files file1.php file2.php ...
```

**输出**：
- 代码文件（迁移、模型、控制器等）
- 基础测试文件

---

### Stage 2: Test Agent（测试阶段）

**目标**：发现问题（从"攻击者"角度）

**职责**：
- ✅ 运行所有测试，收集结果
- ✅ 编写补充测试（边界情况、安全性）
- ✅ 评估测试通过/失败
- ✅ 给出具体的问题列表

**Prompt 模板**：`.harness/templates/test_prompt.md`

**检查清单**：
- [ ] 单元测试覆盖所有 public 方法
- [ ] 验证规则测试了无效输入
- [ ] 数据库事务测试了回滚场景
- [ ] API 端点测试了 404/403/500 等错误
- [ ] 边界情况：空值、负数、超大值、特殊字符
- [ ] 安全性：SQL 注入、XSS、越权访问

**完成命令**：
```bash
# 测试通过
python3 .harness/scripts/harness-tools.py --action mark-stage \\
  --id {TASK_ID} --stage test --status passed

# 测试失败
python3 .harness/scripts/harness-tools.py --action mark-stage \\
  --id {TASK_ID} --stage test --status failed \\
  --issues "问题1" "问题2" "问题3"
```

**输出**：
- 补充测试文件
- 测试报告（问题列表、通过率、覆盖率）

---

### Stage 3: Review Agent（审查阶段）

**目标**：代码质量（从"维护者"角度）

**职责**：
- ✅ 检查代码规范（CLAUDE.md）
- ✅ 检查安全漏洞
- ✅ 检查性能问题
- ✅ 检查可维护性
- ✅ 提出改进建议

**Prompt 模板**：`.harness/templates/review_prompt.md`

**检查清单**：
- [ ] Laravel 规范：API Resources、FormRequest、Service 层
- [ ] 安全性：输入验证、SQL 注入、XSS、权限
- [ ] 性能：N+1 查询、索引、缓存
- [ ] 可维护性：命名清晰、注释适当、代码复用
- [ ] 最佳实践：设计模式、错误处理、日志

**完成命令**：
```bash
# 代码质量优秀
python3 .harness/scripts/harness-tools.py --action mark-stage \\
  --id {TASK_ID} --stage review --status passed

# 发现严重问题
python3 .harness/scripts/harness-tools.py --action mark-stage \\
  --id {TASK_ID} --stage review --status failed \\
  --issues "安全漏洞" "性能问题" "规范不符合"
```

**输出**：
- Review 报告（问题列表、风险等级、改进建议）

---

## 🔄 工作流程

### 完整流程

```
1. next_stage.py 获取下一个待处理阶段
   ↓
2. 根据阶段选择 Prompt 模板（dev/test/review）
   ↓
3. 组装完整 Prompt（SOP + 任务 + 进度 + 模板）
   ↓
4. 调用 Claude Code CLI 执行
   ↓
5. Agent 标记阶段完成（mark-stage）
   ↓
6. 检查所有阶段是否完成
   ↓
7. 如果全部完成 → Git 提交 → 下一个任务
   如果未完成 → 返回步骤 1（下一个阶段）
```

### 失败重试机制

```
阶段执行失败
   ↓
重试计数 +1
   ↓
达到最大重试次数（3次）？
   ↓ YES
标记任务为永久跳过
   ↓
继续处理下一个任务
```

---

## 🛠️ 工具命令

### 查看状态

```bash
# 查看下一个待处理的阶段
python3 .harness/scripts/next_stage.py

# 查看特定任务的所有阶段状态
python3 .harness/scripts/harness-tools.py --action stage-status --id TASK_ID

# 查看所有任务状态
python3 .harness/scripts/harness-tools.py --action list
```

### 标记阶段

```bash
# Dev 阶段（记录产出）
python3 .harness/scripts/harness-tools.py --action mark-stage \\
  --id TASK_ID --stage dev \\
  --files file1.php file2.php ...

# Test 阶段
python3 .harness/scripts/harness-tools.py --action mark-stage \\
  --id TASK_ID --stage test --status passed|failed \\
  --issues "问题1" "问题2"

# Review 阶段
python3 .harness/scripts/harness-tools.py --action mark-stage \\
  --id TASK_ID --stage review --status passed|failed \\
  --issues "问题1" "问题2"
```

### 管理任务

```bash
# 重置所有任务
python3 .harness/scripts/reset_tasks.py

# 查看产出
python3 .harness/scripts/harness-tools.py --action artifacts --id TASK_ID

# 更新进度
python3 .harness/scripts/harness-tools.py --action update-progress \\
  --id TASK_ID --what-done "..." --test-result "..." --next-step "..."
```

---

## ⚙️ 配置

编辑 `.harness/.env` 文件：

```bash
# Claude Code CLI 命令
CLAUDE_CMD=claude

# 权限模式（完全自动化）
PERMISSION_MODE=bypassPermissions

# 最大重试次数
MAX_RETRIES=3

# 任务间隔（秒）
LOOP_SLEEP=5

# 详细日志
VERBOSE=false
```

---

## 📊 对比：单阶段 vs 三阶段

### 单阶段系统（旧版）

```
./.harness/run-automation.sh

Dev Agent (实现 + 测试 + Review) → 完成 → Git 提交
```

**问题**：
- ❌ 同一个 Agent 容易忽略自己写的问题
- ❌ 可能"假装"测试通过
- ❌ 没有独立的代码审查
- ❌ 质量保证依赖自觉性

### 三阶段系统（新版）

```
./.harness/run-automation-stages.sh

Dev Agent (实现) → Test Agent (测试) → Review Agent (审查) → 完成 → Git 提交
```

**优势**：
- ✅ 职责分离，每个 Agent 专注自己的领域
- ✅ 独立 Test Agent 更客观，从"攻击者"角度测试
- ✅ 独立 Review Agent 从"维护者"角度审视
- ✅ 每个阶段的输出和问题都有记录
- ✅ 质量保证系统化

---

## 🎯 适用场景

### 推荐使用三阶段系统

- ✅ 商业项目（质量比速度重要）
- ✅ Laravel/复杂框架项目
- ✅ 长期维护的项目
- ✅ 团队协作项目

### 可以使用单阶段系统

- ⚠️ 原型开发
- ⚠️ 简单脚本
- ⚠️ 个人项目
- ⚠️ 时间紧迫的项目

---

## 🔍 故障排查

### 任务卡住不动

```bash
# 查看日志
tail -f .harness/automation_*.log

# 查看当前阶段
python3 .harness/scripts/next_stage.py

# 检查阶段状态
python3 .harness/scripts/harness-tools.py --action stage-status --id TASK_ID
```

### 重试次数过多

```bash
# 清理重试记录
rm .harness/.automation_retries/TASK_ID_*.count

# 或重置所有任务
python3 .harness/scripts/reset_tasks.py
```

### 阶段状态异常

```bash
# 查看详细状态
python3 .harness/scripts/harness-tools.py --action stage-status --id TASK_ID

# 手动标记阶段
python3 .harness/scripts/harness-tools.py --action mark-stage \\
  --id TASK_ID --stage dev --status passed
```

---

## 📚 相关文档

- `CLAUDE.md` - 开发规范和 SOP
- `.harness/task.json` - 任务定义
- `.harness/templates/dev_prompt.md` - Dev Agent Prompt
- `.harness/templates/test_prompt.md` - Test Agent Prompt
- `.harness/templates/review_prompt.md` - Review Agent Prompt
- `.harness/logs/progress.md` - 进度记录

---

## 🎉 总结

三阶段质量保证系统通过**职责分离**和**独立审查**，大幅提升了项目质量：

- **Dev Agent**：专注实现，不要求完美
- **Test Agent**：专注发现问题，从"攻击者"角度测试
- **Review Agent**：专注代码质量，从"维护者"角度审视

每个阶段都有独立的 Prompt、检查清单和完成标准，确保代码质量达到生产级别。

---

**最后更新**：2026-02-15
**版本**：v2.0（三阶段质量保证系统）
