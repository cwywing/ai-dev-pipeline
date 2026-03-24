/**
 * agentcall - 复杂任务调用
 *
 * 对于不稳定、需要模糊处理的复杂任务，封装成 agentcall 扔给传统 Agent 去处理。
 * 实现"确定性代码 + 模糊性 Agent"的混合调度。
 */

import { AgentCallError } from '../errors.js';
import { Scope } from '../scope.js';

/**
 * Agent 调用配置
 */
export const DEFAULT_AGENT_CONFIG = {
  model: 'claude-3-5-sonnet-20241022',
  maxRetries: 2,            // Agent 重试次数
  timeout: 120000,           // 120秒超时
  temperature: 0.7,          // 较高温度用于创造性任务
  maxTokens: 8192,
  tools: [],                 // 工具列表
  onProgress: null,           // 进度回调
};

/**
 * agentcall 实现
 *
 * @param {Scope} context - 作用域上下文
 * @param {string} prompt - 任务描述
 * @param {object} opts - 配置选项
 * @returns {Promise<ExecutionResult>}
 */
export async function agentcall(context, prompt, opts = {}) {
  const config = { ...DEFAULT_AGENT_CONFIG, ...opts };

  // 构建系统提示词
  const systemPrompt = buildSystemPrompt(context, config);

  // 构建用户提示词
  const fullPrompt = buildUserPrompt(prompt, context, config);

  // 调用 Agent
  const result = await callAgent(systemPrompt, fullPrompt, config);

  // 处理结果
  return processAgentResult(result, context);
}

/**
 * 构建系统提示词
 *
 * @param {Scope} context - 作用域
 * @param {object} config - 配置
 * @returns {string}
 */
function buildSystemPrompt(context, config) {
  let systemPrompt = config.systemPrompt || `
你是一个专业的 AI 开发助手，擅长实现各种功能模块。
请根据用户的需求实现代码，确保：
1. 遵循代码规范和最佳实践
2. 生成的代码可以直接运行
3. 包含必要的错误处理
`;

  // 注入约束条件
  if (context.constraints.length > 0) {
    systemPrompt += `\n\n约束条件:\n`;
    context.constraints.forEach(c => {
      systemPrompt += `- ${c}\n`;
    });
  }

  // 注入已有变量
  const variables = context.getAllVariables();
  if (Object.keys(variables).length > 0) {
    systemPrompt += `\n\n已有上下文:\n`;
    Object.entries(variables).forEach(([key, value]) => {
      systemPrompt += `- ${key}: ${JSON.stringify(value)}\n`;
    });
  }

  return systemPrompt;
}

/**
 * 构建用户提示词
 *
 * @param {string} prompt - 任务描述
 * @param {Scope} context - 作用域
 * @param {object} config - 配置
 * @returns {string}
 */
function buildUserPrompt(prompt, context, config) {
  let userPrompt = prompt;

  // 注入产出文件列表
  if (context.artifacts.length > 0) {
    userPrompt += `\n\n已生成的文件:\n`;
    context.artifacts.forEach(a => {
      userPrompt += `- ${a.path}\n`;
    });
  }

  // 注入设计决策
  const decisions = context.getAllDecisions();
  if (decisions.length > 0) {
    userPrompt += `\n\n已有设计决策:\n`;
    decisions.forEach(d => {
      userPrompt += `- [${d.category}] ${d.decision} (原因: ${d.reason || '未指定'})\n`;
    });
  }

  return userPrompt;
}

/**
 * 调用 Agent（底层实现）
 *
 * @param {string} systemPrompt - 系统提示词
 * @param {string} userPrompt - 用户提示词
 * @param {object} config - 配置
 * @returns {Promise<object>}
 */
