#!/usr/bin/env python3
"""
Agent CPU 集成脚本

提供 Python 端调用 Node.js Agent CPU Runtime 的接口。
用于与现有 harness-tools.py 系统集成。

使用示例：
    python3 .harness/scripts/run-agent-cpu.py --execute --task-id TASK_001 --flow-type dev
"""

import sys
import io
import argparse
import json
import subprocess
from pathlib import Path
from datetime import datetime

# 强制终端输出使用 UTF-8 编码，防止 Windows 下打印 Emoji 崩溃
if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

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


def get_project_root():
    """获取项目根目录"""
    script_dir = Path(__file__).parent
    return script_dir.parent.parent


def run_node_command(command, timeout=300, env=None):
    """
    运行 Node.js 命令

    Args:
        command: 命令列表
        timeout: 超时时间（秒）
        env: 环境变量字典

    Returns:
        tuple: (returncode, stdout, stderr)
    """
    try:
        import os
        # 合并环境变量
        run_env = {**os.environ, **(env or {})}

        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=timeout,
            cwd=get_project_root(),
            env=run_env
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
    # 如果没有提供 task_data，自动从任务文件加载
    if not task_data:
        # 尝试从 pending 目录加载
        harness_dir = Path(__file__).parent.parent.resolve()
        task_file = harness_dir / 'tasks' / 'pending' / f'{task_id}.json'
        if task_file.exists():
            try:
                with open(task_file, 'r', encoding='utf-8') as f:
                    loaded_data = json.load(f)
                    # 提取有用字段
                    task_data = {
                        'description': loaded_data.get('d', ''),
                        'acceptance': loaded_data.get('a', []),
                        'artifacts': loaded_data.get('artifacts', []),
                        'metadata': {
                            'category': loaded_data.get('c', ''),
                            'priority': loaded_data.get('pr', ''),
                        }
                    }
            except Exception:
                pass

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

    # 设置环境变量
    run_env = {
        'TASK_DATA': json.dumps(task_data, ensure_ascii=False)
    }

    # 将脚本写入临时文件以避免 shell 转义问题
    import tempfile
    import os as _os
    flow_code = get_flow_code(flow_type)
    with tempfile.NamedTemporaryFile(mode='w', suffix='.js', delete=False, encoding='utf-8') as f:
        f.write(flow_code)
        script_path = f.name

    try:
        returncode, stdout, stderr = run_node_command([
            'node',
            str(get_agent_cpu_path() / 'cli.js'),
            'run',
            '--script',
            script_path,
            '--task-id',
            task_id,
            '--category',
            category
        ], timeout=600, env=run_env)
    finally:
        # 清理临时文件
        try:
            _os.unlink(script_path)
        except Exception:
            pass

    if returncode != 0:
        error(f'Agent CPU 执行失败: {stderr}', file=sys.stderr)
        return {
            'success': False,
            'taskId': task_id,
            'error': stderr,
            'stdout': stdout
        }

    # 解析输出并打印完整日志
    try:
        # 打印 Node.js 的所有输出（包含 TestFlow 的详细日志）
        if stdout:
            print(stdout)

        return {
            'success': True,
            'taskId': task_id,
            'flowType': flow_type,
            'output': stdout
        }
    except Exception as e:
        return {
            'success': True,
            'taskId': task_id,
            'output': stdout
        }


