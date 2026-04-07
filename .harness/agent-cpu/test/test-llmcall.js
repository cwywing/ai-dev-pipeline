/**
 * llmcall 测试脚本
 */

import { llmcall } from './builtins/llmcall.js';

async function test() {
  console.log("测试 llmcall...");
  try {
    // 简化 prompt 测试 - 使用更长的超时
    const result = await llmcall("say hello", {}, { timeout: 180000 });
    console.log("成功:", result);
  } catch (e) {
    console.error("失败:", e.message);
  }
}

test();
