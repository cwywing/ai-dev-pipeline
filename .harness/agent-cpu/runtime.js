/**
 * Agent CPU Runtime - 核心运行时
 *
 * 解析和执行流程代码，管理内置函数调用。
 *
 * 核心运行机制：
 * 1. 生成：接收用户需求 -> LLM 生成流程代码（例如包含 for 循环、条件判断的脚本）
 * 2. 执行：系统自动运行这段代码
 * 3. 自愈：如果执行出错，LLM 会捕获错误日志，自动修改代码并重新执行
 */

import vm from 'vm';
import { ScopeManager, globalScopeManager } from './scope.js';
import { SelfHealingEngine, globalSelfHealingEngine } from './self-healing.js';
import { knowledgeBase } from './knowledge-base.js';
import { humanReviewManager, ReviewType } from './human-review.js';
import {
  llmcall,
  llmcallBatch,
  llmcallParallel,
  agentcall,
  agentcallWithRetry,
  metacall,
  metacallEq,
  metacallNotNull,
  metacallType,
  metacallSchema,
  metacallMatch,
  metacallIn,
  metacallRange,
  metacallCustom,
  AssertionCollector
} from './builtins/index.js';
import { AgentCPUError, SelfHealingError } from './errors.js';
import fs from 'fs/promises';
import path from 'path';

/**
 * Agent CPU 配置
 */
export const DEFAULT_CONFIG = {
  maxRetries: 3,                    // 自愈最大重试次数
  enableSelfHealing: true,         // 是否启用自愈
  enableHumanReview: true,         // 是否启用人工审查
  enableKnowledgeBase: true,        // 是否启用知识库
  autoSyncOnSuccess: true,         // 成功时自动同步到知识库
  scopeManager: null,               // 作用域管理器
  selfHealingEngine: null,         // 自愈引擎
  sandbox: true,                   // 是否启用沙箱
  contextLimit: 100000,            // 上下文限制（字符数）
  onLog: null,                     // 日志回调
  onError: null,                   // 错误回调
  onProgress: null,               // 进度回调
};

/**
 * Agent CPU 核心运行时
 */
export class AgentCPU {
  /**
   * @param {object} config - 配置
   */
  constructor(config = {}) {
    this.config = { ...DEFAULT_CONFIG, ...config };

    // 初始化管理器
    this.scopeManager = this.config.scopeManager || new ScopeManager();
    this.selfHealingEngine = this.config.selfHealingEngine || new SelfHealingEngine({
      maxRetries: this.config.maxRetries,
      enableSelfHealing: this.config.enableSelfHealing
    });

    // 初始化知识库
    if (this.config.enableKnowledgeBase) {
      knowledgeBase.initialize();
    }

    // 状态
    this.currentTask = null;
    this.executionLog = [];
    this.startTime = null;
  }

  /**
   * 执行流程代码
   *
   * @param {string|Function} script - 流程代码或函数
   * @param {object} context - 上下文
   * @returns {Promise<ExecutionResult>}
   */
  async execute(script, context = {}) {
    this.startTime = Date.now();
    this.currentTask = context.taskId || 'unknown';
    this.executionLog = [];

    this._log('info', `开始执行任务: ${this.currentTask}`);

    // 创建根作用域
    const rootScope = this.scopeManager.getRoot();

    // 设置上下文变量
    if (context.variables) {
      Object.entries(context.variables).forEach(([key, value]) => {
        rootScope.set(key, value);
      });
    }

    // 设置约束
    if (context.constraints) {
      context.constraints.forEach(c => rootScope.addConstraint(c));
    }

    try {
      // 检查是否需要架构审查
      if (this.config.enableHumanReview && context.needsArchitectureReview) {
        await this._requestArchitectureReview(context);
      }

      // 使用自愈机制执行
      const result = await this.selfHealingEngine.executeWithSelfHealing(
        () => this._executeScript(script, context),
        (error, ctx) => this._generateFixScript(error, ctx, script),
        { scope: rootScope, taskId: this.currentTask }
      );

      // 同步到知识库
      if (this.config.autoSyncOnSuccess && this.config.enableKnowledgeBase) {
        await this._syncToKnowledgeBase(script, context, result);
      }

      // 检查是否需要验收审查
      if (this.config.enableHumanReview && context.needsAcceptanceReview) {
        await this._requestAcceptanceReview(context, result);
      }

      this._log('success', `任务完成: ${this.currentTask}`, {
        duration: Date.now() - this.startTime,
        artifacts: rootScope.artifacts
      });

      return {
        success: true,
        scope: rootScope.serialize(),
        artifacts: rootScope.artifacts,
        decisions: rootScope.decisions,
        duration: Date.now() - this.startTime,
        executionLog: this.executionLog
      };
    } catch (error) {
      this._log('error', `任务失败: ${error.message}`, { error: error.stack });

      if (this.config.onError) {
        this.config.onError(error, this.executionLog);
      }

      throw error;
    }
  }