def get_flow_code(flow_type):
    """获取流程代码（裸代码体，由 runtime.js 包装为 async function）"""
    if flow_type == 'dev':
        return r'''
console.log("[DevFlow] 开始开发流程...");
const taskId = context.taskId || 'unknown';
const taskDesc = context.task?.description || '未提供';

// 构建 Prompt
const prompt = `你是 Dev Agent，按照任务描述编写代码。

任务描述:
${taskDesc}

请直接输出代码，不要多余解释。`;

console.log("[DevFlow] 调用 LLM...");

try {
  // llmcall 直接返回 content 字符串
  const llmOutput = await builtins.llmcall(prompt, { model: 'sonnet' }) || '';
  console.log("[DevFlow] LLM 返回长度:", llmOutput.length);

  // metacall 断言：确保 LLM 返回了有效内容
  builtins.metacall(llmOutput.length > 0, "LLM 返回为空代码", "检查 prompt 是否正确传递");

  // 提取代码
  let code = llmOutput;
  const match = llmOutput.match(/```php\n?([\s\S]*?)```/i);
  if (match) {
    code = match[1].trim();
  }

  console.log("[DevFlow] 提取到代码，长度: " + code.length);

  // 保存到工作区（使用项目根相对路径）
  const workspaceDir = '.harness/agent-cpu/workspace/' + taskId;
  await builtins.mkdir(workspaceDir, { recursive: true });
  const safeId = taskId.replace(/[^a-zA-Z0-9_]/g, '_');
  const outputFile = workspaceDir + '/' + safeId + '.php';
  await builtins.writeFile(outputFile, code);
  console.log("[DevFlow] 代码已写入:", outputFile);

  // 架构审查触发器：检测高风险操作
  const highRiskPatterns = [
    { pattern: /Route::/, label: '路由/接口变更 (Route::)' },
    { pattern: /Schema::(create|table)\b/, label: '数据库表结构变更 (Schema::create/table)' },
    { pattern: /DROP\s+TABLE/i, label: '数据库表删除 (DROP TABLE)' },
    { pattern: /->raw\s*\(/, label: '原生 SQL 注入 (->raw)' },
    { pattern: /config\s*\(\s*['"]\w+\.php['"]\s*\)/, label: '配置文件写入/修改' }
  ];
  const riskDetected = highRiskPatterns
    .filter(r => r.pattern.test(code))
    .map(r => r.label);

  let requireReview = false;
  if (riskDetected.length > 0) {
    requireReview = true;
    console.log("\n⚠️  [Human Review Required] 触发架构审查：检测到高风险操作，流水线将挂起等待人工确认。");
    riskDetected.forEach(r => console.log("    - " + r));
  }

  return { success: true, code, artifacts: [{ path: outputFile, type: 'service' }], requireReview };
} catch (e) {
  console.error("[DevFlow] LLM 调用失败:", e.message);
  return { success: false, error: e.message };
}
'''
    elif flow_type == 'test':
        return r'''
const artifacts = context.task?.artifacts || [];

console.log("[TestFlow] 开始测试流程...");
console.log("[TestFlow] 找到 " + artifacts.length + " 个文件");

let issueCount = 0;

// 检查每个文件
for (const artifact of artifacts) {
  if (artifact.path && artifact.path.endsWith(".php")) {
    console.log("[TestFlow] 检查文件: " + artifact.path);
    try {
      const content = await builtins.readFile(artifact.path);
      console.log("[TestFlow] 文件内容长度: " + content.length);

      // 检查硬编码密钥/Token (Hard Rule)
      if (content.match(/sk_[a-z]+_[a-z0-9]+/i) ||
          content.match(/TOKEN\s*=\s*['"][^'"]+['"]/i) ||
          content.match(/SECRET\s*=\s*['"][^'"]+['"]/i) ||
          content.match(/KEY\s*=\s*['"][^'"]+['"]/i)) {
        console.log("发现硬编码密钥/Token!");
        issueCount++;
      }

      // 检查 SQL 拼接 (Hard Rule)
      if (content.includes("DB::raw(") ||
          content.includes("DB::statement(") && content.match(/['\"].*WHERE.*['\"]\s*\./) ||
          content.match(/UPDATE\s+\w+\s+SET.*['\"]\s*\./i) ||
          content.match(/SELECT\s+.*FROM.*['\"]\s*\./i)) {
        console.log("发现 SQL 拼接!");
        issueCount++;
      }

      // 检查 eval() 使用 (Hard Rule)
      if (content.includes("eval(")) {
        console.log("发现 eval() 使用!");
        issueCount++;
      }
    } catch (e) {
      console.log("[TestFlow] 读取文件失败: " + e.message);
    }
  }
}

console.log("[TestFlow] 检查完成，发现 " + issueCount + " 个问题");

return { success: true, issueCount };
'''
    elif flow_type == 'review':
        return r'''
console.log("[ReviewFlow] 开始审查流程...");
const artifacts = context.task?.artifacts || [];

// 简单的质量评分
let score = 10;
if (artifacts.length === 0) {
  score = 5;
}

console.log("[ReviewFlow] 审查完成，质量评分: " + score + "/10");

return { success: true, qualityScore: score };
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
