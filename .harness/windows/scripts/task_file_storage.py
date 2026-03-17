#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Task File Storage - 单文件任务存储系统 (Windows 版本)
每个任务单独保存为一个 JSON 文件

功能：
- 每个任务独立存储（~1 KB/文件）
- 通过 task-index.json 快速索引
- 原子更新，并发安全
- Claude CLI 友好（1 KB 文件）

目录结构：
.harness/
├── task-index.json           # 索引文件
└── tasks/
    ├── pending/              # 待处理任务
    │   ├── TASK_ID_001.json
    │   └── ...
    └── completed/            # 已完成任务（按年/月归档）
        └── 2026/
            └── 02/
                ├── TASK_ID_002.json
                └── ...
"""

import json
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime
from collections import defaultdict
import shutil

from task_utils import TaskCodec
from console_output import success, error, warning, info


class TaskFileStorage:
    """单文件任务存储系统"""

    INDEX_VERSION = 2  # 索引版本（升级以支持单文件模式）

    def __init__(self, harness_dir: Optional[Path] = None):
        """
        初始化 TaskFileStorage

        Args:
            harness_dir: .harness 目录路径，默认使用脚本文件的父目录的父目录下的 .harness
        """
        if harness_dir is None:
            script_dir = Path(__file__).parent  # scripts 目录
            harness_dir = script_dir.parent.parent  # .harness 目录

        self.harness_dir = Path(harness_dir)
        self.index_path = self.harness_dir / 'task-index.json'
        self.tasks_dir = self.harness_dir / 'tasks'
        self.pending_dir = self.tasks_dir / 'pending'
        self.completed_dir = self.tasks_dir / 'completed'

        # 索引缓存
        self._index_cache = None

    def initialize(self):
        """初始化目录结构"""
        self.tasks_dir.mkdir(exist_ok=True)
        self.pending_dir.mkdir(exist_ok=True)
        self.completed_dir.mkdir(exist_ok=True)

    def migrate_from_json(self, source_file: Optional[Path] = None) -> Dict[str, Any]:
        """
        从传统 JSON 文件迁移到单文件模式

        Args:
            source_file: 源文件路径，默认为 task.json

        Returns:
            迁移统计信息
        """
        if source_file is None:
            source_file = self.harness_dir / 'task.json'

        info(f"🔄 开始迁移任务到单文件模式...")
        info(f"📖 源文件: {source_file}")

        # 加载原始数据
        from task_utils import load_tasks
        data = load_tasks(str(source_file))
        tasks = data.get('tasks', [])

        info(f"   总任务数: {len(tasks)}")

        # 初始化目录
        self.initialize()

        # 统计信息
        stats = {
            'total': len(tasks),
            'pending': 0,
            'completed': 0,
            'errors': []
        }

        # 处理每个任务
        for i, task in enumerate(tasks, 1):
            try:
                task_id = task['id']
                is_completed = task.get('passes', False)

                # 确定目标路径
                if is_completed:
                    # 已完成：按年/月归档
                    completed_month = self._get_completed_month(task)
                    target_file = self.completed_dir / completed_month / f'{task_id}.json'
                    stats['completed'] += 1
                else:
                    # 待处理
                    target_file = self.pending_dir / f'{task_id}.json'
                    stats['pending'] += 1

                # 保存任务文件
                target_file.parent.mkdir(parents=True, exist_ok=True)
                encoded_task = TaskCodec.encode_task(task)

                temp_file = target_file.with_suffix('.tmp')
                with open(temp_file, 'w', encoding='utf-8') as f:
                    json.dump(encoded_task, f, indent=2, ensure_ascii=False)

                temp_file.replace(target_file)

                if i % 50 == 0:
                    info(f"   进度: {i}/{len(tasks)}")

            except Exception as e:
                stats['errors'].append(f"{task_id}: {str(e)}")
                warning(f"   任务 {task_id} 迁移失败: {e}")

        # 创建索引
        info(f"\n📇 创建索引文件...")
        self._rebuild_index()

        # 输出统计
        success(f"\n迁移完成！")
        info(f"   总任务: {stats['total']}")
        info(f"   待处理: {stats['pending']}")
        info(f"   已完成: {stats['completed']}")
        if stats['errors']:
            info(f"   错误: {len(stats['errors'])} 个")
            for error_msg in stats['errors']:
                info(f"     - {error_msg}")

        return stats

    def load_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        加载单个任务

        Args:
            task_id: 任务 ID

        Returns:
            任务字典（完整格式），如果不存在返回 None
        """
        index = self.load_index()
        task_info = index['index'].get(task_id)

        if not task_info:
            return None

        task_file = self.harness_dir / task_info['file']

        if not task_file.exists():
            # 索引损坏，尝试重建
            self._rebuild_index()

            # 重新查找（避免无限递归）
            index = self.load_index()
            task_info = index['index'].get(task_id)

            if not task_info:
                return None

            task_file = self.harness_dir / task_info['file']
            if not task_file.exists():
                return None

        try:
            with open(task_file, 'r', encoding='utf-8') as f:
                encoded = json.load(f)

            return TaskCodec.decode_task(encoded)

        except (FileNotFoundError, json.JSONDecodeError, IOError) as e:
            warning(f"加载任务 {task_id} 失败: {e}")
            return None
        except Exception as e:
            raise RuntimeError(f"加载任务 {task_id} 时发生意外错误: {e}") from e

    def save_task(self, task: Dict[str, Any]) -> bool:
        """
        保存单个任务（原子写入）

        Args:
            task: 任务字典（完整格式）

        Returns:
            是否保存成功
        """
        task_id = task['id']
        is_completed = task.get('passes', False)

        # 编码任务
        encoded = TaskCodec.encode_task(task)

        # 确定目标路径
        if is_completed:
            # 已完成：按年/月归档
            completed_month = self._get_completed_month(task)
            target_file = self.completed_dir / completed_month / f'{task_id}.json'
        else:
            # 待处理
            target_file = self.pending_dir / f'{task_id}.json'

        # 查找并删除旧文件（如果位置变化）
        old_index = self.load_index()['index'].get(task_id)
        if old_index:
            old_file = self.harness_dir / old_index['file']
            if old_file.exists() and old_file != target_file:
                try:
                    old_file.unlink()
                except Exception:
                    pass  # 忽略删除失败

        # 原子写入
        try:
            target_file.parent.mkdir(parents=True, exist_ok=True)

            temp_file = target_file.with_suffix('.tmp')
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(encoded, f, indent=2, ensure_ascii=False)

            temp_file.replace(target_file)

            # 更新索引
            self._update_index_entry(task_id, target_file, task)

            # 清除缓存
            self._index_cache = None

            return True

        except Exception as e:
            warning(f"保存任务 {task_id} 失败: {e}")
            return False

    def load_all_tasks(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        加载所有任务

        Args:
            status: 过滤状态 ('pending', 'completed', None)

        Returns:
            任务列表
        """
        index = self.load_index()
        tasks = []

        for task_id, info in index['index'].items():
            if status and info['status'] != status:
                continue

            task = self.load_task(task_id)
            if task:
                tasks.append(task)

        return tasks

    def load_all_pending_tasks(self) -> List[Dict[str, Any]]:
        """
        加载所有待处理任务

        Returns:
            待处理任务列表
        """
        return self.load_all_tasks('pending')

    def complete_task(self, task_id: str) -> bool:
        """
        标记任务完成并移动到 completed

        Args:
            task_id: 任务 ID

        Returns:
            是否完成成功
        """
        return self.move_to_completed(task_id)

    def load_index(self) -> Dict[str, Any]:
        """
        加载索引文件（缓存）

        Returns:
            索引字典
        """
        if self._index_cache is not None:
            return self._index_cache

        if not self.index_path.exists():
            # 索引不存在，重建
            self._rebuild_index()
            return self._index_cache

        try:
            with open(self.index_path, 'r', encoding='utf-8') as f:
                self._index_cache = json.load(f)
            return self._index_cache

        except Exception as e:
            warning(f"加载索引失败: {e}，重建索引...")
            self._rebuild_index()
            return self._index_cache

    def _rebuild_index(self):
        """重建索引文件"""
        index = {
            'version': self.INDEX_VERSION,
            'storage_mode': 'single_file',
            'project': 'SIM-Laravel Admin API',
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat(),
            'total_tasks': 0,
            'pending': 0,
            'completed': 0,
            'index': {},
            'modules': {},
            'priorities': defaultdict(int)
        }

        # 扫描待处理任务
        if self.pending_dir.exists():
            for task_file in self.pending_dir.glob('*.json'):
                try:
                    with open(task_file, 'r', encoding='utf-8') as f:
                        task = TaskCodec.decode_task(json.load(f))

                    task_id = task['id']
                    index['index'][task_id] = self._create_index_entry(task_file, task, 'pending')
                    index['pending'] += 1

                    # 统计模块和优先级
                    self._update_stats(index, task)

                except Exception as e:
                    warning(f"索引失败 {task_file}: {e}")

        # 扫描已完成任务
        if self.completed_dir.exists():
            for task_file in self.completed_dir.rglob('*.json'):
                try:
                    with open(task_file, 'r', encoding='utf-8') as f:
                        task = TaskCodec.decode_task(json.load(f))

                    task_id = task['id']
                    index['index'][task_id] = self._create_index_entry(task_file, task, 'completed')
                    index['completed'] += 1

                    # 统计模块和优先级
                    self._update_stats(index, task)

                except Exception as e:
                    warning(f"索引失败 {task_file}: {e}")

        index['total_tasks'] = index['pending'] + index['completed']
        index['updated_at'] = datetime.now().isoformat()

        # 保存索引
        self._save_index(index)

        self._index_cache = index

        info(f"索引重建完成: {index['total_tasks']} 个任务")

    def _create_index_entry(
        self,
        task_file: Path,
        task: Dict[str, Any],
        status: str
    ) -> Dict[str, Any]:
        """创建索引条目"""
        return {
            'file': str(task_file.relative_to(self.harness_dir)),
            'status': status,
            'priority': task.get('priority', 'P2'),
            'module': task.get('module', ''),
            'category': task.get('category', ''),
            'description': task.get('description', ''),
            'updated_at': datetime.now().isoformat()
        }

    def _update_stats(self, index: Dict[str, Any], task: Dict[str, Any]):
        """更新统计信息"""
        # 模块统计
        module = task.get('module', 'Unknown')
        index['modules'][module] = index['modules'].get(module, 0) + 1

        # 优先级统计
        priority = task.get('priority', 'P2')
        index['priorities'][priority] += 1

    def _update_index_entry(
        self,
        task_id: str,
        task_file: Path,
        task: Dict[str, Any]
    ):
        """更新索引中的单个条目"""
        if self._index_cache is None:
            self.load_index()

        old_entry = self._index_cache['index'].get(task_id)
        old_status = old_entry['status'] if old_entry else None
        new_status = 'completed' if task.get('passes', False) else 'pending'

        # 更新条目
        self._index_cache['index'][task_id] = self._create_index_entry(
            task_file,
            task,
            new_status
        )

        # 更新计数（考虑状态变化）
        if old_status and old_status != new_status:
            if old_status == 'pending':
                self._index_cache['pending'] = max(0, self._index_cache['pending'] - 1)
            else:
                self._index_cache['completed'] = max(0, self._index_cache['completed'] - 1)

        if new_status == 'pending':
            self._index_cache['pending'] += 1
        else:
            self._index_cache['completed'] += 1

        self._index_cache['total_tasks'] = self._index_cache['pending'] + self._index_cache['completed']
        self._index_cache['updated_at'] = datetime.now().isoformat()

        # 保存索引
        self._save_index(self._index_cache)

    def _save_index(self, index: Dict[str, Any]):
        """保存索引文件"""
        temp_file = self.index_path.with_suffix('.tmp')
        with open(temp_file, 'w', encoding='utf-8') as f:
            json.dump(index, f, indent=2, ensure_ascii=False)

        temp_file.replace(self.index_path)

    def _get_completed_month(self, task: Dict[str, Any]) -> str:
        """
        获取任务完成月份

        Args:
            task: 任务字典

        Returns:
            YYYY/MM 格式
        """
        # 尝试从 stages 获取完成时间
        stages = task.get('stages', {})
        if stages:
            for stage_name in ['review', 'test', 'dev']:
                stage = stages.get(stage_name, {})
                if stage.get('completed') and stage.get('completed_at'):
                    try:
                        dt = datetime.fromisoformat(stage['completed_at'].replace('Z', '+00:00'))
                        return dt.strftime('%Y/%m')
                    except (ValueError, AttributeError):
                        pass

        # 默认当前月份
        return datetime.now().strftime('%Y/%m')

    def get_stats(self) -> Dict[str, Any]:
        """获取存储统计信息"""
        index = self.load_index()

        # 计算文件大小
        total_size = 0
        pending_size = 0
        completed_size = 0
        file_count = 0

        if self.pending_dir.exists():
            for f in self.pending_dir.glob('*.json'):
                total_size += f.stat().st_size
                pending_size += f.stat().st_size
                file_count += 1

        if self.completed_dir.exists():
            for f in self.completed_dir.rglob('*.json'):
                total_size += f.stat().st_size
                completed_size += f.stat().st_size
                file_count += 1

        index_size = self.index_path.stat().st_size if self.index_path.exists() else 0

        return {
            'total_tasks': index['total_tasks'],
            'pending': index['pending'],
            'completed': index['completed'],
            'file_count': file_count,
            'total_size_kb': round(total_size / 1024, 2),
            'pending_size_kb': round(pending_size / 1024, 2),
            'completed_size_kb': round(completed_size / 1024, 2),
            'index_size_kb': round(index_size / 1024, 2),
            'avg_file_size_kb': round(total_size / file_count / 1024, 3) if file_count > 0 else 0,
            'modules': dict(index.get('modules', {})),
            'priorities': dict(index.get('priorities', {}))
        }

    def clear_cache(self):
        """清除索引缓存"""
        self._index_cache = None

    def move_to_completed(self, task_id: str) -> bool:
        """
        将任务从 pending 移动到 completed（并删除 pending 文件）

        Args:
            task_id: 任务 ID

        Returns:
            是否移动成功
        """
        # 加载任务
        task = self.load_task(task_id)
        if not task:
            error(f"任务 {task_id} 不存在")
            return False

        # 标记为已完成
        task['passes'] = True

        # 使用 save_task() 保存（会自动处理文件移动和索引更新）
        success = self.save_task(task)

        if success:
            # 额外检查：确保 pending 目录中的文件已被删除
            pending_file = self.pending_dir / f'{task_id}.json'
            if pending_file.exists():
                try:
                    pending_file.unlink()
                    success(f"已删除 pending 目录中的文件: {pending_file}")
                except Exception as e:
                    warning(f"删除 pending 文件失败: {e}")
                    # 不影响整体结果

        return success

    def cleanup_pending_duplicates(self) -> List[str]:
        """
        清理 pending 目录中与 completed 目录重复的任务文件

        Returns:
            清理的任务 ID 列表
        """
        cleaned = []

        if not self.pending_dir.exists():
            return cleaned

        # 加载索引
        index = self.load_index()

        # 检查每个 pending 文件
        for pending_file in self.pending_dir.glob('*.json'):
            task_id = pending_file.stem

            # 检查索引中该任务的状态
            task_info = index['index'].get(task_id)
            if task_info and task_info['status'] == 'completed':
                # 任务已完成，但 pending 文件仍存在，删除它
                try:
                    pending_file.unlink()
                    cleaned.append(task_id)
                    success(f"清理重复文件: {task_id}")
                except Exception as e:
                    warning(f"清理失败 {task_id}: {e}")

        if cleaned:
            info(f"\n清理统计:")
            info(f"   清理文件数: {len(cleaned)}")
            for task_id in cleaned:
                info(f"     - {task_id}")

        return cleaned


def main():
    """命令行入口"""
    import argparse

    parser = argparse.ArgumentParser(
        description='单文件任务存储工具 - 每个任务独立存储'
    )
    parser.add_argument(
        '--action',
        choices=['migrate', 'stats', 'rebuild-index', 'cleanup', 'test'],
        default='stats',
        help='执行的操作'
    )
    parser.add_argument(
        '--source',
        type=str,
        default=None,
        help='源文件路径（仅用于 migrate）'
    )

    args = parser.parse_args()

    storage = TaskFileStorage()

    if args.action == 'migrate':
        result = storage.migrate_from_json(
            Path(args.source) if args.source else None
        )
    elif args.action == 'stats':
        storage.initialize()
        stats = storage.get_stats()
        info(f"单文件存储统计:")
        info(f"   总任务: {stats['total_tasks']}")
        info(f"   待处理: {stats['pending']}")
        info(f"   已完成: {stats['completed']}")
        info(f"   文件总数: {stats['file_count']}")
        info(f"   总大小: {stats['total_size_kb']} KB")
        info(f"     - pending: {stats['pending_size_kb']} KB")
        info(f"     - completed: {stats['completed_size_kb']} KB")
        info(f"   索引大小: {stats['index_size_kb']} KB")
        info(f"   平均文件大小: {stats['avg_file_size_kb']} KB")
        info(f"\n模块分布:")
        for module, count in sorted(stats['modules'].items(), key=lambda x: -x[1]):
            info(f"     {module}: {count}")
        result = None
    elif args.action == 'rebuild-index':
        storage.initialize()
        storage._rebuild_index()
        result = None
    elif args.action == 'cleanup':
        # 清理 pending 目录中的重复文件
        storage.initialize()
        info("清理 pending 目录中的重复文件...")
        cleaned = storage.cleanup_pending_duplicates()
        if cleaned:
            success(f"\n清理完成！共清理 {len(cleaned)} 个重复文件")
        else:
            success(f"\n没有发现重复文件")
        result = None
    elif args.action == 'test':
        # 测试加载性能
        import time

        storage.initialize()

        info("性能测试")
        info("=" * 50)

        # 测试 1: 加载索引
        start = time.time()
        index = storage.load_index()
        elapsed = (time.time() - start) * 1000
        success(f"加载索引: {elapsed:.2f} ms")

        # 测试 2: 加载单个任务
        if index['index']:
            first_task_id = next(iter(index['index']))
            start = time.time()
            task = storage.load_task(first_task_id)
            elapsed = (time.time() - start) * 1000
            success(f"加载单个任务: {elapsed:.2f} ms")

        # 测试 3: 加载所有待处理任务
        start = time.time()
        pending_tasks = storage.load_all_tasks('pending')
        elapsed = (time.time() - start) * 1000
        success(f"加载待处理任务 ({len(pending_tasks)} 个): {elapsed:.2f} ms")

        result = None

    return result


if __name__ == '__main__':
    main()
