#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SIM-Laravel 自动化循环脚本（三阶段质量保证系统）(Windows 版本)
Dev Agent -> Test Agent -> Review Agent

Windows 跨平台版本 - 完全复刻 run-automation-stages.sh 功能
"""

import json
import base64
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ============================================================================
#                      Windows 终端编码修复
# ============================================================================
if sys.platform == 'win32':
    # 设置 Windows 控制台输出编码为 UTF-8
    try:
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    except:
        pass

# ============================================================================
#                      输出工具函数 (兼容 Windows GBK)
# ============================================================================
def _safe_print(message: str, file=sys.stdout):
    """安全打印，处理 Windows 控制台编码问题"""
    try:
        file.write(message + '\n')
        file.flush()
    except UnicodeEncodeError:
        # 去除非 GBK 兼容字符（Emoji 等）
        clean_msg = message.encode('gbk', errors='ignore').decode('gbk')
        file.write(clean_msg + '\n')
        file.flush()

def log(message: str) -> None:
    """输出日志"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    msg = f"[{timestamp}] {message}"
    _safe_print(msg)
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(msg + '\n')

def log_verbose(message: str) -> None:
    """输出详细日志（仅 VERBOSE 模式）"""
    if VERBOSE:
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        msg = f"[{timestamp}] [VERBOSE] {message}"
        _safe_print(msg)
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(msg + '\n')

def log_error(message: str) -> None:
    """输出错误日志"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    msg = f"[{timestamp}] [ERROR] {message}"
    _safe_print(msg, file=sys.stderr)
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(msg + '\n')

# ============================================================================
#                      配置常量
# ============================================================================
# windows/run-automation-stages.py 被执行时，当前工作目录是项目根目录
# 所以 HARNESS_DIR 直接使用固定的 ".harness" 路径
SCRIPT_DIR = Path(__file__).parent.resolve()
PROJECT_ROOT = Path.cwd()  # 使用当前工作目录作为项目根目录
HARNESS_DIR = PROJECT_ROOT / ".harness"

# ============================================================================
#                      环境变量加载
# ============================================================================
def load_env_file(env_path: Path) -> Dict[str, str]:
    """从 .env 文件加载环境变量"""
    env_vars = {}
    if env_path.exists():
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    env_vars[key.strip()] = value.strip().strip('"').strip("'")
    return env_vars

# 加载 .harness/.env
env_file = HARNESS_DIR / ".env"
env_config = load_env_file(env_file)

# 默认配置
CLAUDE_CMD = env_config.get("CLAUDE_CMD", "claude")
PYTHON_CMD = env_config.get("PYTHON_CMD", "python")
MAX_RETRIES = int(env_config.get("MAX_RETRIES", "3"))
LOOP_SLEEP = int(env_config.get("LOOP_SLEEP", "5"))
VERBOSE = env_config.get("VERBOSE", "false").lower() == "true"
PERMISSION_MODE = env_config.get("PERMISSION_MODE", "bypassPermissions")

# 超时优化配置
MAX_TIMEOUT_RETRIES = int(env_config.get("MAX_TIMEOUT_RETRIES", "5"))
TIMEOUT_BACKOFF_FACTOR = float(env_config.get("TIMEOUT_BACKOFF_FACTOR", "1.5"))
BASE_SILENCE_TIMEOUT = int(env_config.get("BASE_SILENCE_TIMEOUT", "180"))
MAX_SILENCE_TIMEOUT = int(env_config.get("MAX_SILENCE_TIMEOUT", "600"))

# ============================================================================
#                      日志系统
# ============================================================================
LOG_DIR = HARNESS_DIR / "logs" / "automation"
CURRENT_YEAR = datetime.now().strftime("%Y")
CURRENT_MONTH = datetime.now().strftime("%m")
LOG_DIR_YEAR = LOG_DIR / CURRENT_YEAR / CURRENT_MONTH
LOG_DIR_YEAR.mkdir(parents=True, exist_ok=True)

LOG_FILE = LOG_DIR_YEAR / f"automation_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
PROGRESS_FILE = HARNESS_DIR / "logs" / "progress.md"

def log(message: str) -> None:
    """输出日志"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    msg = f"[{timestamp}] {message}"
    _safe_print(msg)
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(msg + '\n')

def log_verbose(message: str) -> None:
    """输出详细日志（仅 VERBOSE 模式）"""
    if VERBOSE:
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        msg = f"[{timestamp}] [VERBOSE] {message}"
        _safe_print(msg)
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(msg + '\n')

