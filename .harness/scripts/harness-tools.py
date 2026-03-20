#!/usr/bin/env python3
"""
Harness 工具脚本
提供任务状态查询、进度管理等功能
供 AI Agent 调用，不直接执行开发任务

使用示例：
    python3 .harness/scripts/harness-tools.py --action current
    python3 .harness/scripts/harness-tools.py --action mark-done --id Infra_001
    python3 .harness/scripts/harness-tools.py --action update-progress --id Infra_001 ...
"""

import sys
import argparse
import glob
import json
from pathlib import Path
from datetime import datetime
from typing import List

# 导入统一输出模块
from console_output import success, error, warning, info

# 导入任务编解码器
from task_utils import TaskCodec, load_tasks, save_tasks, get_task_json_path

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


def _cleanup_pending_file(task_id: str):
    """
    清理 pending 目录中的任务文件（如果任务已完成）

    Args:
        task_id: 任务 ID
    """
    storage = _get_storage()
    if storage is None:
        return  # 单文件存储不可用，跳过清理

    try:
        pending_file = storage.pending_dir / f'{task_id}.json'
        if pending_file.exists():
            pending_file.unlink()
            success(f"已删除 pending 目录中的文件: {pending_file}", file=sys.stderr)
    except Exception as e:
        warning(f"清理 pending 文件失败 {task_id}: {e}", file=sys.stderr)


def _sync_to_knowledge_base(task_id: str):
    """
    将任务产出同步到知识库

    Args:
        task_id: 任务 ID
    """
    import subprocess
    try:
        result = subprocess.run(
            ['python3', '.harness/scripts/knowledge.py', '--action', 'sync', '--task-id', task_id],
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace'
        )
        if result.returncode == 0:
            success(f"任务 {task_id} 的产出已同步到知识库", file=sys.stderr)
        else:
            warning(f"同步知识库失败: {result.stderr}", file=sys.stderr)
    except Exception as e:
        warning(f"同步知识库异常: {e}", file=sys.stderr)


def run_code_standards_check() -> tuple:
    """
    运行代码规范检查

    Returns:
        (issue_count, output) 元组 - 问题数量和检查输出
    """
    import subprocess
    try:
        script_path = Path(__file__).parent / 'check_code_standards.py'
        if not script_path.exists():
            return (0, "")

        result = subprocess.run(
            ['python3', str(script_path)],
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace'
        )
        return (1 if result.returncode != 0 else 0, result.stdout + result.stderr)
    except Exception as e:
        warning(f"运行代码规范检查失败: {e}", file=sys.stderr)
        return (0, "")


def action_current(args):
    """显示当前待处理任务"""
    # 优先使用 TaskFileStorage
    storage = _get_storage()
    if storage is not None:
        tasks = storage.load_all_pending_tasks()
        for task in tasks:
            if not task.get('passes', False):
                info(f"任务 ID: {task['id']}")
                info(f"类别: {task.get('category', 'general')}")
                info(f"描述: {task['description']}")
                info("")
                info("验收标准:")
                for i, criterion in enumerate(task.get('acceptance', []), 1):
                    info(f"  {i}. {criterion}")
                return 0
        success("所有任务已完成！")
        return 1

    # 回退到旧方式
    data = load_tasks()

    # 找到第一个 passes=false 的任务
    for task in data.get('tasks', []):
        if not task.get('passes', False):
            info(f"任务 ID: {task['id']}")
            info(f"类别: {task.get('category', 'general')}")
            info(f"描述: {task['description']}")
            info("")
            info("验收标准:")
            for i, criterion in enumerate(task.get('acceptance', []), 1):
                info(f"  {i}. {criterion}")
            return 0

    success("所有任务已完成！")
    return 1


