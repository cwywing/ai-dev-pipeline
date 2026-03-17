#!/usr/bin/env python3
"""
测试 harness-tools.py 的 pending 文件清理逻辑
"""

import sys
import os
from pathlib import Path

# 添加脚本目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from task_file_storage import TaskFileStorage
from task_utils import load_tasks, save_tasks
from console_output import success, error, warning, info


def test_early_return_cleanup():
    """
    测试早期返回时的清理逻辑

    场景：
    1. 任务已完成（passes=True）
    2. 但 pending 文件仍然存在
    3. 调用 mark_done 应该清理 pending 文件
    """
    info("测试早期返回清理逻辑")
    info("=" * 60)

    storage = TaskFileStorage()
    storage.initialize()

    # 查找一个已完成的任务
    index = storage.load_index()
    completed_tasks = [
        (task_id, info) for task_id, info in index['index'].items()
        if info['status'] == 'completed'
    ]

    if not completed_tasks:
        warning("没有找到已完成的任务，跳过测试")
        return True

    # 取第一个已完成的任务
    test_task_id, test_task_info = completed_tasks[0]
    info(f"测试任务: {test_task_id}")

    # 检查 pending 文件是否存在
    pending_file = storage.pending_dir / f'{test_task_id}.json'
    info(f"   Pending 文件: {pending_file}")
    info(f"   文件存在: {pending_file.exists()}")

    if pending_file.exists():
        warning("   Pending 文件仍然存在（这不应该发生）")
        info("   这说明之前的清理逻辑有问题")
        return False
    else:
        success("   Pending 文件不存在（正确）")
        return True


def test_cleanup_function():
    """测试 _cleanup_pending_file() 函数"""
    info("\n测试 _cleanup_pending_file() 函数")
    info("=" * 60)

    # 导入函数
    try:
        from harness_tools import _cleanup_pending_file, _get_storage
    except ImportError as e:
        error(f"导入失败: {e}")
        return False

    storage = _get_storage()
    if storage is None:
        warning("TaskFileStorage 不可用")
        return False

    # 创建一个测试用的 pending 文件
    test_task_id = "TEST_CLEANUP_001"
    test_file = storage.pending_dir / f'{test_task_id}.json'

    # 创建测试文件
    test_file.write_text('{"_v": 2, "i": "TEST_CLEANUP_001"}')
    info(f"创建测试文件: {test_file}")
    info(f"   文件存在: {test_file.exists()}")

    # 调用清理函数
    _cleanup_pending_file(test_task_id)

    # 检查文件是否被删除
    if test_file.exists():
        error("   文件未被删除（清理失败）")
        # 手动清理
        test_file.unlink()
        return False
    else:
        success("   文件已被删除（清理成功）")
        return True


def test_all_stages_completed():
    """测试所有阶段完成时的清理逻辑"""
    info("\n测试所有阶段完成时的清理")
    info("=" * 60)

    storage = TaskFileStorage()
    storage.initialize()

    # 查找一个所有阶段都完成的任务
    index = storage.load_index()

    for task_id, info in index['index'].items():
        if info['status'] == 'completed':
            task = storage.load_task(task_id)
            if task and 'stages' in task:
                all_complete = all([
                    task['stages']['dev']['completed'],
                    task['stages']['test']['completed'],
                    task['stages']['review']['completed']
                ])

                if all_complete:
                    info(f"测试任务: {task_id}")
                    info(f"   所有阶段: 完成")

                    # 检查 pending 文件
                    pending_file = storage.pending_dir / f'{task_id}.json'
                    if pending_file.exists():
                        warning(f"   Pending 文件仍然存在: {pending_file}")
                        return False
                    else:
                        success(f"   Pending 文件不存在（正确）")
                        return True

    warning("没有找到所有阶段都完成的任务")
    return True


def main():
    """运行所有测试"""
    info("Harness Tools 清理逻辑测试套件")
    info("=" * 60)
    info("")

    results = []

    # 测试 1: 早期返回清理
    results.append(("早期返回清理", test_early_return_cleanup()))

    # 测试 2: 清理函数
    results.append(("清理函数", test_cleanup_function()))

    # 测试 3: 所有阶段完成
    results.append(("所有阶段完成", test_all_stages_completed()))

    # 输出结果
    info("\n" + "=" * 60)
    info("测试结果")
    info("=" * 60)

    all_passed = True
    for test_name, passed in results:
        status = "通过" if passed else "失败"
        info(f"{test_name}: {status}")
        if not passed:
            all_passed = False

    info("")
    if all_passed:
        success("所有测试通过！")
        return 0
    else:
        warning("有测试失败，请检查修复")
        return 1


if __name__ == '__main__':
    sys.exit(main())
