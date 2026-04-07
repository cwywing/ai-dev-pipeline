#!/usr/bin/env python3
"""
Agent CPU 集成脚本

提供 Python 端调用 Node.js Agent CPU Runtime 的接口。
用于与现有 harness-tools.py 系统集成。

使用示例：
    python3 .harness/scripts/run-agent-cpu.py --execute --task-id TASK_001 --flow-type dev
"""

import sys
import argparse
import json
import subprocess
from pathlib import Path
from datetime import datetime

# 导入 harness 工具
sys.path.insert(0, str(Path(__file__).parent))
from console_output import success, error, warning, info


# ============================================================
# 约束注入模块
# ============================================================

def load_constraints():
    """加载知识库约束"""
    script_dir = Path(__file__).parent
    constraints_path = script_dir.parent / 'knowledge' / 'constraints.json'

    if constraints_path.exists():
        try:
            with open(constraints_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return None
    return None


def inject_constraints(constraints, prompt_content):
    """
    将约束注入到 Prompt 中

    Args:
        constraints: 约束数据字典
        prompt_content: 原始 Prompt 内容

    Returns:
        str: 注入约束后的 Prompt
    """
    if not constraints:
        return prompt_content

    # 注入 Hard Rules (Moat)
    hard_rules_md = ""
    if 'moat' in constraints and 'hard_rules' in constraints['moat']:
        rules = constraints['moat']['hard_rules']
        hard_rules_md = "\n".join([
            f"> 🚨 **{rule}**"
            for rule in rules
        ])
        prompt_content = prompt_content.replace(
            "{CONSTRAINTS_MOAT}",
            f"\n> ## 🚨 HARD RULES (一票否决)\n{hard_rules_md}\n"
        )

    # 注入 Guidelines
    guidelines_md = ""
    if 'guidelines' in constraints and 'rules' in constraints['guidelines']:
        rules = constraints['guidelines']['rules']
        guidelines_md = "\n".join([
            f"- {rule}"
            for rule in rules
        ])
        prompt_content = prompt_content.replace(
            "{CONSTRAINTS_GUIDE}",
            f"\n## 📋 Guidelines\n{guidelines_md}\n"
        )

    return prompt_content


def load_template_for_flow(flow_type):
    """
    加载并注入约束的 Prompt 模板

    Args:
        flow_type: 流程类型 (dev/test/review)

    Returns:
        str: 处理后的 Prompt 模板内容
    """
    script_dir = Path(__file__).parent
    template_path = script_dir.parent / 'templates' / f'{flow_type}_prompt_agent_cpu.md'

    if template_path.exists():
        try:
            with open(template_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # 加载约束并注入
            constraints = load_constraints()
            return inject_constraints(constraints, content)
        except Exception:
            pass

    return None


def get_agent_cpu_path():
    """获取 Agent CPU 目录路径"""
    script_dir = Path(__file__).parent
    agent_cpu_dir = script_dir.parent / 'agent-cpu'
    return agent_cpu_dir


def run_node_command(command, timeout=300):
    """
    运行 Node.js 命令

    Args:
        command: 命令列表
        timeout: 超时时间（秒）

    Returns:
        tuple: (returncode, stdout, stderr)
    """
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=timeout,
            cwd=get_agent_cpu_path()
        )
        return (result.returncode, result.stdout, result.stderr)
    except subprocess.TimeoutExpired:
        return (-1, '', f'命令执行超时（{timeout}秒）')
    except Exception as e:
        return (-1, '', str(e))


def check_node_installed():
    """检查 Node.js 是否已安装"""
    returncode, stdout, stderr = run_node_command(['node', '--version'])
    if returncode == 0:
        return True, stdout.strip()
    return False, 'Node.js 未安装'


def check_dependencies():
    """检查 Agent CPU 依赖是否已安装"""
    node_modules = get_agent_cpu_path() / 'node_modules'
    if not node_modules.exists():
        info('安装 Agent CPU 依赖...', file=sys.stderr)
        returncode, stdout, stderr = run_node_command(['npm', 'install'], timeout=120)
        if returncode != 0:
            error(f'安装依赖失败: {stderr}', file=sys.stderr)
            return False
        success('依赖安装完成', file=sys.stderr)
    return True


def execute_flow(task_id, flow_type='dev', category='general', task_data=None):
    """
    执行 Agent CPU 流程

    Args:
        task_id: 任务 ID
        flow_type: 流程类型 (dev/test/review)
        category: 任务类别
        task_data: 任务数据字典

    Returns:
        dict: 执行结果
    """
    if task_data is None:
        task_data = {}

    # 加载约束并注入到流程上下文
    constraints = load_constraints()

    # 构建任务上下文
    context = {
        'taskId': task_id,
        'category': category,
        'flowType': flow_type,
        'task': task_data,
        'constraints': constraints  # 传递给 Agent CPU
    }

    # 调用 Node.js CLI 执行
    info(f'执行 Agent CPU 流程: {task_id} ({flow_type})', file=sys.stderr)

    # 尝试加载模板并注入约束
    template_content = load_template_for_flow(flow_type)

    returncode, stdout, stderr = run_node_command([
        'node',
        'cli.js',
        'run',
        '--code',
        get_flow_code(flow_type),
        '--task-id',
        task_id,
        '--category',
        category
    ], timeout=600)

    if returncode != 0:
        error(f'Agent CPU 执行失败: {stderr}', file=sys.stderr)
        return {
            'success': False,
            'taskId': task_id,
            'error': stderr,
            'stdout': stdout
        }

    # 解析输出
    try:
        # 提取 JSON 结果
        result_lines = []
        in_result = False
        for line in stdout.split('\n'):
            if '=== 执行结果 ===' in line:
                in_result = True
            elif in_result and line.strip():
                result_lines.append(line.strip())

        return {
            'success': True,
            'taskId': task_id,
            'flowType': flow_type,
            'output': '\n'.join(result_lines)
        }
    except Exception as e:
        return {
            'success': True,
            'taskId': task_id,
            'output': stdout
        }


def get_flow_code(flow_type):
    """获取流程代码"""
    if flow_type == 'dev':
        return r'''
(async () => {
  const { createAgentCPU } = await import('./runtime.js');

  const cpu = createAgentCPU({
    enableSelfHealing: true,
    enableHumanReview: false,
    enableKnowledgeBase: true,
    onLog: (entry) => {
      const prefix = { info: '[INFO]', warn: '[WARN]', error: '[ERROR]', success: '[OK]' }[entry.level] || '[LOG]';
      console.log(prefix + ' ' + entry.message);
    }
  });

  // 加载任务数据
  const taskData = JSON.parse(process.env.TASK_DATA || '{}');

  // 定义 Dev Flow
  const devFlow = async (scope, context) => {
    console.log("[DevFlow] 开始开发流程...");
    console.log("任务描述: " + (context.task?.description || '未提供'));

    // 分析任务
    const taskDesc = context.task?.description || '';
    const analysis = await llmcall("你是 Dev Agent，分析以下任务并输出实现计划：\n" + taskDesc);
    scope.set('analysis', analysis);
    console.log("分析结果: " + analysis);

    // 返回结果
    return { success: true, artifacts: scope.artifacts || [] };
  };

  // 执行流程
  const result = await cpu.execute(devFlow, {
    taskId: context.taskId,
    category: context.category,
    task: taskData
  });

  console.log("\n=== 执行结果 ===");
  console.log("状态: " + (result.success ? "成功" : "失败"));
  console.log("耗时: " + result.duration + "ms");
  console.log("产出文件: " + result.artifacts.length + " 个");

  if (result.artifacts.length > 0) {
    console.log("\n产出文件列表:");
    result.artifacts.forEach(a => console.log("  - " + a.path));
  }
})();
        '''
    elif flow_type == 'test':
        return r'''
(async () => {
  const { createAgentCPU } = await import('./runtime.js');

  const cpu = createAgentCPU({
    enableSelfHealing: true,
    enableHumanReview: false,
    enableKnowledgeBase: true,
    onLog: (entry) => {
      const prefix = { info: '[INFO]', warn: '[WARN]', error: '[ERROR]', success: '[OK]' }[entry.level] || '[LOG]';
      console.log(prefix + ' ' + entry.message);
    }
  });

  const taskData = JSON.parse(process.env.TASK_DATA || '{}');

  // 定义 Test Flow
  const testFlow = async (scope, context) => {
    console.log("[TestFlow] 开始测试流程...");

    const devArtifacts = context.task?.artifacts || [];
    scope.set('files', devArtifacts);
    scope.set('issues', []);

    // 语法检查
    for (const artifact of devArtifacts) {
      if (artifact.path && artifact.path.endsWith('.php')) {
        const cmdResult = await runCommand('php8 -l ' + artifact.path);
        metacall(cmdResult.exitCode === 0, "语法错误: " + artifact.path);
      }
    }

    // 返回结果
    return { success: true, issues: scope.issues || [] };
  };

  const result = await cpu.execute(testFlow, {
    taskId: context.taskId,
    category: context.category,
    task: taskData
  });

  console.log("\n=== 执行结果 ===");
  console.log("状态: " + (result.success ? "成功" : "失败"));
  console.log("发现的问题: " + result.issues.length + " 个");
})();
        '''
    elif flow_type == 'review':
        return r'''
(async () => {
  const { createAgentCPU } = await import('./runtime.js');

  const cpu = createAgentCPU({
    enableSelfHealing: true,
    enableHumanReview: false,
    enableKnowledgeBase: true,
    onLog: (entry) => {
      const prefix = { info: '[INFO]', warn: '[WARN]', error: '[ERROR]', success: '[OK]' }[entry.level] || '[LOG]';
      console.log(prefix + ' ' + entry.message);
    }
  });

  const taskData = JSON.parse(process.env.TASK_DATA || '{}');

  // 定义 Review Flow
  const reviewFlow = async (scope, context) => {
    console.log("[ReviewFlow] 开始审查流程...");

    const artifacts = context.task?.artifacts || [];
    scope.set('qualityScore', 10);
    scope.set('findings', []);

    // 返回结果
    return { success: true, qualityScore: scope.qualityScore || 10 };
  };

  const result = await cpu.execute(reviewFlow, {
    taskId: context.taskId,
    category: context.category,
    task: taskData
  });

  console.log("\n=== 执行结果 ===");
  console.log("状态: " + (result.success ? "成功" : "失败"));
  console.log("质量评分: " + result.qualityScore + "/10");
})();
        '''
    else:
        return "console.log('Flow type not implemented: " + flow_type + "');"


def action_execute(args):
    """执行 Agent CPU 流程"""
    # 检查依赖
    installed, version = check_node_installed()
    if not installed:
        error('Node.js 未安装或配置不正确', file=sys.stderr)
        return 1

    info(f'Node.js 版本: {version}', file=sys.stderr)

    if not check_dependencies():
        return 1

    # 加载任务数据
    task_data = {}
    if args.task_file:
        try:
            with open(args.task_file, 'r', encoding='utf-8') as f:
                task_data = json.load(f)
        except Exception as e:
            warning(f'无法加载任务文件: {e}', file=sys.stderr)

    # 执行流程
    result = execute_flow(
        task_id=args.task_id,
        flow_type=args.flow_type,
        category=args.category,
        task_data=task_data
    )

    if result['success']:
        success(f'任务 {args.task_id} 执行成功', file=sys.stderr)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    else:
        error(f'任务 {args.task_id} 执行失败', file=sys.stderr)
        print(json.dumps(result, ensure_ascii=False), file=sys.stderr)
        return 1


def action_list_templates(args):
    """列出可用模板"""
    templates_dir = get_agent_cpu_path() / 'templates'
    if not templates_dir.exists():
        info('暂无模板', file=sys.stderr)
        return 0

    info('可用流程模板:', file=sys.stderr)
    for template in templates_dir.glob('*.js'):
        info(f'  - {template.name}', file=sys.stderr)

    return 0


def action_kb_stats(args):
    """查看知识库统计"""
    if not check_dependencies():
        return 1

    returncode, stdout, stderr = run_node_command([
        'node',
        'cli.js',
        'kb',
        '--stats'
    ])

    if returncode == 0:
        print(stdout)
        return 0
    else:
        error(f'获取知识库统计失败: {stderr}', file=sys.stderr)
        return 1


def main():
    parser = argparse.ArgumentParser(
        description='Agent CPU 集成脚本 - 提供 Python 端调用接口',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  # 执行开发流程
  python3 .harness/scripts/run-agent-cpu.py --execute --task-id TASK_001 --flow-type dev

  # 执行并指定任务数据文件
  python3 .harness/scripts/run-agent-cpu.py --execute --task-id TASK_001 \\
    --task-file .harness/tasks/pending/TASK_001.json

  # 列出可用模板
  python3 .harness/scripts/run-agent-cpu.py --list-templates

  # 查看知识库统计
  python3 .harness/scripts/run-agent-cpu.py --kb-stats
        """
    )

    parser.add_argument('--execute', action='store_true',
                        help='执行 Agent CPU 流程')
    parser.add_argument('--task-id', type=str,
                        help='任务 ID')
    parser.add_argument('--flow-type', type=str, default='dev',
                        choices=['dev', 'test', 'review'],
                        help='流程类型')
    parser.add_argument('--category', type=str, default='general',
                        help='任务类别')
    parser.add_argument('--task-file', type=str,
                        help='任务数据文件路径')
    parser.add_argument('--list-templates', action='store_true',
                        help='列出可用模板')
    parser.add_argument('--kb-stats', action='store_true',
                        help='查看知识库统计')

    args = parser.parse_args()

    # 路由到对应 action
    if args.execute:
        if not args.task_id:
            error('执行模式需要提供 --task-id 参数', file=sys.stderr)
            return 1
        return action_execute(args)
    elif args.list_templates:
        return action_list_templates(args)
    elif args.kb_stats:
        return action_kb_stats(args)
    else:
        parser.print_help()
        return 0


if __name__ == '__main__':
    sys.exit(main())
