/**
 * metacall - 断言验证调用
 *
 * 一种审视执行流程问题的"伪内建函数"。
 * 它不仅能捕获系统层面的执行报错，还能在代码逻辑层面主动抛出业务错误，
 * 触发 LLM 的自修复机制。
 */

import { AssertionError } from '../errors.js';

/**
 * metacall 实现
 *
 * @param {boolean} condition - 断言条件
 * @param {string} errorMsg - 错误消息
 * @param {string} recoveryHint - 恢复提示（可选）
 * @throws {AssertionError} 当条件不满足时抛出
 */
export function metacall(condition, errorMsg, recoveryHint = '') {
  if (!condition) {
    const error = new AssertionError(errorMsg, null);
    error.recoveryHint = recoveryHint;
    throw error;
  }
  return true;
}

/**
 * metacallAsync - 异步版本的 metacall
 *
 * @param {Promise<boolean>} conditionPromise - 断言条件（Promise）
 * @param {string} errorMsg - 错误消息
 * @param {string} recoveryHint - 恢复提示（可选）
 * @throws {AssertionError} 当条件不满足时抛出
 */
export async function metacallAsync(conditionPromise, errorMsg, recoveryHint = '') {
  const condition = await conditionPromise;

  if (!condition) {
    const error = new AssertionError(errorMsg, null);
    error.recoveryHint = recoveryHint;
    throw error;
  }
  return true;
}

/**
 * metacallEq - 相等断言
 *
 * @param {any} actual - 实际值
 * @param {any} expected - 期望值
 * @param {string} message - 错误消息
 * @throws {AssertionError}
 */
export function metacallEq(actual, expected, message = '') {
  const defaultMsg = `期望 ${JSON.stringify(expected)}, 实际 ${JSON.stringify(actual)}`;
  metacall(actual === expected, message || defaultMsg);
}

/**
 * metacallNotNull - 非空断言
 *
 * @param {any} value - 值
 * @param {string} fieldName - 字段名
 * @throws {AssertionError}
 */
export function metacallNotNull(value, fieldName = 'value') {
  metacall(
    value !== null && value !== undefined,
    `${fieldName} 不能为空`
  );
}

/**
 * metacallType - 类型断言
 *
 * @param {any} value - 值
 * @param {string|Function} expectedType - 期望类型
 * @param {string} fieldName - 字段名
 * @throws {AssertionError}
 */
export function metacallType(value, expectedType, fieldName = 'value') {
  let isValid = false;

  if (typeof expectedType === 'string') {
    isValid = typeof value === expectedType;
  } else if (typeof expectedType === 'function') {
    isValid = value instanceof expectedType;
  }

  metacall(
    isValid,
    `${fieldName} 类型错误: 期望 ${typeof expectedType === 'function' ? expectedType.name : expectedType}, 实际 ${typeof value}`
  );
}

/**
 * metacallSchema - Schema 断言
 *
 * @param {object} data - 数据对象
 * @param {object} schema - Schema 定义
 * @param {string} context - 上下文信息
 * @throws {AssertionError}
 */
export function metacallSchema(data, schema, context = '') {
  const errors = [];

  // 检查必需字段
  if (schema.required) {
    for (const field of schema.required) {
      if (!(field in data) || data[field] === null || data[field] === undefined) {
        errors.push(`缺少必需字段: ${field}`);
      }
    }
  }

  // 检查字段类型
  if (schema.properties) {
    for (const [field, spec] of Object.entries(schema.properties)) {
      if (field in data && data[field] !== null && data[field] !== undefined) {
        const actualType = Array.isArray(data[field]) ? 'array' : typeof data[field];
        const expectedType = spec.type;

        if (expectedType && actualType !== expectedType) {
          errors.push(`字段 ${field} 类型错误: 期望 ${expectedType}, 实际 ${actualType}`);
        }
      }
    }
  }

  // 检查自定义验证
  if (schema.validate) {
    const customErrors = schema.validate(data);
    if (Array.isArray(customErrors)) {
      errors.push(...customErrors);
    } else if (!customErrors) {
      errors.push('自定义验证失败');
    }
  }

  if (errors.length > 0) {
    const contextPrefix = context ? `[${context}] ` : '';
    throw new AssertionError(
      `${contextPrefix}Schema 验证失败:\n${errors.map(e => `  - ${e}`).join('\n')}`,
      data
    );
  }

  return true;
}

