/**
 * Human-in-the-loop - 人工审查机制
 *
 * 在关键节点设置人工挂起点，确保关键决策经过人工确认。
 */

import { HumanReviewError } from './errors.js';
import fs from 'fs/promises';
import path from 'path';

/**
 * 审查点类型
 */
export const ReviewType = {
  ARCHITECTURE: 'architecture',   // 架构审查（Dev 开始前）
  ACCEPTANCE: 'acceptance',       // 验收判定（Review 完成后）
  CRITICAL: 'critical',           // 关键变更审查
};

/**
 * 审查结果
 */
export const ReviewResult = {
  APPROVED: 'approved',           // 审查通过
  REJECTED: 'rejected',           // 审查拒绝
  NEEDS_REVISION: 'needs_revision', // 需要修改
};

/**
 * HumanReview 配置
 */
export const DEFAULT_REVIEW_CONFIG = {
  autoApprove: false,             // 是否自动批准（用于测试）
  reviewDir: '.harness/reviews',  // 审查文件目录
  timeout: 3600000,               // 审查超时（1小时）
  onReviewRequested: null,         // 审查请求回调
  onReviewCompleted: null,         // 审查完成回调
};

/**
 * 审查请求
 */
export class ReviewRequest {
  constructor(type, taskId, content, config = {}) {
    this.id = ReviewRequest._generateId();
    this.type = type;
    this.taskId = taskId;
    this.content = content;
    this.status = 'pending';
    this.createdAt = new Date().toISOString();
    this.updatedAt = this.createdAt;
    this.result = null;
    this.feedback = null;
    this.reviewer = null;
    this.config = config;
  }

  static _idCounter = 0;
  static _generateId() {
    return `review_${++ReviewRequest._idCounter}_${Date.now()}`;
  }

  /**
   * 批准审查
   * @param {string} feedback - 反馈
   * @param {string} reviewer - 审查人
   */
  approve(feedback = '', reviewer = 'human') {
    this.result = ReviewResult.APPROVED;
    this.feedback = feedback;
    this.reviewer = reviewer;
    this.status = 'completed';
    this.updatedAt = new Date().toISOString();
  }

  /**
   * 拒绝审查
   * @param {string} feedback - 拒绝原因
   * @param {string} reviewer - 审查人
   */
  reject(feedback, reviewer = 'human') {
    this.result = ReviewResult.REJECTED;
    this.feedback = feedback;
    this.reviewer = reviewer;
    this.status = 'completed';
    this.updatedAt = new Date().toISOString();
  }

  /**
   * 要求修改
   * @param {string} feedback - 修改建议
   * @param {string} reviewer - 审查人
   */
  requestRevision(feedback, reviewer = 'human') {
    this.result = ReviewResult.NEEDS_REVISION;
    this.feedback = feedback;
    this.reviewer = reviewer;
    this.status = 'completed';
    this.updatedAt = new Date().toISOString();
  }

  /**
   * 序列化
   */
  toJSON() {
    return {
      id: this.id,
      type: this.type,
      taskId: this.taskId,
      status: this.status,
      result: this.result,
      feedback: this.feedback,
      reviewer: this.reviewer,
      createdAt: this.createdAt,
      updatedAt: this.updatedAt,
      content: this.content
    };
  }
}

/**
 * Human-in-the-loop 审查管理器
 */
export class HumanReviewManager {
  constructor(config = {}) {
    this.config = { ...DEFAULT_REVIEW_CONFIG, ...config };
    this.pendingReviews = new Map();
    this.completedReviews = [];
    this.listeners = new Map();
  }

  /**
   * 请求人工审查（阻塞式）
   *
   * @param {string} type - 审查类型
   * @param {string} taskId - 任务 ID
   * @param {object} content - 审查内容
   * @returns {Promise<ReviewRequest>}
   */
  async requestReview(type, taskId, content) {
    // 如果配置为自动批准，直接通过
    if (this.config.autoApprove) {
      const autoRequest = new ReviewRequest(type, taskId, content);
      autoRequest.approve('自动批准（测试模式）', 'auto');
      return autoRequest;
    }

    const request = new ReviewRequest(type, taskId, content);

    // 保存审查请求
    this.pendingReviews.set(request.id, request);

    // 保存到文件
    await this._saveReviewRequest(request);

    // 触发回调
    if (this.config.onReviewRequested) {
      this.config.onReviewRequested(request);
    }

    // 发出审查请求通知
    this._emit('review:requested', request);

    // 等待审查结果（阻塞式）
    return new Promise((resolve, reject) => {
      const timeout = setTimeout(() => {
        this.pendingReviews.delete(request.id);
        reject(new HumanReviewError(
          `审查超时（${this.config.timeout / 1000}秒）`,
          { requestId: request.id, type, taskId }
        ));
      }, this.config.timeout);

      // 监听审查完成
      const checkComplete = setInterval(() => {
        if (request.status === 'completed') {
          clearTimeout(timeout);
          clearInterval(checkComplete);

          // 移动到已完成列表
          this.pendingReviews.delete(request.id);
          this.completedReviews.push(request);

          // 触发回调
          if (this.config.onReviewCompleted) {
            this.config.onReviewCompleted(request);
          }

          this._emit('review:completed', request);
          resolve(request);
        }
      }, 1000);
    });
  }

