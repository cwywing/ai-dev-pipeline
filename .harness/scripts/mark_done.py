#!/usr/bin/env python3
"""
Mark a task as completed by updating its 'passes' field to true.
Usage: python3 mark_done.py --id <TASK_ID>
"""

import sys
import os
import argparse
import json

# 导入单文件存储系统
try:
    from task_file_storage import TaskFileStorage
except ImportError:
    print("❌ 错误: 无法导入 TaskFileStorage", file=sys.stderr)
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description='Mark a task as completed')
    parser.add_argument('--id', required=True, help='Task ID to mark as done')
    args = parser.parse_args()

    try:
        # 使用 TaskFileStorage
        storage = TaskFileStorage()
        storage.initialize()

        # Find and update the task
        task = storage.load_task(args.id)
        if not task:
            print(f"Error: Task {args.id} not found", file=sys.stderr)
            sys.exit(1)

        task['passes'] = True

        # 保存任务（会自动移动到 completed）
        if storage.save_task(task):
            print(f"Marked task {args.id} as completed", file=sys.stderr)
            sys.exit(0)
        else:
            print(f"Error: Failed to save task {args.id}", file=sys.stderr)
            sys.exit(1)

    except FileNotFoundError:
        print(f"Error: Task file not found", file=sys.stderr)
        sys.exit(2)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in task file: {e}", file=sys.stderr)
        sys.exit(2)


if __name__ == '__main__':
    main()