def action_mark_done(args):
    """标记任务为完成（兼容旧版，标记所有阶段为完成）"""
    if not args.id:
        error("需要提供 --id 参数", file=sys.stderr)
        return 1

    # 如果提供了 --files 参数，记录产出
    if args.files:
        try:
            # 调用产出管理工具记录文件
            import subprocess
            result = subprocess.run(
                ['python3', '.harness/scripts/artifacts.py', '--action', 'record', '--id', args.id] + args.files,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace'
            )
            if result.returncode != 0:
                warning(f"记录产出失败: {result.stderr}", file=sys.stderr)
        except Exception as e:
            warning(f"记录产出异常: {e}", file=sys.stderr)

    # 优先使用 TaskFileStorage
    storage = _get_storage()
    if storage is not None:
        task = storage.load_task(args.id)
        if not task:
            error(f"未找到任务 {args.id}", file=sys.stderr)
            return 1

        # 检查是否已经完成
        if task.get('passes', False):
            info(f"任务 {args.id} 已经是完成状态", file=sys.stderr)
            # 即使任务已完成，也要清理 pending 文件（防止残留）
            _cleanup_pending_file(args.id)
            return 0

        # 标记为完成
        task['passes'] = True
        task['stages'] = {
            'dev': {'completed': True, 'completed_at': datetime.now().isoformat(), 'issues': []},
            'test': {'completed': True, 'completed_at': datetime.now().isoformat(), 'issues': [], 'test_results': {}},
            'review': {'completed': True, 'completed_at': datetime.now().isoformat(), 'issues': [], 'risk_level': None}
        }

        # 保存任务（会自动移动到 completed）
        if storage.save_task(task):
            success(f"任务 {args.id} 已标记为完成", file=sys.stderr)
            _cleanup_pending_file(args.id)
            return 0
        else:
            error(f"保存任务 {args.id} 失败", file=sys.stderr)
            return 1

    # 回退到旧方式
    data = load_tasks()

    # 查找并更新任务
    task_found = False
    for task in data.get('tasks', []):
        if task['id'] == args.id:
            # 检查是否已经完成
            if task.get('passes', False):
                info(f"任务 {args.id} 已经是完成状态", file=sys.stderr)
                # 即使任务已完成，也要清理 pending 文件（防止残留）
                _cleanup_pending_file(args.id)
                return 0

            task['passes'] = True
            task_found = True
            success(f"任务 {args.id} 已标记为完成", file=sys.stderr)
            break

    if not task_found:
        error(f"未找到任务 {args.id}", file=sys.stderr)
        return 1

    # 保存到 task.json
    save_tasks(data)

    # 清理 pending 目录中的文件（如果任务已完成）
    _cleanup_pending_file(args.id)

    return 0


