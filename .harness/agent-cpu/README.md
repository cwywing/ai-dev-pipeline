# Agent CPU Runtime

> 代码驱动的 AI Agent 引擎 — 让 LLM 从"边想边做"进化为"先规划再执行"

## 核心理念

传统 ReAct 模式让 LLM 边思考边行动，每一步都依赖上下文推断，控制流脆弱且难以调试。Agent CPU 采用**代码驱动范式**：由 LLM 先生成结构化流程代码，再由引擎确定性执行，天然具备对作用域、调用栈、异常处理和复杂控制流的管理能力。

```
传统 ReAct:   用户需求 → LLM 思考 → 调用工具 → LLM 再思考 → ...
Agent CPU:    用户需求 → LLM 生成流程代码 → 引擎执行 → 自愈/审查 → 产出
```

## 三大核心引擎

### 1. 自愈引擎 (Self-Healing Engine)

执行出错时自动捕获错误日志，调用 LLM 生成修复代码并重新执行，支持指数退避重试。

```
metacall 断言失败 → 捕获错误日志 → LLM 生成修复代码 → 重新执行 → 成功/重试耗尽
```

### 2. 经验沉淀 (Knowledge Base)

每次成功执行自动将流程代码、产出物和设计决策存入知识库。未来同类任务可检索复用，让系统拥有"长期记忆"。

### 3. 人工审查门控 (Human-in-the-Loop)

在 Dev 阶段自动检测高风险操作（路由变更、表结构修改等），命中时触发拦截并挂起流水线，等待人工确认。

## 目录结构

```
.harness/
├── agent-cpu/                    # Agent CPU 运行时
│   ├── runtime.js                # 核心运行时（执行引擎入口）
│   ├── cli.js                    # 命令行入口
│   ├── scope.js                  # 作用域管理器（变量/产出物/决策）
│   ├── self-healing.js           # 自愈引擎（指数退避重试）
│   ├── human-review.js           # 人工审查管理
│   ├── knowledge-base.js         # 知识库管理（经验沉淀/检索）
│   ├── errors.js                 # 自定义错误类
│   ├── index.js                  # 统一导出
│   ├── builtins/
│   │   ├── index.js              # 内置函数导出
│   │   ├── llmcall.js            # LLM 调用（含批量/并行）
│   │   ├── agentcall.js          # 复杂任务调用（含重试）
│   │   └── metacall.js           # 断言验证（12+ 种断言）
│   ├── examples/
│   │   ├── basic-flow.js         # 基础流程示例
│   │   ├── self-heal-demo.js     # 自愈机制演示
│   │   └── basic-demo.js         # 入门演示
│   ├── test/                     # 测试
│   └── workspace/                # Dev 流程产出目录
│
├── scripts/
│   ├── run-agent-cpu.py          # Python 端调用入口
│   └── ...                       # 流水线辅助脚本
│
├── knowledge/
│   ├── constraints.json          # 约束规则（硬红线 + 软建议）
│   └── contracts.json            # 接口契约
│
├── knowledge-base/               # 知识库持久化存储
├── templates/                    # Prompt 模板（dev/test/review）
├── tasks/                        # 任务管理（pending/done）
└── artifacts/                    # 产出物存档
```

## 快速开始

### 安装依赖

```bash
cd .harness/agent-cpu
npm install
```

### 配置 API Key

Agent CPU 直接调用 Anthropic-compatible API，支持官方 Anthropic 和兼容 Provider（如智谱AI）。

```bash
# 方式一：环境变量（推荐）
export ANTHROPIC_API_KEY=sk-ant-api03-...          # 官方 Anthropic
export ANTHROPIC_BASE_URL=https://api.anthropic.com/v1/messages  # 可选

# 方式二：智谱AI / 兼容 Provider
export ANTHROPIC_AUTH_TOKEN=cba06ae1fdea48a6a9dd4217d565b77d...
export ANTHROPIC_BASE_URL=https://open.bigmodel.cn/api/anthropic
export ANTHROPIC_AUTH_HEADER=Authorization         # 必需！使用 Bearer Token 格式
export ANTHROPIC_DEFAULT_SONNET_MODEL=glm-5       # 模型名称

# 超时配置（毫秒）
export API_TIMEOUT_MS=300000
```

