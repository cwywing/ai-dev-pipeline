#!/usr/bin/env python3
"""
Output the next pending stage from task-index.json in a prompt-friendly format.
支持三阶段质量保证系统：dev → test → review

支持验证类任务自动执行（2026-02-16 优化）

Returns exit code 1 if no pending stages exist.
"""

import json
import sys
import os
import subprocess
from datetime import datetime
from pathlib import Path

# 导入统一输出模块
from console_output import success, error, warning, info

# Load .env file if it exists (before ENABLE_AUTO_VALIDATION is used)
def load_env_file(env_path: str = '.harness/.env'):
    """Load environment variables from .env file"""
    env_file = Path(env_path)
    if env_file.exists():
        with open(env_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key.strip()] = value.strip()

load_env_file()

# 导入任务编解码器
from task_utils import TaskCodec, load_tasks, save_tasks

# 导入依赖检查
try:
    from context_manager import check_dependencies as check_task_dependencies
    DEPENDENCY_CHECK_ENABLED = True
except ImportError:
    DEPENDENCY_CHECK_ENABLED = False
    warning("无法导入 context_manager，依赖检查功能将不可用", file=sys.stderr)

# 导入单文件存储系统
try:
    from task_file_storage import TaskFileStorage
    _storage = None  # 延迟初始化
except ImportError:
    _storage = None
    warning("无法导入 TaskFileStorage，单文件存储功能将不可用", file=sys.stderr)


def _get_storage():
    """获取 TaskFileStorage 实例（延迟初始化）"""
    global _storage
    if _storage is None:
        try:
            from task_file_storage import TaskFileStorage
            _storage = TaskFileStorage()
            _storage.initialize()
        except Exception as e:
            warning(f"初始化 TaskFileStorage 失败: {e}", file=sys.stderr)
            return None
    return _storage


def run_validation_task(task_id, task):
    """
    自动执行验证类任务

    Args:
        task_id: 任务 ID
        task: 任务字典

    Returns:
        bool: 执行是否成功
    """
    category = task.get('category', '')

    info(f"检测到验证类任务: {task_id} (category: {category})", file=sys.stderr)

    # 获取执行命令
    command = VALIDATION_COMMANDS.get(category)
    if not command:
        warning(f"未定义 category '{category}' 的验证命令", file=sys.stderr)
        return False

    info(f"自动执行验证命令: {command}", file=sys.stderr)

    # 执行命令
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=600  # 10分钟超时
        )

        if result.returncode == 0:
            success(f"验证任务 {task_id} 执行成功", file=sys.stderr)

            # 标记所有阶段为完成
            mark_task_stages_complete(task_id)
            return True
        else:
            error(f"验证任务 {task_id} 执行失败 (退出码: {result.returncode})", file=sys.stderr)
            info(f"输出: {result.stdout}", file=sys.stderr)
            info(f"错误: {result.stderr}", file=sys.stderr)
            return False

    except subprocess.TimeoutExpired:
        warning(f"验证任务 {task_id} 执行超时（10分钟）", file=sys.stderr)
        return False
    except Exception as e:
        warning(f"验证任务 {task_id} 执行异常: {e}", file=sys.stderr)
        return False


