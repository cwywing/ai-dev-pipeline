#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

"""
任务存储引擎
====================================

基于原 task_file_storage.py 重构，接入 Phase 1 基座。

核心职责：
- O(1) 任务存取（单文件模式）
- 阶段状态管理（mark/reset/query）
- Validation 回滚支持（add_issue / reset_stages）
- 原子写入，索引缓存

使用方式:
    from scripts.task_storage import TaskStorage

    storage = TaskStorage()
    task = storage.load_task("Model_001")
    storage.mark_stage("Model_001", "dev")
    storage.add_issue("Model_001", "dev", "Validation failed: ...")
    storage.reset_stages("Model_001", ["dev", "test", "review", "validation"])

====================================
"""

import json
import os
from pathlib import Path
from datetime import datetime
from typing import Any, Optional


# 路径注入 - 需要 scripts/ 和 .harness/ 都在 sys.path 中
import sys as _sys
_scripts_pkg_dir = Path(__file__).parent.resolve()
_sys.path.insert(0, str(_scripts_pkg_dir.parent))    # .harness/
_sys.path.insert(0, str(_scripts_pkg_dir))            # .harness/scripts/ (console_output 等)

from scripts.config import (
    HARNESS_DIR,
    TASKS_DIR,
    ARTIFACTS_DIR,
    get_task_file,
    get_task_dir,
)
from scripts.logger import app_logger


# ========================================
#  TaskCodec 兼容层
# ========================================
# 尝试导入 TaskCodec（原 task_utils.py 提供），
# 如果不可用则直接读写原始 JSON。

try:
    from scripts.task_utils import TaskCodec
    _CODEC_AVAILABLE = True
except ImportError:
    _CODEC_AVAILABLE = False


def _encode_task(task: dict) -> dict:
    """编码任务数据（兼容旧格式）"""
    if _CODEC_AVAILABLE:
        return TaskCodec.encode_task(task)
    return task


def _decode_task(raw: dict) -> dict:
    """解码任务数据（兼容旧格式）"""
    if _CODEC_AVAILABLE:
        return TaskCodec.decode_task(raw)
    return raw


# ========================================
#  TaskStorage
# ========================================