> API Key 可从 [Anthropic Console](https://console.anthropic.com/) 或对应 Provider 获取。

### CLI 使用

```bash
# 执行流程代码（从文件）
node cli.js run --script path/to/script.js --task-id TASK_001 --category dev

# 执行流程代码（内联）
node cli.js run --code "const r = await builtins.llmcall('hello'); builtins.metacall(r, 'empty');"

# 管理人工审查
node cli.js review --list
node cli.js review --approve --id <request-id>

# 知识库管理
node cli.js kb --stats
node cli.js kb --retrieve --category dev
node cli.js kb --cleanup
```

### Python 端调用

```bash
# 执行开发流程
python3 .harness/scripts/run-agent-cpu.py --execute --task-id TASK_001 --flow-type dev

# 执行测试流程
python3 .harness/scripts/run-agent-cpu.py --execute --task-id TASK_001 --flow-type test

# 带任务文件
python3 .harness/scripts/run-agent-cpu.py --execute \
  --task-id TASK_001 \
  --flow-type dev \
  --task-file .harness/tasks/pending/TASK_001.json
```

## 内置函数 (Builtins)

流程代码中通过 `builtins.xxx` 调用，由 runtime.js 在执行时自动注入。

### LLM 调用

| 函数 | 用途 |
|------|------|
| `builtins.llmcall(prompt, config)` | 基础 LLM 调用 |
| `builtins.llmcallBatch(tasks, config)` | 批量串行调用 |
| `builtins.llmcallParallel(tasks, concurrency)` | 并发调用 |

### Agent 调用

| 函数 | 用途 |
|------|------|
| `builtins.agentcall(scope, prompt, opts)` | 复杂任务（需要自主规划） |
| `builtins.agentcallWithRetry(scope, prompt, opts)` | 带重试的复杂任务 |

### 断言验证 (metacall 系列)

| 函数 | 用途 |
|------|------|
| `builtins.metacall(condition, msg, hint)` | 基础布尔断言 |
| `builtins.metacallEq(a, b, msg)` | 相等断言 |
| `builtins.metacallNotNull(v, name)` | 非空断言 |
| `builtins.metacallType(v, type, name)` | 类型断言 |
| `builtins.metacallSchema(data, schema, ctx)` | Schema 验证 |
| `builtins.metacallMatch(v, pattern, name)` | 正则匹配断言 |
| `builtins.metacallIn(v, arr, name)` | 枚举值断言 |
| `builtins.metacallRange(v, min, max, name)` | 范围断言 |
| `builtins.metacallCustom(validator, msg)` | 自定义断言 |

### 文件与命令

| 函数 | 用途 |
|------|------|
| `builtins.writeFile(path, content)` | 写入文件（自动注册 artifact） |
| `builtins.readFile(path)` | 读取文件 |
| `builtins.mkdir(dir, opts)` | 创建目录 |
| `builtins.runCommand(command)` | 执行 Shell 命令 |

### 作用域与知识库

| 函数 | 用途 |
|------|------|
| `builtins.enterScope(config)` | 进入子作用域 |
| `builtins.exitScope()` | 退出子作用域 |
| `builtins.setVar(k, v)` / `builtins.getVar(k)` | 作用域变量读写 |
| `builtins.retrieveKnowledge(query, limit)` | 检索知识库 |
| `builtins.getTemplate(category, ctx)` | 获取流程模板 |
| `builtins.humanReview(type, content)` | 发起人工审查 |

## 护城河机制 (Moat)

约束规则定义在 `.harness/knowledge/constraints.json`，分为两个层级：

### 硬规则 (Hard Rules) — 一票否决

违反即终止流程，不提供修复机会：

- 禁止 SQL 拼接，必须使用参数绑定或 Eloquent ORM
- 禁止硬编码密钥/凭证到代码中
- 禁止在生产环境直接执行数据库迁移
- 禁止使用 `eval()` 或危险函数
- 禁止跳过 CSRF 验证

### 软建议 (Guidelines) — 警告但不阻塞

- 业务逻辑放在 Service 层，Controller 保持精简
- 所有验证使用 FormRequest
- 禁止过度设计

### 高风险操作自动拦截 (Dev 阶段)

代码生成后、写入完成前，自动检测以下模式并触发人工审查：

| 模式 | 风险说明 |
|------|---------|
| `Route::` | 路由/API 接口变更 |
| `Schema::create` / `Schema::table` | 数据库表结构变更 |
| `DROP TABLE` | 数据库表删除 |
| `->raw(` | 原生 SQL 注入 |
| `config('xxx.php')` | 配置文件修改 |

## 运行时配置

```javascript
const cpu = createAgentCPU({
  // 自愈
  maxRetries: 3,               // 最大重试次数
  enableSelfHealing: true,     // 启用自愈引擎

  // 知识库
  enableKnowledgeBase: true,   // 启用知识库
  autoSyncOnSuccess: true,     // 成功时自动沉淀经验

  // 人工审查
  enableHumanReview: true,     // 启用审查门控

  // 执行环境
  sandbox: false,              // 沙箱模式（false 避免模块导入问题）
  contextLimit: 100000,        // 上下文长度限制

  // 回调
  onLog: (entry) => {},        // 日志回调
  onError: (error, log) => {}, // 错误回调
  onProgress: (p) => {}        // 进度回调
});
```

## 执行结果

`cpu.execute()` 返回结构化结果：

```javascript
{
  success: true,              // 是否成功
  scope: { ... },             // 作用域快照
  artifacts: [                // 产出文件列表
    { path: 'app/User.php', type: 'file', metadata: {} }
  ],
  decisions: [                // 设计决策记录
    { category: 'architecture', decision: '...', reason: '...' }
  ],
  issues: [                   // 发现的问题
    { severity: 'warning', file: '...', description: '...' }
  ],
  duration: 1234,             // 执行耗时 (ms)
  executionLog: [ ... ]       // 完整执行日志
}
```

## 完整示例

### Dev 流程（代码生成 + 自动审查）

```bash
TASK_DATA='{"description":"实现用户注册接口","acceptance":["邮箱唯一性验证"]}' \
  python3 .harness/scripts/run-agent-cpu.py \
    --execute --task-id TASK_USER_REG --flow-type dev
```

流程内部执行路径：
1. LLM 根据任务描述生成 PHP 代码
2. `metacall` 断言验证生成结果非空
3. 提取代码 → 写入 workspace
4. 高风险模式检测 → 命中则标记 `requireReview: true`
5. 成功 → 自动沉淀到知识库

### Test 流程（硬规则检测）

```bash
python3 .harness/scripts/run-agent-cpu.py \
  --execute --task-id TASK_USER_REG --flow-type test
```

自动检测：硬编码密钥、SQL 拼接、`eval()` 使用等。

### 编程方式调用

```javascript
import { createAgentCPU } from './runtime.js';

const cpu = createAgentCPU({
  enableSelfHealing: true,
  maxRetries: 2,
  sandbox: false
});

const flowCode = `
const prompt = "根据需求生成代码：${context.task.description}";
const llmOutput = await builtins.llmcall(prompt, { model: 'sonnet' });

builtins.metacall(llmOutput.length > 0, "LLM 返回为空", "检查 prompt");

await builtins.writeFile("output.php", llmOutput);
`;

const result = await cpu.execute(flowCode, {
  taskId: 'FEATURE_001',
  category: 'feature',
  task: { description: '实现用户注册' },
  constraints: ['禁止 SQL 拼接']
});

console.log(result.artifacts);  // ['output.php']
```

## 架构总览

```
┌─────────────────────────────────────────────────────┐
│                  run-agent-cpu.py                    │
│           (Python 端调度入口)                        │
└────────────────────┬────────────────────────────────┘
                     │  子进程调用
                     ▼
┌─────────────────────────────────────────────────────┐
│                      cli.js                         │
│  解析参数 → 加载约束 → 创建 Agent CPU 实例          │
└────────────────────┬────────────────────────────────┘
                     │  cpu.execute(script, context)
                     ▼
┌─────────────────────────────────────────────────────┐
│                   runtime.js                        │
│                                                     │
│  ┌───────────┐  ┌──────────────┐  ┌──────────────┐ │
│  │  Scope     │  │  Builtins    │  │  Knowledge   │ │
│  │  Manager   │  │  (注入)      │  │  Base        │ │
│  └───────────┘  └──────────────┘  └──────────────┘ │
│                                                     │
│  ┌──────────────────────────────────────────────────┐│
│  │           Self-Healing Engine                    ││
│  │  metacall 失败 → 错误日志 → LLM 修复 → 重试    ││
│  └──────────────────────────────────────────────────┘│
│                                                     │
│  ┌──────────────────────────────────────────────────┐│
│  │         Human Review Manager                     ││
│  │  高风险检测 → 拦截 → 等待人工确认 → 继续/拒绝  ││
│  └──────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────┘
                     │  成功
                     ▼
┌─────────────────────────────────────────────────────┐
│              Knowledge Base Sync                     │
│       taskId / flowCode / artifacts / decisions      │
└─────────────────────────────────────────────────────┘
```

## 最佳实践

1. **善用 metacall 断言** — 断言越精确，自愈定位问题越快
2. **合理划分作用域** — 按模块/子任务划分，避免上下文污染
3. **审查点要克制** — 只在架构级变更处触发，频繁拦截会导致"狼来了"效应
4. **利用知识库复用** — 相似任务先检索历史成功经验，避免重复劳动
5. **流程代码保持简洁** — 每个流程控制在 50 行以内，复杂逻辑拆分为子作用域
