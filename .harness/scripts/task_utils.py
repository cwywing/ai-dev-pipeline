#!/usr/bin/env python3
"""
Task Data Codec - 任务数据编码/解码器
处理 task.json 的字段精简（方案4）

功能：
- 自动编码/解码任务数据（完整格式 ↔ 精简格式）
- 向后兼容：自动检测格式版本
- 透明转换：上层代码无需关心底层格式

字段精简映射：
- id → i
- category → c
- description → d
- acceptance → a
- passes → p
- priority → pr
- module → m
- notes → n
- complexity → x
- stages → s
- depends_on → dep (支持两种格式：["id"] 或 [{"id": "x", "reason": "y"}])
- validation → val
- completed → c
- completed_at → t (Unix timestamp)
- issues → i
- test_results → r
- risk_level → l
"""

import json
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime

from console_output import success, error, warning, info


class TaskCodec:
    """任务数据编码/解码器"""

    # 字段映射表（完整格式 → 精简格式）
    FIELD_MAP = {
        'id': 'i',
        'category': 'c',
        'description': 'd',
        'acceptance': 'a',
        'passes': 'p',
        'priority': 'pr',
        'module': 'm',
        'notes': 'n',
        'complexity': 'x',
        'stages': 's',
        'validation': 'val',  # 新增：满意度验证配置
        'depends_on': 'dep',  # 新增：任务依赖关系
    }

    # 阶段字段映射表
    STAGE_FIELD_MAP = {
        'completed': 'c',
        'completed_at': 't',
        'issues': 'i',
        'test_results': 'r',
        'risk_level': 'l',
    }

    # 反向映射缓存（延迟初始化）
    _FIELD_REVERSE_MAP = None
    _STAGE_REVERSE_MAP = None

    # 精简格式的标记字段
    VERSION_MARKER = '_v'  # 用于识别精简格式版本

    # 任务拆分支持
    _index_cache = None  # 索引缓存
    _index_path = None   # 索引文件路径

    @classmethod
    def _get_field_reverse_map(cls) -> Dict[str, str]:
        """获取字段反向映射（缓存）"""
        if cls._FIELD_REVERSE_MAP is None:
            cls._FIELD_REVERSE_MAP = {v: k for k, v in cls.FIELD_MAP.items()}
        return cls._FIELD_REVERSE_MAP

    @classmethod
    def _get_stage_reverse_map(cls) -> Dict[str, str]:
        """获取阶段字段反向映射（缓存）"""
        if cls._STAGE_REVERSE_MAP is None:
            cls._STAGE_REVERSE_MAP = {v: k for k, v in cls.STAGE_FIELD_MAP.items()}
        return cls._STAGE_REVERSE_MAP

    @classmethod
    def encode_task(cls, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        编码任务（完整格式 → 精简格式）

        Args:
            task: 完整格式的任务字典

        Returns:
            精简格式的任务字典
        """
        encoded = {}
        encoded[cls.VERSION_MARKER] = 2  # 标记为精简格式版本2

        # 编码基本字段
        for full_key, short_key in cls.FIELD_MAP.items():
            if full_key in task:
                value = task[full_key]

                # 特殊处理：stages 需要递归编码
                if full_key == 'stages' and isinstance(value, dict):
                    encoded[short_key] = cls._encode_stages(value)
                else:
                    encoded[short_key] = value

        return encoded

    @classmethod
    def decode_task(cls, encoded: Dict[str, Any]) -> Dict[str, Any]:
        """
        解码任务（精简格式 → 完整格式）

        Args:
            encoded: 精简格式的任务字典

        Returns:
            完整格式的任务字典
        """
        decoded = {}

        # 检查是否为精简格式
        is_compact = cls.VERSION_MARKER in encoded

        if is_compact:
            # 精简格式：使用反向映射
            reverse_map = cls._get_field_reverse_map()

            for short_key, value in encoded.items():
                if short_key == cls.VERSION_MARKER:
                    continue  # 跳过版本标记

                full_key = reverse_map.get(short_key, short_key)

                # 特殊处理：stages 需要递归解码
                if full_key == 'stages':
                    decoded[full_key] = cls._decode_stages(value)
                else:
                    decoded[full_key] = value
        else:
            # 已经是完整格式，直接返回
            decoded = encoded

        return decoded

    @classmethod
    def _encode_stages(cls, stages: Dict[str, Any]) -> Dict[str, Any]:
        """编码阶段信息"""
        encoded = {}
        for stage_name, stage_data in stages.items():
            if not isinstance(stage_data, dict):
                encoded[stage_name] = stage_data
                continue

            encoded_stage = {}
            for full_key, short_key in cls.STAGE_FIELD_MAP.items():
                if full_key in stage_data:
                    value = stage_data[full_key]

                    # completed_at 转时间戳
                    if full_key == 'completed_at' and value:
                        if isinstance(value, str):
                            # ISO 8601 字符串转时间戳
                            try:
                                value = int(datetime.fromisoformat(value.replace('Z', '+00:00')).timestamp())
                            except (ValueError, AttributeError):
                                # 转换失败，保持原值
                                pass
                        encoded_stage[short_key] = value
                    else:
                        encoded_stage[short_key] = value

            # 保留未映射的字段
            for key, value in stage_data.items():
                if key not in cls.STAGE_FIELD_MAP:
                    encoded_stage[key] = value

            encoded[stage_name] = encoded_stage
        return encoded

    @classmethod
    def _decode_stages(cls, encoded: Dict[str, Any]) -> Dict[str, Any]:
        """解码阶段信息"""
        decoded = {}
        reverse_map = cls._get_stage_reverse_map()

        for stage_name, stage_data in encoded.items():
            if not isinstance(stage_data, dict):
                decoded[stage_name] = stage_data
                continue

            decoded_stage = {}
            for short_key, value in stage_data.items():
                full_key = reverse_map.get(short_key, short_key)

                # 时间戳转 ISO 字符串
                if full_key == 'completed_at' and value:
                    if isinstance(value, (int, float)):
                        try:
                            decoded_stage[full_key] = datetime.fromtimestamp(value).isoformat()
                        except (ValueError, OSError, OverflowError):
                            # 转换失败，保持原值
                            decoded_stage[full_key] = value
                    else:
                        decoded_stage[full_key] = value
                else:
                    decoded_stage[full_key] = value

            decoded[stage_name] = decoded_stage
        return decoded

    @classmethod
    def get_task_json_path(cls) -> Path:
        """
        获取 task.json 路径（向后兼容）

        注意：新系统使用单文件存储，此方法主要用于获取 .harness 目录路径
        """
        script_dir = Path(__file__).parent
        harness_dir = script_dir.parent

        # 优先返回 .harness/task.json 路径（即使文件不存在）
        # 这样 _get_index_path() 才能正确找到 task-index.json
        return harness_dir / 'task.json'

    @classmethod
    def load_tasks(cls, path: Optional[str] = None) -> Dict[str, Any]:
        """
        加载并解码任务文件

        优先从拆分后的文件加载（如果存在），否则从原始 task.json 加载

        Args:
            path: task.json 文件路径，默认自动查找。
                   如果指定了 path，则不使用拆分文件

        Returns:
            解码后的任务数据（完整格式）

        Raises:
            FileNotFoundError: 文件不存在
            PermissionError: 无读取权限
            ValueError: JSON 格式错误
        """
        # 如果指定了 path，直接使用指定的文件
        if path is not None:
            return cls._load_from_path(path)

        # 尝试从拆分文件加载
        try:
            split_data = cls._load_tasks_from_files()
            if split_data is not None:
                return split_data
        except Exception:
            # 拆分文件加载失败，回退到主文件
            pass

        # 从主文件加载
        task_json_path = cls.get_task_json_path()
        return cls._load_from_path(str(task_json_path))

    @classmethod
    def _load_from_path(cls, path: str) -> Dict[str, Any]:
        """
        从指定路径加载任务文件

        Args:
            path: 文件路径

        Returns:
            解码后的任务数据

        Raises:
            FileNotFoundError: 文件不存在
            PermissionError: 无读取权限
            ValueError: JSON 格式错误
        """
        # 读取并解析文件
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except FileNotFoundError as e:
            raise FileNotFoundError(f"Task file not found: {path}") from e
        except PermissionError as e:
            raise PermissionError(f"No permission to read task file: {path}") from e
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in task file: {path}\n{e}") from e

        # 如果没有 tasks 字段，直接返回
        if 'tasks' not in data:
            return data

        # 检查是否需要解码（通过第一个任务的 _v 字段）
        if data.get('tasks') and len(data['tasks']) > 0:
            first_task = data['tasks'][0]
            needs_decode = cls.VERSION_MARKER in first_task

            if needs_decode:
                # 批量解码任务
                data['tasks'] = [cls.decode_task(t) for t in data['tasks']]

        return data

    @classmethod
    def save_tasks(cls, data: Dict[str, Any], path: Optional[str] = None):
        """
        编码并保存任务文件
        在 single_file_mode 下，会同时更新主 task.json 和单个任务文件

        Args:
            data: 任务数据（完整格式）
            path: task.json 文件路径，默认自动查找
        """
        if path is None:
            path = str(cls.get_task_json_path())

        import os

        # 创建数据副本，避免修改原始数据
        data_copy = json.loads(json.dumps(data, ensure_ascii=False))

        # 编码任务列表
        if 'tasks' in data_copy:
            data_copy['tasks'] = [cls.encode_task(t) for t in data_copy['tasks']]

        # 原子写入:先写临时文件，再重命名
        temp_path = f"{path}.tmp"
        with open(temp_path, 'w', encoding='utf-8') as f:
            json.dump(data_copy, f, indent=2, ensure_ascii=False)

        # 重命名（原子操作）
        Path(temp_path).replace(path)

        # 🔧 新增:在 single_file_mode 下，同时更新单个任务文件
        cls._update_single_file_mode_tasks(data)

    @classmethod
    def _update_single_file_mode_tasks(cls, data: Dict[str, Any]):
        """
        在 single_file_mode 下，更新单个任务文件

        Args:
            data: 任务数据（完整格式）
        """
        try:
            # 检查是否为 single_file_mode
            index = cls._load_index()
            if index is None or index.get('storage_mode') != 'single_file':
                return

            harness_dir = cls.get_task_json_path().parent
            pending_dir = harness_dir / 'tasks' / 'pending'
            completed_dir = harness_dir / 'tasks' / 'completed'

            # 遍历所有任务，更新对应的文件
            for task in data.get('tasks', []):
                task_id = task.get('id')
                if not task_id:
                    continue

                # 确定任务状态
                is_passed = task.get('passes', False)

                # 确定目标目录
                if is_passed:
                    target_dir = completed_dir
                    status = 'completed'
                else:
                    target_dir = pending_dir
                    status = 'pending'

                # 构建文件路径
                task_file = target_dir / f'{task_id}.json'

                # 获取任务的 stages（完整格式）
                stages = task.get('stages', {})
                if not stages:
                    continue

                # 编码 stages（转换为紧凑格式）
                encoded_stages = {}
                for stage_name, stage_data in stages.items():
                    if not isinstance(stage_data, dict):
                        encoded_stages[stage_name] = stage_data
                        continue

                    encoded_stage = {}
                    for full_key, short_key in cls.STAGE_FIELD_MAP.items():
                        if full_key in stage_data:
                            value = stage_data[full_key]
                            if full_key == 'completed_at' and value:
                                if isinstance(value, str):
                                    try:
                                        value = int(datetime.fromisoformat(value.replace('Z', '+00:00')).timestamp())
                                    except (ValueError, AttributeError):
                                        pass
                                encoded_stage[short_key] = value
                            else:
                                encoded_stage[short_key] = value
                    encoded_stages[stage_name] = encoded_stage

                # 创建任务数据（紧凑格式）- 保存所有必需字段
                task_data = {
                    '_v': 2,
                    'i': task_id,
                    'c': task.get('category', 'general'),
                    'd': task.get('description', ''),
                    'a': task.get('acceptance', []),
                    'p': task.get('passes', False),
                    'pr': task.get('priority', 'P3'),
                    'm': task.get('module', 'general'),
                    'n': task.get('notes', ''),
                    'x': task.get('complexity', 'medium'),
                    's': encoded_stages,
                    'val': task.get('validation', {}),  # 新增：满意度验证配置
                }

                # 添加 depends_on 字段（如果存在）
                if task.get('depends_on'):
                    task_data['dep'] = task.get('depends_on')

                # 写入文件（原子操作）
                temp_file = str(task_file) + '.tmp'
                with open(temp_file, 'w', encoding='utf-8') as f:
                    json.dump(task_data, f, indent=2, ensure_ascii=False)
                Path(temp_file).replace(task_file)

        except Exception as e:
            # 不中断保存流程
            pass

    @classmethod
    def get_format_stats(cls, path: Optional[str] = None) -> Dict[str, Any]:
        """
        获取文件格式统计信息

        Args:
            path: task.json 文件路径

        Returns:
            统计信息字典

        Raises:
            FileNotFoundError: 文件不存在
            PermissionError: 无读取权限
            ValueError: JSON 格式错误
        """
        if path is None:
            path = str(cls.get_task_json_path())

        path_obj = Path(path)

        # 检查文件是否存在
        if not path_obj.exists():
            raise FileNotFoundError(f"Task file not found: {path}")

        # 获取文件大小
        try:
            file_size = path_obj.stat().st_size
        except PermissionError as e:
            raise PermissionError(f"No permission to access task file: {path}") from e

        # 读取并解析文件
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in task file: {path}\n{e}") from e

        tasks = data.get('tasks', [])
        total_tasks = len(tasks)

        # 检查格式版本
        if total_tasks > 0:
            is_compact = cls.VERSION_MARKER in tasks[0]
        else:
            is_compact = False

        # 计算平均任务大小
        if total_tasks > 0:
            avg_task_size = file_size / total_tasks
        else:
            avg_task_size = 0

        return {
            'file_size': file_size,
            'file_size_kb': round(file_size / 1024, 2),
            'total_tasks': total_tasks,
            'format': 'compact' if is_compact else 'full',
            'avg_task_size': round(avg_task_size, 2),
        }

    @classmethod
    def _get_index_path(cls) -> Optional[Path]:
        """获取索引文件路径"""
        if cls._index_path is None:
            harness_dir = cls.get_task_json_path().parent
            cls._index_path = harness_dir / 'task-index.json'
        return cls._index_path

    @classmethod
    def _load_index(cls) -> Optional[Dict[str, Any]]:
        """
        加载任务索引（缓存）

        Returns:
            索引字典，如果索引文件不存在则返回 None
        """
        if cls._index_cache is not None:
            return cls._index_cache

        index_path = cls._get_index_path()
        if not index_path.exists():
            return None

        try:
            with open(index_path, 'r', encoding='utf-8') as f:
                cls._index_cache = json.load(f)
            return cls._index_cache
        except (json.JSONDecodeError, IOError):
            return None

    @classmethod
    def _load_tasks_from_files(cls) -> Optional[Dict[str, Any]]:
        """
        从拆分后的文件中加载所有任务

        优先尝试单文件模式，如果不存在则使用旧的拆分模式

        Returns:
            完整的任务数据，如果拆分文件不存在则返回 None
        """
        index = cls._load_index()
        if index is None:
            return None

        harness_dir = cls.get_task_json_path().parent

        # 检查是否为单文件模式（version 2）
        if index.get('storage_mode') == 'single_file':
            return cls._load_from_single_file_mode(index, harness_dir)

        # 否则使用旧的拆分模式
        return cls._load_from_split_mode(index, harness_dir)

    @classmethod
    def _load_from_single_file_mode(
        cls,
        index: Dict[str, Any],
        harness_dir: Path
    ) -> Dict[str, Any]:
        """从单文件模式加载所有任务"""
        all_tasks = []
        loaded_count = 0
        error_count = 0

        # 只加载 pending 任务（自动循环主要需要这个）
        pending_dir = harness_dir / 'tasks' / 'pending'
        if pending_dir.exists():
            for task_file in pending_dir.glob('*.json'):
                try:
                    with open(task_file, 'r', encoding='utf-8') as f:
                        encoded = json.load(f)
                    task = cls.decode_task(encoded)
                    all_tasks.append(task)
                    loaded_count += 1
                except Exception as e:
                    error_count += 1

        # 如果需要所有任务，也加载 completed
        # （大部分情况下只需要 pending，所以注释掉）
        # completed_dir = harness_dir / 'tasks' / 'completed'
        # if completed_dir.exists():
        #     for task_file in completed_dir.rglob('*.json'):
        #         try:
        #             with open(task_file, 'r', encoding='utf-8') as f:
        #                 encoded = json.load(f)
        #             task = cls.decode_task(encoded)
        #             all_tasks.append(task)
        #             loaded_count += 1
        #         except Exception:
        #             error_count += 1

        return {
            'version': 2,
            'project': index.get('project', '配料表安全检测系统'),
            'tasks': all_tasks,
            '_single_file_mode': True,
            '_loaded_count': loaded_count,
            '_error_count': error_count,
        }

    @classmethod
    def _load_from_split_mode(
        cls,
        index: Dict[str, Any],
        harness_dir: Path
    ) -> Dict[str, Any]:
        """从旧的拆分模式加载所有任务（向后兼容）"""
        all_tasks = []
        loaded_files = set()

        # 加载待处理任务
        pending_file = harness_dir / 'tasks' / 'pending.json'
        if pending_file.exists():
            try:
                with open(pending_file, 'r', encoding='utf-8') as f:
                    pending_data = json.load(f)
                    all_tasks.extend(pending_data.get('tasks', []))
                    loaded_files.add('pending')
            except (json.JSONDecodeError, IOError):
                pass

        # 加载已完成任务
        completed_dir = harness_dir / 'tasks' / 'completed'
        if completed_dir.exists():
            for month_file in sorted(completed_dir.glob('*.json')):
                try:
                    with open(month_file, 'r', encoding='utf-8') as f:
                        month_data = json.load(f)
                        all_tasks.extend(month_data.get('tasks', []))
                        loaded_files.add(month_file.stem)
                except (json.JSONDecodeError, IOError):
                    pass

        # 解码任务
        all_tasks = [cls.decode_task(t) for t in all_tasks]

        # 构造完整的任务数据结构
        return {
            'version': 2,
            'project': index.get('project', '配料表安全检测系统'),
            'tasks': all_tasks,
            '_split_source': True,  # 标记来源于拆分文件
        }

    @classmethod
    def clear_index_cache(cls):
        """清除索引缓存"""
        cls._index_cache = None


# 便捷函数（向后兼容旧代码）
def load_tasks(path: Optional[str] = None) -> Dict[str, Any]:
    """加载任务文件（便捷函数）"""
    return TaskCodec.load_tasks(path)


def save_tasks(data: Dict[str, Any], path: Optional[str] = None):
    """保存任务文件（便捷函数）"""
    TaskCodec.save_tasks(data, path)


def get_task_json_path() -> Path:
    """获取 task.json 路径（便捷函数）"""
    return TaskCodec.get_task_json_path()


# 测试代码
if __name__ == '__main__':
    import sys

    # 测试加载
    print("📊 测试 TaskCodec")
    print("=" * 50)

    try:
        data = TaskCodec.load_tasks()
        tasks = data.get('tasks', [])

        print(f"✅ 成功加载任务文件")
        print(f"   总任务数: {len(tasks)}")

        # 显示格式统计
        stats = TaskCodec.get_format_stats()
        print(f"\n📈 文件统计:")
        print(f"   文件大小: {stats['file_size_kb']} KB")
        print(f"   格式版本: {stats['format']}")
        print(f"   平均任务大小: {stats['avg_task_size']} Bytes")

        # 显示第一个任务（解码后）
        if tasks:
            first_task = tasks[0]
            print(f"\n📋 第一个任务示例:")
            print(f"   ID: {first_task.get('id')}")
            print(f"   描述: {first_task.get('description')}")
            if 'stages' in first_task:
                stages = first_task['stages']
                if 'dev' in stages:
                    dev_completed = stages['dev'].get('completed', False)
                    dev_at = stages['dev'].get('completed_at', 'N/A')
                    print(f"   Dev 阶段: {'完成' if dev_completed else '待处理'} ({dev_at})")

        print("\n✅ 所有测试通过！")

    except FileNotFoundError:
        print(f"❌ 错误: task.json 文件不存在", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"❌ 错误: JSON 解析失败 - {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"❌ 错误: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