def action_mark_stage(args):
    """标记任务阶段为完成（三阶段系统）"""
    if not args.id:
        error("需要提供 --id 参数", file=sys.stderr)
        return 1

    if not args.stage:
        error("需要提供 --stage 参数 (dev/test/review)", file=sys.stderr)
        return 1

    # 验证 stage 参数
    valid_stages = ['dev', 'test', 'review']
    if args.stage not in valid_stages:
        error(f"无效的 stage '{args.stage}'，必须是 {valid_stages}", file=sys.stderr)
        return 1

    # 强制要求：Dev 阶段必须提供 --files 参数
    if args.stage == 'dev':
        if not args.files:
            error("Dev 阶段必须提供 --files 参数！", file=sys.stderr)
            error("", file=sys.stderr)
            info("正确用法：", file=sys.stderr)
            info("  python3 .harness/scripts/harness-tools.py --action mark-stage \\", file=sys.stderr)
            info("    --id TASK_ID --stage dev \\", file=sys.stderr)
            info("    --files database/migrations/xxx.php \\", file=sys.stderr)
            info("           app/Models/Tenant.php \\", file=sys.stderr)
            info("           tests/Unit/TenantTest.cpp", file=sys.stderr)
            info("", file=sys.stderr)
            info("如果没有创建新文件（仅修改），使用：", file=sys.stderr)
            info("  --files ''", file=sys.stderr)
            info("", file=sys.stderr)
            error("--files 参数用于追踪产出，这是质量保证系统的核心功能！", file=sys.stderr)
            return 1

    # 如果提供了 --files 参数，记录产出（仅在 dev 阶段）
    if args.files and args.stage == 'dev':
        try:
            import subprocess
            cmd = ['python3', '.harness/scripts/artifacts.py', '--action', 'record', '--id', args.id, '--files'] + args.files

            # 添加扩展参数
            if hasattr(args, 'design_decisions') and args.design_decisions:
                cmd.extend(['--design-decisions'] + args.design_decisions)
            if hasattr(args, 'interface_contracts') and args.interface_contracts:
                cmd.extend(['--interface-contracts'] + args.interface_contracts)
            if hasattr(args, 'constraints') and args.constraints:
                cmd.extend(['--constraints'] + args.constraints)

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace'
            )
            if result.returncode != 0:
                warning(f"记录产出失败: {result.stderr}", file=sys.stderr)
        except Exception as e:
            warning(f"记录产出异常: {e}", file=sys.stderr)

    # 优先使用 TaskFileStorage
    storage = _get_storage()
    if storage is not None:
        task = storage.load_task(args.id)
        if not task:
            error(f"未找到任务 {args.id}", file=sys.stderr)
            return 1

        # 确保 stages 字段存在
        if 'stages' not in task:
            task['stages'] = {
                'dev': {'completed': False, 'completed_at': None, 'issues': []},
                'test': {'completed': False, 'completed_at': None, 'issues': [], 'test_results': {}},
                'review': {'completed': False, 'completed_at': None, 'issues': [], 'risk_level': None}
            }

        stage_info = task['stages'][args.stage]

        # 检查是否已经完成
        if stage_info['completed']:
            info(f"任务 {args.id} 的 {args.stage} 阶段已经是完成状态", file=sys.stderr)
            # 即使阶段已完成，也要检查是否所有阶段都完成并清理 pending 文件
            if 'stages' in task and all([
                task['stages']['dev']['completed'],
                task['stages']['test']['completed'],
                task['stages']['review']['completed']
            ]):
                _cleanup_pending_file(args.id)
            return 0

        # 处理状态和问题
        status = getattr(args, 'status', 'passed')

        # 处理问题列表（在 if/else 之外定义，避免作用域问题）
        issues_list = getattr(args, 'issues', [])
        if isinstance(args.issues, str):
            issues_list = [issue.strip() for issue in args.issues.split(',')]
        elif args.issues:
            issues_list = args.issues

        if status == 'failed':
            # Fail Fast: 失败时不标记为完成，形成自我修复闭环
            stage_info['completed'] = False
            stage_info['issues'] = issues_list

            warning(f"阶段 {args.stage} 执行失败！记录了 {len(issues_list)} 个问题", file=sys.stderr)

            # 状态回滚机制（State Regression）
            if args.stage == 'test':
                # 测试失败：回滚到 Dev 阶段重修
                info("测试不通过，正在将任务打回 Dev 阶段重修...", file=sys.stderr)
                task['stages']['dev']['completed'] = False
                # 把测试报的错丢给 Dev 阶段
                task['stages']['dev']['issues'] = issues_list
                info(f"已将 {len(issues_list)} 个问题传递给 Dev 阶段", file=sys.stderr)

            elif args.stage == 'review':
                # Review 失败：回滚到 Dev 阶段（代码改了必须重新测试）
                info("Review 被拒，正在将任务打回 Dev 阶段重修...", file=sys.stderr)
                task['stages']['dev']['completed'] = False
                task['stages']['test']['completed'] = False  # 代码改了，必须重新测试
                task['stages']['dev']['issues'] = issues_list
                info(f"已重置 Test 和 Dev 阶段，并将 {len(issues_list)} 个问题传递给 Dev", file=sys.stderr)

            # 关键：必须保存回滚后的状态！
            try:
                storage.save_task(task)
            except Exception as e:
                error(f"保存状态失败: {e}", file=sys.stderr)
                return 2

            # 返回非 0 表示失败
            return 1

        else:
            # Test 阶段：先运行代码规范检查
            if args.stage == 'test':
                info("", file=sys.stderr)
                info("=" * 60, file=sys.stderr)
                info("[CODE STANDARDS CHECK] Test 阶段开始前自动检查...", file=sys.stderr)
                info("=" * 60, file=sys.stderr)

                issue_count, check_output = run_code_standards_check()
                if check_output:
                    print(check_output, file=sys.stderr)

                if issue_count > 0:
                    warning(f"代码规范检查发现问题: {issue_count} 个问题", file=sys.stderr)
                    warning("建议: 在进入测试阶段前修复这些问题", file=sys.stderr)
                    info("", file=sys.stderr)
                else:
                    success("代码规范检查通过！", file=sys.stderr)
                    info("", file=sys.stderr)

            # 成功：标记为完成
            stage_info['completed'] = True
            stage_info['completed_at'] = datetime.now().isoformat()
            # 成功了就清空之前的报错信息
            stage_info.pop('issues', None)
            success(f"任务 {args.id} 的 {args.stage} 阶段已标记为完成", file=sys.stderr)

        # 处理测试结果（仅 test 阶段）
        if args.stage == 'test' and hasattr(args, 'test_results') and args.test_results:
            try:
                stage_info['test_results'] = json.loads(args.test_results)
                success(f"测试结果已记录到任务文件", file=sys.stderr)
            except json.JSONDecodeError as e:
                warning(f"解析 test_results JSON 失败: {e}", file=sys.stderr)
            except Exception as e:
                warning(f"处理 test_results 时发生错误: {e}", file=sys.stderr)

        # 检查是否所有阶段都完成，如果是则标记 passes 为 true
        # 注意：如果启用了 validation，则还需检查 validation 阶段
        all_stages_complete = all([
            task['stages']['dev']['completed'],
            task['stages']['test']['completed'],
            task['stages']['review']['completed']
        ])

        # 检查是否需要 validation 阶段
        validation_config = task.get('validation') or {}
        if validation_config.get('enabled', False):
            validation_completed = task['stages'].get('validation', {}).get('completed', False)
            all_stages_complete = all_stages_complete and validation_completed
            if not validation_completed and args.stage == 'review':
                success(f"任务 {args.id} 的 review 阶段已完成，等待 Satisfaction Validation", file=sys.stderr)
            elif validation_completed:
                task['passes'] = True
                success(f"任务 {args.id} 的所有阶段（含 validation）已完成", file=sys.stderr)
        else:
            # 旧任务：没有 validation 配置，review 完成即任务完成
            if all_stages_complete:
                task['passes'] = True
                success(f"任务 {args.id} 的所有阶段已完成，标记任务为完成！", file=sys.stderr)

        # 保存任务
        try:
            storage.save_task(task)
        except Exception as e:
            error(f"保存状态失败: {e}", file=sys.stderr)
            return 2

        # 清理 pending 目录中的文件（如果所有阶段都已完成）
        if all_stages_complete:
            _cleanup_pending_file(args.id)
            # 同步到知识库（新增）
            _sync_to_knowledge_base(args.id)

        return 0

    # 回退到旧方式
    data = load_tasks()

    # 查找并更新任务
    task_found = False
    for task in data.get('tasks', []):
        if task['id'] == args.id:
            task_found = True

            # 确保 stages 字段存在
            if 'stages' not in task:
                task['stages'] = {
                    'dev': {'completed': False, 'completed_at': None, 'issues': []},
                    'test': {'completed': False, 'completed_at': None, 'issues': [], 'test_results': {}},
                    'review': {'completed': False, 'completed_at': None, 'issues': [], 'risk_level': None}
                }

            stage_info = task['stages'][args.stage]

            # 检查是否已经完成
            if stage_info['completed']:
                info(f"任务 {args.id} 的 {args.stage} 阶段已经是完成状态", file=sys.stderr)
                # 即使阶段已完成，也要检查是否所有阶段都完成并清理 pending 文件
                if 'stages' in task and all([
                    task['stages']['dev']['completed'],
                    task['stages']['test']['completed'],
                    task['stages']['review']['completed']
                ]):
                    _cleanup_pending_file(args.id)
                return 0

            # 处理状态和问题
            status = getattr(args, 'status', 'passed')

            # 处理问题列表（在 if/else 之外定义，避免作用域问题）
            issues_list = getattr(args, 'issues', [])
            if isinstance(args.issues, str):
                issues_list = [issue.strip() for issue in args.issues.split(',')]
            elif args.issues:
                issues_list = args.issues

            if status == 'failed':
                # Fail Fast: 失败时不标记为完成，形成自我修复闭环
                stage_info['completed'] = False
                stage_info['issues'] = issues_list

                warning(f"阶段 {args.stage} 执行失败！记录了 {len(issues_list)} 个问题", file=sys.stderr)

                # 状态回滚机制（State Regression）
                if args.stage == 'test':
                    # 测试失败：回滚到 Dev 阶段重修
                    info("测试不通过，正在将任务打回 Dev 阶段重修...", file=sys.stderr)
                    task['stages']['dev']['completed'] = False
                    # 把测试报的错丢给 Dev 阶段
                    task['stages']['dev']['issues'] = issues_list
                    info(f"已将 {len(issues_list)} 个问题传递给 Dev 阶段", file=sys.stderr)

                elif args.stage == 'review':
                    # Review 失败：回滚到 Dev 阶段（代码改了必须重新测试）
                    info("Review 被拒，正在将任务打回 Dev 阶段重修...", file=sys.stderr)
                    task['stages']['dev']['completed'] = False
                    task['stages']['test']['completed'] = False  # 代码改了，必须重新测试
                    task['stages']['dev']['issues'] = issues_list
                    info(f"已重置 Test 和 Dev 阶段，并将 {len(issues_list)} 个问题传递给 Dev", file=sys.stderr)

                # 关键：必须保存回滚后的状态！
                try:
                    save_tasks(data)
                except Exception as e:
                    error(f"保存状态失败: {e}", file=sys.stderr)
                    return 2

                # 返回非 0 表示失败
                return 1

            else:
                # 成功：标记为完成
                stage_info['completed'] = True
                stage_info['completed_at'] = datetime.now().isoformat()
                # 成功了就清空之前的报错信息
                stage_info.pop('issues', None)
                success(f"任务 {args.id} 的 {args.stage} 阶段已标记为完成", file=sys.stderr)

            # 处理测试结果（仅 test 阶段）
            if args.stage == 'test' and hasattr(args, 'test_results') and args.test_results:
                try:
                    stage_info['test_results'] = json.loads(args.test_results)
                    success(f"测试结果已记录到任务文件", file=sys.stderr)
                except json.JSONDecodeError as e:
                    warning(f"解析 test_results JSON 失败: {e}", file=sys.stderr)
                except Exception as e:
                    warning(f"处理 test_results 时发生错误: {e}", file=sys.stderr)

            # 检查是否所有阶段都完成，如果是则标记 passes 为 true
            all_stages_complete = all([
                task['stages']['dev']['completed'],
                task['stages']['test']['completed'],
                task['stages']['review']['completed']
            ])

            # 检查是否需要 validation 阶段
            validation_config = task.get('validation', {})
            if validation_config.get('enabled', False):
                validation_completed = task['stages'].get('validation', {}).get('completed', False)
                all_stages_complete = all_stages_complete and validation_completed
                if validation_completed:
                    task['passes'] = True
                    success(f"任务 {args.id} 的所有阶段（含 validation）已完成", file=sys.stderr)
                elif args.stage == 'review':
                    success(f"任务 {args.id} 的 review 阶段已完成，等待 Satisfaction Validation", file=sys.stderr)
            else:
                # 旧任务：没有 validation 配置，review 完成即任务完成
                if all_stages_complete:
                    task['passes'] = True
                    success(f"任务 {args.id} 的所有阶段已完成，标记任务为完成！", file=sys.stderr)

            break

    if not task_found:
        error(f"未找到任务 {args.id}", file=sys.stderr)
        return 1

    # 保存到 task.json
    save_tasks(data)

    # 清理 pending 目录中的文件（如果所有阶段都已完成）
    # 检查任务是否完全完成
    if 'stages' in task:
        # 检查是否需要 validation 阶段
        validation_config = task.get('validation') or {}
        if validation_config.get('enabled', False):
            validation_completed = task['stages'].get('validation', {}).get('completed', False)
            if all([
                task['stages']['dev']['completed'],
                task['stages']['test']['completed'],
                task['stages']['review']['completed'],
                validation_completed
            ]):
                _cleanup_pending_file(args.id)
        else:
            # 旧任务：没有 validation 配置
            if all([
                task['stages']['dev']['completed'],
                task['stages']['test']['completed'],
                task['stages']['review']['completed']
            ]):
                _cleanup_pending_file(args.id)

    return 0


