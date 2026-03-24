/**
 * Self-Healing Engine - 自愈引擎
 *
 * 捕获执行错误，触发 LLM 生成修复代码，实现自动修复。
 * 采用指数退避策略防止无限重试。
 */

import { SelfHealingError } from './errors.js';

/**
 * 自愈配置
 */
export const DEFAULT_CONFIG = {
  maxRetries: 3,              // 最大重试次数
  backoffMultiplier: 2,      // 退避倍数
  initialBackoff: 1000,       // 初始退避时间（毫秒）
  maxBackoff: 30000,         // 最大退避时间（毫秒）
  enableSelfHealing: true,    // 是否启用自愈
  onRetry: null,              // 重试回调
  onExhausted: null          // 重试耗尽回调
};

export class SelfHealingEngine {
  /**
   * @param {object} config - 自愈配置
   */
  constructor(config = {}) {
    this.config = { ...DEFAULT_CONFIG, ...config };
    this.retryCount = 0;
    this.errorLog = [];
    this.healingHistory = [];
  }

  /**
   * 执行函数，失败时自动修复
   * @param {Function} fn - 要执行的函数
   * @param {Function} fixFn - 修复函数 (error, context) => fixedFn
   * @param {object} context - 上下文
   * @returns {Promise<any>}
   */
  async executeWithSelfHealing(fn, fixFn, context = {}) {
    let lastError = null;
    let currentFn = fn;

    while (this.retryCount < this.config.maxRetries) {
      try {
        const result = await currentFn();
        this._logSuccess();
        return result;
      } catch (error) {
        lastError = error;
        this._logError(error, context);

        if (this.retryCount >= this.config.maxRetries - 1) {
          break;
        }

        // 触发修复
        const backoff = this._calculateBackoff();
        this._logRetry(error, backoff);

        // 调用修复函数生成新的执行函数
        if (fixFn && this.config.enableSelfHealing) {
          currentFn = await fixFn(error, context, {
            attempt: this.retryCount + 1,
            errorLog: this.errorLog
          });

          if (!currentFn) {
            throw new Error('修复函数未能生成有效的修复代码');
          }
        } else {
          // 无修复函数，等待后重试
          await this._sleep(backoff);
        }

        this.retryCount++;
      }
    }

    // 重试耗尽
    this._logExhausted(lastError);
    if (this.config.onExhausted) {
      this.config.onExhausted(lastError, this.errorLog);
    }
    throw new SelfHealingError(
      `自愈机制已耗尽（${this.config.maxRetries}次）: ${lastError?.message || '未知错误'}`,
      lastError,
      this.errorLog
    );
  }

  /**
   * 执行带断言的函数
   * @param {Function} fn - 要执行的函数
   * @param {Function} assertionFn - 断言函数 (result) => boolean
   * @param {string} assertionMsg - 断言失败消息
   * @param {Function} fixFn - 修复函数
   * @param {object} context - 上下文
   * @returns {Promise<any>}
   */
  async executeWithAssertion(fn, assertionFn, assertionMsg, fixFn = null, context = {}) {
    let lastError = null;
    let currentFn = fn;

    while (this.retryCount < this.config.maxRetries) {
      try {
        const result = await currentFn();

        // 执行断言
        if (assertionFn(result)) {
          this._logSuccess();
          return result;
        }

        // 断言失败
        lastError = new AssertionError(assertionMsg, result);
        this._logError(lastError, context);

        if (this.retryCount >= this.config.maxRetries - 1) {
          break;
        }

        // 触发修复
        const backoff = this._calculateBackoff();
        this._logRetry(lastError, backoff);

        if (fixFn && this.config.enableSelfHealing) {
          currentFn = await fixFn(lastError, context, {
            attempt: this.retryCount + 1,
            errorLog: this.errorLog,
            lastResult: result
          });

          if (!currentFn) {
            throw new Error('修复函数未能生成有效的修复代码');
          }
        }

        this.retryCount++;
      } catch (error) {
        lastError = error;
        this._logError(error, context);

        if (this.retryCount >= this.config.maxRetries - 1) {
          break;
        }

        const backoff = this._calculateBackoff();
        this._logRetry(error, backoff);

        if (fixFn && this.config.enableSelfHealing) {
          currentFn = await fixFn(error, context, {
            attempt: this.retryCount + 1,
            errorLog: this.errorLog
          });
        }

        this.retryCount++;
      }
    }

    this._logExhausted(lastError);
    throw new SelfHealingError(
      `断言失败且自愈耗尽: ${assertionMsg}`,
      lastError,
      this.errorLog
    );
  }

  /**
   * 计算退避时间
   * @returns {number}
   */
  _calculateBackoff() {
    const backoff = Math.min(
      this.config.initialBackoff * Math.pow(this.config.backoffMultiplier, this.retryCount),
      this.config.maxBackoff
    );
    // 添加随机抖动（±25%）
    const jitter = backoff * 0.25 * (Math.random() * 2 - 1);
    return Math.floor(backoff + jitter);
  }

  /**
   * 睡眠
   * @param {number} ms - 毫秒
   */
  _sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
  }

  /**
   * 记录错误
   */
  _logError(error, context) {
    const entry = {
      timestamp: new Date().toISOString(),
      attempt: this.retryCount + 1,
      error: {
        message: error.message,
        stack: error.stack,
        type: error.constructor.name
      },
      context: {
        scopeId: context.scope?.id,
        taskId: context.taskId,
        ...context.metadata
      }
    };
    this.errorLog.push(entry);

    if (this.config.onRetry) {
      this.config.onRetry(entry);
    }
  }

  /**
   * 记录成功
   */
  _logSuccess() {
    this.healingHistory.push({
      timestamp: new Date().toISOString(),
      success: true,
      attempts: this.retryCount + 1,
      errorCount: this.errorLog.length
    });
    // 重置计数器
    this.retryCount = 0;
  }

  /**
   * 记录重试
   */
  _logRetry(error, backoff) {
    console.log(`[SelfHealing] Retry ${this.retryCount + 1}/${this.config.maxRetries} after ${backoff}ms`);
    console.log(`[SelfHealing] Error: ${error.message}`);
  }

  /**
   * 记录耗尽
   */
  _logExhausted(error) {
    const entry = {
      timestamp: new Date().toISOString(),
      exhausted: true,
      totalAttempts: this.retryCount + 1,
      error: error?.message || '未知错误',
      errorLog: [...this.errorLog]
    };
    this.healingHistory.push(entry);
    console.error(`[SelfHealing] Exhausted after ${this.retryCount + 1} attempts`);
  }

  /**
   * 获取错误日志
   * @returns {array}
   */
  getErrorLog() {
    return [...this.errorLog];
  }

  /**
   * 获取自愈历史
   * @returns {array}
   */
  getHistory() {
    return [...this.healingHistory];
  }

  /**
   * 重置引擎状态
   */
  reset() {
    this.retryCount = 0;
    this.errorLog = [];
  }

  /**
   * 设置最大重试次数
   * @param {number} max
   */
  setMaxRetries(max) {
    this.config.maxRetries = max;
  }

  /**
   * 禁用自愈
   */
  disableSelfHealing() {
    this.config.enableSelfHealing = false;
  }

  /**
   * 启用自愈
   */
  enableSelfHealing() {
    this.config.enableSelfHealing = true;
  }
}


// 导出单例
export const globalSelfHealingEngine = new SelfHealingEngine();
