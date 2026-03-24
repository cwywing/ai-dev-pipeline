#!/usr/bin/env python3
"""
Agent CPU 集成测试

验证 Agent CPU Runtime 是否能正常工作。
"""

import sys
import json
import subprocess
from pathlib import Path


def run_command(cmd, cwd=None, timeout=60):
    """运行命令"""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=timeout,
            cwd=cwd
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, '', '超时'
    except Exception as e:
        return -1, '', str(e)


def test_node_installed():
    """测试 Node.js 是否安装"""
    print("测试 1: 检查 Node.js 安装...")

    returncode, stdout, stderr = run_command(['node', '--version'])
    if returncode == 0:
        print(f"  ✓ Node.js 已安装: {stdout.strip()}")
        return True
    else:
        print(f"  ✗ Node.js 未安装或配置不正确")
        return False


def test_npm_install():
    """测试 npm 依赖安装"""
    print("\n测试 2: 检查 npm 依赖...")

    agent_cpu_dir = Path(__file__).parent.parent / 'agent-cpu'
    node_modules = agent_cpu_dir / 'node_modules'

    if node_modules.exists():
        print(f"  ✓ 依赖已安装")
        return True

    print(f"  → 安装依赖中...")
    returncode, stdout, stderr = run_command(
        ['npm', 'install'],
        cwd=str(agent_cpu_dir),
        timeout=120
    )

    if returncode == 0:
        print(f"  ✓ 依赖安装成功")
        return True
    else:
        print(f"  ✗ 依赖安装失败: {stderr}")
        return False


def test_cli_help():
    """测试 CLI 帮助信息"""
    print("\n测试 3: 测试 CLI 帮助信息...")

    agent_cpu_dir = Path(__file__).parent.parent / 'agent-cpu'
    returncode, stdout, stderr = run_command(
        ['node', 'cli.js', 'help'],
        cwd=str(agent_cpu_dir)
    )

    if returncode == 0 and 'Agent CPU CLI' in stdout:
        print(f"  ✓ CLI 帮助信息正常")
        return True
    else:
        print(f"  ✗ CLI 帮助信息异常")
        return False


def test_basic_flow():
    """测试基础流程执行"""
    print("\n测试 4: 测试基础流程执行...")

    agent_cpu_dir = Path(__file__).parent.parent / 'agent-cpu'
    returncode, stdout, stderr = run_command(
        ['node', 'cli.js', 'run', '--code', 'console.log("hello from agent-cpu");', '--task-id', 'test_001'],
        cwd=str(agent_cpu_dir),
        timeout=120
    )

    if returncode == 0:
        print(f"  ✓ 基础流程执行成功")
        print(f"    输出: {stdout.strip()}")
        return True
    else:
        print(f"  ✗ 基础流程执行失败")
        print(f"    错误: {stderr}")
        return False


def test_llmcall():
    """测试 llmcall 内置函数"""
    print("\n测试 5: 测试 llmcall 内置函数...")

    agent_cpu_dir = Path(__file__).parent.parent / 'agent-cpu'
    code = '''
(async () => {
  const { llmcall } = await import('./builtins/llmcall.js');
  try {
    const result = await llmcall("返回一个简单的词: world", {});
    console.log("llmcall result:", result);
  } catch (e) {
    console.log("llmcall error (expected in test):", e.message);
  }
})();
'''

    returncode, stdout, stderr = run_command(
        ['node', '-e', code],
        cwd=str(agent_cpu_dir),
        timeout=60
    )

    # llmcall 可能因为没有配置 API 而失败，这是预期的
    print(f"  → llmcall 测试完成 (可能因无 API 配置而跳过)")
    print(f"    输出: {stdout[:200] if stdout else '(无)'}...")
    return True  # 不作为失败条件


def test_scope():
    """测试作用域管理"""
    print("\n测试 6: 测试作用域管理...")

    agent_cpu_dir = Path(__file__).parent.parent / 'agent-cpu'
    code = '''
import { Scope, ScopeManager } from './scope.js';

const manager = new ScopeManager();
const root = manager.getRoot();

root.set('test', 'value');
console.log('Scope test passed:', root.get('test') === 'value');
'''

    returncode, stdout, stderr = run_command(
        ['node', '--input-type=module', '-e', code],
        cwd=str(agent_cpu_dir)
    )

    if returncode == 0 and 'Scope test passed: true' in stdout:
        print(f"  ✓ 作用域管理正常")
        return True
    else:
        print(f"  ✗ 作用域管理异常")
        print(f"    输出: {stdout}")
        print(f"    错误: {stderr}")
        return False


def test_metacall():
    """测试 metacall 断言"""
    print("\n测试 7: 测试 metacall 断言...")

    agent_cpu_dir = Path(__file__).parent.parent / 'agent-cpu'
    code = '''
import { metacall } from './builtins/metacall.js';

try {
  metacall(true, 'Should pass');
  console.log('metacall pass: true');
  metacall(false, 'Should fail');
} catch (e) {
  console.log('metacall fail caught:', e.message === 'Should fail');
}
'''

    returncode, stdout, stderr = run_command(
        ['node', '--input-type=module', '-e', code],
        cwd=str(agent_cpu_dir)
    )

    if returncode == 0 and 'metacall pass: true' in stdout and 'metacall fail caught: true' in stdout:
        print(f"  ✓ metacall 断言正常")
        return True
    else:
        print(f"  ✗ metacall 断言异常")
        print(f"    输出: {stdout}")
        return False


def test_knowledge_base():
    """测试知识库"""
    print("\n测试 8: 测试知识库...")

    agent_cpu_dir = Path(__file__).parent.parent / 'agent-cpu'
    returncode, stdout, stderr = run_command(
        ['node', 'cli.js', 'kb', '--stats'],
        cwd=str(agent_cpu_dir)
    )

    if returncode == 0:
        print(f"  ✓ 知识库 CLI 正常")
        print(f"    {stdout.strip()}")
        return True
    else:
        print(f"  ✗ 知识库 CLI 异常")
        print(f"    错误: {stderr}")
        return False


def main():
    print("=" * 60)
    print("Agent CPU Runtime 集成测试")
    print("=" * 60)

    results = []

    # 基础检查
    if not test_node_installed():
        print("\n✗ Node.js 未安装，无法继续测试")
        return 1

    if not test_npm_install():
        print("\n✗ npm 依赖安装失败，无法继续测试")
        return 1

    # 功能测试
    results.append(("CLI 帮助", test_cli_help()))
    results.append(("作用域管理", test_scope()))
    results.append(("metacall 断言", test_metacall()))
    results.append(("知识库", test_knowledge_base()))

    # 可选测试（可能因环境而失败）
    test_llmcall()  # 不计入结果
    test_basic_flow()  # 不计入结果

    # 汇总
    print("\n" + "=" * 60)
    print("测试结果汇总")
    print("=" * 60)

    passed = sum(1 for _, r in results if r)
    total = len(results)

    for name, result in results:
        status = "✓ 通过" if result else "✗ 失败"
        print(f"  {status}: {name}")

    print(f"\n通过: {passed}/{total}")

    if passed == total:
        print("\n✓ 所有测试通过！")
        return 0
    else:
        print(f"\n✗ 有 {total - passed} 个测试失败")
        return 1


if __name__ == '__main__':
    sys.exit(main())