def action_stage_status(args):
    """显示任务的所有阶段状态"""
    if not args.id:
        error("需要提供 --id 参数", file=sys.stderr)
        return 1

    data = load_tasks()

    # 查找任务
    task = None
    for t in data.get('tasks', []):
        # 支持新格式('i')和旧格式('id')
        task_id = t.get('i') or t.get('id')
        if task_id == args.id:
            task = t
            break

    if not task:
        error(f"未找到任务 {args.id}", file=sys.stderr)
        return 1

    info(f"任务 ID: {task.get('i') or task.get('id')}")
    info(f"描述: {task.get('d') or task.get('description')}")
    info("")

    # 获取 stages（支持新格式 's' 和旧格式 'stages'）
    stages = task.get('s') or task.get('stages', {})

    # 检查是否有 stages 字段
    if not stages:
        # 旧格式
        status = "完成" if task.get('p', task.get('passes', False)) else "待处理"
        info(f"状态: {status} (无阶段信息)")
        return 0

    # 显示各阶段状态
    info("阶段状态:")

    for stage_name in ['dev', 'test', 'review']:
        stage_info = stages.get(stage_name, {})
        # 支持新格式('c')和旧格式('completed')
        completed = stage_info.get('c', stage_info.get('completed', False))

        if completed:
            status_text = "完成"
            completed_at = stage_info.get('t', stage_info.get('completed_at', 'N/A'))
            if completed_at and isinstance(completed_at, int):
                from datetime import datetime
                completed_at = datetime.fromtimestamp(completed_at).isoformat()
            elif completed_at is None:
                completed_at = 'N/A'
            info(f"  [OK] {stage_name.upper()}: {status_text} (完成于: {completed_at})")
        else:
            status_text = "待处理"
            info(f"  [WAIT] {stage_name.upper()}: {status_text}")

        # 显示问题（支持新格式 'i' 和旧格式 'issues'）
        issues_list = stage_info.get('i', stage_info.get('issues', []))
        if isinstance(issues_list, str):
            issues_list = [issue.strip() for issue in issues_list.split(',')]
        elif not isinstance(issues_list, list):
            issues_list = []

        if issues_list:
            info(f"      问题: {len(issues_list)} 个")
            for i, issue in enumerate(issues_list, 1):
                info(f"        {i}. {issue}")

        # 显示测试结果（仅 test 阶段，支持新格式 'r' 和旧格式 'test_results'）
        if stage_name == 'test':
            test_results = stage_info.get('r', stage_info.get('test_results', {}))
            if test_results:
                info("      测试结果:")
                for test_name, result in test_results.items():
                    test_status = "[OK]" if result.get('passed', result.get('s', result.get('status'))) else "[FAIL]"
                    info(f"        {test_status} {test_name}: {result.get('m', result.get('message', 'N/A'))}")

    # 显示风险等级（仅 review 阶段，支持新格式 'l' 和旧格式 'risk_level'）
    review_info = stages.get('review', {})
    risk_level = review_info.get('l', review_info.get('risk_level'))
    if risk_level is not None:
        info(f"\n风险等级: {risk_level}")

    # 显示整体状态
    all_complete = all([
        stages.get('dev', {}).get('c', stages.get('dev', {}).get('completed', False)),
        stages.get('test', {}).get('c', stages.get('test', {}).get('completed', False)),
        stages.get('review', {}).get('c', stages.get('review', {}).get('completed', False))
    ])

    if all_complete:
        success("\n所有阶段已完成！")
    else:
        # 显示下一个阶段
        if not stages.get('dev', {}).get('c', stages.get('dev', {}).get('completed', False)):
            next_stage = 'dev'
        elif not stages.get('test', {}).get('c', stages.get('test', {}).get('completed', False)):
            next_stage = 'test'
        else:
            next_stage = 'review'
        info(f"\n下一个阶段: {next_stage.upper()}")

    return 0


