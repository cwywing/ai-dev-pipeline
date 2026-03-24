# Agent CPU Runtime

> Agent CPU 运行时 - 代码驱动流程自动化框架

## 概述

Agent CPU 是一个基于代码执行流程的 AI Agent 框架。它不再让 LLM "边想边做"（ReAct），而是让 LLM 先编写结构化流程代码，然后由系统执行这段代码。

**核心优势**：
- 确定性控制：代码天然具备对作用域、调用栈和复杂控制流的管理能力
- 自愈能力：执行出错时自动捕获错误并生成修复代码
- 混合调度：llmcall（确定性任务）+ agentcall（模糊性任务）+ metacall（断言验证）

## 目录结构

```
agent-cpu/
├── runtime.js           # 核心运行时
├── scope.js             # 作用域管理器
├── self-healing.js      # 自愈引擎
├── human-review.js      # Human-in-loop 审查
├── knowledge-base.js    # 知识库管理
├── errors.js            # 自定义错误类
├── builtins/
│   ├── index.js         # 内置函数导出
│   ├── llmcall.js       # 确定性任务调用
│   ├── agentcall.js     # 复杂任务调用
│   └── metacall.js      # 断言验证
├── examples/
│   ├── basic-flow.js    # 基础示例
│   └── self-heal-demo.js # 自愈示例
├── cli.js               # 命令行入口
├── index.js             # 统一导出
└── package.json
```

## 快速开始

### 安装依赖

```bash
cd .harness/agent-cpu
npm install
```

### 运行示例

```bash
# 运行基础示例
node examples/basic-flow.js

# 运行自愈示例
node examples/self-heal-demo.js
```

### 使用 CLI

```bash
# 执行流程代码
node cli.js run --code "await llmcall('hello {name}', {name: 'world'})"

# 从文件执行
node cli.js run --script path/to/script.js --task-id MyTask

# 列出待处理审查
node cli.js review --list

# 查看知识库统计
node cli.js kb --stats
```

## 核心概念

### 1. 内置函数

| 函数 | 用途 | 示例 |
|------|------|------|
| `llmcall(prompt, params)` | 确定性文本生成 | `await llmcall("生成{name}的介绍", {name: "猫"})` |
| `agentcall(scope, prompt, opts)` | 复杂任务 | `await agentcall(scope, "实现登录逻辑")` |
| `metacall(condition, msg, hint)` | 断言验证 | `metacall(result.valid, "验证失败")` |

### 2. 作用域管理

```javascript
// 进入子作用域
const childScope = enterScope();

// 在作用域中设置变量
setVar('userId', 123);
const name = getVar('userId');

// 添加产出文件
scope.addArtifact('app/User.php');

// 添加设计决策
scope.addDecision('architecture', '使用 Repository 模式', '解耦数据访问');

// 退出作用域，收集产出
const result = exitScope();
```

### 3. 自愈机制

当 `metacall` 断言失败时，系统会自动：
1. 捕获错误日志
2. 调用 LLM 生成修复代码
3. 重新执行修复后的代码

```javascript
// 最多重试 3 次
const cpu = createAgentCPU({ maxRetries: 3 });
```

### 4. Human-in-loop

在关键节点设置人工审查：

```javascript
// 请求架构审查
await humanReview('architecture', {
  endpoints: ['/api/users', '/api/posts'],
  modules: ['User', 'Post']
});
```

### 5. 知识库

成功执行的流程会自动同步到知识库：

```javascript
// 检索相似流程
const flows = await retrieveKnowledge({
  category: 'API开发',
  tags: ['用户', '认证']
});

// 获取流程模板
const template = await getTemplate('API开发');
```

## 使用示例

### 完整的开发流程

```javascript
import { createAgentCPU } from './runtime.js';

const cpu = createAgentCPU({
  enableSelfHealing: true,
  enableHumanReview: true,
  enableKnowledgeBase: true
});

const flowCode = `
// 1. 架构设计（可能触发人工审查）
const design = await llmcall("设计{module}模块的架构", {
  module: context.module
});