def mark_task_stages_complete(task_id):
    """标记任务的所有阶段为完成"""
    try:
        # 优先使用 TaskFileStorage
        storage = _get_storage()
        if storage is not None:
            task = storage.load_task(task_id)
            if not task:
                error(f"未找到任务 {task_id}", file=sys.stderr)
                return False

            # 确保 stages 字段存在
            if 'stages' not in task:
                task['stages'] = {
                    'dev': {'completed': False, 'completed_at': None, 'issues': []},
                    'test': {'completed': False, 'completed_at': None, 'issues': [], 'test_results': {}},
                    'review': {'completed': False, 'completed_at': None, 'issues': [], 'risk_level': None}
                }

            # 标记所有阶段为完成
            now = datetime.now().isoformat()

            for stage_name in ['dev', 'test', 'review']:
                task['stages'][stage_name]['completed'] = True
                task['stages'][stage_name]['completed_at'] = now

            # 标记任务为完成
            task['passes'] = True

            # 保存任务（会自动移动到 completed）
            if storage.save_task(task):
                success(f"任务 {task_id} 的所有阶段已标记为完成", file=sys.stderr)
                return True
            else:
                error(f"保存任务 {task_id} 失败", file=sys.stderr)
                return False

        # 回退到旧方式
        # 使用 TaskCodec 加载和保存
        data = load_tasks()

        # 查找并更新任务
        for task in data.get('tasks', []):
            if task['id'] == task_id:
                # 确保 stages 字段存在
                if 'stages' not in task:
                    task['stages'] = {
                        'dev': {'completed': False, 'completed_at': None, 'issues': []},
                        'test': {'completed': False, 'completed_at': None, 'issues': [], 'test_results': {}},
                        'review': {'completed': False, 'completed_at': None, 'issues': [], 'risk_level': None}
                    }

                # 标记所有阶段为完成
                now = datetime.now().isoformat()

                for stage_name in ['dev', 'test', 'review']:
                    task['stages'][stage_name]['completed'] = True
                    task['stages'][stage_name]['completed_at'] = now

                # 标记任务为完成
                task['passes'] = True
                success(f"任务 {task_id} 的所有阶段已标记为完成", file=sys.stderr)
                break

        # 保存到 task.json（使用 TaskCodec）
        save_tasks(data)

        return True

    except Exception as e:
        warning(f"标记任务完成失败: {e}", file=sys.stderr)
        return False


# ═══════════════════════════════════════════════════════════════
#                   验证类任务配置
# ═══════════════════════════════════════════════════════════════

# 验证类任务的 category
VALIDATION_CATEGORIES = ['test', 'style', 'validation']

# 自动执行的命令映射
VALIDATION_COMMANDS = {
    'test': 'php8 artisan test',
    'style': './vendor/bin/pint --test',
}

# 是否启用验证任务自动执行
ENABLE_AUTO_VALIDATION = os.environ.get('ENABLE_AUTO_VALIDATION', 'true').lower() == 'true'


