# Harness 快速初始化指南

**适用于：** 将 Harness 系统迁移到新项目时的初始化操作

---

## 一键重置（推荐）

### Windows系统

```bash
cd .harness
scripts\reset_harness.bat
```

### Linux/Mac系统

```bash
cd .harness
chmod +x scripts/reset_harness.sh
./scripts/reset_harness.sh
```

---

## 手动初始化步骤

如果需要更精细的控制，可按以下步骤手动执行。

### 步骤1：清空任务数据

```bash
# Windows
del /q .harness\tasks\pending\*.json
rd /s /q .harness\tasks\completed

# Linux/Mac
rm -rf .harness/tasks/pending/*.json
rm -rf .harness/tasks/completed/*
```

### 步骤2：清空日志

```bash
# Windows
rd /s /q .harness\logs\automation
del /q .harness\logs\progress.md

# Linux/Mac
rm -rf .harness/logs/automation/*
rm -f .harness/logs/progress.md
```

### 步骤3：清空CLI会话

```bash
# Windows
del /q .harness\cli-io\current.json
rd /s /q .harness\cli-io\sessions

# Linux/Mac
rm -f .harness/cli-io/current.json
rm -rf .harness/cli-io/sessions/*
```

### 步骤4：清空产出记录

```bash
# Windows
rd /s /q .harness\artifacts
rd /s /q .harness\reports

# Linux/Mac
rm -rf .harness/artifacts/*
rm -rf .harness/reports/*
```

### 步骤5：重置任务索引

**删除旧索引：**

```bash
# Windows
del /q .harness\task-index.json

# Linux/Mac
rm .harness/task-index.json
```

**创建新索引：**

创建 `.harness/task-index.json` 文件，内容如下：

```json
{
  "version": 1,
  "storage_mode": "single_file",
  "project": "你的项目名称",
  "created_at": "2026-03-17T00:00:00.000000",
  "updated_at": "2026-03-17T00:00:00.000000",
  "total_tasks": 0,
  "pending": 0,
  "completed": 0,
  "index": {},
  "modules": {},
  "priorities": {}
}
```

或使用Python命令：

```bash
python3 -c "
import json
from datetime import datetime
data = {
    'version': 1,
    'storage_mode': 'single_file',
    'project': '你的项目名称',
    'created_at': datetime.now().isoformat(),
    'updated_at': datetime.now().isoformat(),
    'total_tasks': 0,
    'pending': 0,
    'completed': 0,
    'index': {},
    'modules': {},
    'priorities': {}
}
with open('.harness/task-index.json', 'w', encoding='utf-8') as f:
    json.dump(data, f, indent=2, ensure_ascii=False)
"
```

### 步骤7：初始化知识库

**创建知识库目录：**

```bash
# 创建目录
mkdir -p .harness/knowledge
```

**创建接口契约文件 `.harness/knowledge/contracts.json`：**

```json
{
  "version": 1,
  "services": {}
}
```

**创建约束条件文件 `.harness/knowledge/constraints.json`：**

```json
{
  "version": 1,
  "global": [],
  "by_task": {}
}
```

或使用命令：

```bash
# 创建 contracts.json
echo '{"version": 1, "services": {}}' > .harness/knowledge/contracts.json

# 创建 constraints.json
echo '{"version": 1, "global": [], "by_task": {}}' > .harness/knowledge/constraints.json
```

### 步骤8：创建必要目录

```bash
# 创建目录结构
mkdir -p .harness/tasks/pending
mkdir -p .harness/tasks/completed/$(date +%Y/%m)
mkdir -p .harness/logs/automation/$(date +%Y/%m)
mkdir -p .harness/cli-io/sessions
mkdir -p .harness/artifacts
mkdir -p .harness/reports
mkdir -p .harness/knowledge
```

---

## 验证初始化

执行以下命令验证初始化是否成功：

```bash
python3 .harness/scripts/harness-tools.py --action list
```

**预期输出：**

```
[INFO] 项目: 你的项目名称
[INFO] 总任务数: 0
[INFO] 待处理: 0
[INFO] 已完成: 0
```

---

## 初始化检查清单

- [ ] 已清空 `tasks/pending/*.json` 所有任务文件
- [ ] 已清空 `tasks/completed/*` 已完成任务归档
- [ ] 已删除并重新创建 `task-index.json`
- [ ] 已清空 `logs/automation/*` 运行日志
- [ ] 已删除 `logs/progress.md` 进度记录
- [ ] 已删除 `cli-io/current.json` 当前会话
- [ ] 已清空 `cli-io/sessions/*` 会话历史
- [ ] 已清空 `artifacts/*` 产出记录
- [ ] 已清空 `reports/*` 执行报告
- [ ] 已创建 `knowledge/contracts.json` 接口契约文件
- [ ] 已创建 `knowledge/constraints.json` 约束条件文件
- [ ] 已修改 `task-index.json` 中的项目名称
- [ ] 已验证任务列表为空

---

## 常见问题

### Q1: Python命令执行失败

**问题：** 执行Python命令时提示 `python3: command not found`

**解决：**
- Windows: 使用 `python` 替代 `python3`
- Linux/Mac: 确保已安装Python 3，或使用 `python` 命令

### Q2: 目录不存在

**问题：** 某些目录不存在导致删除失败

**解决：** 忽略错误，继续执行。重置脚本会自动创建必要的目录。

### Q3: 权限不足

**问题：** Linux/Mac系统提示权限不足

**解决：** 使用 `chmod +x` 赋予执行权限

```bash
chmod +x .harness/scripts/reset_harness.sh
```

### Q4: 如何保留某些任务

**问题：** 想保留部分任务，只删除其他任务

**解决：**
1. 手动编辑 `tasks/pending/` 目录
2. 只保留需要的任务文件
3. 运行重建索引命令：

```bash
python3 .harness/scripts/task_file_storage.py --action rebuild-index
```

---

## 下一步操作

初始化完成后，可以开始创建任务：

```bash
# 创建第一个任务
python3 .harness/scripts/add_task.py \
  --id TASK_001 \
  --category feature \
  --desc "任务描述" \
  --priority P1 \
  --acceptance "验收标准1" "验收标准2"

# 查看任务列表
python3 .harness/scripts/harness-tools.py --action list

# 启动自动化
./.harness/run-automation.sh
```

---

**最后更新：** 2026-03-18