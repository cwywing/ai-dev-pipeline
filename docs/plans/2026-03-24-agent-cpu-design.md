# Agent CPU 融合设计方案

> 版本: 1.0.0
> 日期: 2026-03-24
> 状态: 已批准

## 1. 概述

### 1.1 背景

传统 Agent 架构（如 ReAct）最大的痛点在于：强迫 LLM 用自然语言在上下文中处理它并不擅长的"确定性控制逻辑"。这导致系统控制力弱、容易陷入死循环或产生幻觉，子 Agent 的能力上限极低。

**Agent CPU** 的破局思路：把控制底座交还给代码。

### 1.2 设计目标

在保持现有 AI Dev Pipeline 三阶段结构（Dev → Test → Review）的前提下，局部引入 Agent CPU 架构，实现：

- **确定性控制**：用代码管理控制流，避免自然语言的模糊性
- **混合调度**：llmcall（确定性）+ agentcall（模糊性）+ metacall（断言）
- **自愈机制**：失败后自动修复，减少人工干预
- **Human-in-loop**：在关键节点设置人工审查点
- **经验沉淀**：成功流程自动同步到知识库

## 2. 架构设计

### 2.1 整体架构

```
┌─────────────────────────────────────────────────────────────────┐
│                    AI Dev Pipeline                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   ┌─────────────┐    ┌─────────────┐    ┌─────────────┐        │
│   │    DEV     │───▶│    TEST    │───▶│   REVIEW    │        │
│   │  Agent     │    │   Agent    │    │   Agent     │        │
│   └─────┬──────┘    └─────┬──────┘    └──────┬──────┘        │
│         │                  │                   │                │
│         ▼                  ▼                   ▼                │
│   ┌─────────────────────────────────────────────────────┐    │
│   │              Agent CPU Runtime (Node.js)              │    │
│   │  ┌───────────┐  ┌───────────┐  ┌───────────┐       │    │
│   │  │ llmcall() │  │agentcall()│  │metacall() │       │    │
│   │  └───────────┘  └───────────┘  └───────────┘       │    │
│   │  ┌───────────────────────────────────────────┐     │    │
│   │  │        作用域管理器 (Scope Manager)        │     │    │
│   │  └───────────────────────────────────────────┘     │    │
│   │  ┌───────────────────────────────────────────┐     │    │
│   │  │        自愈引擎 (Self-healing Engine)      │     │    │
│   │  └───────────────────────────────────────────┘     │    │
│   └─────────────────────────────────────────────────────┘    │
│                              │                                  │
│                              ▼                                  │
│   ┌─────────────────────────────────────────────────────┐    │
│   │              Human-in-the-loop                       │    │
│   │   [架构审查点] ──────────── [验收判定点]              │    │
│   └─────────────────────────────────────────────────────┘    │
│                              │                                  │
│                              ▼                                  │
│   ┌─────────────────────────────────────────────────────┐    │
│   │              知识库 (Knowledge Base)                 │    │
│   │     成功流程代码 ─── 经验沉淀 ─── 复用检索           │    │
│   └─────────────────────────────────────────────────────┘    │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 核心组件

| 组件 | 职责 |
|------|------|
| Agent CPU Runtime | 解析和执行流程代码，管理内置函数 |
| 内置函数 (Builtins) | llmcall / agentcall / metacall |
| 作用域管理器 | 隔离上下文，控制变量作用域 |
| 自愈引擎 | 捕获错误，触发修复重试 |
| Human-in-loop | 关键节点的人工审查机制 |
| 知识库 | 成功案例的沉淀与复用 |

## 3. 内置函数定义

### 3.1 llmcall

**用途**：处理确定性的、细粒度的文本生成或数据提取任务。

**签名**：
```javascript
llmcall(prompt: string, params: object): Promise<string>
```

**示例**：
```javascript
// 在循环中生成多个动物的介绍
for (const animal of animals) {
  const description = await llmcall("生成{animal}的简短介绍", {
    animal: animal.name,
    tone: "专业"
  });
  scope.descriptions.push(description);
}
```

### 3.2 agentcall

**用途**：处理不稳定、需要模糊处理的复杂任务。

**签名**：
```javascript
agentcall(context: Scope, prompt: string, opts: object): Promise<ExecutionResult>
```

**参数**：
- `context`: 当前作用域，包含局部变量和依赖
- `prompt`: 任务描述
- `opts.maxRetries`: 最大重试次数
- `opts.timeout`: 超时时间

**示例**：
```javascript
// 实现复杂的业务逻辑
const controller = await agentcall(scope, "实现用户认证逻辑", {
  maxRetries: 2,
  timeout: 60000
});
scope.files.push(...controller.generatedFiles);
```

### 3.3 metacall

**用途**：审视执行流程问题的"伪内建函数"。不仅捕获系统层面的执行报错，还能在代码逻辑层面主动抛出业务错误，触发 LLM 的自修复机制。

**签名**：
```javascript
metacall(condition: boolean, errorMsg: string, recoveryHint?: string): void
```

**示例**：
```javascript
// 验证文件是否生成成功
metacall(
  scope.files.length > 0,
  "未生成任何文件",
  "检查 writeFile 调用是否正确执行"
);

