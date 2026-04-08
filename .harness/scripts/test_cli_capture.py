#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CLI I/O 捕获测试脚本
====================================

替代原有 Shell 脚本: test_cli_capture.sh

功能:
- 测试 CLI 会话元数据创建
- 测试 CLI 输出文件捕获
- 模拟 CLI 执行并记录输出
- 验证后端 API 读取

使用方式:
    python .harness/scripts/test_cli_capture.py

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

import os
import json
import time
from pathlib import Path
from datetime import datetime

# 路径注入
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.config import PROJECT_ROOT, HARNESS_DIR, CLI_IO_DIR
from scripts.logger import app_logger


def setup_directories():
    """确保必要目录存在"""
    app_logger.info("设置目录结构...")

    sessions_dir = CLI_IO_DIR / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)

    app_logger.success(f"✓ CLI-I/O 目录: {CLI_IO_DIR}")
    app_logger.success(f"✓ Sessions 目录: {sessions_dir}")


def generate_session_id() -> str:
    """生成会话 ID"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    pid = os.getpid()
    return f"test_{timestamp}_{pid}"


def create_session_metadata(session_id: str) -> dict:
    """创建会话元数据"""
    app_logger.info("")
    app_logger.info(f"📝 创建测试会话...")
    app_logger.info(f"   Session ID: {session_id}")

    meta = {
        "session_id": session_id,
        "task_id": "TEST_TASK_001",
        "stage": "test",
        "start_time": datetime.now().isoformat(),
        "active": True
    }

    meta_file = CLI_IO_DIR / "current.json"

    try:
        meta_file.write_text(
            json.dumps(meta, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )
        app_logger.success("✓ 会话元数据已创建")
        return meta
    except Exception as e:
        app_logger.error(f"❌ 创建元数据失败: {e}")
        return None


def simulate_cli_output(session_id: str) -> bool:
    """模拟 CLI 执行并捕获输出"""
    app_logger.info("")
    app_logger.info("📹 模拟 CLI 执行并捕获输出...")

    output_file = CLI_IO_DIR / "sessions" / f"{session_id}_output.txt"

    # 模拟的 CLI 输出内容
    simulated_output = """
================================================================================
🤖 Claude CLI Output Simulation
================================================================================

✓ Analyzing task...
✓ Reading files...
✓ Writing code...

--------------------------------------------------------------------------------
PASS  Tests\\Feature\\Api\\Admin\\UserTest
   ✓ test_user_list_returns_paginated
   ✓ test_user_list_filters_by_name

--------------------------------------------------------------------------------
   Tests:  2 passed, 0 failed
   Duration: 1.23 seconds
   Memory: 45.2 MB