def get_next_pending_stage():
    """获取下一个待处理的阶段"""
    # 优先使用 TaskFileStorage
    storage = _get_storage()
    if storage is not None:
        try:
            # 加载所有待处理任务
            tasks = storage.load_all_pending_tasks()

            # 获取跳过的任务列表
            skip_dir = os.path.join(storage.harness_dir, '.automation_skip')
            skipped_tasks = set()
            if os.path.exists(skip_dir):
                for f in os.listdir(skip_dir):
                    skipped_tasks.add(f)

            # Sort tasks by priority (P0 < P1 < P2 < P3)
            priority_order = {'P0': 0, 'P1': 1, 'P2': 2, 'P3': 3}
            tasks_sorted = sorted(tasks, key=lambda t: priority_order.get(t.get('priority', 'P2'), 1))

            # Find the first task with pending stages
            for task in tasks_sorted:
                task_id = task['id']

                # Skip if task is permanently skipped
                if task_id in skipped_tasks:
                    continue

                # ═══════════════════════════════════════════════════════════════
                #                   验证类任务自动执行
                # ═══════════════════════════════════════════════════════════════
                if ENABLE_AUTO_VALIDATION:
                    category = task.get('category', '')
                    if category in VALIDATION_CATEGORIES:
                        # 检查任务是否已完成
                        if task.get('passes', False):
                            continue

                        # 自动执行验证任务
                        info(f"\n{'='*60}", file=sys.stderr)
                        info(f"自动化系统检测到验证类任务", file=sys.stderr)
                        info(f"{'='*60}\n", file=sys.stderr)

                        success_result = run_validation_task(task_id, task)

                        if success_result:
                            # 任务成功完成，继续下一个任务
                            success(f"验证任务 {task_id} 已自动完成，继续下一个任务\n", file=sys.stderr)
                            continue
                        else:
                            # 验证失败，跳过此任务避免无限循环
                            warning(f"验证任务 {task_id} 自动执行失败", file=sys.stderr)
                            info(f"将跳过此任务，继续处理其他任务", file=sys.stderr)
                            info(f"提示：你可以手动修复问题后，删除 .automation_skip/{task_id} 文件重新尝试\n", file=sys.stderr)

                            # 标记为跳过，避免无限循环
                            skip_dir = os.path.join(storage.harness_dir, '.automation_skip')
                            os.makedirs(skip_dir, exist_ok=True)
                            with open(f"{skip_dir}/{task_id}", 'w') as f:
                                f.write(f"自动执行失败于 {datetime.now().isoformat()}\n")

                            continue

                # Check if task has stages field
                if 'stages' not in task:
                    # Old format, use passes field
                    if not task.get('passes', False):
                        # ═══════════════════════════════════════════════════════════════
                        #                   依赖检查（新增）
                        # ═══════════════════════════════════════════════════════════════
                        if DEPENDENCY_CHECK_ENABLED and 'depends_on' in task:
                            dep_result = check_task_dependencies(storage, task)
                            if not dep_result['satisfied']:
                                info(f"跳过任务 {task_id}：依赖未满足", file=sys.stderr)
                                for dep in dep_result['blocking_deps']:
                                    info(f"  - {dep['task_id']}: {dep.get('reason', '')}", file=sys.stderr)
                                continue
                            if dep_result['warnings']:
                                for w in dep_result['warnings']:
                                    warning(f"  ⚠️  {w}", file=sys.stderr)

                        return {
                            'task_id': task_id,
                            'stage': 'dev',
                            'task': task,
                            'is_legacy': True,
                            'dependencies': task.get('depends_on', {})
                        }
                else:
                    # New format, check stages in order
                    stages = task['stages']

                    # Ensure all stages exist
                    for stage_name in ['dev', 'test', 'review']:
                        if stage_name not in stages:
                            stages[stage_name] = {'completed': False}

                    # ═══════════════════════════════════════════════════════════════
                    #                   依赖检查（新增）
                    # ═══════════════════════════════════════════════════════════════
                    should_skip = False
                    if DEPENDENCY_CHECK_ENABLED and 'depends_on' in task:
                        dep_result = check_task_dependencies(storage, task)
                        if not dep_result['satisfied']:
                            info(f"⏸️  跳过任务 {task_id}：依赖未满足", file=sys.stderr)
                            for dep in dep_result['blocking_deps']:
                                stage_info = f" ({dep.get('stage', 'dev')})" if dep.get('stage') else ""
                                info(f"  ❌ {dep['task_id']}{stage_info}: {dep.get('reason', '未完成')}", file=sys.stderr)
                            should_skip = True
                        elif dep_result['warnings']:
                            info(f"⚠️  任务 {task_id} 依赖警告：", file=sys.stderr)
                            for w in dep_result['warnings']:
                                warning(f"  {w}", file=sys.stderr)

                    if should_skip:
                        continue

                    # Stage 1: dev
                    if not stages['dev']['completed']:
                        return {
                            'task_id': task_id,
                            'stage': 'dev',
                            'task': task,
                            'is_legacy': False,
                            'dependencies': task.get('depends_on', {})
                        }

                    # Stage 2: test
                    if not stages['test']['completed']:
                        return {
                            'task_id': task_id,
                            'stage': 'test',
                            'task': task,
                            'is_legacy': False
                        }

                    # Stage 3: review
                    if not stages['review']['completed']:
                        return {
                            'task_id': task_id,
                            'stage': 'review',
                            'task': task,
                            'is_legacy': False
                        }

                    # Stage 4: validation（新增：满意度验证阶段）
                    # 只在 validation 配置启用时进入该阶段
                    validation_config = task.get('validation', {})
                    if validation_config.get('enabled', False):
                        if not stages.get('validation', {}).get('completed', False):
                            return {
                                'task_id': task_id,
                                'stage': 'validation',
                                'task': task,
                                'is_legacy': False
                            }

            # No pending stages
            return None

        except FileNotFoundError:
            error(f"task-index.json not found", file=sys.stderr)
            sys.exit(2)
        except json.JSONDecodeError as e:
            error(f"Invalid JSON in task-index.json: {e}", file=sys.stderr)
            sys.exit(2)

    # 回退到旧方式
    try:
        # 使用 TaskCodec 加载
        data = load_tasks()

        # 获取跳过的任务列表
        skip_dir = os.path.join(os.path.dirname(__file__), '..', '.automation_skip')
        skipped_tasks = set()
        if os.path.exists(skip_dir):
            for f in os.listdir(skip_dir):
                skipped_tasks.add(f)

        # Find the first task with pending stages
        for task in data.get('tasks', []):
            task_id = task['id']

            # Skip if task is permanently skipped
            if task_id in skipped_tasks:
                continue

            # ═══════════════════════════════════════════════════════════════
            #                   验证类任务自动执行
            # ═══════════════════════════════════════════════════════════════
            if ENABLE_AUTO_VALIDATION:
                category = task.get('category', '')
                if category in VALIDATION_CATEGORIES:
                    # 检查任务是否已完成
                    if task.get('passes', False):
                        continue

                    # 自动执行验证任务
                    info(f"\n{'='*60}", file=sys.stderr)
                    info(f"自动化系统检测到验证类任务", file=sys.stderr)
                    info(f"{'='*60}\n", file=sys.stderr)

                    success_result = run_validation_task(task_id, task)

                    if success_result:
                        # 任务成功完成，继续下一个任务
                        success(f"验证任务 {task_id} 已自动完成，继续下一个任务\n", file=sys.stderr)
                        continue
                    else:
                        # 验证失败，跳过此任务避免无限循环
                        warning(f"验证任务 {task_id} 自动执行失败", file=sys.stderr)
                        info(f"将跳过此任务，继续处理其他任务", file=sys.stderr)
                        info(f"提示：你可以手动修复问题后，删除 .automation_skip/{task_id} 文件重新尝试\n", file=sys.stderr)

                        # 标记为跳过，避免无限循环
                        skip_dir = os.path.join(os.path.dirname(__file__), '..', '.automation_skip')
                        os.makedirs(skip_dir, exist_ok=True)
                        with open(f"{skip_dir}/{task_id}", 'w') as f:
                            f.write(f"自动执行失败于 {datetime.now().isoformat()}\n")

                        continue

            # Check if task has stages field
            if 'stages' not in task:
                # Old format, use passes field
                if not task.get('passes', False):
                    return {
                        'task_id': task_id,
                        'stage': 'dev',
                        'task': task,
                        'is_legacy': True
                    }
            else:
                # New format, check stages in order
                stages = task['stages']

                # Ensure all stages exist
                for stage_name in ['dev', 'test', 'review']:
                    if stage_name not in stages:
                        stages[stage_name] = {'completed': False}

                # Stage 1: dev
                if not stages['dev']['completed']:
                    return {
                        'task_id': task_id,
                        'stage': 'dev',
                        'task': task,
                        'is_legacy': False
                    }

                # Stage 2: test
                if not stages['test']['completed']:
                    return {
                        'task_id': task_id,
                        'stage': 'test',
                        'task': task,
                        'is_legacy': False
                    }

                # Stage 3: review
                if not stages['review']['completed']:
                    return {
                        'task_id': task_id,
                        'stage': 'review',
                        'task': task,
                        'is_legacy': False
                    }

                # Stage 4: validation（新增：满意度验证阶段）
                validation_config = task.get('validation', {})
                if validation_config.get('enabled', False):
                    if not stages.get('validation', {}).get('completed', False):
                        return {
                            'task_id': task_id,
                            'stage': 'validation',
                            'task': task,
                            'is_legacy': False
                        }

        # No pending stages
        return None

    except FileNotFoundError:
        error(f"task.json not found", file=sys.stderr)
        sys.exit(2)
    except json.JSONDecodeError as e:
        error(f"Invalid JSON in task.json: {e}", file=sys.stderr)
        sys.exit(2)


