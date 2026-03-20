#!/usr/bin/env python3
"""
Artifact Manager - 产出管理脚本

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
import shutil
from pathlib import Path
from datetime import datetime

from console_output import success, error, warning, info


def get_artifacts_dir():
    """获取产出目录"""
    return Path('.harness/artifacts')


def get_artifact_file(task_id):
    """获取任务的产出清单文件"""
    return get_artifacts_dir() / f'{task_id}.json'


def record_artifacts(task_id, files, design_decisions=None, interface_contracts=None, constraints=None):
    """
    记录任务产出

    Args:
        task_id: 任务 ID
        files: 文件路径列表
        design_decisions: 设计决策列表 [{decision: str, rationale: str, alternatives: list}]
        interface_contracts: 接口契约列表 [{service: str, method: str, params: list, returns: str, throws: list}]
        constraints: 约束条件列表 [str]
    """
    artifacts_dir = get_artifacts_dir()
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    artifact_file = get_artifact_file(task_id)

    data = {
        'task_id': task_id,
        'files': list(files),
        'created_at': datetime.now().isoformat(),
        'file_count': len(files),
        'design_decisions': design_decisions or [],
        'interface_contracts': interface_contracts or [],
        'constraints': constraints or []
    }

    with open(artifact_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    info(f"已记录任务 {task_id} 的产出：{len(files)} 个文件")

    # 显示扩展字段记录
    if design_decisions:
        info(f"  设计决策: {len(design_decisions)} 条")
    if interface_contracts:
        info(f"  接口契约: {len(interface_contracts)} 条")
    if constraints:
        info(f"  约束条件: {len(constraints)} 条")

    return 0


def get_artifacts(task_id, full=False):
    """
    获取任务的产出清单

    Args:
        task_id: 任务 ID
        full: 是否返回完整数据（包括设计决策、接口契约、约束条件）

    Returns:
        如果 full=False: list - 文件路径列表
        如果 full=True: dict - 完整产出数据
    """
    artifact_file = get_artifact_file(task_id)

    if not artifact_file.exists():
        return [] if not full else {}

    with open(artifact_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    if full:
        return data
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
                        shutil.rmtree(file_path)  # 递归删除非空目录
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


def list_artifacts(task_id=None, show_details=False):
    """
    列出产出

    Args:
        task_id: 任务 ID，如果为 None 则列出所有任务的产出
        show_details: 是否显示详细信息（设计决策、接口契约、约束条件）
    """
    artifacts_dir = get_artifacts_dir()

    if not artifacts_dir.exists():
        info("暂无产出记录")
        return 0

    if task_id:
        # 列出指定任务的产出
        data = get_artifacts(task_id, full=True)
        if not data:
            info(f"任务 {task_id} 没有产出记录")
            return 0

        artifacts = data.get('files', [])
        info(f"任务 {task_id} 的产出（{len(artifacts)} 个文件）：")
        for i, file_path in enumerate(artifacts, 1):
            exists = "✓" if Path(file_path).exists() else "✗"
            info(f"  {exists} {i}. {file_path}")

        # 显示扩展字段
        if show_details or any([data.get('design_decisions'), data.get('interface_contracts'), data.get('constraints')]):
            if data.get('design_decisions'):
                info(f"\n  设计决策 ({len(data['design_decisions'])} 条):")
                for dd in data['design_decisions']:
                    if isinstance(dd, dict):
                        info(f"    - {dd.get('decision', dd)}")
                    else:
                        info(f"    - {dd}")

            if data.get('interface_contracts'):
                info(f"\n  接口契约 ({len(data['interface_contracts'])} 条):")
                for ic in data['interface_contracts']:
                    if isinstance(ic, dict):
                        params_str = ', '.join(ic.get('params', []))
                        info(f"    - {ic.get('service')}::{ic.get('method')}({params_str}) -> {ic.get('returns')}")
                    else:
                        info(f"    - {ic}")

            if data.get('constraints'):
                info(f"\n  约束条件 ({len(data['constraints'])} 条):")
                for c in data['constraints']:
                    info(f"    - {c}")
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

            # 统计扩展字段
            extras = []
            if data.get('design_decisions'):
                extras.append(f"{len(data['design_decisions'])}决策")
            if data.get('interface_contracts'):
                extras.append(f"{len(data['interface_contracts'])}契约")
            if data.get('constraints'):
                extras.append(f"{len(data['constraints'])}约束")

            extra_str = f" [{', '.join(extras)}]" if extras else ""
            info(f"  {task_id}: {file_count} 个文件{extra_str}")

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
  # 记录产出（基本）
  python3 .harness/scripts/artifacts.py --action record --id Infra_001 \\
    --files database/migrations/xxx1.php database/migrations/xxx2.php

  # 记录产出（含设计决策）
  python3 .harness/scripts/artifacts.py --action record --id Model_001 \\
    --files app/Services/UserService.php \\
    --design-decisions "使用 Repository 模式隔离数据访问" "采用软删除而非硬删除"

  # 记录产出（含接口契约）
  python3 .harness/scripts/artifacts.py --action record --id Model_001 \\
    --files app/Services/UserService.php \\
    --interface-contracts "UserService::find|User|null" "UserService::create|User"

  # 记录产出（含约束条件）
  python3 .harness/scripts/artifacts.py --action record --id Model_001 \\
    --files app/Services/UserService.php \\
    --constraints "所有用户查询必须检查 deleted_at" "密码必须使用 bcrypt 加密"

  # 清理产出（实际删除）
  python3 .harness/scripts/artifacts.py --action clean --id Infra_001

  # 清理产出（预览）
  python3 .harness/scripts/artifacts.py --action clean --id Infra_001 --dry-run

  # 列出所有产出
  python3 .harness/scripts/artifacts.py --action list

  # 查看特定任务的产出
  python3 .harness/scripts/artifacts.py --action list --id Infra_001

  # 清理所有产出
  python3 .harness/scripts/artifacts.py --action clean-all

接口契约格式说明:
  格式: "ServiceName::method|return_type" 或 "ServiceName::method|return_type|param1,param2"
  示例: "UserService::find|User|null"
        "UserService::create|User|array $data"
        "OrderService::update|bool|int $id,array $data"

设计决策格式说明:
  每条设计决策是一个字符串，描述做出了什么设计决策及其原因
  示例: "使用 Repository 模式隔离数据访问，便于单元测试"
        "采用软删除而非硬删除，保留数据审计追踪"
        """
    )

    parser.add_argument('--action', required=True,
                        choices=['record', 'clean', 'clean-all', 'list'],
                        help='执行的操作')
    parser.add_argument('--id', help='任务 ID')
    parser.add_argument('--files', nargs='+', help='文件路径列表（用于 record）')
    parser.add_argument('--dry-run', action='store_true',
                        help='预览模式，不实际删除文件')
    # 新增：扩展字段参数
    parser.add_argument('--design-decisions', nargs='+',
                        help='设计决策列表（用于 record）')
    parser.add_argument('--interface-contracts', nargs='+',
                        help='接口契约列表（格式: Service::method|return|params）')
    parser.add_argument('--constraints', nargs='+',
                        help='约束条件列表（用于 record）')

    args = parser.parse_args()

    if args.action == 'record':
        if not args.id:
            error("错误: record 操作需要提供 --id 参数")
            return 1
        if not args.files:
            error("错误: record 操作需要提供 --files 参数")
            return 1

        # 解析接口契约
        interface_contracts = None
        if args.interface_contracts:
            interface_contracts = []
            for contract_str in args.interface_contracts:
                parts = contract_str.split('|')
                if len(parts) >= 2:
                    service_method = parts[0].split('::')
                    if len(service_method) == 2:
                        contract = {
                            'service': service_method[0],
                            'method': service_method[1],
                            'returns': parts[1] if len(parts) > 1 else 'mixed',
                            'params': parts[2].split(',') if len(parts) > 2 and parts[2] else [],
                            'throws': []
                        }
                        interface_contracts.append(contract)
                    else:
                        warning(f"接口契约格式错误: {contract_str}")
                else:
                    warning(f"接口契约格式错误: {contract_str}")

        return record_artifacts(
            args.id,
            args.files,
            design_decisions=args.design_decisions,
            interface_contracts=interface_contracts,
            constraints=args.constraints
        )

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