/**
 * metacallMatch - 正则匹配断言
 *
 * @param {string} value - 值
 * @param {RegExp|string} pattern - 正则表达式
 * @param {string} fieldName - 字段名
 * @throws {AssertionError}
 */
export function metacallMatch(value, pattern, fieldName = 'value') {
  metacall(
    typeof value === 'string' && new RegExp(pattern).test(value),
    `${fieldName} 不匹配模式: ${pattern}`
  );
}

/**
 * metacallIn - 包含断言
 *
 * @param {any} value - 值
 * @param {Array} array - 数组
 * @param {string} fieldName - 字段名
 * @throws {AssertionError}
 */
export function metacallIn(value, array, fieldName = 'value') {
  metacall(
    array.includes(value),
    `${fieldName} 必须是 [${array.join(', ')}] 之一`
  );
}

/**
 * metacallRange - 范围断言
 *
 * @param {number} value - 值
 * @param {number} min - 最小值
 * @param {number} max - 最大值
 * @param {string} fieldName - 字段名
 * @throws {AssertionError}
 */
export function metacallRange(value, min, max, fieldName = 'value') {
  metacall(
    typeof value === 'number' && value >= min && value <= max,
    `${fieldName} 必须在 ${min} 到 ${max} 之间`
  );
}

/**
 * metacallCustom - 自定义断言
 *
 * @param {boolean|Function} validator - 验证器（函数或布尔值）
 * @param {string} message - 错误消息
 * @throws {AssertionError}
 */
export function metacallCustom(validator, message) {
  const isValid = typeof validator === 'function' ? validator() : validator;
  metacall(isValid, message);
}

/**
 * 断言结果收集器
 * 用于批量执行断言，收集所有错误而不是遇到第一个就抛出
 */
export class AssertionCollector {
  constructor() {
    this.errors = [];
  }

  /**
   * 添加断言
   * @param {boolean} condition - 条件
   * @param {string} message - 错误消息
   * @param {string} recoveryHint - 恢复提示
   */
  add(condition, message, recoveryHint = '') {
    if (!condition) {
      const error = new AssertionError(message, null);
      error.recoveryHint = recoveryHint;
      this.errors.push(error);
    }
  }

  /**
   * 添加异步断言
   * @param {Promise<boolean>} conditionPromise
   * @param {string} message
   * @param {string} recoveryHint
   */
  async addAsync(conditionPromise, message, recoveryHint = '') {
    const condition = await conditionPromise;
    this.add(condition, message, recoveryHint);
  }

  /**
   * 检查是否有错误
   * @returns {boolean}
   */
  hasErrors() {
    return this.errors.length > 0;
  }

  /**
   * 获取所有错误
   * @returns {Array<AssertionError>}
   */
  getErrors() {
    return [...this.errors];
  }

  /**
   * 抛出所有错误（如果有）
   * @throws {AssertionError}
   */
  throwIfHasErrors() {
    if (this.errors.length > 0) {
      const error = new AssertionError(
        `发现 ${this.errors.length} 个断言失败:\n${this.errors.map((e, i) => `  ${i + 1}. ${e.message}`).join('\n')}`,
        null
      );
      error.errors = this.errors;
      throw error;
    }
    return true;
  }

  /**
   * 清空错误
   */
  clear() {
    this.errors = [];
  }
}

/**
 * 创建带上下文的 metacall
 *
 * @param {Scope} scope - 作用域
 * @returns {Function}
 */
export function createMetacall(scope) {
  return function(condition, errorMsg, recoveryHint = '') {
    if (!condition) {
      const error = new AssertionError(errorMsg, {
        scopeId: scope.id,
        constraints: scope.constraints,
        currentVariables: Object.keys(scope.variables)
      });
      error.recoveryHint = recoveryHint;
      error.scopeContext = scope.serialize();
      throw error;
    }
    return true;
  };
}

/**
 * 创建异步带上下文的 metacall
 *
 * @param {Scope} scope - 作用域
 * @returns {Function}
 */
export function createMetacallAsync(scope) {
  return async function(conditionPromise, errorMsg, recoveryHint = '') {
    const condition = await conditionPromise;
    return createMetacall(scope)(condition, errorMsg, recoveryHint);
  };
}
