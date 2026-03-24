/**
 * Agent CPU 任务演示
 *
 * 模拟 Dev Agent 使用 Agent CPU 模式处理 Test_UserList_001 任务
 */

import { createAgentCPU } from '../runtime.js';
import fs from 'fs/promises';
import path from 'path';
import { fileURLToPath } from 'url';

// 获取当前文件路径
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// 加载任务数据
async function loadTask(taskId) {
  // 修正路径：从 examples/ 回到项目根目录
  const taskFile = path.resolve(__dirname, '..', '..', 'tasks', 'pending', `${taskId}.json`);
  const content = await fs.readFile(taskFile, 'utf-8');
  return JSON.parse(content);
}

// 演示流程代码
const demoFlowCode = `
// ============================================================
// Agent CPU Dev Flow 演示 - Test_UserList_001
// ============================================================

console.log("[DevFlow] 开始处理任务: " + context.taskId);
console.log("[DevFlow] 任务描述: " + context.task.description);

// 步骤 1: 架构分析
console.log("\\n[DevFlow] 步骤 1: 架构分析...");

const analysis = await llmcall(
  "分析以下任务，输出架构设计要点：\\n" +
  "任务: {task}\\n" +
  "验收标准: {acceptance}",
  {
    task: context.task.description,
    acceptance: context.task.acceptance?.join('\\n') || ''
  },
  { temperature: 0.3 }
);

scope.set('analysis', analysis);
scope.addDecision('architecture', '架构分析', analysis);
console.log("[DevFlow] 分析结果已保存");

// 步骤 2: 记录文件生成计划
console.log("\\n[DevFlow] 步骤 2: 规划文件结构...");

const files = [
  'app/Models/User.php',
  'app/repositories/UserRepository.php',
  'app/service/UserService.php',
  'app/validate/UserListValidate.php',
  'app/controller/Api/Admin/UserController.php',
  'tests/Feature/Api/Admin/UserListTest.php'
];

files.forEach(f => {
  scope.addArtifact(f, { type: 'planned', planned: true });
});

console.log("[DevFlow] 计划生成 " + files.length + " 个文件");

// 步骤 3: 验证分析结果
console.log("\\n[DevFlow] 步骤 3: 验证...");

metacall(
  analysis && analysis.length > 0,
  "分析结果为空"
);

metacall(
  scope.artifacts.length >= 6,
  "文件规划不完整"
);

// 步骤 4: 生成流程代码示例
console.log("\\n[DevFlow] 步骤 4: 生成代码（示例）...");

const codeSnippet = await llmcall(
  "生成用户列表 Service 层代码片段，只返回代码：\\n" +
  "要求：分页查询用户列表",
  {},
  { temperature: 0.3 }
);

scope.addDecision('code', 'Service层代码片段', codeSnippet.substring(0, 100) + '...');

// 步骤 5: 总结
console.log("\\n[DevFlow] === 流程完成 ===");
console.log("[DevFlow] 分析内容长度: " + analysis.length + " 字符");
console.log("[DevFlow] 规划文件数: " + scope.artifacts.length);
console.log("[DevFlow] 设计决策数: " + scope.decisions.length);

// 返回结果
{
  success: true,
  analysisLength: analysis.length,
  fileCount: scope.artifacts.length,
  decisionCount: scope.decisions.length
}
`;

async function main() {
  console.log("=".repeat(60));
  console.log("Agent CPU 任务演示 - Test_UserList_001");
  console.log("=".repeat(60) + "\n");

  const taskId = process.argv[2] || 'Test_UserList_001';

  try {
    // 加载任务
    console.log("[演示] 加载任务: " + taskId);
    const task = await loadTask(taskId);
    console.log("[演示] 任务描述: " + task.description);
    console.log("[演示] 验收标准: " + (task.acceptance?.length || 0) + " 项\n");

    // 创建 Agent CPU
    const cpu = createAgentCPU({
      enableSelfHealing: true,
      enableHumanReview: false,  // 演示模式，关闭人工审查
      enableKnowledgeBase: true,
      autoSyncOnSuccess: true,
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

    // 执行流程
    console.log("\n[演示] 开始执行 Agent CPU 流程...\n");
    const result = await cpu.execute(demoFlowCode, {
      taskId: task.id,
      category: task.category || 'api',
      task: task,
      acceptance: task.acceptance
    });

    // 输出结果
    console.log("\n" + "=".repeat(60));
    console.log("执行结果");
    console.log("=".repeat(60));
    console.log("状态: " + (result.success ? "成功" : "失败"));
    console.log("耗时: " + result.duration + "ms");
    console.log("产出文件: " + result.artifacts.length + " 个");
    console.log("设计决策: " + result.decisions.length + " 个");

    if (result.artifacts.length > 0) {
      console.log("\n产出文件列表:");
      result.artifacts.forEach(a => {
        console.log("  - " + a.path);
      });
    }

    if (result.decisions.length > 0) {
      console.log("\n设计决策:");
      result.decisions.forEach(d => {
        console.log("  - [" + d.category + "] " + d.decision);
      });
    }

    console.log("\n" + "=".repeat(60));
    console.log("演示完成！Agent CPU 模式工作正常。");
    console.log("=".repeat(60));

  } catch (error) {
    console.error("\n演示失败:", error.message);
    process.exit(1);
  }
}

main();