// 2. 架构审查
await humanReview('architecture', { design });

// 3. 生成代码
const code = await agentcall(scope, "实现{module}模块", {
  design,
  constraints: scope.constraints
});

// 4. 验证产出
metacall(code.generatedFiles.length > 0, "未生成任何文件");

// 5. 写入文件
for (const file of code.generatedFiles) {
  if (file.path) {
    await writeFile(file.path, file.code);
  }
}

scope.exit();
`;

const result = await cpu.execute(flowCode, {
  taskId: 'Feature_001',
  category: 'feature',
  module: '用户管理',
  constraints: [
    '使用 Repository 模式',
    '遵循 PSR-12 代码规范'
  ]
});

console.log('产出文件:', result.artifacts);
```

### 批量处理

```javascript
// 使用 llmcallBatch 批量生成
const prompts = [
  { prompt: "生成{animal}的介绍", params: { animal: "猫" } },
  { prompt: "生成{animal}的介绍", params: { animal: "狗" } },
  { prompt: "生成{animal}的介绍", params: { animal: "鸟" } }
];

const results = await llmcallBatch(prompts);

// 使用 llmcallParallel 并行执行（最多 3 个并发）
const parallelResults = await llmcallParallel(prompts, 3);
```

### 断言验证

```javascript
// 基础断言
metacall(userId !== null, "用户ID不能为空");
metacallEq(result.status, 200, "状态码不正确");
metacallIn(role, ['admin', 'user', 'guest'], "无效的角色");

// Schema 验证
metacallSchema(userData, {
  required: ['id', 'name', 'email'],
  properties: {
    id: { type: 'number' },
    name: { type: 'string' },
    email: { type: 'string' }
  }
}, '用户数据');

// 类型验证
metacallType(userId, 'number', 'userId');
metacallType(user, Object, 'user');
```

## 配置

```javascript
const cpu = createAgentCPU({
  maxRetries: 3,               // 自愈最大重试次数
  enableSelfHealing: true,     // 是否启用自愈
  enableHumanReview: true,     // 是否启用人工审查
  enableKnowledgeBase: true,   // 是否启用知识库
  autoSyncOnSuccess: true,     // 成功时自动同步到知识库
  sandbox: true,               // 是否启用沙箱
  contextLimit: 100000,       // 上下文限制
  onLog: (entry) => {},        // 日志回调
  onError: (error, log) => {}, // 错误回调
  onProgress: (progress) => {} // 进度回调
});
```

## 与现有系统集成

Agent CPU 可以作为独立模块集成到现有项目中：

```javascript
import { AgentCPU, globalScopeManager } from './agent-cpu';

// 复用全局作用域管理器
const cpu = createAgentCPU({
  scopeManager: globalScopeManager
});
```

### 与 Python Harness 集成

Agent CPU 可以通过子进程调用 Python 脚本：

```javascript
const pythonResult = await new Promise((resolve, reject) => {
  const proc = spawn('python3', [
    '.harness/scripts/harness-tools.py',
    '--action', 'mark-stage',
    '--id', taskId,
    '--stage', 'dev'
  ]);

  let stdout = '';
  proc.stdout.on('data', d => stdout += d);
  proc.on('close', code => resolve({ code, stdout }));
});
```

## 最佳实践

1. **流程代码要简洁**：每个函数尽量控制在 50 行以内
2. **善用断言**：`metacall` 要尽量精确，便于自愈定位问题
3. **合理设置作用域**：按模块划分作用域，避免上下文污染
4. **利用知识库**：相似的任务检索知识库，复用成功流程
5. **人工审查点要谨慎**：只在关键节点设置，避免阻塞流程

## 限制与注意事项

1. **沙箱限制**：Node.js vm 沙箱不支持所有原生模块
2. **自愈不保证成功**：对于逻辑错误，自愈可能无法修复
3. **上下文长度**：大文件内容可能导致上下文溢出
4. **Human-in-loop 阻塞**：人工审查会阻塞执行直到审查完成

## License

MIT