def log_error(message: str) -> None:
    """输出错误日志"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    msg = f"[{timestamp}] [ERROR] {message}"
    _safe_print(msg, file=sys.stderr)
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(msg + '\n')

# ============================================================================
#                      依赖检查
# ============================================================================
def check_dependencies() -> bool:
    """检查依赖"""
    log("[INFO] 检查依赖...")

    # 检查 Python
    try:
        subprocess.run([PYTHON_CMD, "--version"], capture_output=True, check=True, encoding='utf-8')
    except Exception:
        log_error(f"{PYTHON_CMD} 未安装或不可用")
        return False

    # 检查 task-index.json
    if not (HARNESS_DIR / "task-index.json").exists():
        log_error(".harness/task-index.json 不存在")
        return False

    # 检查 tasks/pending 目录
    if not (HARNESS_DIR / "tasks" / "pending").exists():
        log_error(".harness/tasks/pending/ 目录不存在")
        return False

    log("[OK] 依赖检查通过")
    return True

# ============================================================================
#                      辅助函数
# ============================================================================
def run_subprocess_text(cmd: List[str], input_text: str = None,
                       cwd: str = None) -> 'subprocess.CompletedProcess':
    """
    安全的 subprocess 文本模式执行（兼容 Python 3.7 Windows）

    Python 3.7 在 Windows 上使用 capture_output=True + text=True 会导致
    IndexError: list index out of range，此函数提供兼容的替代方案。
    """
    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        input=input_text.encode('utf-8') if input_text else None,
        cwd=cwd,
        encoding='utf-8',
        errors='replace'
    )
    return result


def calculate_dynamic_timeout(prompt_size_bytes: int, stage: str, retry_count: int = 0) -> int:
    """
    科学计算大模型 CLI 的动态超时时间

    算法设计:
    - 基础超时 = 60秒 (网络握手 + 模型启动)
    - Prompt 大小超时 = prompt_size_bytes / 1024 * 1.5 秒 (阅读推理时间)
    - 阶段产出超时 = dev(240s) / test(180s) / review(120s) / validation(90s)
    - 指数退避 = 超时重试时 * 1.5^retry_count
    - 安全边界 = 最小120秒, 最大1800秒(30分钟)

    参数:
        prompt_size_bytes: 组装好的 prompt 字节数
        stage: 当前阶段 (dev, test, review, validation)
        retry_count: 当前超时重试的次数
    """
    import math

    # 1. 基础网络握手与模型启动时间
    base_timeout = 60

    # 2. Prompt 体积附加时间 (每 KB 增加 1.5 秒)
    kb_size = prompt_size_bytes / 1024
    size_timeout = int(kb_size * 1.5)

    # 3. 阶段输出附加时间 (决定了模型需要生成多少 Token)
    stage_allowance = {
        "dev": 240,         # 预期产出大量代码
        "test": 180,        # 预期产出测试代码
        "review": 120,      # 预期产出审查报告
        "validation": 90     # 预期产出评估得分 (较短)
    }
    stage_time = stage_allowance.get(stage.lower(), 120)

    # 4. 汇总总时长
    total_timeout = base_timeout + size_timeout + stage_time

    # 5. 指数退避策略 (如果之前超时失败了，下一次自动给予更多时间)
    if retry_count > 0:
        total_timeout = int(total_timeout * math.pow(1.5, retry_count))

    # 6. 设立硬性安全边界 (最少 120 秒，最多 30 分钟)
    return max(120, min(total_timeout, 1800))


def run_python_script(script_name: str, args: List[str] = None,
                      capture_output: bool = True,
                      input_text: str = None) -> Tuple[int, str]:
    """运行 Python 脚本"""
    script_path = HARNESS_DIR / "windows" / "scripts" / script_name
    cmd = [PYTHON_CMD, str(script_path)]
    if args:
        cmd.extend(args)

    try:
        # 使用 bytes 模式读取，然后手动解码（避免编码错误）
        result = subprocess.run(
            cmd,
            capture_output=True,
            input=input_text.encode('utf-8') if input_text else None,
        )
        # 尝试用 UTF-8 解码，失败则用系统默认编码
        try:
            stdout = result.stdout.decode('utf-8', errors='replace')
            stderr = result.stderr.decode('utf-8', errors='replace')
        except:
            stdout = result.stdout.decode('gbk', errors='replace')
            stderr = result.stderr.decode('gbk', errors='replace')
        return result.returncode, stdout + stderr
    except Exception as e:
        return 1, str(e)

def get_artifacts_list(task_id: str) -> str:
    """获取任务的产出列表"""
    artifacts_file = HARNESS_DIR / "artifacts" / f"{task_id}.json"

    if not artifacts_file.exists():
        return "（暂无产出记录）"

    try:
        with open(artifacts_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        files = data.get('files', [])
        if files:
            return '\n'.join([f'  - {f}' for f in files])
        else:
            return '  （暂无产出）'
    except Exception as e:
        return f'  （无法读取产出记录: {e}）'

def get_stage_issues(task_id: str, stage: str) -> str:
    """获取前一个阶段的问题"""
    returncode, output = run_python_script(
        "task_utils.py",
        ["--get-stage-issues", task_id, stage],
        capture_output=False
    )
    # 使用内联 Python 获取
    code = f'''
import sys
sys.path.insert(0, '.harness/windows/scripts')
from task_utils import load_tasks
try:
    data = load_tasks()
    for task in data['tasks']:
        if task['id'] == '{task_id}' and 'stages' in task:
            issues = task['stages']['{stage}'].get('issues', [])
            if issues:
                for i, issue in enumerate(issues, 1):
                    print(f'{{i}}. {{issue}}')
            break
except Exception as e:
    print(f'Error: {{e}}', file=sys.stderr)
'''
    try:
        result = subprocess.run(
            [PYTHON_CMD, "-c", code],
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            cwd=str(PROJECT_ROOT)
        )
        return result.stdout.strip()
    except:
        return ""

def get_test_results(task_id: str) -> str:
    """获取测试结果"""
    code = f'''
import sys
sys.path.insert(0, '.harness/windows/scripts')
from task_utils import load_tasks
try:
    data = load_tasks()
    for task in data['tasks']:
        if task['id'] == '{task_id}' and 'stages' in task:
            test_results = task['stages']['test'].get('test_results', {{}})
            if test_results:
                for test_name, result in test_results.items():
                    status = '[PASS]' if result.get('passed') else '[FAIL]'
                    msg = result.get('message', 'N/A')
                    print(f'{{status}} {{test_name}}: {{msg}}')
            break
except Exception as e:
    print(f'Error: {{e}}', file=sys.stderr)
'''
    try:
        result = subprocess.run(
            [PYTHON_CMD, "-c", code],
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            cwd=str(PROJECT_ROOT)
        )
        return result.stdout.strip() or "（暂无测试结果）"
    except:
        return "（暂无测试结果）"

def get_task_complexity(task_id: str) -> str:
    """获取任务复杂度"""
    code = f'''
import sys
sys.path.insert(0, '.harness/windows/scripts')
from task_utils import load_tasks
try:
    data = load_tasks()
    for task in data['tasks']:
        if task['id'] == '{task_id}':
            print(task.get('complexity', 'unknown'))
            break
except Exception as e:
    print('unknown', file=sys.stderr)
'''
    try:
        result = subprocess.run(
            [PYTHON_CMD, "-c", code],
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            cwd=str(PROJECT_ROOT)
        )
        return result.stdout.strip() or "unknown"
    except:
        return "unknown"

def get_hard_timeout(complexity: str) -> int:
    """根据复杂度获取硬超时时间"""
    timeouts = {
        "simple": 900,    # 15分钟
        "medium": 1200,   # 20分钟
        "complex": 1800,  # 30分钟
    }
    return timeouts.get(complexity, 900)


def get_dependency_context(task_id: str) -> str:
    """
    获取依赖任务的上下文信息

    Args:
        task_id: 当前任务 ID

    Returns:
        str: 格式化的依赖上下文字符串
    """
    # 获取依赖任务列表
    code = f'''
import sys
import json
sys.path.insert(0, '.harness/windows/scripts')
from task_utils import load_tasks
try:
    data = load_tasks()
    for task in data['tasks']:
        if task['id'] == '{task_id}':
            deps = task.get('depends_on', [])
            if deps:
                print(json.dumps(deps))
            break
except Exception as e:
    print('[]', file=sys.stderr)
'''
    try:
        result = subprocess.run(
            [PYTHON_CMD, "-c", code],
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            cwd=str(PROJECT_ROOT)
        )
        depends_on = json.loads(result.stdout.strip() or '[]')
    except:
        depends_on = []

    if not depends_on:
        return ""

    context_parts = []
    context_parts.append("# ═══════════════════════════════════════════════════════════════")
    context_parts.append("#                    DEPENDENCY CONTEXT                          ")
    context_parts.append("#                    依赖任务上下文信息                          ")
    context_parts.append("# ═══════════════════════════════════════════════════════════════")
    context_parts.append("")
    context_parts.append(f"**当前任务依赖:** {', '.join(depends_on)}")
    context_parts.append("")
    context_parts.append("以下是依赖任务的产出、设计决策和接口契约，请参考：")
    context_parts.append("")

    # 加载每个依赖任务的信息
    for dep_id in depends_on:
        # 加载产出文件
        artifact_file = HARNESS_DIR / "artifacts" / f"{dep_id}.json"
        if artifact_file.exists():
            try:
                with open(artifact_file, 'r', encoding='utf-8') as f:
                    artifact = json.load(f)

                context_parts.append(f"## 依赖任务: {dep_id}")
                context_parts.append("")

                # 显示产出文件
                files = artifact.get('files', [])
                if files:
                    context_parts.append("**产出文件:**")
                    for f in files:
                        context_parts.append(f"  - {f}")
                    context_parts.append("")

                # 显示设计决策
                design_decisions = artifact.get('design_decisions', [])
                if design_decisions:
                    context_parts.append("**设计决策:**")
                    for dd in design_decisions:
                        if isinstance(dd, dict):
                            context_parts.append(f"  - {dd.get('decision', dd)}")
                        else:
                            context_parts.append(f"  - {dd}")
                    context_parts.append("")

                # 显示接口契约
                interface_contracts = artifact.get('interface_contracts', [])
                if interface_contracts:
                    context_parts.append("**接口契约:**")
                    for ic in interface_contracts:
                        if isinstance(ic, dict):
                            params_str = ', '.join(ic.get('params', []))
                            context_parts.append(f"  - {ic.get('service')}::{ic.get('method')}({params_str}) -> {ic.get('returns')}")
                        else:
                            context_parts.append(f"  - {ic}")
                    context_parts.append("")

                # 显示约束条件
                constraints = artifact.get('constraints', [])
                if constraints:
                    context_parts.append("**约束条件:**")
                    for c in constraints:
                        context_parts.append(f"  - {c}")
                    context_parts.append("")

            except Exception as e:
                context_parts.append(f"  (无法读取任务 {dep_id} 的产出: {e})")
                context_parts.append("")

    # 加载全局约束
    constraints_file = HARNESS_DIR / "knowledge" / "constraints.json"
    if constraints_file.exists():
        try:
            with open(constraints_file, 'r', encoding='utf-8') as f:
                constraints_data = json.load(f)

            global_constraints = constraints_data.get('global', [])
            if global_constraints:
                context_parts.append("## 全局约束条件")
                context_parts.append("")
                context_parts.append("**必须遵循:**")
                for c in global_constraints:
                    context_parts.append(f"  - {c}")
                context_parts.append("")
        except:
            pass

    context_parts.append("")

    return '\n'.join(context_parts)

def clean_duplicate_migrations() -> None:
    """清理重复的迁移文件"""
    migrations_dir = PROJECT_ROOT / "database" / "migrations"
    if not migrations_dir.exists():
        return

    tables = {}
    for f in migrations_dir.glob("*.php"):
        match = re.search(r'create_(\w+)_table', f.stem)
        if match:
            table_name = match.group(1)
            tables.setdefault(table_name, []).append(f)

    deleted_count = 0
    for table_name, files in tables.items():
        if len(files) > 1:
            files_sorted = sorted(files, key=lambda x: x.stat().st_mtime, reverse=True)
            for old_file in files_sorted[1:]:
                try:
                    old_file.unlink()
                    deleted_count += 1
                except:
                    pass

    if deleted_count > 0:
        log(f'  [CLEAN] 清理了 {deleted_count} 个重复的迁移文件')

# ============================================================================
#                      主循环
# ============================================================================
def main():
    log("[START] 启动 SIM-Laravel 三阶段自动化循环...")
    log(f"[LOG] 日志文件: {LOG_FILE}")
    log("配置:")
    log(f"  - CLAUDE_CMD: {CLAUDE_CMD}")
    log(f"  - PYTHON_CMD: {PYTHON_CMD}")
    log(f"  - MAX_RETRIES: {MAX_RETRIES}")
    log(f"  - LOOP_SLEEP: {LOOP_SLEEP}s")
    log(f"  - PERMISSION_MODE: {PERMISSION_MODE}")
    log(f"  - 质量保证: 三阶段 (Dev -> Test -> Review)")
    log("")

    # 检查依赖
    if not check_dependencies():
        sys.exit(1)

    # 创建计数器目录
    retry_dir = HARNESS_DIR / ".automation_retries"
    skip_dir = HARNESS_DIR / ".automation_skip"
    timeout_dir = HARNESS_DIR / ".automation_timeouts"
    retry_dir.mkdir(exist_ok=True)
    skip_dir.mkdir(exist_ok=True)
    timeout_dir.mkdir(exist_ok=True)

    # CLI I/O 目录
    cli_io_dir = HARNESS_DIR / "cli-io" / "sessions"
    cli_io_dir.mkdir(parents=True, exist_ok=True)

    consecutive_failures = 0
    MAX_CONSECUTIVE_FAILURES = 5

    while True:
        log("[INFO] 获取下一个待处理阶段...")

        # 获取下一阶段
        returncode, stage_output = run_python_script("next_stage.py")

        if returncode == 1:
            log("[OK] 所有阶段已完成！退出循环。")
            # 统计任务数
            try:
                with open(HARNESS_DIR / "task-index.json", 'r', encoding='utf-8') as f:
                    data = json.load(f)
                log(f"[STATS] 完成统计：")
                log(f"  - 总任务数: {len(data.get('tasks', []))}")
            except:
                pass
            log(f"  - 日志文件: {LOG_FILE}")
            sys.exit(0)
        elif returncode != 0:
            log_error(f"获取阶段失败: {stage_output}")
            consecutive_failures += 1
            if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                log_error(f"连续失败次数过多 ({consecutive_failures})，停止执行")
                sys.exit(1)
            time.sleep(LOOP_SLEEP)
            continue

        consecutive_failures = 0

        log("当前任务和阶段:")
        _safe_print(stage_output)
        _safe_print("")

        # 解析任务 ID 和阶段
        current_task_id = ""
        current_stage = ""
        for line in stage_output.split('\n'):
            # 移除 [INFO]、[OK]、[ERROR] 等前缀
            clean_line = line.strip()
            import re
            # 移除 [xxx] 前缀
            clean_line = re.sub(r'^\[[A-Z]+\]\s*', '', clean_line)
            if clean_line.startswith("**Task ID:**"):
                current_task_id = clean_line.replace("**Task ID:**", "").strip()
            elif clean_line.startswith("**Current Stage:**"):
                current_stage = clean_line.replace("**Current Stage:**", "").strip().lower()

        log_verbose(f"任务 ID: {current_task_id}")
        log_verbose(f"当前阶段: {current_stage}")

        # 验证解析结果
        if not current_task_id or not current_stage:
            log_error("解析任务 ID 或阶段失败，跳过此迭代")
            log_error(f"原始输出: {stage_output}")
            time.sleep(LOOP_SLEEP)
            continue

        # 验证阶段名称有效性
        valid_stages = ['dev', 'test', 'review', 'validation']
        if current_stage not in valid_stages:
            log_error(f"无效的阶段名称: {current_stage}，有效值: {valid_stages}")
            time.sleep(LOOP_SLEEP)
            continue

        # 检查是否已跳过
        skip_file = skip_dir / current_task_id
        if skip_file.exists():
            log(f"[SKIP] 跳过任务 {current_task_id} (之前已达到最大重试次数)")
            time.sleep(LOOP_SLEEP)
            continue

        # 检查重试次数
        retry_file = retry_dir / f"{current_task_id}_{current_stage}.count"
        current_retry_count = 0
        if retry_file.exists():
            try:
                current_retry_count = int(retry_file.read_text().strip())
            except:
                current_retry_count = 0

            if current_retry_count >= MAX_RETRIES:
                log_error(f"[RETRY] 任务 {current_task_id} 的 {current_stage} 阶段已达到最大重试次数 ({MAX_RETRIES})")
                log_error("[SKIP] 将跳过此任务并继续处理其他任务")
                skip_file.touch()
                time.sleep(LOOP_SLEEP)
                continue

            # 重试前清理产出（仅 dev 阶段）
            if current_stage == "dev":
                log("[CLEAN] 清理任务残留产出...")
                run_python_script("artifacts.py", ["--action", "clean", "--id", current_task_id])

        # 组装 Prompt
        log(f"[INFO] 组装 Prompt（{current_stage} 阶段）...")

        # 获取进度输出
        progress_output = "暂无进度记录（这是第一个任务）"
        if PROGRESS_FILE.exists():
            lines = PROGRESS_FILE.read_text(encoding='utf-8').split('\n')
            progress_output = '\n'.join(lines[-30:])

        # 获取产出列表
        artifacts_list = "（暂无产出）"
        if current_stage in ["test", "review"]:
            artifacts_list = get_artifacts_list(current_task_id)

        # 获取前阶段问题（以及 Validation 回滚的反馈）
        previous_issues = ""
        if current_stage == "dev":
            dev_issues = get_stage_issues(current_task_id, "dev")
            if dev_issues:
                previous_issues = f"需要修复的问题 (来自之前 Validation 阶段的打回重修):\n{dev_issues}"
        elif current_stage == "test":
            dev_issues = get_stage_issues(current_task_id, "dev")
            if dev_issues:
                previous_issues = f"Dev 阶段遗留问题:\n{dev_issues}"
        elif current_stage == "review":
            test_issues = get_stage_issues(current_task_id, "test")
            if test_issues:
                previous_issues = f"Test 阶段发现的问题:\n{test_issues}"

        # 获取测试结果
        test_results = ""
        if current_stage == "review":
            test_results = get_test_results(current_task_id)

        # 读取模板
        template_file = HARNESS_DIR / "templates" / f"{current_stage}_prompt.md"
        if not template_file.exists():
            log_error(f"模板文件不存在: {template_file}")
            log_error(f"当前目录: {os.getcwd()}")
            log_error(f"模板目录内容:")
            try:
                for f in (HARNESS_DIR / "templates").glob("*"):
                    log_error(f"  - {f}")
            except:
                pass
            sys.exit(1)

        template_content = template_file.read_text(encoding='utf-8')

        # 对于 validation 阶段，替换额外的占位符
        if current_stage == "validation":
            # 获取 validation 配置
            code = f'''
import sys
sys.path.insert(0, '.harness/windows/scripts')
from task_utils import load_tasks
data = load_tasks()
for task in data['tasks']:
    if task['id'] == '{current_task_id}':
        val = task.get('validation', {{}})
        print("enabled " + str(val.get('enabled', False)))
        print("threshold " + str(val.get('threshold', 0.8)))
        print("max_retries " + str(val.get('max_retries', 3)))
        break
'''
            result = run_subprocess_text(
                [PYTHON_CMD, "-c", code],
                cwd=str(PROJECT_ROOT)
            )
            val_enabled = False
            val_threshold = 0.8
            val_max_retries = 3
            for line in result.stdout.strip().split('\n'):
                if line.startswith('enabled '):
                    val_enabled = line.split()[1] == 'True'
                elif line.startswith('threshold '):
                    val_threshold = float(line.split()[1])
                elif line.startswith('max_retries '):
                    val_max_retries = int(line.split()[1])

            # 获取重试次数
            validation_retry_file = timeout_dir / f"{current_task_id}_validation_retry.count"
            current_retry = 0
            if validation_retry_file.exists():
                try:
                    current_retry = int(validation_retry_file.read_text().strip())
                except:
                    current_retry = 0

            # 计算阈值百分比
            threshold_percent = int(val_threshold * 100)

            # 获取验收标准（格式化为编号列表）
            code = f'''
import sys
sys.path.insert(0, '.harness/windows/scripts')
from task_utils import load_tasks
data = load_tasks()
for task in data['tasks']:
    if task['id'] == '{current_task_id}':
        items = []
        for i, acc in enumerate(task.get('acceptance', []), 1):
            acc_escaped = acc.replace('\\n', '<br>').replace('|', '\\\\|')
            items.append(f'{{i}}. {{acc_escaped}}')
        sys.stdout.write('<br>'.join(items))
        break
'''
            result = run_subprocess_text(
                [PYTHON_CMD, "-c", code],
                cwd=str(PROJECT_ROOT)
            )
            acceptance_criteria = result.stdout.strip() or "(无验收标准)"

            # 获取产出列表
            artifacts_list_val = get_artifacts_list(current_task_id)

            # 获取测试结果
            test_results_val = get_test_results(current_task_id)

            # 获取任务描述
            code = f'''
import sys
sys.path.insert(0, '.harness/windows/scripts')
from task_utils import load_tasks
data = load_tasks()
for task in data['tasks']:
    if task['id'] == '{current_task_id}':
        sys.stdout.write(task.get('description', ''))
        break
'''
            result = run_subprocess_text(
                [PYTHON_CMD, "-c", code],
                cwd=str(PROJECT_ROOT)
            )
            task_desc = result.stdout.strip() or "任务描述"

            # 替换所有占位符
            template_content = template_content.replace("{TASK_ID}", current_task_id)
            template_content = template_content.replace("{DESCRIPTION}", task_desc)
            template_content = template_content.replace("{ACCEPTANCE_CRITERIA}", acceptance_criteria)
            template_content = template_content.replace("{ARTIFACTS_LIST}", artifacts_list_val)
            template_content = template_content.replace("{TEST_RESULTS}", test_results_val)
            template_content = template_content.replace("{VALIDATION_THRESHOLD}", str(val_threshold))
            template_content = template_content.replace("{VALIDATION_THRESHOLD_PERCENT}", f"{threshold_percent}%")
            template_content = template_content.replace("{CURRENT_RETRY}", str(current_retry))
            template_content = template_content.replace("{MAX_RETRIES}", str(val_max_retries))
        else:
            # 其他阶段只替换 TASK_ID
            template_content = template_content.replace("{TASK_ID}", current_task_id)

        # 构建完整 Prompt
        prompt_parts = [
            "# ═══════════════════════════════════════════════════════════════",
            "#                    SYSTEM INSTRUCTIONS (SOP)                  ",
            "#              Laravel 开发规范 - 必须严格遵循                   ",
            "# ═══════════════════════════════════════════════════════════════",
            "",
        ]

        # 检查 CLAUDE.md - 修复：直接读取并嵌入内容，防止管道模式下 @ 标记失效
        claude_md = PROJECT_ROOT / "CLAUDE.md"
        if claude_md.exists():
            try:
                claude_content = claude_md.read_text(encoding='utf-8')
                prompt_parts.append(claude_content)
                log_verbose("[INFO] 成功将 CLAUDE.md 内容嵌入到 Prompt 中")
                # 添加强制指令
                prompt_parts.append("")
                prompt_parts.append("⚠️ **CRITICAL: You MUST strictly follow the SOP / coding standards provided above.**")
            except Exception as e:
                prompt_parts.append(f"[WARNING] 无法读取 CLAUDE.md: {e}")
                log_error(f"读取 CLAUDE.md 失败: {e}")
        else:
            prompt_parts.append("[WARNING] CLAUDE.md not found in project root")

        # 获取依赖上下文（新增）
        dependency_context = get_dependency_context(current_task_id)
        if dependency_context:
            prompt_parts.append("")
            prompt_parts.append(dependency_context)

        prompt_parts.extend([
            "",
            "",
            "# ═══════════════════════════════════════════════════════════════",
            "#                    RECENT PROGRESS                            ",
            "#                    最近 30 行进度记录                          ",
            "# ═══════════════════════════════════════════════════════════════",
            "",
            progress_output,
            "",
            "",
            "# ═══════════════════════════════════════════════════════════════",
            "#                    CURRENT TASK & STAGE                       ",
            "# ═══════════════════════════════════════════════════════════════",
            "",
            stage_output,
            "",
            "",
            "# ═══════════════════════════════════════════════════════════════",
            "#                    ARTIFACTS & ISSUES                        ",
            "# ═══════════════════════════════════════════════════════════════",
            "",
        ])

        if current_stage in ["test", "review"]:
            prompt_parts.append("**Artifacts to test/review:**")
            prompt_parts.append(artifacts_list)
            prompt_parts.append("")

        if previous_issues:
            prompt_parts.append("**Previous stage issues:**")
            prompt_parts.append(previous_issues)
            prompt_parts.append("")

        if current_stage == "review" and test_results:
            prompt_parts.append("**Test Results:**")
            prompt_parts.append(test_results)
            prompt_parts.append("")

        prompt_parts.append("")
        prompt_parts.append(template_content)

        prompt_content = '\n'.join(prompt_parts)

        # 计算 Prompt 大小（用于动态超时计算）
        prompt_size = len(prompt_content.encode('utf-8'))

        # 写入临时文件
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False,
                                         encoding='utf-8') as prompt_file:
            prompt_file.write(prompt_content)
            prompt_file_path = prompt_file.name

        log_verbose(f"Prompt 已组装到: {prompt_file_path}")

        # ==================================================================
        #                   执行 Claude CLI
        # ==================================================================
        log(f"[AGENT] 调用 Claude Code CLI ({current_stage} Agent)...")
        log("-" * 40)

        # 获取任务复杂度和超时设置
        task_complexity = get_task_complexity(current_task_id)
        hard_timeout = get_hard_timeout(task_complexity)

        # 获取超时计数
        timeout_count_file = timeout_dir / f"{current_task_id}_{current_stage}.count"
        timeout_count = 0
        if timeout_count_file.exists():
            try:
                timeout_count = int(timeout_count_file.read_text().strip())
            except:
                timeout_count = 0

        # 使用动态超时算法计算活性超时时间
        silence_timeout = calculate_dynamic_timeout(prompt_size, current_stage, timeout_count)

        log(f"任务复杂度: {task_complexity}")
        log(f"Prompt 大小: {prompt_size/1024:.1f} KB")
        log(f"硬超时限制: {hard_timeout}秒 ({hard_timeout // 60}分钟)")
        log(f"动态活性超时: {silence_timeout}秒 ({silence_timeout//60}分钟) (第 {timeout_count} 次超时，已智能调整)")

        # 创建 CLI 会话记录
        io_session_id = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{os.getpid()}"
        io_meta_file = HARNESS_DIR / "cli-io" / "current.json"
        io_output_file = cli_io_dir / f"{io_session_id}_output.txt"
        io_start_time = datetime.now().isoformat()

        # 写入会话元数据
        with open(io_meta_file, 'w', encoding='utf-8') as f:
            json.dump({
                "session_id": io_session_id,
                "task_id": current_task_id,
                "stage": current_stage,
                "start_time": io_start_time,
                "prompt_file": prompt_file_path,
                "active": True
            }, f, indent=2)

        log(f"[IO] CLI I/O 捕获已启用 (session: {io_session_id})")

        # 执行 dual_timeout.py
        cmd = [
            PYTHON_CMD,
            str(HARNESS_DIR / "windows" / "scripts" / "dual_timeout.py"),
            "--hard-timeout", str(hard_timeout),
            "--silence-timeout", str(silence_timeout),
            "--claude-cmd", CLAUDE_CMD,
            "--permission-mode", PERMISSION_MODE,
        ]
        if VERBOSE:
            cmd.append("--verbose")

        try:
            # 打开输出文件用于捕获 dual_timeout.py 的输出
            with open(io_output_file, 'w', encoding='utf-8') as output_f:
                # 将 dual_timeout.py 的输出保存到文件
                # 注意：input 必须是 bytes（因为 stdout 是文件对象）
                result = subprocess.run(
                    cmd,
                    input=prompt_content.encode('utf-8'),
                    stdout=output_f,
                    stderr=subprocess.STDOUT
                )
            dual_timeout_exit_code = result.returncode
        except subprocess.TimeoutExpired:
            dual_timeout_exit_code = 124
        except Exception as e:
            log_error(f"执行失败: {e}")
            dual_timeout_exit_code = 1

        # 更新会话元数据
        with open(io_meta_file, 'w', encoding='utf-8') as f:
            json.dump({
                "session_id": io_session_id,
                "task_id": current_task_id,
                "stage": current_stage,
                "start_time": io_start_time,
                "end_time": datetime.now().isoformat(),
                "exit_code": dual_timeout_exit_code,
                "completed": True,
                "active": False
            }, f, indent=2)

        # 保存输出（如果有的话）
        if io_output_file.exists():
            log(f"[IO] CLI I/O 已保存到: {io_output_file}")

        # 检测超时失败
        is_timeout_failure = False
        if dual_timeout_exit_code in [14, 124]:
            is_timeout_failure = True
            log(f"[TIMEOUT] 检测到超时退出（退出码 {dual_timeout_exit_code}），本次不计入逻辑失败次数")

        log("─" * 40)
        _safe_print("")

        # 清理临时文件
        try:
            os.unlink(prompt_file_path)
        except:
            pass

        # 清理重复迁移文件
        if current_stage == "dev" and ("Migration" in current_task_id or "Foundation" in current_task_id):
            log("[CHECK] 检查并清理重复的迁移文件...")
            clean_duplicate_migrations()

        # ==================================================================
        #                   检查阶段状态
        # ==================================================================
        log("[INFO] 检查阶段状态...")

        is_completed = False

        if dual_timeout_exit_code != 0:
            log(f"[FAIL] Agent 异常退出或超时 (Exit Code: {dual_timeout_exit_code})")
        else:
            # 检查是否调用了 mark-stage
            returncode, stage_status_output = run_python_script(
                "harness-tools.py",
                ["--action", "stage-status", "--id", current_task_id, "--stage", current_stage]
            )

            if "完成" in stage_status_output:
                log("[OK] Agent 完美执行并主动调用了 mark-stage！")
                is_completed = True
            else:
                log("[WARN] Agent 正常退出，但未调用 mark-stage 命令。尝试混合检测...")

                # 混合检测
                returncode, detect_result = run_python_script(
                    "detect_stage_completion.py",
                    ["--id", current_task_id, "--stage", current_stage]
                )

                if returncode == 0:
                    log(f"[OK] 混合检测通过: {detect_result}")
                    # 自动调用 mark-stage
                    if current_stage == "dev":
                        # 获取 git 变更文件
                        try:
                            git_result = subprocess.run(
                                ["git", "status", "--porcelain"],
                                capture_output=True,
                                text=True,
                                encoding='utf-8',
                                cwd=str(PROJECT_ROOT)
                            )
                            git_files = ' '.join([
                                line.split(maxsplit=1)[1]
                                for line in git_result.stdout.strip().split('\n')
                                if line
                            ])
                        except:
                            git_files = ""

                        run_python_script(
                            "harness-tools.py",
                            ["--action", "mark-stage", "--id", current_task_id,
                             "--stage", "dev", "--files", git_files]
                        )
                    else:
                        run_python_script(
                            "harness-tools.py",
                            ["--action", "mark-stage", "--id", current_task_id,
                             "--stage", current_stage]
                        )
                    is_completed = True
                elif returncode == 1:
                    log(f"[FAIL] 混合检测未通过: {detect_result}")

                    # 兜底机制：检查输出中的完成文本
                    if io_output_file.exists():
                        try:
                            output_content = io_output_file.read_text(encoding='utf-8')
                            if re.search(r'(review.*已完成|审查.*已完成|阶段已完成|已标记为完成|review.*complete)',
                                        output_content, re.IGNORECASE):
                                log("[WARN] 检测到完成文本，尝试自动标记...")
                                run_python_script(
                                    "harness-tools.py",
                                    ["--action", "mark-stage", "--id", current_task_id,
                                     "--stage", current_stage]
                                )
                                is_completed = True
                                log("[OK] 已根据完成文本自动标记为完成（兜底机制）")
                        except:
                            pass
                else:
                    log(f"[UNKNOWN] 混合检测无法确定: {detect_result}")

            # ═══════════════════════════════════════════════════════════════
            #           Validation Stage 特殊处理与状态回滚机制
            # ═══════════════════════════════════════════════════════════════
            if current_stage == "validation" and not is_completed and io_output_file.exists():
                log("[INFO] 检测到 validation stage，尝试提取满意度分数...")

                try:
                    output_content = io_output_file.read_text(encoding='utf-8')

                    # 严格提取 <score> 标签中的数字（支持整数或浮点数）
                    match = re.search(r'<score>\s*(\d+(?:\.\d+)?)\s*</score>', output_content, re.IGNORECASE)

                    if match:
                        satisfaction_score = float(match.group(1))
                        log(f"[INFO] 提取到满意度分数: {satisfaction_score}")

                        # 获取阈值（需要在此处重新获取，因为模板组装块的变量作用域不覆盖这里）
                        code = f'''
import sys
sys.path.insert(0, '.harness/windows/scripts')
from task_utils import load_tasks
data = load_tasks()
for task in data['tasks']:
    if task['id'] == '{current_task_id}':
        val = task.get('validation', {{}})
        print(val.get('threshold', 0.8))
        break
'''
                        result = run_subprocess_text([PYTHON_CMD, "-c", code], cwd=str(PROJECT_ROOT))
                        val_threshold = float(result.stdout.strip() or "0.8")

                        # 统一归一化为百分制 (0-100) 避免 0.8 和 80 的比较错误
                        normalized_score = satisfaction_score
                        if normalized_score <= 1.0 and normalized_score > 0:
                            normalized_score *= 100

                        normalized_threshold = val_threshold
                        if normalized_threshold <= 1.0:
                            normalized_threshold *= 100

                        # 获取当前重试次数
                        validation_retry_file = timeout_dir / f"{current_task_id}_validation_retry.count"
                        current_retry = int(validation_retry_file.read_text().strip()) if validation_retry_file.exists() else 0

                        # ==========================================
                        # 核心校验逻辑
                        # ==========================================
                        if normalized_score >= normalized_threshold:
                            # ✅ 逻辑成功：分数达标，正常完成
                            run_python_script(
                                "harness-tools.py",
                                ["--action", "mark-validation",
                                 "--id", current_task_id,
                                 "--score", str(normalized_score / 100.0),  # 工具接受 0-1 的比例
                                 "--tries", str(current_retry)]
                            )
                            log(f"[OK] Validation 通过 (得分: {normalized_score:.1f} >= 阈值: {normalized_threshold:.1f})")
                            is_completed = True

                        else:
                            # ❌ 逻辑失败：分数不达标，触发回滚机制 (打回 Dev 重修)
                            log(f"[FAIL] Validation 未达标 (得分: {normalized_score:.1f} < 阈值: {normalized_threshold:.1f})")
                            log("[ROLLBACK] 正在触发状态回滚，打回 Dev 阶段重修...")

                            # 清理输出中的 xml 标签等，截取主要反馈信息
                            feedback_text = re.sub(r'<score>.*?</score>', '', output_content, flags=re.IGNORECASE|re.DOTALL).strip()
                            if len(feedback_text) > 1500:  # 如果太长，截取结尾最核心的结论部分
                                feedback_text = "..." + feedback_text[-1500:]

                            feedback_msg = f"Validation 阶段打回重修 (得分: {normalized_score:.1f}/{normalized_threshold:.1f})。审查反馈如下：\n{feedback_text}"

                            # 使用 Base64 安全编码反馈信息，防止打断内联 Python 的语法
                            feedback_b64 = base64.b64encode(feedback_msg.encode('utf-8')).decode('utf-8')

                            # 使用内联 Python 脚本安全地重置所有相关阶段状态
                            rollback_code = f'''
import sys
import base64
sys.path.insert(0, '.harness/windows/scripts')
from task_utils import load_tasks, save_tasks

try:
    data = load_tasks()
    for task in data['tasks']:
        if task['id'] == '{current_task_id}' and 'stages' in task:
            # 1. 重置各阶段状态
            task['stages']['dev']['completed'] = False
            task['stages']['dev']['completed_at'] = None
            task['stages']['test']['completed'] = False
            task['stages']['test']['completed_at'] = None
            task['stages']['review']['completed'] = False
            task['stages']['review']['completed_at'] = None
            task['stages']['validation']['completed'] = False
            task['stages']['validation']['completed_at'] = None

            # 2. 将反馈注入 dev 阶段的 issues 中
            if 'issues' not in task['stages']['dev']:
                task['stages']['dev']['issues'] = []

            feedback_msg = base64.b64decode('{feedback_b64}').decode('utf-8')
            task['stages']['dev']['issues'].append(feedback_msg)
            break

    save_tasks(data)
    print("SUCCESS")
except Exception as e:
    print(f"ERROR: {{e}}")
'''
                            result = run_subprocess_text([PYTHON_CMD, "-c", rollback_code], cwd=str(PROJECT_ROOT))

                            if "SUCCESS" in result.stdout:
                                log("[OK] 任务状态已成功重置为 dev 阶段。反馈信息已注入。")
                            else:
                                log_error(f"状态回滚失败: {result.stdout} {result.stderr}")

                            # 删除 Validation 重试计数器（因为进入了全新的 dev 循环，重试次数应清零）
                            if validation_retry_file.exists():
                                try:
                                    validation_retry_file.unlink()
                                except:
                                    pass

                            log("[INFO] 结束当前循环，即将重新分配 Dev 任务。")
                            _safe_print("")
                            time.sleep(LOOP_SLEEP)

                            # 直接进入下一次主循环，跳过底部的结算与重试计数器增加逻辑
                            continue

                    else:
                        # ⚠️ 技术性失败：没有按格式输出 <score> 标签
                        log("[WARN] 无法从输出中提取到标准的 <score> 标签。视为技术性失败，保留 pending 状态进入重试流程。")

                except Exception as e:
                    log_error(f"处理 Validation 结果时发生异常: {e}")

        # ==================================================================
        #                   结算阶段状态
        # ==================================================================
        if is_completed:
            log(f"[OK] 任务 {current_task_id} 的 {current_stage} 阶段已完成")

            # 检查是否所有阶段完成
            code = f'''
import sys
sys.path.insert(0, '.harness/windows/scripts')
from task_utils import load_tasks
data = load_tasks()
for task in data['tasks']:
    if task['id'] == '{current_task_id}' and 'stages' in task:
        # 检查标准阶段
        dev_test_review_complete = all([
            task['stages']['dev']['completed'],
            task['stages']['test']['completed'],
            task['stages']['review']['completed']
        ])
        # 检查 validation 阶段（如果启用）
        validation_config = task.get('validation', {{}})
        validation_complete = True
        if validation_config.get('enabled', False):
            validation_complete = task['stages'].get('validation', {{}}).get('completed', True)
        all_complete = dev_test_review_complete and validation_complete
        sys.exit(0 if all_complete else 1)
sys.exit(2)
'''
            result = subprocess.run(
                [PYTHON_CMD, "-c", code],
                capture_output=True,
                encoding='utf-8',
                errors='replace',
                cwd=str(PROJECT_ROOT)
            )

            if result.returncode == 0:
                # 所有阶段完成，创建 Git 提交
                log(f"[SUCCESS] 任务 {current_task_id} 的所有阶段已完成！")

                if (PROJECT_ROOT / ".git").exists():
                    log("[GIT] 创建 Git 提交...")

                    # 获取任务描述
                    code = f'''
import sys
sys.path.insert(0, '.harness/windows/scripts')
from task_utils import load_tasks
data = load_tasks()
for task in data['tasks']:
    if task['id'] == '{current_task_id}':
        print(task['description'])
        break
'''
                    result = subprocess.run(
                        [PYTHON_CMD, "-c", code],
                        capture_output=True,
                        text=True,
                        encoding='utf-8',
                        errors='replace',
                        cwd=str(PROJECT_ROOT)
                    )
                    task_desc = result.stdout.strip()

                    try:
                        subprocess.run(["git", "add", "-A", "."],
                                      capture_output=True,
                                      encoding='utf-8',
                                      cwd=str(PROJECT_ROOT))

                        # 清理提交信息
                        clean_task_desc = re.sub(r' \(三阶段质量保证通过\)', '', task_desc).strip()

                        result = subprocess.run(
                            ["git", "commit", "-m", f"{current_task_id}: {clean_task_desc}"],
                            capture_output=True,
                            text=True,
                            encoding='utf-8',
                            cwd=str(PROJECT_ROOT)
                        )

                        if result.returncode == 0:
                            log(f"[GIT] 已提交: {current_task_id}: {clean_task_desc}")
                        else:
                            log("[GIT] 没有变更需要提交")
                    except Exception as e:
                        log_error(f"Git 提交失败: {e}")

            # 重置重试和超时计数
            try:
                retry_file.unlink()
            except:
                pass
            try:
                timeout_count_file.unlink()
            except:
                pass

        # ==================================================================
        #                   阶段未完成处理
        # ==================================================================
        if not is_completed:
            if is_timeout_failure:
                # 超时失败：增加超时计数
                timeout_count += 1
                timeout_count_file.write_text(str(timeout_count))

                if timeout_count >= MAX_TIMEOUT_RETRIES:
                    log_error(f"[TIMEOUT] 任务 {current_task_id} 的 {current_stage} 阶段超时重试次数过多 ({timeout_count}/{MAX_TIMEOUT_RETRIES})")
                    log_error("[SKIP] 将暂时跳过此任务，继续处理其他任务")
                    skip_file.touch()
                    try:
                        timeout_count_file.unlink()
                    except:
                        pass
                else:
                    log(f"[TIMEOUT] 任务 {current_task_id} 的 {current_stage} 阶段超时 ({timeout_count}/{MAX_TIMEOUT_RETRIES})")
                    next_timeout = int(BASE_SILENCE_TIMEOUT * math.pow(TIMEOUT_BACKOFF_FACTOR, timeout_count))
                    log(f"[INFO] 下次重试将使用更长的超时时间: {next_timeout}秒")
                    log("[INFO] 将在下次循环中重试")
            else:
                # 逻辑错误：增加重试计数
                current_retry_count += 1
                retry_file.write_text(str(current_retry_count))

                log(f"[WARN] 任务 {current_task_id} 的 {current_stage} 阶段尚未完成 (尝试 {current_retry_count}/{MAX_RETRIES})")
                log("[INFO] 将在下次循环中重试")

                if current_retry_count >= MAX_RETRIES:
                    log_error(f"[RETRY] 任务 {current_task_id} 的 {current_stage} 阶段已达到最大重试次数 ({MAX_RETRIES})")
                    log_error("[SKIP] 将跳过此任务并继续处理其他任务")
                    skip_file.touch()

        print("")
        log(f"[SLEEP] 等待 {LOOP_SLEEP}秒后继续...")
        _safe_print("")
        time.sleep(LOOP_SLEEP)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("[BREAK] 用户中断，退出程序")
        sys.exit(0)
    except Exception as e:
        log_error(f"程序异常: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