class TaskStorage:
    """任务存储引擎"""

    def __init__(self):
        self._index_cache: Optional[dict] = None
        self.index_path = HARNESS_DIR / "task-index.json"

    # --------------------------------------------------
    #  基础存取
    # --------------------------------------------------

    def load_index(self) -> dict:
        """加载索引（带缓存）"""
        if self._index_cache is not None:
            return self._index_cache

        if not self.index_path.exists():
            self._rebuild_index()
            return self._index_cache

        try:
            self._index_cache = json.loads(
                self.index_path.read_text(encoding="utf-8")
            )
        except Exception:
            app_logger.warning("索引加载失败，重建索引...")
            self._rebuild_index()

        return self._index_cache

    def _save_index(self, index: dict) -> None:
        """原子写入索引"""
        tmp = self.index_path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(index, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        tmp.replace(self.index_path)
        self._index_cache = index

    def load_task(self, task_id: str) -> Optional[dict]:
        """
        加载单个任务

        Returns:
            任务字典，不存在返回 None
        """
        index = self.load_index()
        entry = index.get("index", {}).get(task_id)
        if not entry:
            return None

        task_file = HARNESS_DIR / entry["file"]
        if not task_file.exists():
            # 索引可能过期，重建
            self._index_cache = None
            index = self.load_index()
            entry = index.get("index", {}).get(task_id)
            if not entry:
                return None
            task_file = HARNESS_DIR / entry["file"]
            if not task_file.exists():
                return None

        try:
            raw = json.loads(task_file.read_text(encoding="utf-8"))
            return _decode_task(raw)
        except Exception as e:
            app_logger.warning(f"加载任务 {task_id} 失败: {e}")
            return None

    def save_task(self, task: dict) -> bool:
        """
        保存任务（原子写入）

        自动处理 pending ↔ completed 的文件迁移和索引更新。
        """
        task_id = task["id"]
        is_completed = task.get("passes", False)

        encoded = _encode_task(task)
        target_file = get_task_file(task_id, completed=is_completed)
        target_file.parent.mkdir(parents=True, exist_ok=True)

        # 清理旧位置文件
        old_entry = self.load_index().get("index", {}).get(task_id)
        if old_entry:
            old_file = HARNESS_DIR / old_entry["file"]
            if old_file.exists() and old_file != target_file:
                try:
                    old_file.unlink()
                except OSError:
                    pass

        # 原子写入
        tmp = target_file.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(encoded, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        tmp.replace(target_file)

        # 更新索引
        self._update_index_entry(task_id, target_file, task)
        return True

    def load_all_pending_tasks(self) -> list[dict]:
        """加载所有待处理任务"""
        index = self.load_index()
        tasks = []
        for task_id, entry in index.get("index", {}).items():
            if entry.get("status") != "pending":
                continue
            task = self.load_task(task_id)
            if task:
                tasks.append(task)
        return tasks

    # --------------------------------------------------
    #  阶段状态管理
    # --------------------------------------------------

    def mark_stage(self, task_id: str, stage: str, *,
                   files: str = "", issues: list = None,
                   test_results: dict = None, risk_level: str = None) -> bool:
        """
        标记阶段完成

        Args:
            task_id: 任务 ID
            stage: 阶段名 (dev/test/review/validation)
            files: Git 变更文件列表（空格分隔，仅 dev 阶段使用）
            issues: 阶段问题列表
            test_results: 测试结果字典（仅 test 阶段）
            risk_level: 风险等级（仅 review 阶段）
        """
        task = self.load_task(task_id)
        if not task:
            app_logger.error(f"mark_stage: 任务 {task_id} 不存在")
            return False

        if "stages" not in task:
            task["stages"] = self._default_stages()

        stage_key = stage.lower()
        if stage_key not in task["stages"]:
            task["stages"][stage_key] = {}

        task["stages"][stage_key]["completed"] = True
        task["stages"][stage_key]["completed_at"] = datetime.now().isoformat()

        if files:
            task["stages"][stage_key]["files"] = files
        if issues is not None:
            task["stages"][stage_key]["issues"] = issues
        if test_results is not None:
            task["stages"][stage_key]["test_results"] = test_results
        if risk_level is not None:
            task["stages"][stage_key]["risk_level"] = risk_level

        return self.save_task(task)

    def reset_stages(self, task_id: str, stages: list[str] = None) -> bool:
        """
        重置指定阶段状态（用于 Validation 回滚）

        Args:
            task_id: 任务 ID
            stages: 要重置的阶段列表，None 表示重置全部
        """
        task = self.load_task(task_id)
        if not task:
            app_logger.error(f"reset_stages: 任务 {task_id} 不存在")
            return False

        if "stages" not in task:
            task["stages"] = self._default_stages()

        if stages is None:
            stages = list(task["stages"].keys())

        for s in stages:
            s = s.lower()
            if s in task["stages"]:
                task["stages"][s]["completed"] = False
                task["stages"][s]["completed_at"] = None

        return self.save_task(task)

    def add_issue(self, task_id: str, stage: str, issue: str) -> bool:
        """
        向指定阶段添加反馈问题（用于 Validation 回滚注入反馈）

        Args:
            task_id: 任务 ID
            stage: 阶段名
            issue: 反馈文本
        """
        task = self.load_task(task_id)
        if not task:
            return False

        if "stages" not in task:
            task["stages"] = self._default_stages()

        stage_key = stage.lower()
        if stage_key not in task["stages"]:
            task["stages"][stage_key] = {}

        if "issues" not in task["stages"][stage_key]:
            task["stages"][stage_key]["issues"] = []

        task["stages"][stage_key]["issues"].append(issue)
        return self.save_task(task)

    def get_stage_issues(self, task_id: str, stage: str) -> list[str]:
        """获取指定阶段的问题列表"""
        task = self.load_task(task_id)
        if not task or "stages" not in task:
            return []

        stage_data = task["stages"].get(stage.lower(), {})
        return stage_data.get("issues", [])

    def get_stage_data(self, task_id: str, stage: str, key: str,
                       default=None) -> Any:
        """获取阶段数据中的指定字段"""
        task = self.load_task(task_id)
        if not task or "stages" not in task:
            return default
        return task["stages"].get(stage.lower(), {}).get(key, default)

    def is_stage_complete(self, task_id: str, stage: str) -> bool:
        """检查指定阶段是否完成"""
        task = self.load_task(task_id)
        if not task or "stages" not in task:
            return False
        return task["stages"].get(stage.lower(), {}).get("completed", False)

    def is_all_stages_complete(self, task_id: str) -> bool:
        """
        检查任务的所有阶段是否完成

        考虑 validation 是否启用。
        """
        task = self.load_task(task_id)
        if not task or "stages" not in task:
            return False

        stages = task["stages"]
        required = ["dev", "test", "review"]

        # validation 阶段仅在启用时要求
        val_cfg = task.get("validation", {})
        if val_cfg.get("enabled", False):
            required.append("validation")

        return all(stages.get(s, {}).get("completed", False) for s in required)

    def mark_validation(self, task_id: str, score: float, tries: int) -> bool:
        """标记 Validation 阶段通过"""
        return self.mark_stage(task_id, "validation")

    # --------------------------------------------------
    #  任务属性便捷方法
    # --------------------------------------------------

    def get_complexity(self, task_id: str) -> str:
        """获取任务复杂度"""
        task = self.load_task(task_id)
        return task.get("complexity", "unknown") if task else "unknown"

    def get_validation_config(self, task_id: str) -> dict:
        """获取 Validation 配置"""
        task = self.load_task(task_id)
        if not task:
            return {"enabled": False, "threshold": 0.8, "max_retries": 3}
        return {
            "enabled": task.get("validation", {}).get("enabled", False),
            "threshold": task.get("validation", {}).get("threshold", 0.8),
            "max_retries": task.get("validation", {}).get("max_retries", 3),
        }

    def get_description(self, task_id: str) -> str:
        """获取任务描述"""
        task = self.load_task(task_id)
        return task.get("description", "") if task else ""

    def get_acceptance(self, task_id: str) -> list[str]:
        """获取验收标准列表"""
        task = self.load_task(task_id)
        return task.get("acceptance", []) if task else []

    def get_depends_on(self, task_id: str) -> list:
        """获取依赖任务列表"""
        task = self.load_task(task_id)
        return task.get("depends_on", []) if task else []

    def is_dependency_satisfied(self, dep_id: str) -> bool:
        """检查单个依赖是否已满足"""
        dep_task = self.load_task(dep_id)
        if not dep_task:
            return False
        if dep_task.get("passes", False):
            return True
        # 检查所有标准阶段
        stages = dep_task.get("stages", {})
        return all(stages.get(s, {}).get("completed", False)
                   for s in ["dev", "test", "review"])

    def is_task_fully_completed(self, task_id: str) -> bool:
        """
        判断任务是否已满足前置依赖条件。

        标准：dev 和 test 阶段均已完成。
        如果任务整体已标记 passes=True，也视为已完成。

        Args:
            task_id: 任务 ID

        Returns:
            True 表示前置产出已就绪
        """
        task = self.load_task(task_id)
        if not task:
            app_logger.debug(f"is_task_fully_completed: 任务 {task_id} 不存在")
            return False

        if task.get("passes", False):
            return True

        stages = task.get("stages", {})
        dev_done = stages.get("dev", {}).get("completed", False)
        test_done = stages.get("test", {}).get("completed", False)
        return dev_done and test_done

    def get_task_artifacts(self, task_id: str) -> dict:
        """
        读取任务的产出记录，提取有助于下游开发的信息。

        优先查找 ARTIFACTS_DIR/{task_id}.json，
        提取 design_decisions、interface_contracts、constraints、files 等字段。

        Args:
            task_id: 任务 ID

        Returns:
            dict: 至少包含空列表的 keys:
                  design_decisions, interface_contracts, constraints, files
        """
        result = {
            "design_decisions": [],
            "interface_contracts": [],
            "constraints": [],
            "files": [],
        }

        artifact_file = ARTIFACTS_DIR / f"{task_id}.json"
        if not artifact_file.exists():
            return result

        try:
            data = json.loads(artifact_file.read_text(encoding="utf-8"))
        except Exception as e:
            app_logger.debug(f"读取 {task_id} 产出文件失败: {e}")
            return result

        for key in result:
            value = data.get(key, [])
            if isinstance(value, list):
                result[key] = value
            elif value:
                result[key] = [value]

        return result

    def complete_task(self, task_id: str) -> bool:
        """标记任务完成并归档"""
        task = self.load_task(task_id)
        if not task:
            return False
        task["passes"] = True
        return self.save_task(task)

    # --------------------------------------------------
    #  产出记录
    # --------------------------------------------------

    def get_artifacts_list(self, task_id: str) -> str:
        """获取任务的产出列表（格式化文本）"""
        artifact_file = ARTIFACTS_DIR / f"{task_id}.json"
        if not artifact_file.exists():
            return ""

        try:
            data = json.loads(artifact_file.read_text(encoding="utf-8"))
            files = data.get("files", [])
            if files:
                return "\n".join(f"  - {f}" for f in files)
        except Exception:
            pass
        return ""

    # --------------------------------------------------
    #  索引管理
    # --------------------------------------------------

    def _rebuild_index(self) -> None:
        """重建索引"""
        index = {
            "version": 2,
            "storage_mode": "single_file",
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "total_tasks": 0,
            "pending": 0,
            "completed": 0,
            "index": {},
        }

        pending_dir = TASKS_DIR / "pending"
        completed_dir = TASKS_DIR / "completed"

        if pending_dir.exists():
            for f in pending_dir.glob("*.json"):
                self._index_scan_file(f, index, "pending")

        if completed_dir.exists():
            for f in completed_dir.rglob("*.json"):
                self._index_scan_file(f, index, "completed")

        index["total_tasks"] = index["pending"] + index["completed"]
        self._save_index(index)

    def _index_scan_file(self, task_file: Path, index: dict,
                         status: str) -> None:
        """扫描单个任务文件并添加到索引"""
        try:
            raw = json.loads(task_file.read_text(encoding="utf-8"))
            task = _decode_task(raw)
            task_id = task["id"]
            index["index"][task_id] = {
                "file": str(task_file.relative_to(HARNESS_DIR)),
                "status": status,
                "priority": task.get("priority", "P2"),
                "module": task.get("module", ""),
                "category": task.get("category", ""),
                "description": task.get("description", ""),
            }
            index[status] += 1
        except Exception as e:
            app_logger.debug(f"索引扫描跳过: {task_file} - {e}")

    def _update_index_entry(self, task_id: str, task_file: Path,
                            task: dict) -> None:
        """更新索引中的单个条目"""
        if self._index_cache is None:
            self.load_index()

        new_status = "completed" if task.get("passes", False) else "pending"
        old_entry = self._index_cache.get("index", {}).get(task_id)
        old_status = old_entry.get("status") if old_entry else None

        self._index_cache.setdefault("index", {})[task_id] = {
            "file": str(task_file.relative_to(HARNESS_DIR)),
            "status": new_status,
            "priority": task.get("priority", "P2"),
            "module": task.get("module", ""),
            "category": task.get("category", ""),
            "description": task.get("description", ""),
            "updated_at": datetime.now().isoformat(),
        }

        # 更新计数
        if old_status and old_status != new_status:
            self._index_cache[old_status] = max(0, self._index_cache.get(old_status, 0) - 1)
        self._index_cache[new_status] = self._index_cache.get(new_status, 0) + 1
        self._index_cache["total_tasks"] = self._index_cache["pending"] + self._index_cache["completed"]
        self._index_cache["updated_at"] = datetime.now().isoformat()

        self._save_index(self._index_cache)

    # --------------------------------------------------
    #  内部工具
    # --------------------------------------------------

    @staticmethod
    def _default_stages() -> dict:
        """返回默认的阶段结构"""
        return {
            "dev": {"completed": False, "completed_at": None, "issues": []},
            "test": {"completed": False, "completed_at": None, "issues": [], "test_results": {}},
            "review": {"completed": False, "completed_at": None, "issues": [], "risk_level": None},
            "validation": {"completed": False, "completed_at": None},
        }

    def clear_cache(self) -> None:
        """清除索引缓存"""
        self._index_cache = None
