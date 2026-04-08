#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI Dev Pipeline - 核心调度引擎
====================================

替代原 run-automation-stages.sh / windows/run-automation-stages.py，
成为跨平台统一的多智能体编排入口。

三阶段质量保证流水线: Dev -> Test -> Review -> (Validation)

架构特点:
- 全原生模块导入，零 subprocess 调用内部脚本
- DualTimeoutExecutor 统一双超时机制
- Validation 满意度评分与自动回滚
- 指数退避超时策略

使用方式:
    python .harness/scripts/run_automation.py            # 持续运行
    python .harness/scripts/run_automation.py --once     # 单次执行
    python .harness/scripts/run_automation.py --verbose   # 详细日志

====================================
"""

from __future__ import annotations

import math
import os
import platform
import re
import sys
import time
from datetime import datetime
from pathlib import Path

# Windows UTF-8 修复
if platform.system() == "Windows":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ========================================
#  路径注入 - Phase 1 基座
# ========================================
_scripts_dir = Path(__file__).parent.resolve()
sys.path.insert(0, str(_scripts_dir.parent))

from scripts.config import (
    PROJECT_ROOT,
    HARNESS_DIR,
    LOG_DIR,
    CLI_IO_DIR,
    TASKS_DIR,
    ARTIFACTS_DIR,
    TEMPLATES_DIR,
    CLAUDE_CMD,
    PERMISSION_MODE,
    BASE_SILENCE_TIMEOUT,
    MAX_SILENCE_TIMEOUT,
    TIMEOUT_BACKOFF_FACTOR,
    MAX_TIMEOUT_RETRIES,
    MAX_RETRIES,
    LOOP_SLEEP,
    get_timeout_for_stage,
)
from scripts.logger import app_logger

# ========================================
#  原生模块导入 - Phase 3 依赖
# ========================================
from scripts.task_storage import TaskStorage
from scripts.next_stage import get_next_pending_stage
from scripts.detect_stage_completion import DetectStageCompletion
from scripts.dual_timeout import DualTimeoutExecutor


# ========================================
#  AutomationEngine
# ========================================

class AutomationEngine:
    """
    自动化调度引擎

    职责:
    - 管理主循环生命周期
    - 协调 Dev/Test/Review/Validation 阶段
    - 动态超时计算（指数退避）
    - Validation 满意度评分与回滚
    """

    # 活性超时的最低值（低于此值不合理）
    MIN_SILENCE_TIMEOUT = 30

    def __init__(self, single_run: bool = False, verbose: bool = False):
        self.single_run = single_run
        self.verbose = verbose
        self.storage = TaskStorage()

        # 临时状态目录
        self.retry_dir = HARNESS_DIR / ".automation_retries"
        self.skip_dir = HARNESS_DIR / ".automation_skip"
        self.timeout_dir = HARNESS_DIR / ".automation_timeouts"

    # ========================================
    #  初始化
    # ========================================

    def ensure_directories(self) -> None:
        """确保必要目录存在"""
        for d in [
            self.retry_dir,
            self.skip_dir,
            self.timeout_dir,
            CLI_IO_DIR / "sessions",
            TASKS_DIR / "pending",
            TASKS_DIR / "completed",
            ARTIFACTS_DIR,
            LOG_DIR,
        ]:
            d.mkdir(parents=True, exist_ok=True)

    def check_prerequisites(self) -> bool:
        """检查运行前提"""
        checks = [
            (HARNESS_DIR / "task-index.json", "task-index.json"),
            (TASKS_DIR / "pending", "tasks/pending/"),
        ]

        all_ok = True
        for path, name in checks:
            if path.exists():
                app_logger.debug(f"  [OK] {name}")
            else:
                app_logger.error(f"  [MISSING] {name}")
                all_ok = False

        return all_ok

    # ========================================
    #  计数器管理
    # ========================================

    def _read_counter(self, directory: Path, key: str) -> int:
        """读取计数器"""
        f = directory / f"{key}.count"
        if f.exists():
            try:
                return int(f.read_text().strip())
            except (ValueError, OSError):
                return 0
        return 0

    def _write_counter(self, directory: Path, key: str, value: int) -> None:
        """写入计数器"""
        directory.mkdir(parents=True, exist_ok=True)
        (directory / f"{key}.count").write_text(str(value), encoding="utf-8")

    def _clear_counters(self, task_id: str, stage: str) -> None:
        """清除指定任务/阶段的计数器"""
        key = f"{task_id}_{stage}"
        for d in (self.retry_dir, self.timeout_dir):
            f = d / f"{key}.count"
            if f.exists():
                try:
                    f.unlink()
                except OSError:
                    pass

    def _increment_counter(self, directory: Path, task_id: str,
                           stage: str) -> int:
        """递增计数器并返回新值"""
        key = f"{task_id}_{stage}"
        val = self._read_counter(directory, key) + 1
        self._write_counter(directory, key, val)
        return val

    def _is_skipped(self, task_id: str) -> bool:
        """检查任务是否被永久跳过"""
        return (self.skip_dir / task_id).exists()

    def _mark_skipped(self, task_id: str) -> None:
        """永久跳过任务"""
        self.skip_dir.mkdir(parents=True, exist_ok=True)
        (self.skip_dir / task_id).write_text(
            f"Reached max retries at {datetime.now().isoformat()}\n",
            encoding="utf-8",
        )

    # ========================================
    #  超时计算
    # ========================================

    def _calculate_timeout(self, stage: str, prompt_size: int,
                           timeout_count: int) -> tuple:
        """
        计算动态超时

        Args:
            stage: 当前阶段
            prompt_size: Prompt 字节数
            timeout_count: 已超时次数

        Returns:
            (hard_timeout, silence_timeout)
        """
        # 基于阶段的基准超时（含指数退避）
        base = get_timeout_for_stage(stage, timeout_count)

        # Prompt 越大，需要越多时间
        size_bonus = int(prompt_size / 1024 * 1.0)

        # 总硬超时 = 基准 + prompt 补偿，封顶
        hard = min(base + size_bonus, MAX_SILENCE_TIMEOUT)

        # 活性超时：硬超时的一定比例，但不低于最小值
        silence = max(int(hard * 0.6), self.MIN_SILENCE_TIMEOUT)
        silence = min(silence, hard - 5)  # 活性超时必须小于硬超时

        return hard, silence

    # ========================================
    #  Prompt 组装
    # ========================================

    def _assemble_prompt(self, task_id: str, stage: str) -> str:
        """
        组装传递给 Claude CLI 的 Prompt

        组成:
        1. CLAUDE.md 项目规范（如果存在）
        2. 阶段专用模板（如果存在）
        3. 任务上下文（description, acceptance, issues）
        """
        parts = []

        # 1. CLAUDE.md
        claude_md = PROJECT_ROOT / "CLAUDE.md"
        if claude_md.exists():
            parts.append(claude_md.read_text(encoding="utf-8", errors="replace"))

        # 2. 阶段模板
        template = TEMPLATES_DIR / f"{stage}_prompt.md"
        if template.exists():
            tpl = template.read_text(encoding="utf-8", errors="replace")
            tpl = tpl.replace("{TASK_ID}", task_id)
            parts.append(tpl)

        # 3. 任务上下文
        ctx = self._build_task_context(task_id, stage)
        if ctx:
            parts.append(ctx)

        return "\n\n".join(parts)

    def _build_task_context(self, task_id: str, stage: str) -> str:
        """构建任务上下文（供 Agent 理解当前任务状态）"""
        task = self.storage.load_task(task_id)
        if not task:
            return ""

        lines = [
            "=" * 60,
            f"Current Task: {task_id}",
            f"Stage: {stage.upper()}",
            f"Description: {task.get('description', '')}",
            "=" * 60,
        ]

        # 验收标准
        acceptance = task.get("acceptance", [])
        if acceptance:
            lines.append("")
            lines.append("Acceptance Criteria:")
            for i, ac in enumerate(acceptance, 1):
                lines.append(f"  {i}. {ac}")

        # 当前阶段的 issues（被打回时）
        current_issues = self.storage.get_stage_issues(task_id, stage)
        if current_issues:
            lines.append("")
            lines.append(f"Previous {stage.upper()} Issues (must fix):")
            for i, issue in enumerate(current_issues, 1):
                lines.append(f"  {i}. {issue}")

        # 前一阶段的 issues（仅当当前阶段无 issues 时）
        if not current_issues and stage in ("test", "review"):
            prev = {"test": "dev", "review": "test"}.get(stage)
            prev_issues = self.storage.get_stage_issues(task_id, prev)
            if prev_issues:
                lines.append("")
                lines.append(f"Previous {prev.upper()} Issues (for reference):")
                for i, issue in enumerate(prev_issues, 1):
                    lines.append(f"  {i}. {issue}")

        # 产出文件
        artifacts = self.storage.get_artifacts_list(task_id)
        if artifacts:
            lines.append("")
            lines.append(f"Artifacts from previous stages:")
            lines.append(artifacts)

        return "\n".join(lines)

    # ========================================
    #  Agent 执行
    # ========================================

    def _execute_agent(self, prompt: str, stage: str,
                       task_id: str, timeout_count: int) -> dict:
        """
        执行 Claude CLI Agent

        Returns:
            {
                "exit_code": int,
                "output_file": Path,
                "is_timeout": bool,
                "session_id": str,
            }
        """
        prompt_bytes = len(prompt.encode("utf-8"))
        hard, silence = self._calculate_timeout(stage, prompt_bytes, timeout_count)

        app_logger.info(
            f"Executing Agent: stage={stage}, "
            f"timeout={hard}s, silence={silence}s, "
            f"prompt={prompt_bytes // 1024}KB"
        )

        # Claude CLI 命令
        cmd = [
            CLAUDE_CMD,
            "--print",
            "--permission-mode", PERMISSION_MODE,
        ]

        # 创建会话记录
        session_id = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{os.getpid()}"
        output_file = CLI_IO_DIR / "sessions" / f"{session_id}_output.txt"
        meta_file = CLI_IO_DIR / "current.json"

        # 写入会话元数据
        import json
        meta_file.write_text(
            json.dumps({
                "session_id": session_id,
                "task_id": task_id,
                "stage": stage,
                "start_time": datetime.now().isoformat(),
                "active": True,
                "prompt_size": prompt_bytes,
            }, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        # 实例化执行器并执行
        executor = DualTimeoutExecutor(
            hard_timeout=hard,
            silence_timeout=silence,
            verbose=self.verbose,
        )

        exit_code = executor.execute(cmd, prompt)

        # 更新会话元数据
        meta_file.write_text(
            json.dumps({
                "session_id": session_id,
                "task_id": task_id,
                "stage": stage,
                "end_time": datetime.now().isoformat(),
                "exit_code": exit_code,
                "active": False,
            }, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        is_timeout = exit_code in (14, 124)

        if is_timeout:
            label = "silence" if exit_code == 14 else "hard"
            app_logger.warning(f"Agent timeout ({label}): {task_id}/{stage}")
        else:
            app_logger.info(f"Agent exited: code={exit_code}, {task_id}/{stage}")

        return {
            "exit_code": exit_code,
            "output_file": output_file,
            "is_timeout": is_timeout,
            "session_id": session_id,
        }

    # ========================================
    #  阶段完成检测
    # ========================================

    def _detect_completion(self, task_id: str, stage: str) -> tuple:
        """
        检测阶段是否完成

        Returns:
            (is_complete: bool, message: str)
        """
        detector = DetectStageCompletion(task_id, stage)
        code, message = detector.detect()

        if code == 0:
            return True, message
        elif code == 2:
            app_logger.warning(f"Detection uncertain: {message}")
            return False, message
        else:
            return False, message

    # ========================================
    #  Validation 处理
    # ========================================

    def _handle_validation(self, task_id: str,
                           output_file: Path) -> tuple:
        """
        处理 Validation 阶段结果

        1. 提取 <score> 标签
        2. 与阈值比较
        3. 未达标时执行回滚

        Returns:
            (is_passed: bool, score: float | None)
        """
        if not output_file.exists():
            app_logger.warning("Validation: output file not found")
            return False, None

        content = output_file.read_text(encoding="utf-8", errors="ignore")

        # 提取分数
        match = re.search(
            r"<score>\s*(\d+(?:\.\d+)?)\s*</score>",
            content, re.IGNORECASE,
        )
        if not match:
            app_logger.warning("Validation: <score> tag not found")
            self._rollback_to_dev(task_id, "No <score> tag in output")
            return False, None

        score = float(match.group(1))

        # 归一化到百分制
        if score <= 1.0:
            score = score * 100

        # 从任务配置获取阈值
        val_cfg = self.storage.get_validation_config(task_id)
        threshold = val_cfg.get("threshold", 80.0)
        max_retries = val_cfg.get("max_retries", 3)

        app_logger.info(f"Validation score: {score:.1f} (threshold: {threshold:.1f})")

        if score >= threshold:
            app_logger.success(
                f"Validation PASSED: {score:.1f} >= {threshold:.1f}"
            )
            return True, score

        # 未达标 -> 回滚
        app_logger.warning(
            f"Validation FAILED: {score:.1f} < {threshold:.1f}"
        )

        # 检查回滚次数
        val_retry_count = self._read_counter(
            self.retry_dir, f"{task_id}_validation"
        )

        if val_retry_count >= max_retries:
            app_logger.error(
                f"Validation max retries reached ({max_retries}), "
                f"permanently skipping {task_id}"
            )
            self._mark_skipped(task_id)
            return False, score

        # 构造反馈信息
        feedback_lines = [
            f"[Validation Rollback] Score {score:.1f}/{threshold:.1f} "
            f"(attempt {val_retry_count + 1}/{max_retries})",
        ]

        # 尝试从输出中提取评审意见（<feedback> 标签或最后几行）
        fb_match = re.search(
            r"<feedback>(.*?)</feedback>",
            content, re.IGNORECASE | re.DOTALL,
        )
        if fb_match:
            feedback_lines.append(fb_match.group(1).strip())
        else:
            # 取输出最后 500 字符作为反馈
            feedback_lines.append(content[-500:])

        feedback = "\n".join(feedback_lines)

        self._rollback_to_dev(task_id, feedback)

        return False, score

    def _rollback_to_dev(self, task_id: str, feedback: str) -> None:
        """
        回滚任务到 Dev 阶段

        1. 重置所有阶段状态
        2. 将 Validation 失败原因注入 Dev 阶段的 issues
        """
        app_logger.info(f"Rolling back {task_id} to Dev stage...")

        # 重置全部阶段
        self.storage.reset_stages(
            task_id,
            ["dev", "test", "review", "validation"],
        )

        # 注入反馈到 Dev 阶段
        self.storage.add_issue(task_id, "dev", feedback)

        # 递增回滚计数器
        self._increment_counter(self.retry_dir, task_id, "validation")

        app_logger.warning(
            f"Task {task_id} rolled back to Dev. "
            f"Issues injected for next Dev Agent."
        )

    # ========================================
    #  阶段结算
    # ========================================

    def _settle_stage(self, task_id: str, stage: str,
                      is_completed: bool, result: dict) -> None:
        """
        结算阶段结果

        完成时: 持久化阶段状态 + 清理计数器
        失败时: 递增计数器 / 超限则跳过
        """
        if is_completed:
            # 持久化阶段完成状态
            self.storage.mark_stage(task_id, stage)
            self.storage.clear_cache()
            self._clear_counters(task_id, stage)
            app_logger.success(
                f"Stage completed: {task_id}/{stage}"
            )
        else:
            if result["is_timeout"]:
                count = self._increment_counter(
                    self.timeout_dir, task_id, stage
                )
                app_logger.warning(
                    f"Timeout retry: {task_id}/{stage} "
                    f"({count}/{MAX_TIMEOUT_RETRIES})"
                )
                if count >= MAX_TIMEOUT_RETRIES:
                    app_logger.error(
                        f"Max timeout retries: {task_id}/{stage}, skipping"
                    )
                    self._mark_skipped(task_id)
            else:
                count = self._increment_counter(
                    self.retry_dir, task_id, stage
                )
                app_logger.warning(
                    f"Retry: {task_id}/{stage} "
                    f"({count}/{MAX_RETRIES})"
                )
                if count >= MAX_RETRIES:
                    app_logger.error(
                        f"Max retries: {task_id}/{stage}, skipping"
                    )
                    self._mark_skipped(task_id)

    # ========================================
    #  主循环
    # ========================================

    def run(self) -> int:
        """
        执行主循环

        Returns:
            退出码 (0=全部完成, 1=错误)
        """
        app_logger.info("=" * 60)
        app_logger.info("AI Dev Pipeline - Automation Engine")
        app_logger.info("=" * 60)

        # 初始化
        self.ensure_directories()
        if not self.check_prerequisites():
            app_logger.error("Prerequisites check failed")
            return 1

        app_logger.info(f"Project:   {PROJECT_ROOT}")
        app_logger.info(f"Claude:    {CLAUDE_CMD} ({PERMISSION_MODE})")
        app_logger.info(f"Timeout:   base={BASE_SILENCE_TIMEOUT}s, "
                       f"max={MAX_SILENCE_TIMEOUT}s, "
                       f"backoff=x{TIMEOUT_BACKOFF_FACTOR}")
        app_logger.info(f"Mode:      {'single-run' if self.single_run else 'continuous'}")

        # 主循环
        iteration = 0

        while True:
            iteration += 1

            app_logger.info("")
            app_logger.info("-" * 60)
            app_logger.info(f"Iteration #{iteration}")
            app_logger.info("-" * 60)

            # ── 1. 获取下一个任务 ──────────────────────────
            task_info = get_next_pending_stage()

            if task_info is None:
                app_logger.success("All tasks completed. No pending stages.")
                return 0

            task_id = task_info["task_id"]
            stage = task_info["stage"]
            description = task_info.get("description", "")

            app_logger.info(f"Task: {task_id} | Stage: {stage.upper()}")
            if description:
                app_logger.info(f"Desc: {description[:80]}")

            # ── 2. 检查是否被跳过 ──────────────────────────
            if self._is_skipped(task_id):
                app_logger.info(f"Skipped: {task_id} (max retries reached)")
                if self.single_run:
                    return 0
                time.sleep(LOOP_SLEEP)
                continue

            # ── 3. 读取超时计数 ──────────────────────────
            timeout_count = self._read_counter(
                self.timeout_dir, f"{task_id}_{stage}"
            )

            # ── 4. 组装 Prompt ──────────────────────────
            prompt = self._assemble_prompt(task_id, stage)
            prompt_size = len(prompt.encode("utf-8"))
            app_logger.info(f"Prompt assembled: {prompt_size // 1024}KB")

            # ── 5. 执行 Agent ──────────────────────────
            result = self._execute_agent(
                prompt=prompt,
                stage=stage,
                task_id=task_id,
                timeout_count=timeout_count,
            )

            # ── 6. 检测阶段是否完成 ──────────────────────────
            is_completed = False

            if result["exit_code"] == 0:
                is_completed, detect_msg = self._detect_completion(
                    task_id, stage
                )
                if is_completed:
                    app_logger.info(f"Detection: PASS - {detect_msg}")
                else:
                    app_logger.info(f"Detection: NOT YET - {detect_msg}")
            else:
                app_logger.warning(
                    f"Agent exited with code {result['exit_code']}"
                )

            # ── 7. Validation 特殊处理 ──────────────────────────
            if stage == "validation" and is_completed:
                passed, score = self._handle_validation(
                    task_id, result["output_file"]
                )
                if passed:
                    self.storage.mark_stage(task_id, "validation")
                    self.storage.clear_cache()
                    self._clear_counters(task_id, "validation")
                    app_logger.success(
                        f"Task {task_id} validation PASSED "
                        f"(score={score:.1f})"
                    )
                else:
                    # 回滚已完成，回到循环头部重新开始 Dev 阶段
                    is_completed = False

            # ── 8. 结算 ──────────────────────────
            if is_completed:
                self._settle_stage(task_id, stage, True, result)

                # 检查任务是否全部完成
                if self.storage.is_all_stages_complete(task_id):
                    self.storage.complete_task(task_id)
                    self.storage.clear_cache()
                    app_logger.success(
                        f"Task FULLY COMPLETE: {task_id}"
                    )
            else:
                self._settle_stage(task_id, stage, False, result)

            # ── 9. 单次模式退出 ──────────────────────────
            if self.single_run:
                return 0

            # ── 10. 休眠 ──────────────────────────
            app_logger.info(f"Sleeping {LOOP_SLEEP}s...")
            time.sleep(LOOP_SLEEP)


# ========================================
#  CLI 入口
# ========================================

def main():
    """命令行入口"""
    import argparse

    parser = argparse.ArgumentParser(
        description="AI Dev Pipeline - Automation Engine",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python .harness/scripts/run_automation.py          # continuous loop
    python .harness/scripts/run_automation.py --once   # single iteration
    python .harness/scripts/run_automation.py -v       # verbose logging
        """,
    )

    parser.add_argument(
        "--once", action="store_true",
        help="Run a single iteration and exit",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true",
        help="Enable verbose/debug logging",
    )

    args = parser.parse_args()

    try:
        engine = AutomationEngine(
            single_run=args.once,
            verbose=args.verbose,
        )
        exit_code = engine.run()
        sys.exit(exit_code)

    except KeyboardInterrupt:
        app_logger.info("Interrupted by user")
        sys.exit(0)

    except Exception as e:
        app_logger.exception(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