================================================================================
✅ Task completed successfully
================================================================================
""".strip()

    try:
        output_file.write_text(simulated_output, encoding="utf-8")
        app_logger.success("✓ CLI 执行完成")
        app_logger.success(f"✓ 输出文件: {output_file.relative_to(CLI_IO_DIR)}")

        # 显示文件大小
        size = output_file.stat().st_size
        app_logger.info(f"   文件大小: {size} 字节")

        return True

    except Exception as e:
        app_logger.error(f"❌ 写入输出文件失败: {e}")
        return False


def update_session_metadata(session_id: str):
    """更新会话元数据（标记完成）"""
    app_logger.info("")
    app_logger.info("📊 更新会话元数据...")

    meta_file = CLI_IO_DIR / "current.json"

    if not meta_file.exists():
        app_logger.warning("⚠️  元数据文件不存在")
        return False

    try:
        meta = json.loads(meta_file.read_text(encoding="utf-8"))

        # 更新状态
        meta["end_time"] = datetime.now().isoformat()
        meta["exit_code"] = 0
        meta["completed"] = True
        meta["active"] = False

        meta_file.write_text(
            json.dumps(meta, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )

        app_logger.success("✓ 会话元数据已更新")
        return True

    except Exception as e:
        app_logger.error(f"❌ 更新元数据失败: {e}")
        return False


def verify_output_file(session_id: str) -> bool:
    """验证输出文件"""
    app_logger.info("")
    app_logger.info("📡 验证输出文件...")

    output_file = CLI_IO_DIR / "sessions" / f"{session_id}_output.txt"

    if not output_file.exists():
        app_logger.error("❌ 输出文件未创建")
        return False

    try:
        content = output_file.read_text(encoding="utf-8")
        lines = content.strip().split("\n")

        app_logger.info(f"   输出行数: {len(lines)}")

        # 检查关键内容
        checks = [
            ("Claude CLI", "Claude CLI" in content),
            ("测试结果", "passed" in content),
            ("任务完成", "completed" in content or "✅" in content)
        ]

        all_passed = True
        for name, result in checks:
            status = "✓" if result else "✗"
            app_logger.info(f"   {status} {name}")

            if not result:
                all_passed = False

        return all_passed

    except Exception as e:
        app_logger.error(f"❌ 验证输出文件失败: {e}")
        return False


def test_api_read() -> bool:
    """测试后端 API 读取"""
    app_logger.info("")
    app_logger.info("📡 测试后端 API 读取...")

    meta_file = CLI_IO_DIR / "current.json"

    if not meta_file.exists():
        app_logger.warning("⚠️  元数据文件不存在")
        return False

    try:
        # 直接读取 JSON 文件（模拟 API 读取）
        meta = json.loads(meta_file.read_text(encoding="utf-8"))

        if meta.get("active"):
            app_logger.info("   API 返回 active=True (会话进行中)")
        else:
            app_logger.info("   API 返回 active=False (会话已完成)")

        task_id = meta.get("task_id", "N/A")
        session_id = meta.get("session_id", "N/A")
        stage = meta.get("stage", "N/A")

        app_logger.info(f"   Task ID: {task_id}")
        app_logger.info(f"   Session ID: {session_id}")
        app_logger.info(f"   Stage: {stage}")

        # 检查输出文件
        output_file = CLI_IO_DIR / "sessions" / f"{session_id}_output.txt"
        if output_file.exists():
            output_size = output_file.stat().st_size
            app_logger.info(f"   输出大小: {output_size} 字节")
        else:
            app_logger.warning("   ⚠️  输出文件不存在")

        app_logger.success("✓ API 读取测试通过")
        return True

    except Exception as e:
        app_logger.error(f"❌ API 读取测试失败: {e}")
        return False


def cleanup_test_files(session_id: str):
    """清理测试文件"""
    app_logger.info("")
    app_logger.info("🧹 清理测试文件...")

    files_to_clean = [
        CLI_IO_DIR / "current.json",
        CLI_IO_DIR / "sessions" / f"{session_id}_output.txt"
    ]

    for file_path in files_to_clean:
        if file_path.exists():
            try:
                file_path.unlink()
                app_logger.debug(f"   已删除: {file_path.relative_to(CLI_IO_DIR)}")
            except Exception as e:
                app_logger.warning(f"   无法删除: {file_path} - {e}")

    app_logger.success("✓ 清理完成")


def main():
    """主函数"""
    app_logger.info("=" * 60)
    app_logger.info("🚀 CLI I/O 捕获测试")
    app_logger.info("=" * 60)
    app_logger.info(f"Harness 目录: {HARNESS_DIR}")
    app_logger.info(f"CLI-I/O 目录: {CLI_IO_DIR}")
    app_logger.info("")

    # 设置目录
    setup_directories()

    # 生成会话 ID
    session_id = generate_session_id()

    # 创建会话元数据
    meta = create_session_metadata(session_id)
    if not meta:
        app_logger.error("测试失败：无法创建会话元数据")
        return 1

    # 模拟 CLI 输出
    cli_ok = simulate_cli_output(session_id)

    # 更新元数据
    update_session_metadata(session_id)

    # 验证输出文件
    verify_ok = verify_output_file(session_id)

    # 测试 API 读取
    api_ok = test_api_read()

    # 清理测试文件
    cleanup_test_files(session_id)

    # 汇总结果
    app_logger.info("")
    app_logger.info("=" * 60)
    app_logger.info("📊 测试结果")
    app_logger.info("=" * 60)

    checks = [
        ("CLI 执行模拟", cli_ok),
        ("输出文件验证", verify_ok),
        ("API 读取测试", api_ok)
    ]

    all_passed = True
    for name, result in checks:
        status = "✅" if result else "❌"
        app_logger.info(f"   {status} {name}")
        if not result:
            all_passed = False

    app_logger.info("")

    # 列出生成的文件
    app_logger.info("📁 生成的文件:")
    app_logger.info(f"   - {CLI_IO_DIR.relative_to(HARNESS_DIR)}/current.json")
    app_logger.info(f"   - {CLI_IO_DIR.relative_to(HARNESS_DIR)}/sessions/{session_id}_output.txt")

    app_logger.info("")
    app_logger.info("💡 接下来可以:")
    app_logger.info("   1. 运行自动化: python .harness/scripts/run_automation.py")
    app_logger.info("   2. 查看 CLI 会话: less .harness/cli-io/sessions/")

    app_logger.info("=" * 60)

    if all_passed:
        app_logger.success("🎉 CLI I/O 捕获测试完成！")
        return 0
    else:
        app_logger.warning("⚠️  部分测试失败")
        return 1


if __name__ == "__main__":
    sys.exit(main())