  /**
   * 执行脚本
   */
  async _executeScript(script, context = {}) {
    const scope = this.scopeManager.getCurrent();

    // 构建内置函数映射
    const builtins = this._createBuiltins(scope, context);

    // 如果是字符串，包装为 async 函数
    let executableScript = script;
    if (typeof script === 'string') {
      executableScript = `(async function(scope, context) { ${script} })`;
    }

    // 创建沙箱上下文
    const sandbox = {
      ...builtins,
      scope,
      context,
      console: {
        log: (...args) => this._log('info', args.join(' ')),
        error: (...args) => this._log('error', args.join(' ')),
        warn: (...args) => this._log('warn', args.join(' '))
      },
      setTimeout,
      setInterval,
      Promise,
      Math,
      JSON,
      Array,
      Object,
      String,
      Number,
      Boolean,
      Date,
      RegExp,
      Error
    };

    if (this.config.sandbox) {
      // 使用 vm 沙箱执行
      const vmContext = vm.createContext(sandbox);
      const scriptInstance = new vm.Script(`(async () => {
        const { ${Object.keys(builtins).join(', ')} } = this;
        ${typeof script === 'string' ? script : ''}
      })()`);

      return await scriptInstance.runInContext(vmContext);
    } else {
      // 直接执行
      if (typeof script === 'function') {
        return await script(builtins, scope, context);
      } else {
        const fn = eval(executableScript);
        return await fn(scope, context);
      }
    }
  }

  /**
   * 创建内置函数
   */
  _createBuiltins(scope, context) {
    return {
      // llmcall 系列
      llmcall: (...args) => llmcall(...args),
      llmcallBatch: (tasks, config) => llmcallBatch(tasks, config),
      llmcallParallel: (tasks, concurrency, config) => llmcallParallel(tasks, concurrency, config),

      // agentcall 系列
      agentcall: (ctx, prompt, opts) => agentcall(ctx || scope, prompt, opts),
      agentcallWithRetry: (ctx, prompt, opts) => agentcallWithRetry(ctx || scope, prompt, opts),

      // metacall 系列
      metacall: (condition, msg, hint) => metacall(condition, msg, hint),
      metacallEq: (a, b, msg) => metacallEq(a, b, msg),
      metacallNotNull: (v, name) => metacallNotNull(v, name),
      metacallType: (v, type, name) => metacallType(v, type, name),
      metacallSchema: (data, schema, ctx) => metacallSchema(data, schema, ctx),
      metacallMatch: (v, pattern, name) => metacallMatch(v, pattern, name),
      metacallIn: (v, arr, name) => metacallIn(v, arr, name),
      metacallRange: (v, min, max, name) => metacallRange(v, min, max, name),
      metacallCustom: (validator, msg) => metacallCustom(validator, msg),
      AssertionCollector: AssertionCollector,

      // 作用域管理
      enterScope: (config) => this.scopeManager.enterScope(config),
      exitScope: () => this.scopeManager.exitScope(),
      getScope: () => scope,
      setVar: (k, v) => scope.set(k, v),
      getVar: (k) => scope.get(k),

      // Human-in-loop
      humanReview: (type, content) => humanReviewManager.requestReview(type, this.currentTask, content),

      // 知识库
      retrieveKnowledge: (query, limit) => knowledgeBase.retrieve(query, limit),
      getTemplate: (category, ctx) => knowledgeBase.generateTemplate(category, ctx),

      // 文件操作
      writeFile: async (filePath, content) => {
        await fs.writeFile(filePath, content, 'utf-8');
        scope.addArtifact(filePath, { type: 'file' });
        this._log('info', `文件已写入: ${filePath}`);
        return true;
      },
      readFile: (filePath) => fs.readFile(filePath, 'utf-8'),

      // 工具函数
      sleep: (ms) => new Promise(r => setTimeout(r, ms)),
      retry: async (fn, maxRetries = 3) => {
        for (let i = 0; i < maxRetries; i++) {
          try {
            return await fn();
          } catch (e) {
            if (i === maxRetries - 1) throw e;
            await new Promise(r => setTimeout(r, 1000 * (i + 1)));
          }
        }
      }
    };
  }

