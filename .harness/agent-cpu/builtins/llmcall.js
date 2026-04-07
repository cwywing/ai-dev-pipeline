/**
 * llmcall - 确定性任务调用
 *
 * 负责处理确定性的、细粒度的文本生成或数据提取任务。
 */

import { LLMCallError } from '../errors.js';

export const DEFAULT_LLM_CONFIG = {
  model: 'sonnet',
  temperature: 0.3,
  timeout: 60000,
  retries: 2,
  onTokenUsage: null,
};

export async function llmcall(prompt, params = {}, config = {}) {
  const llmConfig = { ...DEFAULT_LLM_CONFIG, ...config };
  const renderedPrompt = renderTemplate(prompt, params);
  const response = await callLLM(renderedPrompt, llmConfig);

  if (!response || !response.content) {
    throw new LLMCallError('LLM 返回为空', response);
  }

  return response.content;
}

function renderTemplate(template, params) {
  return template.replace(/\{(\w+)\}/g, (match, key) => {
    if (key in params) {
      return String(params[key]);
    }
    return match;
  });
}

async function callLLM(prompt, config) {
  const startTime = Date.now();

  try {
    const result = await callClaudeCLI(prompt, config);
    const duration = Date.now() - startTime;

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

async function callClaudeCLI(prompt, config) {
  const { spawn } = await import('child_process');
  const { writeFile, unlink } = await import('fs/promises');
  const os = await import('os');
  const path = await import('path');

  const isWindows = os.platform() === 'win32';

  return new Promise(async (resolve, reject) => {
    if (isWindows) {
      // Windows: 使用 Python subprocess + base64 编码
      const tempDir = os.tmpdir();
      const scriptPath = path.join(tempDir, `claude_llm_${Date.now()}.py`);
      const claudePath = process.env.APPDATA + '/npm/claude.cmd';

      // 使用 base64 编码避免转义问题
      const promptBase64 = Buffer.from(prompt, 'utf-8').toString('base64');
      const modelArg = config.model ? `, "--model", "${config.model}"` : '';

      const pythonScript = `# -*- coding: utf-8 -*-
import subprocess
import sys
import base64
import os
os.environ['PYTHONIOENCODING'] = 'utf-8'
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')
prompt = base64.b64decode("${promptBase64}").decode('utf-8')
claude = r"${claudePath}"
result = subprocess.run(
    [claude, "--print", "--output-format", "json"${modelArg}],
    input=prompt,
    capture_output=True,
    text=True,
    encoding='utf-8',
    timeout=120
)
sys.stdout.write(result.stdout)
if result.stderr:
    sys.stderr.write(result.stderr)
sys.exit(result.returncode)
`;

      await writeFile(scriptPath, pythonScript, 'utf8');

      const proc = spawn('python', [scriptPath], {
        stdio: ['ignore', 'pipe', 'pipe'],
        shell: false,
        windowsHide: true
      });

      let stdout = '';
      let stderr = '';

      proc.stdout.on('data', (data) => {
        stdout += data.toString();
      });

      proc.stderr.on('data', (data) => {
        stderr += data.toString();
      });

      proc.on('close', async (code) => {
        await unlink(scriptPath).catch(() => {});

        if (stdout.trim()) {
          try {
            const response = JSON.parse(stdout);
            resolve({
              content: response.result || stdout.trim(),
              usage: response.usage || {}
            });
          } catch (e) {
            resolve({ content: stdout.trim(), usage: {} });
          }
        } else {
          reject(new Error(`Claude CLI failed: ${stderr || 'unknown error'}`));
        }
      });

      proc.on('error', async (err) => {
        await unlink(scriptPath).catch(() => {});
        reject(new Error(`Spawn error: ${err.message}`));
      });

      setTimeout(() => {
        proc.kill();
        reject(new Error('LLM 调用超时'));
      }, config.timeout || 120000);

    } else {
      // Unix: 使用 stdin 传递 prompt
      const args = ['--print', '--output-format', 'json'];
      if (config.model) {
        args.push('--model', config.model);
      }

      const proc = spawn('claude', args, {
        shell: false,
        stdio: ['pipe', 'pipe', 'pipe']
      });

      let stdout = '';
      let stderr = '';

      proc.stdout.on('data', (data) => {
        stdout += data.toString();
      });

      proc.stderr.on('data', (data) => {
        stderr += data.toString();
      });

      proc.stdin.write(prompt);
      proc.stdin.end();

      proc.on('close', (code) => {
        if (code === 0 || stdout.trim()) {
          try {
            const response = JSON.parse(stdout);
            resolve({
              content: response.result || stdout.trim(),
              usage: response.usage || {}
            });
          } catch (e) {
            resolve({ content: stdout.trim(), usage: {} });
          }
        } else {
          reject(new Error(`Claude CLI exited with code ${code}: ${stderr}`));
        }
      });

      proc.on('error', (err) => {
        reject(new Error(`Spawn error: ${err.message}`));
      });

      setTimeout(() => {
        proc.kill();
        reject(new Error('LLM 调用超时'));
      }, config.timeout || 120000);
    }
  });
}

export async function llmcallBatch(tasks, config = {}) {
  const results = [];
  for (const task of tasks) {
    const result = await llmcall(task.prompt, task.params || {}, config);
    results.push(result);
  }
  return results;
}

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

export function createLLMCall(scope, defaultConfig = {}) {
  return async function(prompt, params = {}, config = {}) {
    const mergedParams = {
      ...scope.getAllVariables(),
      ...params
    };
    const constraints = scope.constraints.length > 0
      ? `\n\n约束条件:\n${scope.constraints.map(c => `- ${c}`).join('\n')}`
      : '';
    const finalPrompt = prompt + constraints;
    return llmcall(finalPrompt, mergedParams, { ...defaultConfig, ...config });
  };
}
