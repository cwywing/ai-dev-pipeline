/**
 * llmcall - 确定性任务调用
 *
 * 直接请求 Anthropic-compatible Messages API，支持 tool_use、messages 历史和 system prompt。
 * 支持官方 Anthropic API 及兼容 Provider（如 bigmodel.cn / 智谱AI）。
 */

import { LLMCallError } from '../errors.js';

export const DEFAULT_LLM_CONFIG = {
  // 模型可通过环境变量或参数覆盖
  // 官方 Anthropic: ANTHROPIC_DEFAULT_SONNET_MODEL
  // 智谱AI: ANTHROPIC_DEFAULT_SONNET_MODEL
  model: process.env.ANTHROPIC_DEFAULT_SONNET_MODEL || process.env.ANTHROPIC_MODEL || 'claude-sonnet-4-20250514',
  max_tokens: 8192,
  temperature: 0.3,
  timeout: parseInt(process.env.API_TIMEOUT_MS || '300000', 10),
  system: null,
  tools: [],
};

// API 端点配置（优先环境变量）
const API_BASE = process.env.ANTHROPIC_BASE_URL || 'https://api.anthropic.com/v1/messages';

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

  // 只有当 prompt 非空时才添加 user 消息
  if (renderedPrompt.trim()) {
    messages.push({ role: 'user', content: renderedPrompt });
  }

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

  // 如果要求返回原始响应（用于 tool_use 提取）
  if (llmConfig.returnRawResponse) {
    return response;
  }

  // 提取文本内容（向后兼容）
  const content = extractTextContent(response);

  if (content === null || content === undefined) {
    throw new LLMCallError('LLM 返回内容为空', response);
  }

  return content;
}

/**
 * 调用 Anthropic-compatible API
 */
async function callAnthropicAPI(body, timeoutMs) {
  const apiKey = getApiKey();

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  try {
    // 构建请求头（支持多种 Provider 格式）
    const headers = {
      'anthropic-version': '2023-06-01',
      'content-type': 'application/json',
    };

    // Authorization: Bearer 格式（如智谱AI）
    if (process.env.ANTHROPIC_AUTH_HEADER === 'Authorization') {
      headers['Authorization'] = `Bearer ${apiKey}`;
    } else {
      // x-api-key 格式（官方 Anthropic）
      headers['x-api-key'] = apiKey;
    }

    const res = await fetch(API_BASE, {
      method: 'POST',
      signal: controller.signal,
      headers,
      body: JSON.stringify(body),
    });

    clearTimeout(timer);

    if (!res.ok) {
      let errBody = '';
      try { errBody = await res.text(); } catch (_) {}
      throw new LLMCallError(
        `API 错误 ${res.status}: ${errBody || res.statusText}`,
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
 * 获取 API 认证信息
 * 优先级: ANTHROPIC_AUTH_TOKEN > ANTHROPIC_API_KEY
 */
function getApiKey() {
  // 智谱AI / 兼容 Provider 格式
  const authToken = process.env.ANTHROPIC_AUTH_TOKEN;
  if (authToken) return authToken;

  // 官方 Anthropic 格式
  const apiKey = process.env.ANTHROPIC_API_KEY;
  if (apiKey) return apiKey;

  throw new LLMCallError(
    '未找到认证信息。请设置 ANTHROPIC_AUTH_TOKEN（智谱AI）或 ANTHROPIC_API_KEY（Anthropic）',
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
