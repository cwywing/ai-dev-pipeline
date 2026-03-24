/**
 * Agent CPU 基础演示（无 LLM 调用）
 *
 * 演示 Agent CPU 的基本机制，不依赖外部 LLM
 */

import { createAgentCPU } from '../runtime.js';
import { Scope } from '../scope.js';
import { metacall, metacallEq, metacallNotNull } from '../builtins/index.js';

async function main() {
  console.log("=".repeat(60));
  console.log("Agent CPU 基础演示（无 LLM）");
  console.log("=".repeat(60) + "\n");

  // 创建 Agent CPU（禁用 LLM 调用）
  const cpu = createAgentCPU({
    enableSelfHealing: true,
    enableHumanReview: false,
    enableKnowledgeBase: true,
    autoSyncOnSuccess: false,  // 演示模式，禁用知识库同步
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

  // 演示流程代码（不调用 LLM）
  const demoFlow = `
// ============================================================
// Agent CPU 基础演示流程
// ============================================================

console.log("[Demo] 开始 Agent CPU 演示流程");

// 步骤 1: 模拟架构分析（使用模拟数据）
console.log("\\n[Demo] 步骤 1: 架构分析...");
scope.set('module', 'User');
scope.set('endpoint', '/api/v1/admin/users');
scope.set('method', 'GET');

const analysis = "用户列表 API - 分页查询 - Admin 端接口";
scope.addDecision('analysis', '架构设计', analysis);
console.log("[Demo] 分析结果: " + analysis);

// 步骤 2: 模拟文件生成计划
console.log("\\n[Demo] 步骤 2: 文件规划...");

const plannedFiles = [
  { path: 'app/Models/User.php', type: 'model' },
  { path: 'app/repositories/UserRepository.php', type: 'repository' },
  { path: 'app/service/UserService.php', type: 'service' },
  { path: 'app/validate/UserListValidate.php', type: 'validate' },
  { path: 'app/controller/Api/Admin/UserController.php', type: 'controller' },
  { path: 'tests/Feature/Api/Admin/UserListTest.php', type: 'test' }
];

plannedFiles.forEach(f => {
  scope.addArtifact(f.path, { ...f, generated: true });
});

console.log("[Demo] 计划生成 " + plannedFiles.length + " 个文件");

// 步骤 3: 验证约束
console.log("\\n[Demo] 步骤 3: 验证约束...");

// 添加约束
scope.addConstraint('使用 Repository 模式');
scope.addConstraint('遵循 PSR-12 代码规范');

metacall(
  scope.constraints.includes('使用 Repository 模式'),
  "缺少 Repository 模式约束"
);

metacall(
  plannedFiles.length >= 6,
  "文件数量不足"
);

console.log("[Demo] 约束验证通过");

// 步骤 4: 验证变量
console.log("\\n[Demo] 步骤 4: 验证变量...");

metacallNotNull(scope.get('module'), 'module');
metacallNotNull(scope.get('endpoint'), 'endpoint');
metacallEq(scope.get('method'), 'GET', 'HTTP 方法不正确');

console.log("[Demo] 变量验证通过");
console.log("[Demo] module = " + scope.get('module'));
console.log("[Demo] endpoint = " + scope.get('endpoint'));

// 步骤 5: 模拟代码片段（硬编码）
console.log("\\n[Demo] 步骤 5: 代码生成示例...");

const codeSnippet = \`
// UserService.php
public function getUserList(array $params): array
{
    \\$page = \\$params['page'] ?? 1;
    \\$pageSize = \\$params['page_size'] ?? 15;

    return User::query()
        ->select(['id', 'username', 'email', 'created_at'])
        ->paginate(\\$pageSize, ['*'], 'page', \\$page);
}
\`;

scope.addDecision('code', 'Service层代码片段', codeSnippet.substring(0, 50) + '...');
console.log("[Demo] 代码片段已保存");

// 步骤 6: 模拟执行结果
console.log("\\n[Demo] 步骤 6: 模拟执行...");

const executionResult = {
  success: true,
  filesGenerated: plannedFiles.length,
  validationPassed: true,
  module: scope.get('module'),
  endpoint: scope.get('endpoint')
};

// 最终断言
metacall(
  executionResult.success === true,
  "执行结果不正确"
);

metacall(
  scope.artifacts.length >= 6,
  "产出文件数量不正确"
);

// 完成
console.log("\\n[Demo] === 流程完成 ===");
console.log("[Demo] 产出文件数: " + scope.artifacts.length);
console.log("[Demo] 设计决策数: " + scope.decisions.length);
console.log("[Demo] 约束条件数: " + scope.constraints.length);

// 返回结果
executionResult;
`;

  // 执行流程
  console.log("[Demo] 开始执行 Agent CPU 流程...\n");

  try {
    const result = await cpu.execute(demoFlow, {
      taskId: 'Demo_001',
      category: 'demo',
      description: 'Agent CPU 基础功能演示'
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
        console.log("  - " + a.path + " (" + a.type + ")");
      });
    }

    if (result.decisions.length > 0) {
      console.log("\n设计决策:");
      result.decisions.forEach(d => {
        console.log("  - [" + d.category + "] " + d.decision);
      });
    }

    console.log("\n" + "=".repeat(60));
    console.log("Agent CPU 基础演示完成！");
    console.log("=".repeat(60));
    console.log("\n演示要点:");
    console.log("1. 内置函数 (metacall, scope.set/get)");
    console.log("2. 作用域管理 (artifacts, decisions, constraints)");
    console.log("3. 断言验证 (metacallNotNull, metacallEq)");
    console.log("4. 自愈机制 (失败时自动重试)");
    console.log("5. 知识库集成 (可选同步)");

  } catch (error) {
    console.error("\n演示失败:", error.message);
    process.exit(1);
  }
}

main();
