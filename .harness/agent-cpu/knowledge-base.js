/**
 * Knowledge Base - 知识库管理
 *
 * 实现成功流程的自动同步与复用。
 */

import fs from 'fs/promises';
import path from 'path';

/**
 * 知识库条目
 */
export class KnowledgeEntry {
  constructor(data = {}) {
    this.id = data.id || KnowledgeEntry._generateId();
    this.taskId = data.taskId || '';
    this.category = data.category || 'general';
    this.flowCode = data.flowCode || '';
    this.artifacts = data.artifacts || [];
    this.decisions = data.decisions || [];
    this.successRate = data.successRate || 1.0;
    this.usageCount = data.usageCount || 0;
    this.tags = data.tags || [];
    this.metadata = data.metadata || {};
    this.createdAt = data.createdAt || new Date().toISOString();
    this.updatedAt = data.updatedAt || this.createdAt;
    this.lastUsedAt = data.lastUsedAt || null;
  }

  static _idCounter = 0;
  static _generateId() {
    return `kb_${++KnowledgeEntry._idCounter}_${Date.now()}`;
  }

  /**
   * 增加使用次数
   */
  incrementUsage() {
    this.usageCount++;
    this.lastUsedAt = new Date().toISOString();
    this.updatedAt = this.lastUsedAt;
  }

  /**
   * 更新成功率
   */
  updateSuccessRate(success) {
    const totalAttempts = this.usageCount + 1;
    const previousSuccesses = this.successRate * this.usageCount;
    this.successRate = (previousSuccesses + (success ? 1 : 0)) / totalAttempts;
    this.usageCount = totalAttempts;
    this.lastUsedAt = new Date().toISOString();
    this.updatedAt = this.lastUsedAt;
  }

  /**
   * 序列化
   */
  toJSON() {
    return {
      id: this.id,
      taskId: this.taskId,
      category: this.category,
      flowCode: this.flowCode,
      artifacts: this.artifacts,
      decisions: this.decisions,
      successRate: this.successRate,
      usageCount: this.usageCount,
      tags: this.tags,
      metadata: this.metadata,
      createdAt: this.createdAt,
      updatedAt: this.updatedAt,
      lastUsedAt: this.lastUsedAt
    };
  }
}

/**
 * 知识库配置
 */
export const DEFAULT_KB_CONFIG = {
  kbDir: '.harness/knowledge-base',  // 知识库目录
  maxEntries: 1000,                   // 最大条目数
  autoSync: true,                     // 是否自动同步
  similarityThreshold: 0.7,           // 相似度阈值
  onSync: null,                       // 同步回调
  onRetrieve: null,                   // 检索回调
};

/**
 * 知识库管理器
 */
export class KnowledgeBase {
  constructor(config = {}) {
    this.config = { ...DEFAULT_KB_CONFIG, ...config };
    this.entries = new Map();
    this.index = {
      byCategory: new Map(),
      byTags: new Map(),
      byTaskId: new Map()
    };
    this.initialized = false;
  }

  /**
   * 初始化知识库
   */
  async initialize() {
    if (this.initialized) return;

    try {
      const kbDir = path.resolve(this.config.kbDir);
      await fs.mkdir(kbDir, { recursive: true });

      // 加载现有条目
      const files = await fs.readdir(kbDir);
      for (const file of files) {
        if (file.endsWith('.json')) {
          try {
            const content = await fs.readFile(path.join(kbDir, file), 'utf-8');
            const data = JSON.parse(content);
            const entry = new KnowledgeEntry(data);
            this.entries.set(entry.id, entry);
            this._indexEntry(entry);
          } catch (e) {
            console.warn(`加载知识库条目失败: ${file}`);
          }
        }
      }

      this.initialized = true;
      console.log(`[KnowledgeBase] 已加载 ${this.entries.size} 个条目`);
    } catch (error) {
      console.error(`[KnowledgeBase] 初始化失败: ${error.message}`);
    }
  }

  /**
   * 索引条目
   */
  _indexEntry(entry) {
    // 按类别索引
    if (!this.index.byCategory.has(entry.category)) {
      this.index.byCategory.set(entry.category, new Set());
    }
    this.index.byCategory.get(entry.category).add(entry.id);

    // 按标签索引
    for (const tag of entry.tags) {
      if (!this.index.byTags.has(tag)) {
        this.index.byTags.set(tag, new Set());
      }
      this.index.byTags.get(tag).add(entry.id);
    }

    // 按任务 ID 索引
    if (entry.taskId) {
      this.index.byTaskId.set(entry.taskId, entry.id);
    }
  }

  /**
   * 同步任务到知识库
   *
   * @param {object} data - 同步数据
   * @returns {Promise<KnowledgeEntry>}
   */
  async sync(data) {
    await this.initialize();

    // 检查是否已存在
    const existingId = this.index.byTaskId.get(data.taskId);
    let entry;

    if (existingId) {
      // 更新现有条目
      entry = this.entries.get(existingId);
      Object.assign(entry, {
        flowCode: data.flowCode || entry.flowCode,
        artifacts: data.artifacts || entry.artifacts,
        decisions: data.decisions || entry.decisions,
        metadata: { ...entry.metadata, ...data.metadata }
      });
      entry.updatedAt = new Date().toISOString();
    } else {
      // 创建新条目
      entry = new KnowledgeEntry({
        taskId: data.taskId,
        category: data.category || 'general',
        flowCode: data.flowCode,
        artifacts: data.artifacts || [],
        decisions: data.decisions || [],
        tags: data.tags || [],
        metadata: data.metadata || {}
      });
      this.entries.set(entry.id, entry);
      this._indexEntry(entry);
    }

    // 保存到文件
    await this._saveEntry(entry);

    // 触发回调
    if (this.config.onSync) {
      this.config.onSync(entry);
    }

    return entry;
  }

