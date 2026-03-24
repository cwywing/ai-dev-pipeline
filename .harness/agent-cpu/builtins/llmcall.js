/**
 * llmcall - 确定性任务调用
 *
 * 负责处理确定性的、细粒度的文本生成或数据提取任务。
 * 例如在循环中生成多个不同实体的介绍。
 */

import { LLMCallError } from '../errors.js';

/**
 * LLM 调用配置
 */
export const DEFAULT_LLM_CONFIG = {
  model: 'claude-3-5-sonnet-20241022',
  temperature: 0.3,          // 低温度确保确定性
  maxTokens: 4096,
  timeout: 60000,            // 60秒超时
  retries: 2,               // LLM 调用重试次数
  onTokenUsage: null,       // Token 使用回调
};

/**
 * llmcall 实现
 *
 * @param {string} prompt - 提示词（支持模板变量）
 * @param {object} params - 模板参数
 * @param {object} config - LLM 配置
 * @returns {Promise<string>}
 */
export async function llmcall(prompt, params = {}, config = {}) {
  const llmConfig = { ...DEFAULT_LLM_CONFIG, ...config };

  // 模板替换
  const renderedPrompt = renderTemplate(prompt, params);

  // 调用 LLM
  const response = await callLLM(renderedPrompt, llmConfig);

  // 验证响应
  if (!response || !response.content) {
    throw new LLMCallError('LLM 返回为空', response);
  }

  return response.content;
}

/**
 * 模板渲染
 * 支持 {variable} 格式的变量替换
 *
 * @param {string} template - 模板字符串
 * @param {object} params - 参数
 * @returns {string}
 */
function renderTemplate(template, params) {
  return template.replace(/\{(\w+)\}/g, (match, key) => {
    if (key in params) {
      return String(params[key]);
    }
    return match;  // 保留未匹配的变量
  });
}

/**
 * 调用 LLM（底层实现，需要集成具体 LLM API）
 * 这里使用 Claude Code 的 Claude CLI 作为示例
 *
 * @param {string} prompt - 渲染后的提示词
 * @param {object} config - LLM 配置
 * @returns {Promise<object>}
 */
async function callLLM(prompt, config) {
  const startTime = Date.now();

  try {
    // 使用 Claude Code CLI 调用
    const result = await callClaudeCLI(prompt, config);

    const duration = Date.now() - startTime;

    // 回调 token 使用情况
    if (config.onTokenUsage && result.usage) {
      config.onTokenUsage({
        inputTokens: result.usage.input_tokens,
        outputTokens: result.usage.output_tokens,
        duration
      });
    }

    return {
      content: result.content,
      usage: result.usage,
      duration,
      model: config.model
    };
  } catch (error) {
    throw new LLMCallError(`LLM 调用失败: ${error.message}`, { prompt, config });
  }
}

/**
 * 调用 Claude CLI
 *
 * @param {string} prompt - 提示词
 * @param {object} config - 配置
 * @returns {Promise<object>}
 */
async function callClaudeCLI(prompt, config) {
  const { spawn } = await import('child_process');

  return new Promise((resolve, reject) => {
    const args = [
      'claude',
      '-p',
      prompt,
      '--output-format',
      'json',
      '--max-tokens',
      String(config.maxTokens)
    ];

    if (config.model) {
      args.push('--model', config.model);
    }

    const proc = spawn(args[0], args.slice(1), {
      timeout: config.timeout,
      shell: true
    });

    let stdout = '';
    let stderr = '';

    proc.stdout.on('data', (data) => {
      stdout += data.toString();
    });

    proc.stderr.on('data', (data) => {
      stderr += data.toString();
    });

    proc.on('close', (code) => {
      if (code === 0) {
        try {
          const response = JSON.parse(stdout);
          resolve(response);
        } catch (e) {
          // 如果不是 JSON，返回原始内容
          resolve({ content: stdout.trim() });
        }
      } else {
        reject(new Error(`Claude CLI exited with code ${code}: ${stderr}`));
      }
    });

    proc.on('error', (err) => {
      reject(err);
    });

    // 超时处理
    setTimeout(() => {
      proc.kill();
      reject(new Error('LLM 调用超时'));
    }, config.timeout);
  });
}

/**
 * 批量 llmcall
 *
 * @param {Array<{prompt: string, params: object}>} tasks - 任务列表
 * @param {object} config - LLM 配置
 * @returns {Promise<Array<string>>}
 */
export async function llmcallBatch(tasks, config = {}) {
  const results = [];

  for (const task of tasks) {
    const result = await llmcall(task.prompt, task.params || {}, config);
    results.push(result);
  }

  return results;
}

/**
 * 并行批量 llmcall
 *
 * @param {Array<{prompt: string, params: object}>} tasks - 任务列表
 * @param {number} concurrency - 并发数
 * @param {object} config - LLM 配置
 * @returns {Promise<Array<string>>}
 */
export async function llmcallParallel(tasks, concurrency = 3, config = {}) {
  const results = new Array(tasks.length);

  // 分批处理
  for (let i = 0; i < tasks.length; i += concurrency) {
    const batch = tasks.slice(i, i + concurrency);
    const batchPromises = batch.map((task, j) =>
      llmcall(task.prompt, task.params || {}, config)
        .then(result => ({ index: i + j, result }))
    );

    const batchResults = await Promise.all(batchPromises);
    batchResults.forEach(({ index, result }) => {
      results[index] = result;
    });
  }

  return results;
}

/**
 * llmcall 工厂函数 - 创建带上下文的 llmcall
 *
 * @param {Scope} scope - 作用域
 * @param {object} defaultConfig - 默认配置
 * @returns {Function}
 */
export function createLLMCall(scope, defaultConfig = {}) {
  return async function(prompt, params = {}, config = {}) {
    // 注入作用域变量到参数
    const mergedParams = {
      ...scope.getAllVariables(),
      ...params
    };

    // 注入约束到提示词
    const constraints = scope.constraints.length > 0
      ? `\n\n约束条件:\n${scope.constraints.map(c => `- ${c}`).join('\n')}`
      : '';

    const finalPrompt = prompt + constraints;

    return llmcall(finalPrompt, mergedParams, { ...defaultConfig, ...config });
  };
}
