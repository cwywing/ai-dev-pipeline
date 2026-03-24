/**
 * Scope Manager - 作用域管理器
 *
 * 利用代码的"变量作用域"特性，映射 LLM 的渐进式披露与有限上下文管理机制。
 * 开发某一个模块时，只需将该模块的局部变量和依赖传入，避免了传统 Agent
 * "全量投喂上下文"导致的注意力涣散。
 */

export class Scope {
  /**
   * @param {Scope|null} parent - 父作用域
   * @param {object} config - 作用域配置
   */
  constructor(parent = null, config = {}) {
    this.parent = parent;
    this.id = Scope._generateId();
    this.variables = {};
    this.artifacts = [];       // 产出文件列表
    this.decisions = [];      // 设计决策
    this.constraints = config.constraints || [];  // 约束条件
    this.metadata = config.metadata || {};
    this.createdAt = new Date().toISOString();
  }

  static _idCounter = 0;
  static _generateId() {
    return `scope_${++Scope._idCounter}_${Date.now()}`;
  }

  /**
   * 设置变量
   * @param {string} key - 变量名
   * @param {any} value - 变量值
   */
  set(key, value) {
    this.variables[key] = value;
  }

  /**
   * 获取变量（支持从父作用域查找）
   * @param {string} key - 变量名
   * @returns {any}
   */
  get(key) {
    if (key in this.variables) {
      return this.variables[key];
    }
    if (this.parent) {
      return this.parent.get(key);
    }
    return undefined;
  }

  /**
   * 检查变量是否存在
   * @param {string} key - 变量名
   * @returns {boolean}
   */
  has(key) {
    if (key in this.variables) {
      return true;
    }
    if (this.parent) {
      return this.parent.has(key);
    }
    return false;
  }

  /**
   * 添加产出文件
   * @param {string} filePath - 文件路径
   * @param {object} metadata - 文件元数据
   */
  addArtifact(filePath, metadata = {}) {
    this.artifacts.push({
      path: filePath,
      ...metadata,
      addedAt: new Date().toISOString()
    });
  }

  /**
   * 添加设计决策
   * @param {string} category - 决策类别
   * @param {string} decision - 决策内容
   * @param {string} reason - 决策原因
   */
  addDecision(category, decision, reason = '') {
    this.decisions.push({
      category,
      decision,
      reason,
      madeAt: new Date().toISOString()
    });
  }

  /**
   * 添加约束条件
   * @param {string} constraint - 约束内容
   */
  addConstraint(constraint) {
    if (!this.constraints.includes(constraint)) {
      this.constraints.push(constraint);
    }
  }

  /**
   * 检查约束是否满足
   * @param {string} constraint - 约束内容
   * @returns {boolean}
   */
  satisfiesConstraint(constraint) {
    return this.constraints.includes(constraint);
  }

  /**
   * 进入子作用域
   * @param {object} config - 子作用域配置
   * @returns {Scope}
   */
  enterChild(config = {}) {
    const childScope = new Scope(this, {
      constraints: [...this.constraints],  // 继承父作用域的约束
      metadata: {
        parentId: this.id,
        ...config.metadata
      }
    });
    return childScope;
  }

  /**
   * 退出作用域，收集产出
   * @returns {object}
   */
  exit() {
    return {
      scopeId: this.id,
      files: [...this.artifacts],
      decisions: [...this.decisions],
      variables: { ...this.variables }
    };
  }

  /**
   * 获取所有变量（包含父作用域）
   * @returns {object}
   */
  getAllVariables() {
    const vars = this.parent ? this.parent.getAllVariables() : {};
    return { ...vars, ...this.variables };
  }

  /**
   * 获取链路上所有决策
   * @returns {array}
   */
  getAllDecisions() {
    const decisions = this.parent ? this.parent.getAllDecisions() : [];
    return [...decisions, ...this.decisions];
  }

  /**
   * 序列化作用域（用于日志和调试）
   * @returns {object}
   */
  serialize() {
    return {
      id: this.id,
      parentId: this.parent?.id || null,
      variables: Object.keys(this.variables),
      artifactCount: this.artifacts.length,
      decisionCount: this.decisions.length,
      constraintCount: this.constraints.length,
      createdAt: this.createdAt
    };
  }
}

/**
 * Scope Manager - 管理全局作用域栈
 */
export class ScopeManager {
  constructor() {
    this.rootScope = new Scope(null, {
      metadata: { type: 'root' }
    });
    this.currentScope = this.rootScope;
    this.scopeHistory = [this.currentScope];
  }

  /**
   * 获取当前作用域
   * @returns {Scope}
   */
  getCurrent() {
    return this.currentScope;
  }

  /**
   * 进入新的作用域
   * @param {object} config - 作用域配置
   * @returns {Scope}
   */
  enterScope(config = {}) {
    this.currentScope = this.currentScope.enterChild(config);
    this.scopeHistory.push(this.currentScope);
    return this.currentScope;
  }

  /**
   * 退出当前作用域，返回父作用域
   * @returns {object} 退出作用域时收集的产出
   */
  exitScope() {
    if (this.currentScope.parent) {
      const output = this.currentScope.exit();
      this.currentScope = this.currentScope.parent;
      return output;
    }
    return this.currentScope.exit();
  }

  /**
   * 进入根作用域
   */
  enterRoot() {
    this.currentScope = this.rootScope;
  }

  /**
   * 重置到根作用域
   */
  reset() {
    this.currentScope = this.rootScope;
    this.scopeHistory = [this.currentScope];
  }

  /**
   * 获取所有历史作用域的摘要
   * @returns {array}
   */
  getHistory() {
    return this.scopeHistory.map(s => s.serialize());
  }

  /**
   * 获取根作用域
   * @returns {Scope}
   */
  getRoot() {
    return this.rootScope;
  }
}

// 导出单例
export const globalScopeManager = new ScopeManager();
