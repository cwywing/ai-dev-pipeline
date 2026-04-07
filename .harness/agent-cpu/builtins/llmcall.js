/**
 * llmcall - 确定性任务调用
 *
 * 直接请求 Anthropic Messages API，支持 tool_use、messages 历史和 system prompt。
 */

import { LLMCallError } from '../errors.js';

export const DEFAULT_LLM_CONFIG = {
  model: 'claude-sonnet-4-20250514',
  max_tokens: 8192,
  temperature: 0.3,
  timeout: 300000,    // 5 分钟
  system: null,
  tools: [],
};

const API_BASE = 'https://api.anthropic.com/v1/messages';

/**
 * 主调用函数
 *
 * @param {string} prompt - 用户消息
 * @param {object} params - 模板参数（用于 {key} 占位替换）
 * @param {object} config - 配置
 * @param {string} [config.system] - 系统提示词
 * @param {array}  [config.messages] - 对话历史 [{role, content}]
 * @param {array}  [config.tools] - 工具定义 [{name, description, input_schema}]
 * @param {string} [config.model] - 模型名称
 * @param {number} [config.temperature]
 * @param {number} [config.max_tokens]
 * @param {number} [config.timeout]
 * @returns {Promise<object>} 完整 API 响应 { content, usage, stop_reason, ... }
 */
export async function llmcall(prompt, params = {}, config = {}) {
  const llmConfig = { ...DEFAULT_LLM_CONFIG, ...config };
  const renderedPrompt = renderTemplate(prompt, params);

  // 构建 messages 数组
  const messages = [...(llmConfig.messages || [])];
  messages.push({ role: 'user', content: renderedPrompt });

  const body = {
    model: llmConfig.model,
    max_tokens: llmConfig.max_tokens,
    temperature: llmConfig.temperature,
    system: llmConfig.system || undefined,
    messages,
  };

  // 有 tools 才加入，避免 API 报错
  if (llmConfig.tools && llmConfig.tools.length > 0) {
    body.tools = llmConfig.tools;
  }

  const response = await callAnthropicAPI(body, llmConfig.timeout);

  // 提取文本内容（向后兼容）
  const content = extractTextContent(response);

  if (content === null || content === undefined) {
    throw new LLMCallError('LLM 返回内容为空', response);
  }

  return content;
}

/**
 * 调用 Anthropic Messages API
 */
async function callAnthropicAPI(body, timeoutMs) {
  const apiKey = getApiKey();

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const res = await fetch(API_BASE, {
      method: 'POST',
      signal: controller.signal,
      headers: {
        'x-api-key': apiKey,
        'anthropic-version': '2023-06-01',
        'content-type': 'application/json',
      },
      body: JSON.stringify(body),
    });

    clearTimeout(timer);

    if (!res.ok) {
      let errBody = '';
      try { errBody = await res.text(); } catch (_) {}
      throw new LLMCallError(
        `Anthropic API 错误 ${res.status}: ${errBody || res.statusText}`,
        { status: res.status, body: errBody }
      );
    }

    const data = await res.json();
    return data;

  } catch (err) {
    clearTimeout(timer);
    if (err.name === 'AbortError') {
      throw new LLMCallError(`LLM 调用超时（${timeoutMs}ms）`, {});
    }
    throw new LLMCallError(`LLM 调用失败: ${err.message}`, { cause: err });
  }
}

/**
 * 从 API 响应中提取文本内容
 * 支持多 block 响应（text / tool_use 混合）
 */
function extractTextContent(response) {
  if (!response || !response.content) return null;

  // 纯文本 block，直接返回
  const textBlocks = response.content.filter(b => b.type === 'text');
  if (textBlocks.length > 0) {
    return textBlocks.map(b => b.text).join('\n');
  }

  // 如果只有 tool_use block，返回空（caller 应检查 tool_use）
  const toolBlocks = response.content.filter(b => b.type === 'tool_use');
  if (toolBlocks.length > 0) {
    return null; // caller 通过 response.content 自己处理 tool_use
  }

  return null;
}

/**
 * 模板渲染：替换 {key} 占位符
 */
function renderTemplate(template, params) {
  return template.replace(/\{(\w+)\}/g, (match, key) => {
    if (key in params) return String(params[key]);
    return match;
  });
}

/**
 * 获取 API Key
 * 优先级: process.env.ANTHROPIC_API_KEY
 */
function getApiKey() {
  const apiKey = process.env.ANTHROPIC_API_KEY;
  if (apiKey) return apiKey;

  throw new LLMCallError(
    '未找到 ANTHROPIC_API_KEY。请设置环境变量 process.env.ANTHROPIC_API_KEY',
    {}
  );
}

// ============================================================
// 批量与并行
// ============================================================

/**
 * 批量串行调用
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
 * 并发调用（分批）
 */
export async function llmcallParallel(tasks, concurrency = 3, config = {}) {
  const results = new Array(tasks.length);
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
 * 创建带约束注入的 llmcall 工厂函数
 */
export function createLLMCall(defaultConfig = {}) {
  return async function(prompt, params = {}, config = {}) {
    const mergedConfig = { ...defaultConfig, ...config };
    return llmcall(prompt, params, mergedConfig);
  };
}