def action_update_progress(args):
    """更新 .harness/logs/progress.md"""
    if not args.id:
        error("需要提供 --id 参数", file=sys.stderr)
        return 1

    data = load_tasks()

    # 查找任务
    task = None
    for t in data.get('tasks', []):
        # 支持新格式('i')和旧格式('id')
        task_id = t.get('i') or t.get('id')
        if task_id == args.id:
            task = t
            break

    if not task:
        error(f"未找到任务 {args.id}", file=sys.stderr)
        return 1

    # 组装进度内容
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    what_done = args.what_done or "- 任务完成"
    test_result = args.test_result or "- 验证通过"
    next_step = args.next_step or "- 继续下一个任务"

    progress_entry = f"""
### {timestamp} - {args.id}

**描述**: {task['description']}

**做了什么**:
{what_done}

**测试结果**:
{test_result}

**下一步**:
{next_step}

---
"""

    # 追加到 .harness/logs/progress.md
    try:
        with open('.harness/logs/progress.md', 'a', encoding='utf-8') as f:
            f.write(progress_entry)
        success(f"已更新 .harness/logs/progress.md", file=sys.stderr)
        return 0
    except Exception as e:
        error(f"无法更新 .harness/logs/progress.md: {e}", file=sys.stderr)
        return 1


