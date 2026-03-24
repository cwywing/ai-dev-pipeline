/**
 * Agent CPU 示例 - 基础流程
 *
 * 演示如何使用 Agent CPU 执行一个简单的开发流程
 */

import { createAgentCPU } from '../runtime.js';
import { knowledgeBase } from '../knowledge-base.js';

async function main() {
  console.log('=== Agent CPU 基础示例 ===\n');

  // 创建 Agent CPU 实例
  const cpu = createAgentCPU({
    enableSelfHealing: true,
    enableHumanReview: false,  // 示例模式，关闭人工审查
    enableKnowledgeBase: true,
    onLog: (entry) => {
      const prefix = {
        info: '[INFO]',
        warn: '[WARN]',
        error: '[ERROR]',
        success: '[OK]'
      }[entry.level] || '[LOG]';
      console.log(`${prefix} ${entry.message}`);
    }
  });

  // 定义流程代码
  const flowCode = `
// 1. 分析任务
const analysis = await llmcall("分析以下任务并提取关键信息:\\n{task}", {
  task: task.description
});

// 2. 创建产物列表
const artifacts = analysis.split("\\n").filter(s => s.trim());
metacall(artifacts.length > 0, "分析结果为空");

// 3. 记录设计决策
scope.addDecision("analysis", "使用 LLM 提取关键信息", "简单高效");

// 4. 返回结果
console.log("分析完成，提取了 " + artifacts.length + " 个关键点");
artifacts;
`;

  // 执行流程
  try {
    const result = await cpu.execute(flowCode, {
      taskId: 'example_001',
      category: 'analysis',
      variables: {
        task: {
          description: '实现用户登录功能，需要验证用户名密码，返回 JWT token'
        }
      }
    });

    console.log('\n=== 执行结果 ===');
    console.log('状态:', result.success ? '成功' : '失败');
    console.log('耗时:', result.duration + 'ms');
    console.log('产出文件:', result.artifacts.length);
    console.log('设计决策:', result.decisions.length);

    // 同步到知识库
    console.log('\n同步到知识库...');
    await knowledgeBase.sync({
      taskId: 'example_001',
      category: 'analysis',
      flowCode,
      artifacts: result.artifacts,
      decisions: result.decisions
    });
    console.log('同步完成');

  } catch (error) {
    console.error('\n执行失败:', error.message);
  }
}

// 运行示例
main();
