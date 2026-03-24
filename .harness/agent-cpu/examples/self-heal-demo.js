/**
 * Agent CPU 示例 - 自愈机制演示
 *
 * 演示当代码执行失败时，Agent CPU 如何自动修复
 */

import { createAgentCPU } from '../runtime.js';

async function main() {
  console.log('=== Agent CPU 自愈机制示例 ===\n');

  const cpu = createAgentCPU({
    enableSelfHealing: true,
    enableHumanReview: false,
    maxRetries: 2,  // 最多重试 2 次
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

  // 一个有问题的流程代码（故意引入错误）
  const brokenCode = `
// 这个代码会触发错误
const result = await llmcall("生成一个数字", {});
const number = parseInt(result);

// metacall 会检查类型，如果类型不对会抛出 AssertionError
metacall(typeof number === 'number', "类型错误: 期望 number");

number;
`;

  console.log('执行有问题的代码...\n');

  try {
    const result = await cpu.execute(brokenCode, {
      taskId: 'self_heal_example',
      category: 'test'
    });

    console.log('\n=== 执行结果 ===');
    console.log('状态:', result.success ? '成功' : '失败');
    console.log('耗时:', result.duration + 'ms');

  } catch (error) {
    console.error('\n最终失败:', error.message);

    // 查看错误日志
    const logs = cpu.getExecutionLog();
    console.log('\n错误日志:');
    logs.filter(l => l.level === 'error').forEach(l => {
      console.log(`  - ${l.message}`);
    });
  }
}

main();