// 验证数据类型
metacall(
  result.schema === "User",
  `Schema 不匹配: 期望 User, 实际 ${result.schema}`
);
```

## 4. 自愈机制

### 4.1 流程图

```
┌──────────────┐
│  执行脚本     │
└──────┬───────┘
       ▼
┌──────────────┐    失败     ┌──────────────┐
│  metacall   │────────────▶│ 捕获错误日志  │
│  断言检查    │             └──────┬───────┘
└──────┬──────┘                  │
       │  通过                    ▼
       ▼                  ┌──────────────┐
┌──────────────┐          │  LLM 生成    │
│   继续执行   │◀─────────│  修复代码    │
└──────────────┘          └──────┬───────┘
                                 │ 重试
                                 ▼
                          ┌──────────────┐
                          │  重新执行    │
                          └──────────────┘
                          (最多 N 次，N 可配置)
```

### 4.2 配置参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| maxRetries | 3 | 最大重试次数 |
| backoffMultiplier | 2 | 退避倍数 |
| initialBackoff | 1000 | 初始退避时间（毫秒） |
| maxBackoff | 30000 | 最大退避时间（毫秒） |

## 5. Human-in-the-loop 审查点

### 5.1 审查点配置

| 审查点 | 触发时机 | 审查内容 | 阻塞类型 |
|--------|----------|----------|----------|
| **架构审查** | Dev 开始前 | 接口契约、数据结构、模块边界 | 阻塞式 |
| **验收判定** | Review 完成后 | 最终质量评估、风险确认 | 阻塞式 |

### 5.2 架构审查触发条件

当任务满足以下任一条件时，触发架构审查：

1. 新增接口数量 >= 3
2. 新增数据库表
3. 涉及跨模块调用
4. 涉及外部服务集成

### 5.3 审查结果处理

```javascript
// 审查通过
await humanReviewPass(taskId, reviewType);

// 审查拒绝，附带修改建议
await humanReviewReject(taskId, reviewType, {
  reason: "接口契约不清晰",
  suggestions: ["添加字段类型定义", "明确错误码"]
});
```

## 6. 作用域管理

### 6.1 设计原理

利用代码的"变量作用域"特性，映射 LLM 的渐进式披露与有限上下文管理机制。

### 6.2 Scope 结构

```javascript
class Scope {
  constructor(parent = null) {
    this.parent = parent;
    this.variables = {};
    this.artifacts = [];      // 产出文件列表
    this.decisions = [];      // 设计决策
    this.constraints = [];    // 约束条件
  }

  // 进入子作用域
  enterScope(childScope) {
    // 继承父作用域的约束
    childScope.constraints = [...this.constraints];
  }

  // 退出作用域，收集产出
  exitScope() {
    return {
      files: this.artifacts,
      decisions: this.decisions
    };
  }
}
```

## 7. 知识库集成

### 7.1 自动同步机制

任务成功后，自动将流程代码同步到知识库：

```javascript
// 任务完成时调用
await knowledgeBase.sync({
  taskId: task.id,
  category: task.category,
  flowCode: generatedFlowScript,
  artifacts: scope.artifacts,
  decisions: scope.decisions,
  successRate: calculateSuccessRate(task)
});
```

### 7.2 检索与复用

```javascript
// 根据任务类型检索相似流程
const similarFlows = await knowledgeBase.retrieve({
  category: "API开发",
  keywords: ["用户", "认证"],
  limit: 3
});
```

## 8. 推行计划

### 阶段一：基础设施（1-2周）

- [x] 设计文档
- [ ] 实现 Agent CPU Runtime（Node.js）
- [ ] 实现三个内置函数
- [ ] 实现自愈引擎
- [ ] 实现基础知识库同步

### 阶段二：Dev 阶段试点（1周）

- [ ] 改造 Dev Agent 生成流程代码
- [ ] 实现 Human-in-loop 架构审查
- [ ] 小模块试点验证

### 阶段三：全链路扩展（1-2周）

- [ ] 扩展到 Test / Review 阶段
- [ ] 实现 IDE 级可视化监控
- [ ] 全面推广

## 9. 技术选型

| 组件 | 技术选型 | 理由 |
|------|----------|------|
| 执行环境 | Node.js | 生态系统丰富，与现有 Python 系统解耦 |
| 流程语言 | JavaScript | LLM 生成成本低，语法简洁 |
| 进程调用 | child_process | 与 Python harness-tools.py 无缝集成 |

## 10. 风险与缓解

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| LLM 生成无效流程代码 | 中 | 高 | 自愈机制 + Human-in-loop |
| 自愈循环无法收敛 | 低 | 高 | 最大重试次数限制 |
| 上下文泄漏 | 中 | 中 | 作用域严格隔离 |

## 11. 附录

### 11.1 文件结构

```
.harness/
├── agent-cpu/
│   ├── runtime.js           # 核心运行时
│   ├── builtins/
│   │   ├── llmcall.js       # 确定性任务
│   │   ├── agentcall.js     # 复杂任务
│   │   └── metacall.js      # 断言验证
│   ├── scope.js             # 作用域管理
│   ├── self-healing.js      # 自愈引擎
│   ├── human-review.js      # 人工审查
│   └── knowledge-base.js    # 知识库集成
├── package.json             # Node.js 依赖
└── templates/
    └── flow-template.md     # 流程代码模板
```

### 11.2 参考资料

- Agent CPU 原始设计文档（群聊记录）
- AI Dev Pipeline 三阶段系统设计