def main():
    next_stage = get_next_pending_stage()

    if next_stage is None:
        # 检查是否所有任务都完成了
        data = load_tasks()

        has_pending = False
        for task in data.get('tasks', []):
            if 'stages' in task:
                # 检查标准阶段
                dev_test_review_complete = all([
                    task['stages']['dev']['completed'],
                    task['stages']['test']['completed'],
                    task['stages']['review']['completed']
                ])

                # 检查 validation 阶段（如果启用）
                validation_config = task.get('validation', {})
                validation_complete = True
                if validation_config.get('enabled', False):
                    validation_complete = task['stages'].get('validation', {}).get('completed', False)

                if not dev_test_review_complete or not validation_complete:
                    has_pending = True
                    break
            else:
                if not task.get('passes', False):
                    has_pending = True
                    break

        if has_pending:
            # 有未完成的阶段，但都被跳过了
            info("# All pending stages are skipped", file=sys.stderr)
            info("# No valid stages remaining to process", file=sys.stderr)
            sys.exit(1)
        else:
            info("# All stages completed")
        sys.exit(1)

    # Output in a prompt-friendly format
    task = next_stage['task']
    task_id = next_stage['task_id']
    stage = next_stage['stage']

    info(f"## Current Task & Stage")
    info(f"**Task ID:** {task_id}")
    info(f"**Current Stage:** {stage.upper()}")
    info(f"**Category:** {task.get('category', 'general')}")
    info(f"**Description:** {task['description']}")
    info("")

    # Stage-specific information
    if stage == 'dev':
        info(f"**Stage Goal:** 实现功能（不要求完美）")
        info(f"**Next Stage:** test")
    elif stage == 'test':
        info(f"**Stage Goal:** 测试并发现问题")
        info(f"**Next Stage:** review")

        # Show artifacts from dev stage
        info(f"**Artifacts to Test:**")
        artifacts = get_task_artifacts(task_id)
        if artifacts:
            for artifact in artifacts:
                info(f"  - {artifact}")
        else:
            info(f"  (暂无产出记录)")
    elif stage == 'review':
        info(f"**Stage Goal:** 代码审查和质量评估")
        info(f"**Next Stage:** complete")

        # Show artifacts
        info(f"**Artifacts to Review:**")
        artifacts = get_task_artifacts(task_id)
        if artifacts:
            for artifact in artifacts:
                info(f"  - {artifact}")
        else:
            info(f"  (暂无产出记录)")

        # Show test results
        if 'stages' in task and task['stages']['test'].get('test_results'):
            info(f"**Test Results:**")
            for test_name, result in task['stages']['test']['test_results'].items():
                status = "[OK]" if result.get('passed') else "[FAIL]"
                info(f"  {status} {test_name}: {result.get('message', 'N/A')}")

    elif stage == 'validation':
        info(f"**Stage Goal:** Satisfaction Validation - Claude 独立评估实现是否满足要求")
        info(f"**Next Stage:** complete")

        # Show validation config
        validation_config = task.get('validation', {})
        if validation_config.get('enabled', False):
            info(f"**Validation Config:**")
            info(f"   Threshold: {validation_config.get('threshold', 0.8)}")
            info(f"   Max Retries: {validation_config.get('max_retries', 3)}")

        # Show artifacts for review
        info(f"**Artifacts to Validate:**")
        artifacts = get_task_artifacts(task_id)
        if artifacts:
            for artifact in artifacts:
                info(f"  - {artifact}")
        else:
            info(f"  (暂无产出记录)")


    info("")

    # 显示当前阶段的问题（被打回重修时）
    if 'stages' in task and stage in task['stages']:
        issues = task['stages'][stage].get('issues', [])
        if issues:
            info(f"之前执行失败，被打回重修！需要解决以下问题:")
            for i, issue in enumerate(issues, 1):
                info(f"  {i}. {issue}")
            info("")

    # Show previous stage issues if any（兼容逻辑）
    if stage in ['test', 'review'] and 'stages' in task:
        prev_stage = 'dev' if stage == 'test' else 'test'
        prev_issues = task['stages'][prev_stage].get('issues', [])
        # 只有当前阶段没有问题时，才显示前一阶段的问题
        if not issues and prev_issues:
            info(f"Issues from {prev_stage.upper()} stage:")
            for i, issue in enumerate(prev_issues, 1):
                info(f"  {i}. {issue}")
            info("")

    info(f"**Acceptance Criteria:**")
    for i, criterion in enumerate(task.get('acceptance', []), 1):
        info(f"  {i}. {criterion}")
    info("")

    return 0


def get_task_artifacts(task_id):
    """获取任务的产出清单"""
    try:
        artifacts_dir = os.path.join(os.path.dirname(__file__), '..', 'artifacts')
        artifact_file = os.path.join(artifacts_dir, f'{task_id}.json')

        if not os.path.exists(artifact_file):
            return []

        with open(artifact_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        return data.get('files', [])
    except:
        return []


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(2)