  /**
   * 检查是否需要审查
   *
   * @param {string} type - 审查类型
   * @param {object} context - 上下文
   * @returns {boolean}
   */
  shouldReview(type, context = {}) {
    // 架构审查条件：新增接口 >= 3 或涉及数据库变更
    if (type === ReviewType.ARCHITECTURE) {
      const { newEndpoints = 0, hasDatabaseChange = false } = context;
      return newEndpoints >= 3 || hasDatabaseChange;
    }

    // 验收审查条件：所有任务都完成审查
    if (type === ReviewType.ACCEPTANCE) {
      return true; // 总是需要验收
    }

    // 关键变更审查条件
    if (type === ReviewType.CRITICAL) {
      return context.isBreakingChange || context.isSecuritySensitive;
    }

    return false;
  }

  /**
   * 处理审查响应
   *
   * @param {string} requestId - 审查请求 ID
   * @param {string} result - 审查结果
   * @param {string} feedback - 反馈
   * @param {string} reviewer - 审查人
   */
  async processReviewResponse(requestId, result, feedback, reviewer = 'human') {
    const request = this.pendingReviews.get(requestId);
    if (!request) {
      throw new Error(`审查请求不存在: ${requestId}`);
    }

    switch (result) {
      case ReviewResult.APPROVED:
        request.approve(feedback, reviewer);
        break;
      case ReviewResult.REJECTED:
        request.reject(feedback, reviewer);
        break;
      case ReviewResult.NEEDS_REVISION:
        request.requestRevision(feedback, reviewer);
        break;
      default:
        throw new Error(`无效的审查结果: ${result}`);
    }

    // 更新文件
    await this._saveReviewRequest(request);
    this._emit('review:response', request);
  }

  /**
   * 获取待审查列表
   *
   * @returns {Array<ReviewRequest>}
   */
  getPendingReviews() {
    return Array.from(this.pendingReviews.values());
  }

  /**
   * 获取已完成审查列表
   *
   * @param {string} taskId - 任务 ID（可选）
   * @returns {Array<ReviewRequest>}
   */
  getCompletedReviews(taskId = null) {
    const reviews = this.completedReviews;
    if (taskId) {
      return reviews.filter(r => r.taskId === taskId);
    }
    return [...reviews];
  }

  /**
   * 保存审查请求到文件
   *
   * @param {ReviewRequest} request
   */
  async _saveReviewRequest(request) {
    try {
      const reviewDir = path.resolve(this.config.reviewDir);
      await fs.mkdir(reviewDir, { recursive: true });

      const filePath = path.join(reviewDir, `${request.id}.json`);
      await fs.writeFile(filePath, JSON.stringify(request.toJSON(), null, 2), 'utf-8');
    } catch (error) {
      console.error(`保存审查请求失败: ${error.message}`);
    }
  }

  /**
   * 添加事件监听器
   *
   * @param {string} event - 事件名
   * @param {Function} listener - 监听器
   */
  on(event, listener) {
    if (!this.listeners.has(event)) {
      this.listeners.set(event, []);
    }
    this.listeners.get(event).push(listener);
  }

  /**
   * 移除事件监听器
   *
   * @param {string} event - 事件名
   * @param {Function} listener - 监听器
   */
  off(event, listener) {
    if (this.listeners.has(event)) {
      const listeners = this.listeners.get(event);
      const index = listeners.indexOf(listener);
      if (index > -1) {
        listeners.splice(index, 1);
      }
    }
  }

  /**
   * 发出事件
   *
   * @param {string} event - 事件名
   * @param {any} data - 数据
   */
  _emit(event, data) {
    if (this.listeners.has(event)) {
      this.listeners.get(event).forEach(listener => {
        try {
          listener(data);
        } catch (error) {
          console.error(`事件监听器执行失败: ${error.message}`);
        }
      });
    }
  }

  /**
   * 设置自动批准模式
   *
   * @param {boolean} autoApprove
   */
  setAutoApprove(autoApprove) {
    this.config.autoApprove = autoApprove;
  }

  /**
   * 获取审查统计
   *
   * @returns {object}
   */
  getStats() {
    return {
      pending: this.pendingReviews.size,
      completed: this.completedReviews.length,
      approved: this.completedReviews.filter(r => r.result === ReviewResult.APPROVED).length,
      rejected: this.completedReviews.filter(r => r.result === ReviewResult.REJECTED).length,
      needsRevision: this.completedReviews.filter(r => r.result === ReviewResult.NEEDS_REVISION).length
    };
  }
}

/**
 * 架构审查辅助函数
 *
 * @param {Scope} scope - 作用域
 * @param {object} design - 设计内容
 * @returns {boolean} 是否需要架构审查
 */
export function needsArchitectureReview(scope, design) {
  // 检查是否需要架构审查
  const newEndpoints = design.endpoints?.length || 0;
  const hasDatabaseChange = design.databaseChanges?.length > 0;
  const involvesMultipleModules = design.modules?.length > 2;

  return newEndpoints >= 3 || hasDatabaseChange || involvesMultipleModules;
}

/**
 * 验收审查辅助函数
 *
 * @param {object} task - 任务对象
 * @param {object} result - 执行结果
 * @returns {boolean} 是否需要验收审查
 */
export function needsAcceptanceReview(task, result) {
  // 简单实现：总是需要验收
  return true;
}

// 导出单例
export const humanReviewManager = new HumanReviewManager();
