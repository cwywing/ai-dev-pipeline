#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Prompt 管道模式测试脚本

用于测试通过 subprocess 管道发送大 prompt 给 Claude CLI 的场景。
模拟 run-automation-stages.py 的 prompt 组装过程，验证管道模式是否正常工作。

用法:
    python .harness/scripts/test_pipeline_prompt.py
    python .harness/scripts/test_pipeline_prompt.py --short    # 简短测试
    python .harness/scripts/test_pipeline_prompt.py --verbose  # 详细输出
"""

import argparse
import subprocess
import sys
import time
from pathlib import Path
from datetime import datetime

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent.parent.resolve()
HARNESS_DIR = PROJECT_ROOT / ".harness"

# 颜色输出
class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'


def print_header(msg):
    print(f"{Colors.HEADER}{msg}{Colors.ENDC}")


def print_success(msg):
    print(f"{Colors.OKGREEN}{msg}{Colors.ENDC}")


def print_error(msg):
    print(f"{Colors.FAIL}{msg}{Colors.ENDC}")


def print_warning(msg):
    print(f"{Colors.WARNING}{msg}{Colors.ENDC}")


def build_validation_prompt(short: bool = False) -> str:
    """
    构建 Validation 阶段的完整 prompt
    模拟 run-automation-stages.py 的逻辑
    """
    prompt_parts = []

    # 1. Header
    prompt_parts.append("# " + "=" * 76)
    prompt_parts.append("#                    SYSTEM INSTRUCTIONS (SOP)")
    prompt_parts.append("#              Laravel 开发规范 - 必须严格遵循")
    prompt_parts.append("# " + "=" * 76)
    prompt_parts.append("")

    # 2. CLAUDE.md 内容（修复后：嵌入实际内容）
    claude_md = PROJECT_ROOT / "CLAUDE.md"
    if claude_md.exists():
        claude_content = claude_md.read_text(encoding='utf-8')
        prompt_parts.append(claude_content)
        prompt_parts.append("")
        prompt_parts.append("⚠️ **CRITICAL: You MUST strictly follow the SOP / coding standards provided above.**")
    else:
        prompt_parts.append("[WARNING] CLAUDE.md not found")

    # 3. 进度记录
    prompt_parts.append("")
    prompt_parts.append("# " + "=" * 76)
    prompt_parts.append("#                    RECENT PROGRESS")
    prompt_parts.append("#                    最近 30 行进度记录")
    prompt_parts.append("# " + "=" * 76)
    progress_file = HARNESS_DIR / "logs" / "progress.md"
    if progress_file.exists():
        lines = progress_file.read_text(encoding='utf-8').split('\n')
        progress_output = '\n'.join(lines[-30:])
        prompt_parts.append(progress_output)
    else:
        prompt_parts.append("暂无进度记录")

    # 4. 当前任务信息
    prompt_parts.append("")
    prompt_parts.append("# " + "=" * 76)
    prompt_parts.append("#                    CURRENT TASK & STAGE")
    prompt_parts.append("# " + "=" * 76)

    if short:
        # 简短版本：只包含基本信息
        prompt_parts.append("**Task ID:** Test_Final_001")
        prompt_parts.append("**Current Stage:** validation")
        prompt_parts.append("**Description:** API 自动化测试修复项目最终验收")
    else:
        # 完整版本：包含所有信息
        prompt_parts.append("## Current Task & Stage")
        prompt_parts.append("**Task ID:** Test_Final_001")
        prompt_parts.append("**Current Stage:** VALIDATION")
        prompt_parts.append("**Category:** feature")
        prompt_parts.append("**Description:** API 自动化测试修复项目最终验收")
        prompt_parts.append("")
        prompt_parts.append("**Stage Goal:** Satisfaction Validation - Claude 独立评估实现是否满足要求")
        prompt_parts.append("**Next Stage:** complete")
        prompt_parts.append("**Validation Config:**")
        prompt_parts.append("   Threshold: 0.8")
        prompt_parts.append("   Max Retries: 3")
        prompt_parts.append("**Artifacts to Validate:**")
        prompt_parts.append("  - 暂无产出记录")
        prompt_parts.append("")
        prompt_parts.append("**Acceptance Criteria:**")
        prompt_parts.append("  1. 测试通过率从 1.7% 提升至 80%+")
        prompt_parts.append("  2. 路由注册从 54 条增加至 100+ 条")
        prompt_parts.append("  3. 所有 P0 和 P1 任务已完成")
        prompt_parts.append("  4. Laravel Pint 检查通过")
        prompt_parts.append("  5. Allure 测试报告可查看")
        prompt_parts.append("  6. 无 500 错误")

    # 5. Validation 模板
    template_file = HARNESS_DIR / "templates" / "validation_prompt.md"
    if template_file.exists():
        template_content = template_file.read_text(encoding='utf-8')

        # 替换占位符
        if short:
            template_content = template_content.replace("{TASK_ID}", "Test_Final_001")
            template_content = template_content.replace("{DESCRIPTION}", "API 自动化测试修复项目最终验收")
            template_content = template_content.replace("{ACCEPTANCE_CRITERIA}", "1. 测试通过率 80%+ 2. 路由 100+ 条 3. P0/P1 完成 4. Pint 通过")
            template_content = template_content.replace("{ARTIFACTS_LIST}", "暂无产出")
            template_content = template_content.replace("{TEST_RESULTS}", "无")
            template_content = template_content.replace("{VALIDATION_THRESHOLD}", "0.8")
            template_content = template_content.replace("{VALIDATION_THRESHOLD_PERCENT}", "80%")
            template_content = template_content.replace("{CURRENT_RETRY}", "0")
            template_content = template_content.replace("{MAX_RETRIES}", "3")

        prompt_parts.append("")
        prompt_parts.append(template_content)
    else:
        prompt_parts.append("[ERROR] validation_prompt.md not found")

    return '\n'.join(prompt_parts)


def run_claude_via_pipeline(prompt: str, timeout: int = 180) -> tuple:
    """
    通过管道模式调用 Claude CLI
    返回 (return_code, stdout, stderr, elapsed_time)
    """
    import shutil

    # 查找 claude 命令
    claude_cmd = shutil.which('claude')
    if not claude_cmd:
        # 尝试使用 cmd /c
        claude_cmd = 'claude'

    # 构建命令
    cmd = ['cmd', '/c', claude_cmd, '--print', '--permission-mode', 'bypassPermissions']

    start_time = time.time()

    try:
        # 使用 Popen 进行管道交互
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=False  # binary mode for Windows compatibility
        )

        # 发送 prompt
        stdout_data, stderr_data = proc.communicate(
            input=prompt.encode('utf-8'),
            timeout=timeout
        )

        elapsed = time.time() - start_time

        return (
            proc.returncode,
            stdout_data.decode('utf-8', errors='replace'),
            stderr_data.decode('utf-8', errors='replace') if stderr_data else "",
            elapsed
        )

    except subprocess.TimeoutExpired:
        elapsed = time.time() - start_time
        proc.kill()
        return (-1, "", f"Timeout after {timeout}s", elapsed)
    except Exception as e:
        elapsed = time.time() - start_time
        return (-1, "", str(e), elapsed)


def test_pipeline(short: bool = False, verbose: bool = False):
    """执行管道测试"""
    total_start_time = time.time()

    print_header("\n" + "=" * 60)
    print_header("  Prompt 管道模式测试")
    print_header("=" * 60 + "\n")

    # 1. 构建 prompt
    build_start = time.time()
    print(f"{Colors.BOLD}[1/4] 构建 Prompt...{Colors.ENDC}")
    prompt = build_validation_prompt(short=short)
    prompt_size = len(prompt.encode('utf-8'))
    build_time = time.time() - build_start

    print_success(f"   Prompt 大小: {prompt_size:,} bytes ({prompt_size/1024:.1f} KB)")
    print_success(f"   Prompt 行数: {len(prompt.split(chr(10)))} 行")
    print_success(f"   构建用时: {build_time:.2f} 秒")

    if verbose:
        print(f"\n{Colors.WARNING}--- Prompt 预览 (前 500 字符) ---{Colors.ENDC}")
        print(prompt[:500])
        print(f"{Colors.WARNING}--- Prompt 预览结束 ---\n{Colors.ENDC}")

    # 2. 执行 Claude
    print(f"\n{Colors.BOLD}[2/4] 通过管道发送 Prompt 到 Claude CLI...{Colors.ENDC}")
    print(f"   超时设置: 180 秒 (3分钟)")
    print(f"   发送中...\n")

    exec_start = time.time()
    returncode, stdout, stderr, elapsed = run_claude_via_pipeline(prompt, timeout=180)
    exec_time = time.time() - exec_start

    # 3. 输出结果
    print(f"\n{Colors.BOLD}[3/4] Claude 输出结果:{Colors.ENDC}")
    print("-" * 60)

    if stdout:
        # 显示前 1000 字符
        display = stdout[:2000]
        print(display)
        if len(stdout) > 2000:
            print(f"\n{Colors.WARNING}... (还有 {len(stdout) - 2000} 字符){Colors.ENDC}")
    else:
        print_warning("   无 stdout 输出")

    if stderr and verbose:
        print(f"\n{Colors.WARNING}--- Stderr ---{Colors.ENDC}")
        print(stderr[:500])

    # 4. 分析结果
    print(f"\n{Colors.BOLD}[4/4] 结果分析:{Colors.ENDC}")

    if returncode == 0 and stdout:
        print_success("   ✓ 管道通信成功")

        # 检查是否有有效输出
        if len(stdout.strip()) > 10:
            print_success(f"   ✓ 收到有效输出 ({len(stdout)} 字符)")
        else:
            print_warning("   ⚠ 输出内容较少")

        # 检查是否包含关键标记
        if '<score>' in stdout:
            print_success("   ✓ 包含 <score> 标记")
        else:
            print_warning("   ⚠ 未找到 <score> 标记")

    elif returncode == -1:
        print_error(f"   ✗ 执行超时 ({elapsed:.1f}s)")
    else:
        print_error(f"   ✗ 执行失败 (返回码: {returncode})")
        if stderr:
            print(f"   错误信息: {stderr[:200]}")

    # 5. 总运行时间
    total_time = time.time() - total_start_time

    print("\n" + "=" * 60)
    print_header("  测试完成")
    print("=" * 60)

    # 显示详细时间统计
    print(f"\n{Colors.BOLD}📊 运行时间统计:{Colors.ENDC}")
    print(f"   ├─ Prompt 构建:    {build_time:>6.2f} 秒")
    print(f"   ├─ Claude 执行:    {exec_time:>6.2f} 秒")
    print(f"   └─ 总计:          {total_time:>6.2f} 秒")

    if short:
        print(f"\n   {Colors.WARNING}(使用简短 prompt){Colors.ENDC}")
    else:
        print(f"\n   {Colors.WARNING}(完整 prompt: {prompt_size/1024:.1f} KB){Colors.ENDC}")

    print()

    return returncode == 0 and bool(stdout.strip())


def main():
    parser = argparse.ArgumentParser(
        description='Prompt 管道模式测试脚本',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
    python .harness/scripts/test_pipeline_prompt.py
    python .harness/scripts/test_pipeline_prompt.py --short
    python .harness/scripts/test_pipeline_prompt.py --verbose
        """
    )

    parser.add_argument('--short', action='store_true',
                        help='使用简短版本的 prompt 进行测试')
    parser.add_argument('--verbose', action='store_true',
                        help='显示详细输出（包括 prompt 预览和 stderr）')

    args = parser.parse_args()

    success = test_pipeline(short=args.short, verbose=args.verbose)

    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
