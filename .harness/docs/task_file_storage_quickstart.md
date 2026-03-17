# Task.json 单文件存储系统 - 快速开始指南

## 🎯 概述

**当前状态**: ✅ 已启用单文件存储模式

**核心优势**:
- ⚡ **极快加载**: 3.56 ms（vs 原来 50 ms）
- 📦 **文件小巧**: 每个任务 ~0.6 KB
- 🎯 **Claude CLI 友好**: <1 KB 文件，编辑极快
- 🔒 **原子操作**: 修改单个任务不影响其他

---

## 📂 目录结构

```
.harness/
├── task-index.json              # 索引文件（78 KB）
├── task.json                    # 备份（保留）
└── tasks/
    ├── pending/                 # 待处理任务（35 个文件）
    │   ├── TASK_ID_001.json     # ~0.6 KB
    │   └── ...
    └── completed/               # 已完成任务（按年/月归档）
        └── 2026/
            └── 02/              # 2026年2月
                ├── TASK_ID_002.json
                └── ... (209 个文件)
```

---

## 🚀 日常使用

### 查看当前任务

```bash
# 自动使用单文件模式
python3 .harness/scripts/harness-tools.py --action current

# 输出示例：
# 任务 ID: SIM_Multi_Tenant_Isolation_Test_001
# 描述: 多租户数据隔离安全测试
```

### 自动化循环

```bash
# 完全兼容，无需修改
./.harness/run-automation-stages.sh
```

性能提升：
- 加载下一个任务：~2 ms（索引 1.66 ms + 任务 0.19 ms）
- 保存单个任务：<1 ms

### 查看统计

```bash
python3 .harness/scripts/task_file_storage.py --action stats

# 输出示例：
# 📊 单文件存储统计:
#    总任务: 244
#    待处理: 35
#    已完成: 209
#    文件总数: 244
#    平均文件大小: 0.769 KB
```

---

## 🔧 维护操作

### 重建索引

**何时需要**：
- 索引文件损坏
- 任务文件被手动移动
- 需要刷新统计信息

```bash
python3 .harness/scripts/task_file_storage.py --action rebuild-index
```

### 性能测试

```bash
python3 .harness/scripts/task_file_storage.py --action test

# 输出示例：
# ✅ 加载索引: 1.66 ms
# ✅ 加载单个任务: 0.19 ms
# ✅ 加载待处理任务 (35 个): 3.56 ms
```

---

## 💻 代码使用

### 加载单个任务

```python
from task_file_storage import TaskFileStorage

storage = TaskFileStorage()

# 加载
task = storage.load_task('TASK_ID_001')
print(task['description'])

# 修改
task['passes'] = True

# 保存（原子操作，<1 ms）
storage.save_task(task)
```

### 加载所有待处理任务

```python
# 只加载 pending，不加载 completed
pending_tasks = storage.load_all_tasks('pending')

print(f"待处理: {len(pending_tasks)} 个")
```

---

## ⚠️ 故障排除

### 问题1: 索引损坏

**症状**：
```
⚠️  加载索引失败: ...，重建索引...
```

**解决**：
```bash
python3 .harness/scripts/task_file_storage.py --action rebuild-index
```

---

### 问题2: 任务文件丢失

**症状**：
```
⚠️  任务 TASK_ID_001 不存在
```

**解决**：
1. 检查文件是否存在：
   ```bash
   ls .harness/tasks/pending/TASK_ID_001.json
   ls .harness/tasks/completed/*/*/TASK_ID_001.json
   ```

2. 重建索引：
   ```bash
   python3 .harness/scripts/task_file_storage.py --action rebuild-index
   ```

---

### 问题3: 性能下降

**症状**：加载时间明显变慢

**可能原因**：
- 待处理任务过多（>100 个）
- 文件系统碎片化

**解决**：
1. 检查统计：
   ```bash
   python3 .harness/scripts/task_file_storage.py --action stats
   ```

2. 如果 pending 任务过多，考虑定期完成任务

---

## 📊 性能基准

### 当前性能

| 操作 | 耗时 |
|------|------|
| 加载索引 | 1.66 ms |
| 加载单个任务 | 0.19 ms |
| 加载所有待处理（35个） | 3.56 ms |
| 保存单个任务 | <1 ms |

### 对比原始方案

| 指标 | 原始 | 当前 | 提升 |
|------|------|------|------|
| 加载所有任务 | 50 ms | 3.56 ms | **93%** ⚡ |
| 单文件大小 | 268 KB | 0.6 KB | **99.8%** ⚡ |
| Claude CLI 编辑 | 可能失败 | 完美 | **∞** ✅ |

---

## 🎯 最佳实践

### 1. 定期重建索引

```bash
# 每周执行一次
python3 .harness/scripts/task_file_storage.py --action rebuild-index
```

### 2. 备份策略

```bash
# 备份索引（最重要）
cp .harness/task-index.json .harness/task-index.json.backup

# 备份所有任务
tar czf tasks-backup-$(date +%Y%m%d).tar.gz .harness/tasks/
```

### 3. 监控文件数量

```bash
# 检查文件数量
find .harness/tasks -name "*.json" | wc -l

# 建议：
# - < 1000: 当前方案最优
# - 1000-5000: 当前方案可用
# - > 5000: 考虑迁移到 SQLite
```

---

## 🔄 回退方案

### 回退到传统模式

如果需要回退到原始的单一 task.json：

```bash
# 1. 删除索引
rm .harness/task-index.json

# 2. 系统会自动使用 task.json
python3 .harness/scripts/harness-tools.py --action current
```

### 重新启用单文件模式

```bash
# 重建索引即可
python3 .harness/scripts/task_file_storage.py --action rebuild-index
```

---

## 📚 相关文档

- [第一阶段报告](.harness/docs/task_json_optimization_report.md) - 字段精简
- [第二阶段报告](.harness/docs/task_json_optimization_report_phase2.md) - 任务拆分
- [第三阶段报告](.harness/docs/task_json_optimization_report_phase3.md) - 单文件模式（当前）
- [完整总结](.harness/docs/task_json_optimization_summary.md) - 总体概览

---

## ✅ 检查清单

部署前检查：

- [x] 单文件模式已启用
- [x] 索引文件存在且有效
- [x] 所有任务已迁移（244 个）
- [x] 性能测试通过
- [x] 现有脚本兼容

立即可用！🚀
