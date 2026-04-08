#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

"""
下一阶段调度器
====================================

基于原 next_stage.py 重写，返回结构化字典而非纯文本。

核心逻辑：
1. 按 P0→P3 优先级排序
2. 跳过被 .automation_skip 标记的任务
3. 检查任务依赖是否已满足
4. 自动执行验证类任务（test/style）
5. 按 dev → test → review → validation 顺序推进

使用方式:
    from scripts.next_stage import get_next_pending_stage

    result = get_next_pending_stage()
    # result = {"task_id": ..., "stage": ..., "task": ..., "description": ...}
    # result = None  (所有任务已完成)

====================================
"""

import os
import sys
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional


# 路径注入
_scripts_dir = Path(__file__).parent.resolve()
sys.path.insert(0, str(_scripts_dir.parent))

from scripts.config import (
    HARNESS_DIR,
    TASKS_DIR,
    ENABLE_AUTO_VALIDATION,
)
from scripts.logger import app_logger
from scripts.task_storage import TaskStorage


# ========================================
#  验证类任务配置
# ========================================

VALIDATION_CATEGORIES = ["test", "style", "validation"]

VALIDATION_COMMANDS = {
    "test": "php artisan test",
    "style": "vendor/bin/pint --test",
}

# 优先级排序映射
_PRIORITY_ORDER = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}


# ========================================
#  核心函数
# ========================================

def get_next_pending_stage() -> Optional[dict]:
    """
    获取下一个待处理的任务阶段

    Returns:
        dict: {
            "task_id": str,
            "stage": str,          # dev / test / review / validation
            "task": dict,          # 完整任务数据
            "description": str,
            "category": str,
        }
        None: 没有待处理任务
    """
    storage = TaskStorage()

    # 加载所有待处理任务
    tasks = storage.load_all_pending_tasks()

    # 按优先级排序
    tasks.sort(key=lambda t: _PRIORITY_ORDER.get(t.get("priority", "P2"), 1))

    # 加载跳过列表
    skip_dir = HARNESS_DIR / ".automation_skip"
    skipped = set()
    if skip_dir.exists():
        skipped = {f.name for f in skip_dir.iterdir() if f.is_file()}

    blocked_report = []

    for task in tasks:
        task_id = task["id"]

        # 跳过被标记的任务
        if task_id in skipped:
            continue

        # 依赖检查
        deps_ok, blocked_by = _check_dependencies(task, storage)
        if not deps_ok:
            blocked_report.append({"task_id": task_id, "blocked_by": blocked_by})
            continue

        # 验证类任务自动执行
        if ENABLE_AUTO_VALIDATION:
            category = task.get("category", "")
            if category in VALIDATION_CATEGORIES and not task.get("passes", False):
                if _auto_execute_validation(task_id, task, category, storage):
                    app_logger.info(f"验证任务 {task_id} 自动完成，继续下一个")
                    continue
                else:
                    app_logger.warning(f"验证任务 {task_id} 自动执行失败，跳过")
                    _mark_skipped(task_id, skip_dir)
                    continue

        # 确定下一个阶段
        stage = _next_stage_for(task)
        if stage is None:
            continue

        return {
            "task_id": task_id,
            "stage": stage,
            "task": task,
            "description": task.get("description", ""),
            "category": task.get("category", "general"),
            "depends_on": task.get("depends_on", []),
        }

    # 报告被阻塞的任务
    if blocked_report:
        app_logger.info("部分任务因依赖未满足被跳过:")
        for item in blocked_report:
            deps_str = ", ".join(
                b.get("id", str(b)) + (f" ({b['reason']})" if b.get("reason") else "")
                for b in item["blocked_by"]
            )
            app_logger.info(f"  {item['task_id']} 等待: {deps_str}")

    return None


def _next_stage_for(task: dict) -> Optional[str]:
    """
    确定任务的下一个待处理阶段

    阶段推进顺序: dev → test → review → validation(可选)
    """
    # 旧格式（无 stages 字段）
    if "stages" not in task:
        if not task.get("passes", False):
            return "dev"
        return None

    stages = task["stages"]

    for stage_name in ["dev", "test", "review"]:
        if not stages.get(stage_name, {}).get("completed", False):
            return stage_name

    # validation 阶段（仅在启用时）
    val_cfg = task.get("validation", {})
    if val_cfg.get("enabled", False):
        if not stages.get("validation", {}).get("completed", False):
            return "validation"

    return None


def _check_dependencies(task: dict, storage: TaskStorage) -> tuple:
    """
    检查任务依赖是否满足

    逐条检查 depends_on 中的任务 ID，
    要求前置任务的 dev + test 阶段均已完成才算满足。
    未通过的依赖会通过 app_logger.info 打印，方便排查死锁。

    Returns:
        (satisfied: bool, blocked_by: list)
    """
    depends_on = task.get("depends_on", [])
    if not depends_on:
        return True, []

    task_id = task["id"]
    blocked = []

    for dep in depends_on:
        if isinstance(dep, dict):
            dep_id = dep.get("id") or dep.get("task_id")
            dep_reason = dep.get("reason", "")
        else:
            dep_id = dep
            dep_reason = ""

        if not storage.is_task_fully_completed(dep_id):
            info = {"id": dep_id}
            if dep_reason:
                info["reason"] = dep_reason
            blocked.append(info)
            app_logger.info(
                f"任务 {task_id} 因依赖 {dep_id} 未完成被挂起"
            )

    return len(blocked) == 0, blocked


def _auto_execute_validation(task_id: str, task: dict,
                             category: str, storage: TaskStorage) -> bool:
    """自动执行验证类任务"""
    command = VALIDATION_COMMANDS.get(category)
    if not command:
        app_logger.warning(f"未定义 category '{category}' 的验证命令")
        return False

    app_logger.info(f"自动执行验证命令: {command}")

    try:
        result = subprocess.run(
            command, shell=True,
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            timeout=600, cwd=HARNESS_DIR.parent,
        )

        if result.returncode == 0:
            # 标记所有阶段完成
            storage.complete_task(task_id)
            return True
        else:
            app_logger.warning(f"验证失败 (exit={result.returncode}): {result.stdout[:200]}")
            return False

    except subprocess.TimeoutExpired:
        app_logger.warning(f"验证任务超时 (10min)")
        return False
    except Exception as e:
        app_logger.warning(f"验证任务异常: {e}")
        return False


def _mark_skipped(task_id: str, skip_dir: Path) -> None:
    """标记任务为永久跳过"""
    skip_dir.mkdir(parents=True, exist_ok=True)
    (skip_dir / task_id).write_text(
        f"自动执行失败于 {datetime.now().isoformat()}\n",
        encoding="utf-8",
    )
