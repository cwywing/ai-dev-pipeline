/**
 * Custom Errors - 自定义错误类
 */

export class AgentCPUError extends Error {
  constructor(message, details = {}) {
    super(message);
    this.name = 'AgentCPUError';
    this.details = details;
  }
}

export class SelfHealingError extends Error {
  constructor(message, originalError, errorLog = []) {
    super(message);
    this.name = 'SelfHealingError';
    this.originalError = originalError;
    this.errorLog = errorLog;
  }
}

export class AssertionError extends Error {
  constructor(message, result) {
    super(message);
    this.name = 'AssertionError';
    this.result = result;
  }
}

export class ScopeError extends Error {
  constructor(message, scopeInfo = {}) {
    super(message);
    this.name = 'ScopeError';
    this.scopeInfo = scopeInfo;
  }
}

export class HumanReviewError extends Error {
  constructor(message, reviewInfo = {}) {
    super(message);
    this.name = 'HumanReviewError';
    this.reviewInfo = reviewInfo;
  }
}

export class LLMCallError extends Error {
  constructor(message, llmResponse = {}) {
    super(message);
    this.name = 'LLMCallError';
    this.llmResponse = llmResponse;
  }
}

export class AgentCallError extends Error {
  constructor(message, details = {}) {
    super(message);
    this.name = 'AgentCallError';
    this.details = details;
  }
}