def action_verify(args):
    """验证任务完成度"""
    if not args.id:
        error("需要提供 --id 参数", file=sys.stderr)
        return 1

    data = load_tasks()

    # 查找任务
    task = None
    for t in data.get('tasks', []):
        # 支持新格式('i')和旧格式('id')
        task_id = t.get('i') or t.get('id')
        if task_id == args.id:
            task = t
            break

    if not task:
        error(f"未找到任务 {args.id}", file=sys.stderr)
        return 1

    category = task.get('category', 'general')

    info(f"验证任务: {args.id}")
    info(f"类别: {category}")
    info("验收标准:")

    all_passed = True
    for i, criterion in enumerate(task.get('acceptance', []), 1):
        # 简单验证：检查文件是否存在
        if '存在' in criterion:
            # 提取文件路径（处理通配符）
            parts = criterion.split()
            file_pattern = parts[0]

            # 使用 glob 查找匹配的文件
            matching_files = glob.glob(file_pattern)

            if matching_files:
                info(f"  [OK] {i}. {criterion}")
                if len(matching_files) > 1:
                    info(f"     找到 {len(matching_files)} 个匹配文件")
            else:
                error(f"  [FAIL] {i}. {criterion} - 文件不存在")
                all_passed = False
        else:
            warning(f"  [WARN] {i}. {criterion} - 需要手动验证")

    if all_passed:
        success(f"\n任务 {args.id} 验证通过")
        return 0
    else:
        warning(f"\n任务 {args.id} 验证未完全通过")
        return 1


