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
import shutil
import subprocess
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
    get_project_config,
    format_project_config_for_prompt,
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

        # 📊 运行统计
        self.stats = {
            "tasks_completed": 0,
            "stages_completed": 0,
            "tasks_skipped": 0,
            "timeout_kills": 0,
        }

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
        0. [SYSTEM DIRECTORY CONTEXT] 工作区与引擎路径隔离说明
        0.5. project-config.json 项目全局约定
        1. CLAUDE.md 项目规范
        1.5. 依赖上下文（depends_on 前置任务的产出）
        2. 阶段专用模板
        3. 任务上下文
        """
        parts = []

        # 0. 系统目录上下文（确保 Agent 知道在哪里写代码）
        parts.append(
            f"# [SYSTEM DIRECTORY CONTEXT]\nBusiness code dir: `{PROJECT_ROOT}` | Engine & PRD dir: `{HARNESS_DIR}`"
        )

        # 0.5. 项目全局约定（仅 dev 阶段注入，test/review 不需要）
        if stage == "dev":
            project_cfg_text = format_project_config_for_prompt(get_project_config())
            if project_cfg_text:
                parts.append(project_cfg_text)

        # 1. CLAUDE.md
        claude_md = PROJECT_ROOT / "CLAUDE.md"
        if claude_md.exists():
            parts.append(claude_md.read_text(encoding="utf-8", errors="replace"))

        # 1.5. 依赖上下文（前置任务的产出注入）
        dep_ctx = self._build_dependency_context(task_id)
        if dep_ctx:
            parts.append(dep_ctx)

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

    def _build_dependency_context(self, task_id: str) -> str:
        """
        构建依赖上下文：从 depends_on 前置任务的产出中
        提取接口契约、设计决策、约束等信息，注入到 Prompt。

        Returns:
            Markdown 格式的依赖上下文文本，无依赖则返回空字符串
        """
        depends_on = self.storage.get_depends_on(task_id)
        if not depends_on:
            return ""

        sections = []

        for dep in depends_on:
            # 支持字典格式 {"id": "xxx", "reason": "..."}
            dep_id = dep.get("id") or dep.get("task_id") if isinstance(dep, dict) else dep

            artifacts = self.storage.get_task_artifacts(dep_id)
            has_content = any(artifacts.values())

            if not has_content:
                app_logger.debug(
                    f"依赖上下文: {dep_id} 无可用产出，跳过"
                )
                continue

            dep_desc = self.storage.get_description(dep_id)
            block = [f"# [DEPENDENCY CONTEXT FROM: {dep_id}]"]
            block.append("")

            if dep_desc:
                block.append(f"> {dep_desc}")
                block.append("")

            # 设计决策
            decisions = artifacts.get("design_decisions", [])
            if decisions:
                block.append("## Design Decisions")
                for d in decisions:
                    if isinstance(d, dict):
                        title = d.get("title", d.get("decision", ""))
                        detail = d.get("detail", d.get("rationale", ""))
                        block.append(f"- {title}")
                        if detail:
                            block.append(f"  {detail}")
                    else:
                        block.append(f"- {d}")
                block.append("")

            # 接口契约
            contracts = artifacts.get("interface_contracts", [])
            if contracts:
                block.append("## Interface Contracts")
                for c in contracts:
                    if isinstance(c, dict):
                        svc = c.get("service", c.get("name", ""))
                        method = c.get("method", "")
                        sig = c.get("signature", "")
                        block.append(f"- **{svc}**")
                        if method:
                            block.append(f"  - method: `{method}`")
                        if sig:
                            block.append(f"  - signature: `{sig}`")
                        # 额外字段（兼容 return_type / returns 两种命名）
                        for k in ("params", "return_type", "returns",
                                  "description", "throws"):
                            v = c.get(k)
                            if v:
                                block.append(f"  - {k}: {v}")
                    else:
                        block.append(f"- {c}")
                block.append("")

            # 约束条件
            constraints = artifacts.get("constraints", [])
            if constraints:
                block.append("## Constraints")
                for c in constraints:
                    if isinstance(c, dict):
                        desc = c.get("description", c.get("rule", ""))
                        scope = c.get("scope", c.get("module", ""))
                        block.append(f"- [{scope}] {desc}" if scope else f"- {desc}")
                    else:
                        block.append(f"- {c}")
                block.append("")

            # 产出文件列表（简要）
            files = artifacts.get("files", [])
            if files:
                block.append("## Files")
                for f in files:
                    block.append(f"- `{f}`")
                block.append("")

            sections.append("\n".join(block))
            app_logger.info(
                f"依赖上下文: {dep_id} 注入 "
                f"(decisions={len(decisions)}, "
                f"contracts={len(contracts)}, "
                f"constraints={len(constraints)}, "
                f"files={len(files)})"
            )

        if not sections:
            return ""

        header = (
            "# [DEPENDENCY CONTEXT]\n\n"
            "The following context was produced by prerequisite tasks. "
            "You MUST respect these design decisions, interface contracts, "
            "and constraints when implementing the current task.\n"
        )
        return header + "\n\n---\n\n".join(sections)

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

        # 实例化执行器并执行（cwd=PROJECT_ROOT 确保代码写到工作区）
        executor = DualTimeoutExecutor(
            hard_timeout=hard,
            silence_timeout=silence,
            verbose=self.verbose,
            cwd=PROJECT_ROOT,
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
        threshold = val_cfg.get("threshold", 0.8)
        max_retries = val_cfg.get("max_retries", 3)

        # 统一到百分制：threshold <= 1.0 视为 0-1 比例值
        if threshold <= 1.0:
            threshold = threshold * 100

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
    #  Git 自动提交
    # ========================================

    def _git_commit_task(self, task_id: str) -> bool:
        """
        任务三轮完成后，自动提交到目标工作区的 git 仓库

        Args:
            task_id: 任务 ID

        Returns:
            True if committed, False otherwise
        """
        # 1. 检查 PROJECT_ROOT 是否为 git 仓库
        git_dir = PROJECT_ROOT / ".git"
        if not git_dir.exists():
            app_logger.debug(
                f"Git: PROJECT_ROOT 不是 git 仓库，跳过提交"
            )
            return False

        # 2. 检查 git 是否可用
        git_cmd = "git"
        if platform.system() == "Windows":
            resolved = shutil.which("git")
            if not resolved:
                app_logger.warning("Git: 未找到 git 命令，跳过提交")
                return False
            git_cmd = resolved

        # 3. 获取任务描述
        task_info = self.storage.load_task(task_id)
        description = task_info.get("description", "") if task_info else ""
        # 清理描述：限制长度，去除换行
        desc_short = (description[:60] + "...") if len(description) > 60 else description
        desc_short = desc_short.replace("\n", " ").replace("\r", "").strip()

        # 4. 生成提交信息
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        commit_msg = (
            f"feat({task_id}): {desc_short}\n\n"
            f"Generated by AI Dev Pipeline\n"
            f"Task: {task_id} | {timestamp}"
        )

        # 5. 检查是否有变更
        try:
            result = subprocess.run(
                [git_cmd, "status", "--porcelain"],
                cwd=str(PROJECT_ROOT),
                capture_output=True,
                text=True,
                timeout=10,
            )
            has_changes = bool(result.stdout.strip())
            if not has_changes:
                app_logger.debug(f"Git: {task_id} 无变更，跳过提交")
                return False
        except subprocess.TimeoutExpired:
            app_logger.warning(f"Git: status 检查超时，跳过提交")
            return False
        except Exception as e:
            app_logger.warning(f"Git: status 检查失败 - {e}")
            return False

        # 6. 执行 git add -A
        try:
            subprocess.run(
                [git_cmd, "add", "-A"],
                cwd=str(PROJECT_ROOT),
                capture_output=True,
                timeout=30,
                check=True,
            )
        except subprocess.TimeoutExpired:
            app_logger.warning(f"Git: add 操作超时，跳过提交")
            return False
        except subprocess.CalledProcessError as e:
            app_logger.warning(f"Git: add 失败 - {e}")
            return False
        except Exception as e:
            app_logger.warning(f"Git: add 异常 - {e}")
            return False

        # 7. 执行 git commit
        try:
            commit_result = subprocess.run(
                [git_cmd, "commit", "-m", commit_msg],
                cwd=str(PROJECT_ROOT),
                capture_output=True,
                text=True,
                timeout=30,
            )

            if commit_result.returncode == 0:
                # 提取 commit hash
                hash_match = re.search(
                    r"\[[\w\-\.]+\s+([a-f0-9]+)\]",
                    commit_result.stdout,
                )
                commit_hash = hash_match.group(1) if hash_match else "unknown"
                app_logger.success(
                    f"Git: {task_id} 已提交 -> {commit_hash[:8]}"
                )
                return True
            else:
                # 可能是因为没有变更（unrelated histories 等）
                stderr = commit_result.stderr.strip()
                if "nothing to commit" in stderr.lower():
                    app_logger.debug(f"Git: {task_id} 无变更，跳过提交")
                    return False
                app_logger.warning(
                    f"Git: commit 失败 - {stderr[:200]}"
                )
                return False

        except subprocess.TimeoutExpired:
            app_logger.warning(f"Git: commit 操作超时，跳过提交")
            return False
        except Exception as e:
            app_logger.warning(f"Git: commit 异常 - {e}")
            return False

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
            self.stats["stages_completed"] += 1
            app_logger.success(
                f"Stage completed: {task_id}/{stage}"
            )

            # 知识库同步：dev/review 阶段完成时沉淀产出
            if stage in ("dev", "review"):
                self._sync_knowledge(task_id)
        else:
            if result["is_timeout"]:
                count = self._increment_counter(
                    self.timeout_dir, task_id, stage
                )
                self.stats["timeout_kills"] += 1
                app_logger.warning(
                    f"Timeout retry: {task_id}/{stage} "
                    f"({count}/{MAX_TIMEOUT_RETRIES})"
                )
                if count >= MAX_TIMEOUT_RETRIES:
                    app_logger.error(
                        f"Max timeout retries: {task_id}/{stage}, skipping"
                    )
                    self._mark_skipped(task_id)
                    self.stats["tasks_skipped"] += 1
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
                    self.stats["tasks_skipped"] += 1

    # ========================================
    #  知识库同步
    # ========================================

    def _sync_knowledge(self, task_id: str) -> None:
        """
        触发知识库同步

        在 dev/review 阶段完成时调用，
        将任务的接口契约和约束沉淀到全局知识库。
        同步失败不影响主流程。
        """
        try:
            from scripts.knowledge import KnowledgeManager
            km = KnowledgeManager()
            result = km.sync_task_artifacts(task_id)
            total = result["contracts_synced"] + result["constraints_synced"]
            if total > 0:
                app_logger.info(
                    f"[Knowledge Sync] {task_id}: "
                    f"+{result['contracts_synced']} contracts, "
                    f"+{result['constraints_synced']} constraints"
                )
        except Exception as e:
            # 知识库同步不应阻塞主流程
            app_logger.warning(f"[Knowledge Sync] {task_id} 失败: {e}")

    # ========================================
    #  Validation 裁判
    # ========================================

    def _run_validation(self, task_id: str,
                        timeout_count: int) -> tuple:
        """
        执行 Validation 阶段（旁路常规 Agent 流程）

        使用 SatisfactionValidator 作为 LLM 裁判，
        将裁判输出写入临时文件供 _handle_validation 提取 <score>。

        Returns:
            (output_text: str, exit_code: int)
        """
        app_logger.info(f"[Validation] 启动裁判: {task_id}")

        try:
            from scripts.validate_satisfaction import SatisfactionValidator
        except ImportError as e:
            app_logger.error(f"[Validation] 无法导入 SatisfactionValidator: {e}")
            return f"[Import error: {e}]\n<score>0</score>", 1

        validator = SatisfactionValidator(task_id)
        output_text, exit_code = validator.evaluate()

        return output_text, exit_code

    # ========================================
    #  任务队列统计
    # ========================================

    def _count_ready_tasks(self) -> dict:
        """统计任务队列：ready / blocked / skipped / no_pending_stage"""
        tasks = self.storage.load_all_pending_tasks()

        skipped = set()
        if self.skip_dir.exists():
            skipped = {f.name for f in self.skip_dir.iterdir() if f.is_file()}

        ready = 0
        blocked = 0
        skipped_count = len(skipped)

        for task in tasks:
            task_id = task["id"]
            if task_id in skipped:
                continue

            # 依赖检查
            deps_ok = True
            for dep in task.get("depends_on", []):
                dep_id = (dep.get("id") or dep.get("task_id")
                          if isinstance(dep, dict) else dep)
                if not self.storage.is_task_fully_completed(dep_id):
                    deps_ok = False
                    break

            if not deps_ok:
                blocked += 1
                continue

            # 检查是否有待处理阶段
            has_pending = False
            stages = task.get("stages", {})
            for sn in ("dev", "test", "review"):
                if not stages.get(sn, {}).get("completed", False):
                    has_pending = True
                    break
            if not has_pending and "stages" not in task:
                has_pending = True  # 旧格式无 stages 字段

            if has_pending:
                ready += 1

        return {
            "ready": ready,
            "blocked": blocked,
            "skipped": skipped_count,
            "total": len(tasks),
        }

    def _print_run_summary(self) -> None:
        """打印运行摘要"""
        s = self.stats
        pending = self.storage.load_all_pending_tasks()
        pending_ids = {t["id"] for t in pending}
        # 减去已完成的不在 pending 中的任务
        completed_in_archive = len(list(
            (TASKS_DIR / "completed").rglob("*.json")
        ))

        app_logger.info("")
        app_logger.info("=" * 60)
        app_logger.info("Run Summary")
        app_logger.info("=" * 60)
        app_logger.info(f"  Stages completed:   {s['stages_completed']}")
        app_logger.info(f"  Tasks completed:    {s['tasks_completed']}")
        app_logger.info(f"  Tasks skipped:      {s['tasks_skipped']}")
        app_logger.info(f"  Timeout kills:      {s['timeout_kills']}")
        app_logger.info(f"  Pending (in queue): {len(pending)}")
        app_logger.info(f"  Archived total:     {completed_in_archive}")
        app_logger.info("=" * 60)

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
            self._print_run_summary()
            return 1

        app_logger.info(f"Project:   {PROJECT_ROOT}")
        app_logger.info(f"Claude:    {CLAUDE_CMD} ({PERMISSION_MODE})")
        app_logger.info(f"Timeout:   base={BASE_SILENCE_TIMEOUT}s, "
                       f"max={MAX_SILENCE_TIMEOUT}s, "
                       f"backoff=x{TIMEOUT_BACKOFF_FACTOR}")
        # 🔑 配置指纹 - 快速验证配置是否正确加载
        import hashlib as _hl
        _cfg_fp = _hl.md5(
            f"{BASE_SILENCE_TIMEOUT}:{MAX_SILENCE_TIMEOUT}:"
            f"{TIMEOUT_BACKOFF_FACTOR}:{MAX_RETRIES}:{MAX_TIMEOUT_RETRIES}".encode()
        ).hexdigest()[:8]
        app_logger.info(f"Config ID:  {_cfg_fp} "
                       f"(base={BASE_SILENCE_TIMEOUT}s, max={MAX_SILENCE_TIMEOUT}s)")
        app_logger.info(f"Mode:      {'single-run' if self.single_run else 'continuous'}")

        # 项目配置状态
        project_cfg = get_project_config()
        if project_cfg:
            proj_name = project_cfg.get("project", {}).get("name", "")
            proj_fw = project_cfg.get("tech_stack", {}).get("framework", "")
            app_logger.info(f"Config:    project-config.json "
                           f"(name={proj_name or '(empty)'}, "
                           f"framework={proj_fw or '(empty)'})")
        else:
            app_logger.info("Config:    project-config.json not configured")

        # 📋 任务队列概览
        queue_info = self._count_ready_tasks()
        app_logger.info("")
        app_logger.info(f"Task Queue: {queue_info['total']} total, "
                       f"ready={queue_info['ready']}, "
                       f"blocked={queue_info['blocked']}, "
                       f"skipped={queue_info['skipped']}")
        if queue_info['ready'] > 0:
            app_logger.info(f"Next: {queue_info['ready']} task(s) ready to execute")
        elif queue_info['blocked'] > 0 and queue_info['skipped'] == 0:
            app_logger.warning("All pending tasks are blocked by dependencies!")
        elif queue_info['total'] == 0:
            app_logger.info("No tasks in queue")

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
                self._print_run_summary()
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

            # ── 4. Validation 阶段：旁路常规流程 ──────────────────
            if stage == "validation":
                output_text, val_exit_code = self._run_validation(
                    task_id, timeout_count
                )
                is_completed = (val_exit_code == 0)

                if is_completed:
                    # 将裁判输出写入临时文件，复用 _handle_validation 提取 <score>
                    val_output_file = CLI_IO_DIR / "sessions" / f"val_{task_id}_result.txt"
                    val_output_file.parent.mkdir(parents=True, exist_ok=True)
                    val_output_file.write_text(output_text, encoding="utf-8")

                    passed, score = self._handle_validation(
                        task_id, val_output_file
                    )
                    if passed:
                        self.storage.mark_stage(task_id, "validation")
                        self.storage.clear_cache()
                        self._clear_counters(task_id, "validation")
                        app_logger.success(
                            f"Task {task_id} validation PASSED "
                            f"(score={score:.1f})"
                        )
                        self._settle_stage(task_id, stage, True, {
                            "exit_code": 0,
                            "output_file": val_output_file,
                            "is_timeout": False,
                            "session_id": f"val_{task_id}",
                        })

                        if self.storage.is_all_stages_complete(task_id):
                            self.storage.complete_task(task_id)
                            self.storage.clear_cache()
                            self.stats["tasks_completed"] += 1
                            app_logger.success(f"Task FULLY COMPLETE: {task_id}")
                            # 自动提交到目标工作区 git 仓库
                            self._git_commit_task(task_id)
                    else:
                        # 回滚已完成，结算为失败
                        self._settle_stage(task_id, stage, False, {
                            "exit_code": val_exit_code,
                            "output_file": val_output_file,
                            "is_timeout": False,
                            "session_id": f"val_{task_id}",
                        })
                else:
                    # 裁判执行失败（超时/异常），走常规失败结算
                    is_timeout = val_exit_code in (14, 124)
                    self._settle_stage(task_id, stage, False, {
                        "exit_code": val_exit_code,
                        "output_file": CLI_IO_DIR / "sessions" / f"val_{task_id}_result.txt",
                        "is_timeout": is_timeout,
                        "session_id": f"val_{task_id}",
                    })

                if self.single_run:
                    return 0
                time.sleep(LOOP_SLEEP)
                continue

            # ── 5. 组装 Prompt ──────────────────────────
            prompt = self._assemble_prompt(task_id, stage)
            prompt_size = len(prompt.encode("utf-8"))
            app_logger.info(f"Prompt assembled: {prompt_size // 1024}KB")

            # ── 6. 执行 Agent ──────────────────────────
            result = self._execute_agent(
                prompt=prompt,
                stage=stage,
                task_id=task_id,
                timeout_count=timeout_count,
            )

            # ── 7. 检测阶段是否完成 ──────────────────────────
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

            # ── 8. 结算 ──────────────────────────
            if is_completed:
                self._settle_stage(task_id, stage, True, result)

                # 检查任务是否全部完成
                if self.storage.is_all_stages_complete(task_id):
                    self.storage.complete_task(task_id)
                    self.storage.clear_cache()
                    self.stats["tasks_completed"] += 1
                    app_logger.success(
                        f"Task FULLY COMPLETE: {task_id}"
                    )
                    # 自动提交到目标工作区 git 仓库
                    self._git_commit_task(task_id)
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
        engine._print_run_summary()
        sys.exit(0)

    except Exception as e:
        app_logger.exception(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