async function callAgent(systemPrompt, userPrompt, config) {
  const { spawn } = await import('child_process');

  return new Promise((resolve, reject) => {
    // 构建 Claude CLI 命令
    const args = [
      'claude',
      '-p',
      userPrompt,
      '--system',
      systemPrompt,
      '--output-format',
      'json',
      '--max-tokens',
      String(config.maxTokens),
      '--model',
      config.model
    ];

    if (config.tools && config.tools.length > 0) {
      // 添加工具配置
      args.push('--tools');
      args.push(JSON.stringify(config.tools));
    }

    const proc = spawn(args[0], args.slice(1), {
      timeout: config.timeout,
      shell: true
    });

    let stdout = '';
    let stderr = '';

    proc.stdout.on('data', (data) => {
      stdout += data.toString();
      if (config.onProgress) {
        config.onProgress(data.toString());
      }
    });

    proc.stderr.on('data', (data) => {
      stderr += data.toString();
    });

    proc.on('close', (code) => {
      if (code === 0) {
        try {
          const response = JSON.parse(stdout);
          resolve({
            content: response.content,
            usage: response.usage,
            stopReason: response.stop_reason
          });
        } catch (e) {
          resolve({
            content: stdout.trim(),
            usage: {},
            stopReason: 'completed'
          });
        }
      } else {
        reject(new Error(`Agent exited with code ${code}: ${stderr}`));
      }
    });

    proc.on('error', (err) => {
      reject(err);
    });

    setTimeout(() => {
      proc.kill();
      reject(new Error('Agent 调用超时'));
    }, config.timeout);
  });
}

/**
 * 处理 Agent 结果
 *
 * @param {object} result - Agent 返回结果
 * @param {Scope} context - 作用域
 * @returns {ExecutionResult}
 */
function processAgentResult(result, context) {
  const executionResult = {
    content: result.content,
    stopReason: result.stopReason,
    usage: result.usage,
    generatedFiles: [],
    decisions: [],
    metadata: {}
  };

  // 尝试解析生成的代码
  try {
    // 查找 ``` 代码块
    const codeBlocks = result.content.match(/```[\s\S]*?```/g) || [];
    codeBlocks.forEach(block => {
      const match = block.match(/```(\w+)?\n([\s\S]*?)```/);
      if (match) {
        const language = match[1] || 'unknown';
        const code = match[2].trim();
        executionResult.generatedFiles.push({
          language,
          code
        });
      }
    });

    // 查找文件路径标记
    const fileMarkers = result.content.match(/\/\/ file: (.+)/g) || [];
    fileMarkers.forEach(marker => {
      const path = marker.replace('// file: ', '').trim();
      if (path && !executionResult.generatedFiles.some(f => f.path === path)) {
        executionResult.generatedFiles.push({ path, code: '' });
      }
    });
  } catch (e) {
    // 解析失败，忽略
  }

  return executionResult;
}

/**
 * 带重试的 agentcall
 *
 * @param {Scope} context - 作用域上下文
 * @param {string} prompt - 任务描述
 * @param {object} opts - 配置选项
 * @returns {Promise<ExecutionResult>}
 */
export async function agentcallWithRetry(context, prompt, opts = {}) {
  const config = { ...DEFAULT_AGENT_CONFIG, ...opts };
  let lastError = null;

  for (let attempt = 0; attempt <= config.maxRetries; attempt++) {
    try {
      return await agentcall(context, prompt, {
        ...opts,
        onProgress: (progress) => {
          if (config.onProgress) {
            config.onProgress({ attempt, progress });
          }
        }
      });
    } catch (error) {
      lastError = error;
      console.log(`[agentcall] Attempt ${attempt + 1} failed: ${error.message}`);

      if (attempt < config.maxRetries) {
        // 重试前等待
        await new Promise(r => setTimeout(r, 1000 * (attempt + 1)));
      }
    }
  }

  throw new AgentCallError(
    `Agent 调用失败（已重试 ${config.maxRetries} 次）: ${lastError?.message || '未知错误'}`,
    { prompt, attempts: config.maxRetries + 1 }
  );
}

