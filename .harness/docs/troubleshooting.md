# 故障排查指南

自动化系统常见问题诊断与解决方案。

---

## 问题 1：Agent 长时间沉默/超时无限递增

### 现象
- Agent 运行超过 10 分钟无输出
- 活性超时从 180 秒递增到 1500+ 秒
- 形成 infinite loop

### 根本原因
1. **任务过于复杂**：验收标准超过 5 个，范围过大
2. **Prompt 过长**：CLAUDE.md + 进度 + 任务 + 模板，处理时间过长
3. **超时配置无上限**：指数递增无最大限制

### 解决方案

#### 方案 A：添加最大超时上限（立即生效）

编辑 `.harness/.env`：
```bash
MAX_SILENCE_TIMEOUT=600  # 最大活性超时（秒）
```

超时递增路径（配置 `TIMEOUT_BACKOFF_FACTOR=1.5`）：
| 次数 | 超时时间 | 分钟数 |
|------|----------|--------|
| 1 | 270 秒 | 4.5 分钟 |
| 2 | 405 秒 | 6.75 分钟 |
| 3 | 607 秒 | 10 分钟 |
| 4+ | **600 秒（上限）** | 10 分钟 |

#### 方案 B：拆分大任务（根本解决）

**识别复杂任务**：
- 验收标准 > 5 个
- 描述包含「所有」「全部」等词
- 需要多个独立模块

**拆分示例**：
```bash
# 原任务: SIM_Service_Unit_Tests_001（6 个验收标准）
# 拆分为 4 个小任务：

python3 .harness/scripts/add_task.py \
  --id SIM_OperatorAdapter_Test_001 \
  --category test \
  --desc "为 OperatorAdapterManager 添加单元测试" \
  --priority P1 \
  --acceptance "测试覆盖率 >= 80%" "所有测试通过"
```

---

## 问题 2：Agent 未执行 mark-stage 命令

### 现象
- 任务实际已完成，但系统认为失败
- 触发无限重试
- 自动化流程阻塞

### 根本原因
- Prompt 中标记命令不够显眼
- Agent 忘记执行最后的标记步骤

### 解决方案

已在模板中添加 **CRITICAL 区块**：

```markdown
## 🚨🚨🚨 CRITICAL: 完成任务后必须执行此命令 🚨🚨🚨

python3 .harness/scripts/harness-tools.py --action mark-stage --id {TASK_ID} --stage dev --files <文件列表>
```

**验证命令执行成功**：
- 必须看到输出：`✓ Dev 阶段已标记为完成`
- 如果没有看到此输出，请重新执行

### 手动补救

如果 Agent 确实忘记执行，手动标记：

```bash
# Dev 阶段
python3 .harness/scripts/harness-tools.py --action mark-stage \
  --id TASK_ID --stage dev --files file1.php file2.php

# Test 阶段
python3 .harness/scripts/harness-tools.py --action mark-stage \
  --id TASK_ID --stage test --test-results '{"passed": true}'

# Review 阶段
python3 .harness/scripts/harness-tools.py --action mark-stage \
  --id TASK_ID --stage review
```

---

## 问题 3：阶段完成检测失败

### 现象
- Agent 声称完成了任务
- 系统未检测到完成状态

### 诊断命令

```bash
# 检查阶段状态
python3 .harness/scripts/harness-tools.py --action stage-status --id TASK_ID

# 检查任务索引
python3 .harness/scripts/task_file_storage.py --action stats

# 查看实时日志
tail -f .harness/logs/$(date +%Y/%m)/automation_*.log
```

### 混合模式检测

当 Agent 未主动调用 mark-stage 时，系统会自动检测：

```bash
python3 .harness/scripts/detect_stage_completion.py --id TASK_ID --stage test
```

**检测逻辑**：
- **Dev 阶段**：Git 变更 + 产出记录
- **Test 阶段**：测试执行痕迹
- **Review 阶段**：审查关键词 + 完成状态文本匹配

---

## 问题 4：任务卡在某个阶段

### 现象
- 任务状态始终显示 `pending`
- 没有进展

### 诊断步骤

```bash
# 1. 检查当前任务
python3 .harness/scripts/harness-tools.py --action current

# 2. 检查下一阶段
python3 .harness/scripts/next_stage.py

# 3. 检查重试计数
ls -la .harness/.automation_retries/
ls -la .harness/.automation_timeouts/

# 4. 检查跳过列表
cat .harness/.automation_skip/*
```

### 手动干预

```bash
# 重置任务状态
python3 .harness/scripts/harness-tools.py --action reset --id TASK_ID

# 标记任务完成
python3 .harness/scripts/harness-tools.py --action mark-done --id TASK_ID

# 跳过任务
echo "TASK_ID" >> .harness/.automation_skip/TASK_ID
```

---

## 常用诊断命令速查

```bash
# 查看当前任务
python3 .harness/scripts/harness-tools.py --action current

# 查看所有任务
python3 .harness/scripts/harness-tools.py --action list

# 查看阶段状态
python3 .harness/scripts/harness-tools.py --action stage-status --id TASK_ID

# 检查下一阶段
python3 .harness/scripts/next_stage.py

# 重建任务索引
python3 .harness/scripts/task_file_storage.py --action rebuild-index

# 查看存储统计
python3 .harness/scripts/task_file_storage.py --action stats
```

---

## 配置参考

编辑 `.harness/.env`：

| 配置 | 默认值 | 说明 |
|------|--------|------|
| `BASE_SILENCE_TIMEOUT` | 180 | 基础活性超时（秒） |
| `MAX_SILENCE_TIMEOUT` | 600 | 最大活性超时（秒） |
| `TIMEOUT_BACKOFF_FACTOR` | 1.5 | 超时递增因子 |
| `MAX_TIMEOUT_RETRIES` | 5 | 超时最大重试次数 |
| `MAX_RETRIES` | 3 | 阶段失败最大重试次数 |

---

**最后更新**: 2026-03
**维护者**: 配料表安全检测系统 Team