  /**
   * 生成修复脚本（自愈机制）
   */
  async _generateFixScript(error, context, originalScript) {
    this._log('warn', `尝试修复错误: ${error.message}`);

    const fixPrompt = `
请修复以下流程代码中的错误：

错误信息: ${error.message}
错误类型: ${error.constructor.name}

原始代码:
\`\`\`javascript
${typeof originalScript === 'string' ? originalScript : 'Function 类型代码'}
\`\`\`

错误日志:
${this.executionLog.slice(-5).map(e => `- ${e.message}`).join('\n')}

请生成修复后的代码，保持相同的函数签名和返回值格式。
确保修复后代码可以正常运行。
`;

    try {
      const fixCode = await llmcall(fixPrompt, {
        task: this.currentTask
      }, { temperature: 0.3 });

      this._log('info', '已生成修复代码');

      // 返回新的执行函数
      return () => this._executeScript(fixCode, context);
    } catch (e) {
      this._log('error', `生成修复代码失败: ${e.message}`);
      throw new AgentCPUError(`自愈失败: ${e.message}`);
    }
  }

  /**
   * 请求架构审查
   */
  async _requestArchitectureReview(context) {
    this._log('info', '请求架构审查...');

    const request = await humanReviewManager.requestReview(
      ReviewType.ARCHITECTURE,
      this.currentTask,
      {
        task: context,
        scope: this.scopeManager.getCurrent().serialize()
      }
    );

    if (request.result === 'rejected') {
      throw new AgentCPUError(`架构审查被拒绝: ${request.feedback}`);
    }

    if (request.result === 'needs_revision') {
      // 需要修改，将反馈注入上下文
      context.architectureFeedback = request.feedback;
      this._log('warn', `需要修改架构: ${request.feedback}`);
    }

    this._log('success', '架构审查通过');
  }

  /**
   * 请求验收审查
   */
  async _requestAcceptanceReview(context, result) {
    this._log('info', '请求验收审查...');

    const request = await humanReviewManager.requestReview(
      ReviewType.ACCEPTANCE,
      this.currentTask,
      {
        task: context,
        result,
        artifacts: result.artifacts,
        decisions: result.decisions
      }
    );

    if (request.result === 'rejected') {
      throw new AgentCPUError(`验收审查被拒绝: ${request.feedback}`);
    }

    this._log('success', '验收审查通过');
  }

  /**
   * 同步到知识库
   */
  async _syncToKnowledgeBase(script, context, result) {
    try {
      await knowledgeBase.sync({
        taskId: this.currentTask,
        category: context.category || 'general',
        flowCode: typeof script === 'string' ? script : '[Function]',
        artifacts: (result && result.artifacts) || [],
        decisions: (result && result.decisions) || [],
        metadata: {
          duration: result?.duration || 0,
          scope: result?.scope
        }
      });

      this._log('info', '已同步到知识库');
    } catch (e) {
      this._log('warn', `同步知识库失败: ${e.message}`);
    }
  }

  /**
   * 记录日志
   */
  _log(level, message, data = {}) {
    const entry = {
      timestamp: new Date().toISOString(),
      level,
      message,
      ...data
    };
    this.executionLog.push(entry);

    if (this.config.onLog) {
      this.config.onLog(entry);
    }
  }

  /**
   * 获取执行日志
   */
  getExecutionLog() {
    return [...this.executionLog];
  }

  /**
   * 获取当前状态
   */
  getStatus() {
    return {
      taskId: this.currentTask,
      isRunning: this.startTime !== null,
      duration: this.startTime ? Date.now() - this.startTime : 0,
      logCount: this.executionLog.length
    };
  }

  /**
   * 重置状态
   */
  reset() {
    this.scopeManager.reset();
    this.selfHealingEngine.reset();
    this.currentTask = null;
    this.executionLog = [];
    this.startTime = null;
  }
}

// 导出单例和工厂函数
export const globalAgentCPU = new AgentCPU();

export function createAgentCPU(config = {}) {
  return new AgentCPU(config);
}
