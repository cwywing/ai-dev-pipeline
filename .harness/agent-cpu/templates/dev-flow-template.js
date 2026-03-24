/**
 * DevFlow 模板 - 功能开发流程
 *
 * 这是 Dev Agent 应该生成的流程代码模板。
 * LLM 需要根据具体任务填充模板中的占位符。
 */

// ============================================================
// 模板结构说明
// ============================================================
// 这个模板定义了开发功能的标准流程：
// 1. 架构设计 - 分析任务，设计模块结构（可能触发人工审查）
// 2. 生成代码 - 按分层顺序生成代码（Model -> Repository -> Service -> Controller -> Route）
// 3. 验证结果 - 使用 metacall 断言验证产出
// 4. 记录决策 - 将设计决策记录到作用域
// ============================================================

/**
 * 标准功能开发流程
 *
 * @param {object} task - 任务对象，包含 description, acceptance 等
 * @param {object} scope - Agent CPU 作用域
 * @returns {Promise<object>} 执行结果
 */
async function devFlow(task, scope) {
  // ============================================================
  // 步骤 1: 架构设计
  // ============================================================
  console.log("[DevFlow] 开始架构设计...");

  // 1.1 分析需求，提取关键信息
  const analysis = await llmcall(
    `分析以下任务，提取关键信息：
任务：{description}
验收标准：{acceptance}

请输出：
1. 端点类型（App端/Admin端）
2. 需要创建的模块列表
3. 数据表结构（如涉及数据库）
4. 关键接口列表

任务描述：
${task.description}

验收标准：
${(task.acceptance || []).map((a, i) => `${i + 1}. ${a}`).join('\n')}`,
    {},
    { temperature: 0.3 }
  );
  scope.set('analysis', analysis);

  // 1.2 记录设计决策
  scope.addDecision('analysis', '架构分析完成', analysis);

  // 1.3 检查是否需要架构审查（新增接口 >= 3 或涉及数据库变更）
  const needsArchReview = analysis.includes('新增接口') && analysis.includes('3');
  if (needsArchReview) {
    console.log("[DevFlow] 检测到需要架构审查...");
    // 注意：这里只是记录，实际审查由 runtime 处理
    scope.set('needsArchitectureReview', true);
  }

  // ============================================================
  // 步骤 2: 生成代码 - Model 层
  // ============================================================
  console.log("[DevFlow] 生成 Model 层...");

  const modelResult = await agentcall(
    scope,
    `根据以下分析结果，生成 Model 文件：

分析：{analysis}

要求：
1. 遵循 ThinkPHP 8 规范
2. 放在 app/Models/ 目录
3. 包含 fillable, casts, relations 等
4. 输出格式：// file: app/Models/XXX.php\n\n\`\`\`php\n{code}\n\`\`\`

${task.description}`,
    { temperature: 0.3 }
  );

  // 提取并写入文件
  for (const file of modelResult.generatedFiles || []) {
    if (file.path && file.code) {
      await writeFile(file.path, file.code);
      scope.addArtifact(file.path, { type: 'model', layer: 'Model' });
    }
  }

  // 验证 Model 生成成功
  metacall(
    scope.artifacts.some(a => a.path.includes('Models/')),
    "Model 层生成失败"
  );

  // ============================================================
  // 步骤 3: 生成代码 - Repository 层
  // ============================================================
  console.log("[DevFlow] 生成 Repository 层...");

  const repoResult = await agentcall(
    scope,
    `根据以下分析结果，生成 Repository 文件：

分析：{analysis}
Model：{modelName}

要求：
1. 遵循 ThinkPHP 8 规范
2. 放在 app/repositories/ 目录
3. 封装数据访问逻辑
4. 输出格式：// file: app/repositories/XXXRepository.php\n\n\`\`\`php\n{code}\n\`\`\``,
    { temperature: 0.3 }
  );

  for (const file of repoResult.generatedFiles || []) {
    if (file.path && file.code) {
      await writeFile(file.path, file.code);
      scope.addArtifact(file.path, { type: 'repository', layer: 'Repository' });
    }
  }

  metacall(
    scope.artifacts.some(a => a.path.includes('repositories/')),
    "Repository 层生成失败"
  );

  // ============================================================
  // 步骤 4: 生成代码 - Service 层
  // ============================================================
  console.log("[DevFlow] 生成 Service 层...");

  const serviceResult = await agentcall(
    scope,
    `根据以下分析结果，生成 Service 文件：

分析：{analysis}
Repository：{repoName}

要求：
1. 遵循 ThinkPHP 8 规范
2. 放在 app/service/ 目录
3. 封装业务逻辑
4. 输出格式：// file: app/service/XXXService.php\n\n\`\`\`php\n{code}\n\`\`\``,
    { temperature: 0.3 }
  );

  for (const file of serviceResult.generatedFiles || []) {
    if (file.path && file.code) {
      await writeFile(file.path, file.code);
      scope.addArtifact(file.path, { type: 'service', layer: 'Service' });
    }
  }

  metacall(
    scope.artifacts.some(a => a.path.includes('service/')),
    "Service 层生成失败"
  );

  // ============================================================
  // 步骤 5: 生成代码 - Controller 层
  // ============================================================
  console.log("[DevFlow] 生成 Controller 层...");

  const controllerResult = await agentcall(
    scope,
    `根据以下分析结果，生成 Controller 文件：

分析：{analysis}
Service：{serviceName}

要求：
1. 遵循 ThinkPHP 8 规范
2. 放在 app/controller/Api/Admin/ 或 app/controller/Api/App/ 目录
3. 使用 Validate 验证器
4. 调用 Service 层，Controller 保持精简
5. 输出格式：// file: app/controller/Api/XXX.php\n\n\`\`\`php\n{code}\n\`\`\``,
    { temperature: 0.3 }
  );

  for (const file of controllerResult.generatedFiles || []) {
    if (file.path && file.code) {
      await writeFile(file.path, file.code);
      scope.addArtifact(file.path, { type: 'controller', layer: 'Controller' });
    }
  }

  metacall(
    scope.artifacts.some(a => a.path.includes('controller/')),
    "Controller 层生成失败"
  );

  // ============================================================
  // 步骤 6: 生成代码 - Validate 层
  // ============================================================
  console.log("[DevFlow] 生成 Validate 层...");

  const validateResult = await agentcall(
    scope,
    `根据以下分析结果，生成 Validate 验证器文件：

分析：{analysis}

要求：
1. 遵循 ThinkPHP 8 规范
2. 放在 app/validate/ 目录
3. 包含所有必要验证规则
4. 支持场景验证（create, update）
5. 输出格式：// file: app/validate/XXXValidate.php\n\n\`\`\`php\n{code}\n\`\`\``,
    { temperature: 0.3 }
  );

  for (const file of validateResult.generatedFiles || []) {
    if (file.path && file.code) {
      await writeFile(file.path, file.code);
      scope.addArtifact(file.path, { type: 'validate', layer: 'Validate' });
    }
  }

  // ============================================================
  // 步骤 7: 定义路由
  // ============================================================
  console.log("[DevFlow] 定义路由...");

  const routeResult = await llmcall(
    `根据以下分析结果，生成路由定义：

分析：{analysis}

要求：
1. 在 route/app.php 中添加路由
2. 遵循路由顺序规范（Admin 端在前，App 端在后）
3. 使用 Route::{method}('uri', 'Controller/method') 格式

输出格式：只需要输出需要在 route/app.php 中添加的代码，不需要完整文件`,
    {},
    { temperature: 0.3 }
  );

  // 读取现有路由文件，追加新路由
  const routeFile = 'route/app.php';
  const existingRoutes = await readFile(routeFile);
  const newRoutes = routeResult;
  const updatedRoutes = existingRoutes + '\n' + newRoutes;

  await writeFile(routeFile, updatedRoutes);
  scope.addArtifact(routeFile, { type: 'route', layer: 'Route' });

  // ============================================================
  // 步骤 8: 生成测试文件
  // ============================================================
  console.log("[DevFlow] 生成测试文件...");

  const testResult = await agentcall(
    scope,
    `根据以下信息，生成单元测试文件：

任务：{description}
产出文件：{artifacts}

要求：
1. 使用 PHPUnit
2. 放在 tests/Unit/ 或 tests/Feature/ 目录
3. 测试基本功能和边界情况
4. 输出格式：// file: tests/XXXTest.php\n\n\`\`\`php\n{code}\n\`\`\``,
    {
      temperature: 0.3
    }
  );

  for (const file of testResult.generatedFiles || []) {
    if (file.path && file.code) {
      await writeFile(file.path, file.code);
      scope.addArtifact(file.path, { type: 'test' });
    }
  }

  // ============================================================
  // 步骤 9: 最终验证
  // ============================================================
  console.log("[DevFlow] 执行最终验证...");

  // 验证所有核心文件都已生成
  const hasModel = scope.artifacts.some(a => a.type === 'model');
  const hasService = scope.artifacts.some(a => a.type === 'service');
  const hasController = scope.artifacts.some(a => a.type === 'controller');

  metacall(hasModel, "缺少 Model 层");
  metacall(hasService, "缺少 Service 层");
  metacall(hasController, "缺少 Controller 层");

  // ============================================================
  // 完成
  // ============================================================
  console.log("[DevFlow] 开发流程完成！");

  return scope.exit();
}

// 导出流程函数
export { devFlow };
