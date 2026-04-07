/**
 * Agent CPU CLI - 命令行入口
 *
 * 用于测试和调试 Agent CPU
 *
 * 使用方法:
 *   node cli.js run --script path/to/script.js
 *   node cli.js run --code "await llmcall('hello')"
 *   node cli.js review --request review_id --approve
 */

import { AgentCPU, createAgentCPU } from './runtime.js';
import { humanReviewManager, ReviewResult } from './human-review.js';
import { knowledgeBase } from './knowledge-base.js';
import fs from 'fs/promises';

const args = process.argv.slice(2);
const command = args[0];

async function main() {
  switch (command) {
    case 'run':
      await runCommand();
      break;
    case 'review':
      await reviewCommand();
      break;
    case 'kb':
      await kbCommand();
      break;
    case 'help':
      showHelp();
      break;
    default:
      showHelp();
  }
}

async function runCommand() {
  const scriptIndex = args.indexOf('--script');
  const codeIndex = args.indexOf('--code');
  const taskIdIndex = args.indexOf('--task-id');
  const categoryIndex = args.indexOf('--category');

  let script;
  let taskId = 'cli-run';
  let category = 'general';

  if (scriptIndex !== -1 && args[scriptIndex + 1]) {
    script = await fs.readFile(args[scriptIndex + 1], 'utf-8');
  } else if (codeIndex !== -1 && args[codeIndex + 1]) {
    script = args[codeIndex + 1];
  } else {
    console.error('请提供 --script 或 --code 参数');
    process.exit(1);
  }

  if (taskIdIndex !== -1 && args[taskIdIndex + 1]) {
    taskId = args[taskIdIndex + 1];
  }

  if (categoryIndex !== -1 && args[categoryIndex + 1]) {
    category = args[categoryIndex + 1];
  }

  const cpu = createAgentCPU({
    enableSelfHealing: true,
    enableHumanReview: false,  // CLI 模式默认关闭人工审查
    enableKnowledgeBase: true,
    sandbox: false,  // CLI 模式禁用沙箱以支持动态 import
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

  try {
    const result = await cpu.execute(script, {
      taskId,
      category
    });

    console.log('\n=== 执行结果 ===');
    console.log(`状态: ${result.success ? '成功' : '失败'}`);
    console.log(`耗时: ${result.duration}ms`);
    console.log(`产出文件: ${result.artifacts.length} 个`);
    console.log(`设计决策: ${result.decisions.length} 个`);

    if (result.artifacts.length > 0) {
      console.log('\n产出文件列表:');
      result.artifacts.forEach(a => console.log(`  - ${a.path}`));
    }

    process.exit(result.success ? 0 : 1);
  } catch (error) {
    console.error('\n执行失败:', error.message);
    process.exit(1);
  }
}

async function reviewCommand() {
  const action = args[1];

  if (action === '--list') {
    const pending = humanReviewManager.getPendingReviews();
    console.log('\n待处理审查:');
    if (pending.length === 0) {
      console.log('  无');
    } else {
      pending.forEach(r => {
        console.log(`  - ${r.id} [${r.type}] ${r.taskId}: ${r.content?.task?.description?.substring(0, 50) || ''}`);
      });
    }

    const stats = humanReviewManager.getStats();
    console.log('\n统计:');
    console.log(`  待处理: ${stats.pending}`);
    console.log(`  已完成: ${stats.completed}`);
    console.log(`  通过: ${stats.approved}`);
    console.log(`  拒绝: ${stats.rejected}`);
    return;
  }

  if (action === '--approve' || action === '--reject') {
    const requestIdIndex = args.indexOf('--id');
    if (requestIdIndex === -1) {
      console.error('请提供 --id 参数');
      process.exit(1);
    }

    const requestId = args[requestIdIndex + 1];
    const feedbackIndex = args.indexOf('--feedback');
    const feedback = feedbackIndex !== -1 ? args[feedbackIndex + 1] : '';

    const result = action === '--approve' ? ReviewResult.APPROVED : ReviewResult.REJECTED;

    await humanReviewManager.processReviewResponse(requestId, result, feedback);
    console.log(`审查已处理: ${requestId} -> ${result}`);
    return;
  }

  console.log('支持的 review 命令:');
  console.log('  --list              列出待处理审查');
  console.log('  --approve --id XXX  批准审查');
  console.log('  --reject --id XXX  拒绝审查');
}

async function kbCommand() {
  const kbAction = args[1];

  await knowledgeBase.initialize();

  if (kbAction === '--stats') {
    const stats = knowledgeBase.getStats();
    console.log('\n知识库统计:');
    console.log(`  总条目数: ${stats.totalEntries}`);
    console.log(`  平均成功率: ${(stats.averageSuccessRate * 100).toFixed(1)}%`);
    console.log('\n按类别:');
    Object.entries(stats.byCategory).forEach(([cat, count]) => {
      console.log(`  ${cat}: ${count}`);
    });
    return;
  }

  if (kbAction === '--retrieve') {
    const categoryIndex = args.indexOf('--category');
    const limitIndex = args.indexOf('--limit');

    const query = {};
    if (categoryIndex !== -1) query.category = args[categoryIndex + 1];
    if (limitIndex !== -1) query.limit = parseInt(args[limitIndex + 1]) || 3;

    const results = await knowledgeBase.retrieve(query, query.limit || 3);

    console.log(`\n检索结果 (${results.length} 条):`);
    results.forEach(entry => {
      console.log(`\n  ID: ${entry.id}`);
      console.log(`  类别: ${entry.category}`);
      console.log(`  成功率: ${(entry.successRate * 100).toFixed(1)}%`);
      console.log(`  使用次数: ${entry.usageCount}`);
    });
    return;
  }

  if (kbAction === '--cleanup') {
    const deleted = await knowledgeBase.cleanup(0.3);
    console.log(`已清理 ${deleted} 个低成功率条目`);
    return;
  }

  console.log('支持的 kb 命令:');
  console.log('  --stats              显示统计');
  console.log('  --retrieve           检索条目');
  console.log('  --cleanup            清理低成功率条目');
}

function showHelp() {
  console.log(`
Agent CPU CLI

用法:
  node cli.js <command> [options]

命令:
  run          执行流程代码
  review       管理审查请求
  kb           管理知识库
  help         显示帮助

run 选项:
  --script <path>    从文件加载脚本
  --code <code>      直接提供代码
  --task-id <id>     设置任务 ID
  --category <cat>   设置任务类别

review 选项:
  --list              列出待处理审查
  --approve --id XXX  批准审查
  --reject --id XXX   拒绝审查

kb 选项:
  --stats             显示统计
  --retrieve          检索条目
  --cleanup           清理低成功率条目
`);
}

main().catch(console.error);