  /**
   * 检索相似条目
   *
   * @param {object} query - 查询条件
   * @param {number} limit - 返回数量
   * @returns {Promise<Array<KnowledgeEntry>>}
   */
  async retrieve(query, limit = 3) {
    await this.initialize();

    let candidates = new Set();

    // 按类别筛选
    if (query.category) {
      const categoryIds = this.index.byCategory.get(query.category);
      if (categoryIds) {
        candidates = new Set([...candidates, ...categoryIds]);
      }
    }

    // 按标签筛选
    if (query.tags && query.tags.length > 0) {
      const tagIds = new Set();
      for (const tag of query.tags) {
        const ids = this.index.byTags.get(tag);
        if (ids) {
          ids.forEach(id => tagIds.add(id));
        }
      }
      if (candidates.size === 0) {
        candidates = tagIds;
      } else {
        // 取交集
        candidates = new Set([...candidates].filter(id => tagIds.has(id)));
      }
    }

    // 如果没有筛选条件，返回所有
    if (candidates.size === 0) {
      candidates = new Set(this.entries.keys());
    }

    // 计算相似度并排序
    const results = [];
    for (const id of candidates) {
      const entry = this.entries.get(id);
      if (!entry) continue;

      const similarity = this._calculateSimilarity(entry, query);
      if (similarity >= this.config.similarityThreshold) {
        results.push({ entry, similarity });
      }
    }

    // 按相似度排序
    results.sort((a, b) => b.similarity - a.similarity);

    const topResults = results.slice(0, limit).map(r => r.entry);

    // 触发回调
    if (this.config.onRetrieve) {
      this.config.onRetrieve(topResults, query);
    }

    return topResults;
  }

  /**
   * 计算相似度
   */
  _calculateSimilarity(entry, query) {
    let score = 0;
    let maxScore = 0;

    // 类别匹配
    if (query.category && entry.category === query.category) {
      score += 0.3;
    }
    maxScore += 0.3;

    // 标签匹配
    if (query.tags && query.tags.length > 0) {
      const matchCount = query.tags.filter(t => entry.tags.includes(t)).length;
      score += 0.2 * (matchCount / query.tags.length);
    }
    maxScore += 0.2;

    // 关键词匹配
    if (query.keywords && query.keywords.length > 0) {
      const content = (entry.flowCode + ' ' + entry.decisions.join(' ')).toLowerCase();
      const matchCount = query.keywords.filter(k => content.includes(k.toLowerCase())).length;
      score += 0.3 * (matchCount / query.keywords.length);
    }
    maxScore += 0.3;

    // 成功率加成
    score += 0.2 * entry.successRate;
    maxScore += 0.2;

    return maxScore > 0 ? score / maxScore : 0;
  }

  /**
   * 生成流程模板
   *
   * @param {string} category - 类别
   * @param {object} context - 上下文
   * @returns {Promise<string>}
   */
  async generateTemplate(category, context = {}) {
    const entries = await this.retrieve({ category, limit: 1 });

    if (entries.length === 0) {
      return this._getDefaultTemplate(category);
    }

    const entry = entries[0];

    // 增加使用次数
    entry.incrementUsage();
    await this._saveEntry(entry);

    // 返回流程代码
    return entry.flowCode;
  }

  /**
   * 获取默认模板
   */
  _getDefaultTemplate(category) {
    return `// ${category} 流程模板
async function ${category.toLowerCase()}Flow(task) {
  const scope = enterScope();

  try {
    // 1. 分析需求
    const analysis = await llmcall("分析{task}", { task: task.description });

    // 2. 生成代码
    const code = await agentcall(scope, "实现功能", {});

    // 3. 验证结果
    metacall(code.generated, "代码生成失败");

    return scope.exit();
  } catch (error) {
    console.error("流程执行失败:", error);
    throw error;
  }
}
`;
  }

  /**
   * 保存条目到文件
   */
  async _saveEntry(entry) {
    try {
      const kbDir = path.resolve(this.config.kbDir);
      await fs.mkdir(kbDir, { recursive: true });

      const filePath = path.join(kbDir, `${entry.id}.json`);
      await fs.writeFile(filePath, JSON.stringify(entry.toJSON(), null, 2), 'utf-8');
    } catch (error) {
      console.error(`[KnowledgeBase] 保存条目失败: ${error.message}`);
    }
  }

  /**
   * 获取统计信息
   */
  getStats() {
    return {
      totalEntries: this.entries.size,
      byCategory: Object.fromEntries(
        [...this.index.byCategory.entries()].map(([k, v]) => [k, v.size])
      ),
      averageSuccessRate: this._calculateAverageSuccessRate()
    };
  }

  /**
   * 计算平均成功率
   */
  _calculateAverageSuccessRate() {
    if (this.entries.size === 0) return 0;
    const sum = [...this.entries.values()].reduce((acc, e) => acc + e.successRate, 0);
    return sum / this.entries.size;
  }

  /**
   * 清理低成功率条目
   */
  async cleanup(minSuccessRate = 0.3) {
    const toDelete = [];

    for (const [id, entry] of this.entries) {
      if (entry.successRate < minSuccessRate && entry.usageCount > 3) {
        toDelete.push(id);
      }
    }

    for (const id of toDelete) {
      const entry = this.entries.get(id);
      this.entries.delete(id);

      // 删除文件
      try {
        const filePath = path.join(this.config.kbDir, `${id}.json`);
        await fs.unlink(filePath);
      } catch (e) {
        // 忽略
      }
    }

    return toDelete.length;
  }
}

// 导出单例
export const knowledgeBase = new KnowledgeBase();
