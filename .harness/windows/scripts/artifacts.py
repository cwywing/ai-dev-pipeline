#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Artifact Manager - 产出管理脚本 (Windows 版本)

功能：
1. 记录每个任务创建的文件（产出清单）
2. 重试时清理产出
3. 重置任务时清理产出
4. 提供产出查询功能
"""

import json
import os
import glob
import argparse
import sys
from pathlib import Path
from datetime import datetime

from console_output import success, error, warning, info


def get_artifacts_dir():
    """获取产出目录"""
    return Path('.harness/artifacts')


def get_artifact_file(task_id):
    """获取任务的产出清单文件"""
    return get_artifacts_dir() / f'{task_id}.json'


def record_artifacts(task_id, files):
    """
    记录任务产出

    Args:
        task_id: 任务 ID
        files: 文件路径列表
    """
    artifacts_dir = get_artifacts_dir()
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    artifact_file = get_artifact_file(task_id)

    data = {
        'task_id': task_id,
        'files': list(files),
        'created_at': datetime.now().isoformat(),
        'file_count': len(files)
    }

    with open(artifact_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    info(f"已记录任务 {task_id} 的产出：{len(files)} 个文件")
    return 0


def get_artifacts(task_id):
    """
    获取任务的产出清单

    Returns:
        list: 文件路径列表，如果不存在返回空列表
    """
    artifact_file = get_artifact_file(task_id)

    if not artifact_file.exists():
        return []

    with open(artifact_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    return data.get('files', [])


def clean_artifacts(task_id, dry_run=False):
    """
    清理任务的产出

    Args:
        task_id: 任务 ID
        dry_run: 是否只显示不删除
    """
    artifacts = get_artifacts(task_id)

    if not artifacts:
        info(f"任务 {task_id} 没有产出记录")
        return 0

    info(f"准备清理任务 {task_id} 的产出（{len(artifacts)} 个文件）：")

    cleaned = 0
    for file_path in artifacts:
        if Path(file_path).exists():
            if dry_run:
                info(f"  [DRY RUN] 将删除: {file_path}")
            else:
                try:
                    if Path(file_path).is_dir():
                        Path(file_path).rmdir()
                    else:
                        Path(file_path).unlink()
                    success(f"  已删除: {file_path}")
                    cleaned += 1
                except Exception as e:
                    error(f"  删除失败: {file_path} - {e}")
        else:
            info(f"  - 不存在: {file_path}")

    if not dry_run and cleaned > 0:
        # 删除产出清单文件
        artifact_file = get_artifact_file(task_id)
        if artifact_file.exists():
            artifact_file.unlink()

        # 清理重试计数
        retry_file = Path('.harness/.automation_retries') / f'{task_id}.count'
        if retry_file.exists():
            retry_file.unlink()

        # 清理跳过记录
        skip_file = Path('.harness/.automation_skip') / task_id
        if skip_file.exists():
            skip_file.unlink()

        success(f"清理完成：删除了 {cleaned} 个文件")
    elif dry_run:
        info(f"[DRY RUN] 将删除 {len(artifacts)} 个文件")

    return 0


def list_artifacts(task_id=None):
    """
    列出产出

    Args:
        task_id: 任务 ID，如果为 None 则列出所有任务的产出
    """
    artifacts_dir = get_artifacts_dir()

    if not artifacts_dir.exists():
        info("暂无产出记录")
        return 0

    if task_id:
        # 列出指定任务的产出
        artifacts = get_artifacts(task_id)
        if not artifacts:
            info(f"任务 {task_id} 没有产出记录")
            return 0

        info(f"任务 {task_id} 的产出（{len(artifacts)} 个文件）：")
        for i, file_path in enumerate(artifacts, 1):
            exists = "OK" if Path(file_path).exists() else "FAIL"
            info(f"  {exists} {i}. {file_path}")
    else:
        # 列出所有任务的产出
        artifact_files = list(artifacts_dir.glob('*.json'))

        if not artifact_files:
            info("暂无产出记录")
            return 0

        info(f"所有任务的产出（{len(artifact_files)} 个任务）：")
        info("")

        total_files = 0
        for artifact_file in sorted(artifact_files):
            with open(artifact_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            task_id = data['task_id']
            file_count = data['file_count']
            total_files += file_count

            info(f"  {task_id}: {file_count} 个文件")

        info("")
        info(f"  总计: {len(artifact_files)} 个任务, {total_files} 个文件")

    return 0


def clean_all_artifacts(dry_run=False):
    """清理所有产出"""
    artifacts_dir = get_artifacts_dir()

    if not artifacts_dir.exists():
        info("暂无产出记录")
        return 0

    artifact_files = list(artifacts_dir.glob('*.json'))

    if not artifact_files:
        info("暂无产出记录")
        return 0

    info(f"准备清理所有任务的产出（{len(artifact_files)} 个任务）：")

    for artifact_file in artifact_files:
        with open(artifact_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        task_id = data['task_id']
        info(f"\n  清理任务 {task_id}...")
        clean_artifacts(task_id, dry_run=dry_run)

    if not dry_run:
        # 删除产出目录
        if artifacts_dir.exists() and not list(artifacts_dir.glob('*')):
            artifacts_dir.rmdir()

    return 0


def main():
    import sys

    parser = argparse.ArgumentParser(
        description='Harness 产出管理工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  # 记录产出
  python .harness\windows\scripts\artifacts.py --action record --id SIM_Foundation_001 ^
    --files database/migrations/xxx1.php database/migrations/xxx2.php

  # 清理产出（实际删除）
  python .harness\windows\scripts\artifacts.py --action clean --id SIM_Foundation_001

  # 清理产出（预览）
  python .harness\windows\scripts\artifacts.py --action clean --id SIM_Foundation_001 --dry-run

  # 列出所有产出
  python .harness\windows\scripts\artifacts.py --action list

  # 查看特定任务的产出
  python .harness\windows\scripts\artifacts.py --action list --id SIM_Foundation_001

  # 清理所有产出
  python .harness\windows\scripts\artifacts.py --action clean-all
        """
    )

    parser.add_argument('--action', required=True,
                        choices=['record', 'clean', 'clean-all', 'list'],
                        help='执行的操作')
    parser.add_argument('--id', help='任务 ID')
    parser.add_argument('--files', nargs='+', help='文件路径列表（用于 record）')
    parser.add_argument('--dry-run', action='store_true',
                        help='预览模式，不实际删除文件')

    args = parser.parse_args()

    if args.action == 'record':
        if not args.id:
            error("错误: record 操作需要提供 --id 参数")
            return 1
        if not args.files:
            error("错误: record 操作需要提供 --files 参数")
            return 1
        return record_artifacts(args.id, args.files)

    elif args.action == 'clean':
        if not args.id:
            error("错误: clean 操作需要提供 --id 参数")
            return 1
        return clean_artifacts(args.id, dry_run=args.dry_run)

    elif args.action == 'clean-all':
        return clean_all_artifacts(dry_run=args.dry_run)

    elif args.action == 'list':
        return list_artifacts(task_id=args.id)

    return 0


if __name__ == '__main__':
    import sys
    sys.exit(main())