def action_list(args):
    """列出所有任务状态（从 task-index.json 加载所有任务）"""
    # 优先使用 TaskFileStorage 获取所有任务
    storage = _get_storage()
    if storage is not None:
        try:
            index = storage.load_index()
            total_tasks = index.get('total_tasks', 0)
            completed = index.get('completed', 0)
            pending = index.get('pending', 0)

            info(f"项目: {index.get('project', 'N/A')}")
            info(f"总任务数: {total_tasks}")
            info(f"已完成: {completed}")
            info(f"待处理: {pending}")
            info("")

            # 只显示待处理任务（自动循环只处理 pending）
            pending_tasks = storage.load_all_pending_tasks()
            for task in pending_tasks:
                task_completed = task.get('passes', False)
                status = "[OK]" if task_completed else "[WAIT]"
                task_id = task.get('id', '')
                task_desc = task.get('description', '')
                info(f"{status} {task_id} - {task_desc}")
        except Exception as e:
            # 回退到旧方式
            warning(f"单文件存储异常，回退到旧系统: {e}", file=sys.stderr)
            _action_list_legacy(args)
    else:
        _action_list_legacy(args)
    return 0


def _action_list_legacy(args):
    """旧版 action_list（从 task.json 加载）"""
    data = load_tasks()

    info(f"项目: {data.get('project', 'N/A')}")
    info(f"总任务数: {len(data.get('tasks', []))}")

    # 支持新格式('p')和旧格式('passes')
    completed = sum(1 for t in data.get('tasks', []) if t.get('p', t.get('passes', False)))
    pending = sum(1 for t in data.get('tasks', []) if not t.get('p', t.get('passes', False)))
    info(f"已完成: {completed}")
    info(f"待处理: {pending}")
    info("")

    for task in data.get('tasks', []):
        # 支持新格式('p')和旧格式('passes')
        task_completed = task.get('p', task.get('passes', False))
        status = "[OK]" if task_completed else "[WAIT]"
        # 支持新格式('i')和旧格式('id')
        task_id = task.get('i') or task.get('id')
        # 支持新格式('d')和旧格式('description')
        task_desc = task.get('d') or task.get('description', '')
        info(f"{status} {task_id} - {task_desc}")


def action_mark_validation(args):
    """标记 satisfaction 验证完成"""
    if not args.id:
        error("需要提供 --id 参数", file=sys.stderr)
        return 1

    # 优先使用 TaskFileStorage
    storage = _get_storage()
    if storage is not None:
        task = storage.load_task(args.id)
        if not task:
            error(f"未找到任务 {args.id}", file=sys.stderr)
            return 1

        # 初始化 validation stage（如果不存在）
        if 'stages' not in task:
            task['stages'] = {
                'dev': {'completed': False, 'completed_at': None, 'issues': []},
                'test': {'completed': False, 'completed_at': None, 'issues': [], 'test_results': {}},
                'review': {'completed': False, 'completed_at': None, 'issues': [], 'risk_level': None}
            }

        # 初始化 validation 阶段
        if 'validation' not in task['stages']:
            task['stages']['validation'] = {
                'completed': False,
                'completed_at': None,
                'issues': []
            }

        # 记录验证结果
        task['stages']['validation']['completed'] = True
        task['stages']['validation']['completed_at'] = datetime.now().isoformat()
        task['stages']['validation']['score'] = getattr(args, 'score', None)
        task['stages']['validation']['tries'] = getattr(args, 'tries', 0)

        # 检查是否所有阶段都完成
        all_complete = all([
            task['stages']['dev']['completed'],
            task['stages']['test']['completed'],
            task['stages']['review']['completed'],
            task['stages'].get('validation', {}).get('completed', True)  # validation 可选
        ])

        if all_complete:
            task['passes'] = True
            success(f"任务 {args.id} 的所有阶段（含 validation）已完成", file=sys.stderr)
        else:
            success(f"任务 {args.id} 的 validation 阶段已完成", file=sys.stderr)

        # 保存任务
        try:
            storage.save_task(task)
        except Exception as e:
            error(f"保存状态失败: {e}", file=sys.stderr)
            return 2

        # 清理 pending（如果全部完成）
        if all_complete:
            _cleanup_pending_file(args.id)

        return 0

    # 回退到旧方式
    error("旧版 task.json 不支持 validation 阶段", file=sys.stderr)
    return 1


