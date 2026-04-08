#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Harness 系统重置脚本
====================================

替代原有 Shell 脚本: reset_harness.sh

功能:
- 清空所有任务数据
- 重置日志和会话
- 重建 task-index.json
- 初始化知识库

使用方式:
    python .harness/scripts/reset_harness.py

====================================
"""

import sys
import platform

# Windows UTF-8 修复
if platform.system() == 'Windows':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except:
        pass

import shutil
import json
from pathlib import Path
from datetime import datetime

# 路径注入
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.config import (
    HARNESS_DIR,
    PROJECT_ROOT,
    TASKS_DIR,
    KNOWLEDGE_DIR,
    ARTIFACTS_DIR,
    CLI_IO_DIR
)
from scripts.logger import app_logger


def _get_current_year_month():
    """获取当前年月"""
    now = datetime.now()
    return now.strftime("%Y"), now.strftime("%m")


def confirm_reset():
    """确认重置操作"""
    app_logger.warning("⚠️" + "=" * 58)
    app_logger.warning("⚠️  Harness 系统重置")
    app_logger.warning("⚠️" + "=" * 58)
    app_logger.info("")
    app_logger.warning("此操作将清空以下内容:")
    app_logger.warning("   - 所有待处理任务 (tasks/pending/)")
    app_logger.warning("   - 所有已完成任务 (tasks/completed/)")
    app_logger.warning("   - 所有产出记录 (artifacts/)")
    app_logger.warning("   - 所有 CLI 会话 (cli-io/)")
    app_logger.warning("   - 所有运行日志 (logs/automation/)")
    app_logger.warning("   - 任务索引文件 (task-index.json)")
    app_logger.info("")

    try:
        confirm = input("⚠️  确认重置? 此操作不可撤销! 输入 'yes' 继续: ").strip().lower()
    except EOFError:
        # 非交互式环境
        confirm = "no"
        app_logger.info("(非交互模式，视为取消)")

    if confirm != "yes":
        app_logger.info("操作已取消")
        return False

    return True


def clear_directory(directory: Path, pattern: str = "*"):
    """清空目录内容"""
    if not directory.exists():
        return 0

    count = 0
    for item in directory.glob(pattern):
        try:
            if item.is_file():
                item.unlink()
                count += 1
            elif item.is_dir():
                shutil.rmtree(item)
                count += 1
        except Exception as e:
            app_logger.warning(f"   无法删除: {item} - {e}")

    return count


def clear_tasks():
    """清空任务数据"""
    app_logger.info("")
    app_logger.info("1️⃣  清空任务数据...")

    # 清空 pending
    pending_dir = TASKS_DIR / "pending"
    if pending_dir.exists():
        pending_count = clear_directory(pending_dir, "*.json")
        app_logger.success(f"   ✓ 已清空 pending: {pending_count} 个文件")

    # 清空 completed (按年月)
    completed_dir = TASKS_DIR / "completed"
    if completed_dir.exists():
        # 保留目录结构，只清空文件
        for year_dir in completed_dir.rglob("*"):
            if year_dir.is_dir():
                file_count = clear_directory(year_dir, "*.json")
                if file_count > 0:
                    app_logger.debug(f"   已清空: {year_dir.relative_to(TASKS_DIR)} - {file_count} 个")
        app_logger.success("   ✓ 已清空 completed 目录")


def clear_artifacts():
    """清空产出记录"""
    app_logger.info("")
    app_logger.info("2️⃣  清空产出记录...")

    artifacts_dir = ARTIFACTS_DIR
    count = clear_directory(artifacts_dir, "*.json")
    app_logger.success(f"   ✓ 已清空 artifacts: {count} 个文件")


def clear_cli_io():
    """清空 CLI 会话"""
    app_logger.info("")
    app_logger.info("3️⃣  清空 CLI 会话...")

    # 清空 current.json
    current_file = CLI_IO_DIR / "current.json"
    if current_file.exists():
        current_file.unlink()
        app_logger.debug("   ✓ 已删除 current.json")

    # 清空 sessions 目录
    sessions_dir = CLI_IO_DIR / "sessions"
    if sessions_dir.exists():
        session_count = clear_directory(sessions_dir)
        app_logger.success(f"   ✓ 已清空 sessions: {session_count} 个文件")


def clear_logs():
    """清空运行日志"""
    app_logger.info("")
    app_logger.info("4️⃣  清空运行日志...")

    logs_dir = HARNESS_DIR / "logs"
    if logs_dir.exists():
        # 保留 logs 目录本身
        for item in logs_dir.rglob("*"):
            if item.is_file() and item.suffix in [".log", ".txt", ".md"]:
                try:
                    item.unlink()
                except Exception as e:
                    app_logger.warning(f"   无法删除: {item}")

        # 删除空的子目录
        for subdir in sorted(logs_dir.rglob("*"), key=lambda p: len(p.parts), reverse=True):
            if subdir.is_dir() and not any(subdir.iterdir()):
                try:
                    subdir.rmdir()
                except:
                    pass

        app_logger.success("   ✓ 已清空 logs 目录")


def reset_task_index():
    """重置任务索引"""
    app_logger.info("")
    app_logger.info("5️⃣  重置任务索引...")

    # 获取项目名称
    index_file = HARNESS_DIR / "task-index.json"
    project_name = "新项目"

    if index_file.exists():
        try:
            old_data = json.loads(index_file.read_text(encoding="utf-8"))
            old_project = old_data.get("project", "新项目")
            app_logger.info(f"   当前项目名称: {old_project}")

            # 询问新名称
            try:
                new_name = input(f"   输入新项目名称 (直接回车保持 '{old_project}'): ").strip()
                project_name = new_name if new_name else old_project
            except EOFError:
                project_name = old_project
                app_logger.info(f"(非交互模式，使用: {project_name})")

        except Exception:
            pass

    # 创建新的 task-index.json
    new_index = {
        "version": 1,
        "storage_mode": "single_file",
        "project": project_name,
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
        "total_tasks": 0,
        "pending": 0,
        "completed": 0,
        "index": {},
        "modules": {},
        "priorities": {}
    }

    index_file.write_text(
        json.dumps(new_index, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

    app_logger.success(f"   ✓ 已创建 task-index.json (项目: {project_name})")


def init_knowledge_base():
    """初始化知识库"""
    app_logger.info("")
    app_logger.info("6️⃣  初始化知识库...")

    # 确保目录存在
    KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)

    # contracts.json
    contracts_file = KNOWLEDGE_DIR / "contracts.json"
    contracts_data = {
        "version": 1,
        "updated_at": datetime.now().isoformat(),
        "services": {}
    }
    contracts_file.write_text(
        json.dumps(contracts_data, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )
    app_logger.success("   ✓ 已初始化 contracts.json")

    # constraints.json
    constraints_file = KNOWLEDGE_DIR / "constraints.json"
    constraints_data = {
        "version": 1,
        "updated_at": datetime.now().isoformat(),
        "global": [],
        "by_task": {}
    }
    constraints_file.write_text(
        json.dumps(constraints_data, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )
    app_logger.success("   ✓ 已初始化 constraints.json")


def ensure_directories():
    """确保必要的目录结构存在"""
    app_logger.info("")
    app_logger.info("7️⃣  创建目录结构...")

    year, month = _get_current_year_month()

    directories = [
        TASKS_DIR / "pending",
        TASKS_DIR / "completed" / year / month,
        KNOWLEDGE_DIR,
        ARTIFACTS_DIR,
        CLI_IO_DIR / "sessions",
        HARNESS_DIR / "logs" / "automation" / year / month
    ]

    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)
        app_logger.debug(f"   ✓ {directory.relative_to(HARNESS_DIR)}")


def main():
    """主函数"""
    app_logger.info("")
    app_logger.info("=" * 60)
    app_logger.info("🚀 Harness 系统重置")
    app_logger.info("=" * 60)
    app_logger.info(f"Harness 目录: {HARNESS_DIR}")
    app_logger.info(f"项目目录: {PROJECT_ROOT}")
    app_logger.info("")

    # 确认操作
    if not confirm_reset():
        return 1

    # 执行清空
    clear_tasks()
    clear_artifacts()
    clear_cli_io()
    clear_logs()

    # 重置索引
    reset_task_index()

    # 初始化知识库
    init_knowledge_base()

    # 创建目录
    ensure_directories()

    # 完成
    app_logger.info("")
    app_logger.info("=" * 60)
    app_logger.success("✅ Harness 系统重置完成！")
    app_logger.info("=" * 60)
    app_logger.info("")
    app_logger.info("下一步操作:")
    app_logger.info("   1. 使用 add_task.py 创建新任务")
    app_logger.info("   2. 运行 run_automation.py 启动自动化")
    app_logger.info("")

    return 0


if __name__ == "__main__":
    sys.exit(main())