def main():
    parser = argparse.ArgumentParser(
        description='Harness 工具脚本 - 供 AI Agent 调用',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  # 查看当前任务
  python3 .harness/scripts/harness-tools.py --action current

  # 标记任务完成（旧版，一次性完成）
  python3 .harness/scripts/harness-tools.py --action mark-done --id Infra_001

  # 标记阶段完成（三阶段系统）
  python3 .harness/scripts/harness-tools.py --action mark-stage --id Infra_001 --stage dev \\
    --files file1.php file2.php

  # 标记阶段完成（包含设计决策和接口契约）
  python3 .harness/scripts/harness-tools.py --action mark-stage --id Infra_001 --stage dev \\
    --files file1.php file2.php \\
    --design-decisions "使用Repository模式隔离数据访问" "采用事件驱动架构" \\
    --interface-contracts "UserService::create|User|name,email" \\
    --constraints "用户名必须唯一" "邮箱格式验证"

  # 标记阶段完成但发现问题
  python3 .harness/scripts/harness-tools.py --action mark-stage --id Infra_001 --stage test \\
    --status failed --issues "测试未通过,覆盖率不足"

  # 查看阶段状态
  python3 .harness/scripts/harness-tools.py --action stage-status --id Infra_001

  # 更新进度
  python3 .harness/scripts/harness-tools.py --action update-progress --id Infra_001 \\
    --what-done "创建 Migration 文件" \\
    --test-result "文件已创建，验证通过" \\
    --next-step "继续下一个任务"

  # 验证任务
  python3 .harness/scripts/harness-tools.py --action verify --id Infra_001

  # 列出所有任务
  python3 .harness/scripts/harness-tools.py --action list
        """
    )

    parser.add_argument('--action', required=True,
                        choices=['current', 'mark-done', 'mark-stage', 'stage-status', 'update-progress', 'verify', 'list', 'mark-validation'],
                        help='执行的操作')

    # 通用参数
    parser.add_argument('--id', help='任务 ID')
    parser.add_argument('--files', nargs='+', help='文件路径列表（用于 mark-stage dev 记录产出）')
    parser.add_argument('--what-done', help='做了什么（用于 update-progress）')
    parser.add_argument('--test-result', help='测试结果（用于 update-progress）')
    parser.add_argument('--next-step', help='下一步（用于 update-progress）')

    # 阶段相关参数
    parser.add_argument('--stage', choices=['dev', 'test', 'review', 'validation'], help='阶段名称（用于 mark-stage 或 mark-validation）')
    parser.add_argument('--status', choices=['passed', 'failed'], help='阶段状态（用于 mark-stage）')
    parser.add_argument('--issues', nargs='+', help='问题列表（用于 mark-stage --status failed）')
    parser.add_argument('--test-results', type=str, help='测试结果JSON字符串（用于 mark-stage test）')

    # 新增：validation 阶段参数
    parser.add_argument('--score', type=float, help='满意度评分（用于 mark-validation，0.0-1.0）')
    parser.add_argument('--tries', type=int, help='验证尝试次数（用于 mark-validation）')

    # 新增：扩展产出参数（用于知识库同步）
    parser.add_argument('--design-decisions', nargs='+', help='设计决策列表（用于 mark-stage dev）')
    parser.add_argument('--interface-contracts', nargs='+', help='接口契约列表（格式：Service::method|return|params）')
    parser.add_argument('--constraints', nargs='+', help='约束条件列表')

    args = parser.parse_args()

    # 路由到对应的 action
    actions = {
        'current': action_current,
        'mark-done': action_mark_done,
        'mark-stage': action_mark_stage,
        'stage-status': action_stage_status,
        'update-progress': action_update_progress,
        'verify': action_verify,
        'list': action_list,
        'mark-validation': action_mark_validation,  # 新增：满意度验证阶段
    }

    action_func = actions.get(args.action)
    if action_func:
        return action_func(args)
    else:
        error(f"未知的操作: {args.action}", file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
