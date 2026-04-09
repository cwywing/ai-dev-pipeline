#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
阶段完成检测器
====================================

基于原 detect_stage_completion.py 重写，接入 Phase 1 基座。

防御性检测顺序（绝对真理链）：
1. TaskStorage.is_stage_complete() → 物理 JSON 状态（最高优先级）
2. CLI 会话日志中的 mark-stage 输出
3. Git 变更检测（兜底）

退出码:
    0 - 阶段已完成
    1 - 阶段未完成
    2 - 无法确定（触发人工审查）

使用方式:
    from scripts.detect_stage_completion import DetectStageCompletion

    detector = DetectStageCompletion("Model_001", "dev")
    exit_code, message = detector.detect()

====================================
"""

import re
import json
import subprocess
import sys
from pathlib import Path
from typing import Optional


# 路径注入
_scripts_dir = Path(__file__).parent.resolve()
sys.path.insert(0, str(_scripts_dir.parent))

from scripts.config import (
    HARNESS_DIR,
    CLI_IO_DIR,
    ARTIFACTS_DIR,
)
from scripts.logger import app_logger
from scripts.task_storage import TaskStorage


class DetectStageCompletion:
    """混合模式阶段完成检测器（防御性设计）"""

    RECENT_SESSIONS_COUNT = 5

    def __init__(self, task_id: str, stage: str):
        """
        Args:
            task_id: 任务 ID
            stage: 阶段名 (dev/test/review)
        """
        self.task_id = task_id
        self.stage = stage.lower()
        self._cli_sessions_dir = CLI_IO_DIR / "sessions"
        self._storage = TaskStorage()

    # --------------------------------------------------
    #  公开接口
    # --------------------------------------------------

    def detect(self) -> tuple:
        """
        执行阶段完成检测

        Returns:
            (exit_code: int, message: str)
            exit_code: 0(完成), 1(未完成), 2(无法确定)
        """
        app_logger.debug(f"检测阶段完成: {self.task_id} @ {self.stage}")

        dispatch = {
            "dev": self._check_dev,
            "test": self._check_test,
            "review": self._check_review,
        }

        checker = dispatch.get(self.stage)
        if not checker:
            return 2, f"未知阶段: {self.stage}"

        return checker()

    # --------------------------------------------------
    #  Dev 阶段检测
    # --------------------------------------------------

    def _check_dev(self) -> tuple:
        """
        Dev 完成条件（防御性检测链）：

        第一道防线：TaskStorage 物理状态（绝对真理）
        第二道防线：CLI 会话日志中 mark-stage 输出
        第三道防线：Git 变更检测
        """
        # 第一道防线：TaskStorage 绝对真理
        if self._storage.is_stage_complete(self.task_id, "dev"):
            app_logger.debug(f"[第一防线] TaskStorage 确认 dev 完成: {self.task_id}")
            return 0, "Dev 完成 (TaskStorage 物理状态确认)"

        # 第二道防线：CLI 会话日志
        sessions = self._get_recent_sessions()
        for f in sessions:
            output = self._load_output(f)
            params = self._detect_cli_params(output)
            if params["mark_stage_called"]:
                # 再次验证 TaskStorage（可能有时延）
                if self._storage.is_stage_complete(self.task_id, "dev"):
                    return 0, "Dev 完成 (TaskStorage 确认 + mark-stage 日志)"
                return 0, "Dev 完成 (mark-stage 调用日志)"

        # 第三道防线：Git 变更 + 产出记录（兜底）
        git_detected, git_detail = self._detect_git_changes()
        has_artifacts = self._has_artifacts()

        conditions = []
        if git_detected:
            conditions.append(f"Git 变更 ({git_detail})")
        if has_artifacts:
            conditions.append("产出记录存在")

        if conditions:
            return 0, f"Dev 完成 (兜底检测): {'; '.join(conditions)}"

        return 1, "Dev 未完成: 无物理状态确认 / mark-stage 痕迹 / Git 变更"

    # --------------------------------------------------
    #  Test 阶段检测
    # --------------------------------------------------

    def _check_test(self) -> tuple:
        """
        Test 完成条件（防御性检测链）：

        第一道防线：TaskStorage 物理状态（绝对真理）
        第二道防线：CLI 会话日志中 --test-results / --issues / 测试执行痕迹
        第三道防线：测试文件创建（兜底）
        """
        # 第一道防线：TaskStorage 绝对真理
        if self._storage.is_stage_complete(self.task_id, "test"):
            app_logger.debug(f"[第一防线] TaskStorage 确认 test 完成: {self.task_id}")
            return 0, "Test 完成 (TaskStorage 物理状态确认)"

        # 第二道防线：CLI 会话日志
        sessions = self._get_recent_sessions()
        has_test_results = False
        has_issues = False
        has_test_exec = False
        has_test_files = False

        for f in sessions:
            output = self._load_output(f)
            params = self._detect_cli_params(output)
            if params["test_results_provided"]:
                has_test_results = True
            if params["issues_reported"]:
                has_issues = True

            test_info = self._detect_test_execution(output)
            if test_info["test_command_found"]:
                has_test_exec = True
            if test_info["test_file_created"]:
                has_test_files = True

        score = sum([has_test_results, has_issues, has_test_exec, has_test_files])
        labels = []
        if has_test_results: labels.append("--test-results 调用")
        if has_issues: labels.append("--issues 调用")
        if has_test_exec: labels.append("测试执行痕迹")
        if has_test_files: labels.append("测试文件创建")

        # 第二道防线至少满足 1 项
        if score >= 1:
            # 再次验证 TaskStorage
            if self._storage.is_stage_complete(self.task_id, "test"):
                return 0, f"Test 完成 (TaskStorage 确认 + {score} 项日志证据)"
            return 0, f"Test 完成 (日志证据): {score} 项 - {'; '.join(labels)}"

        # 第三道防线：测试文件创建（弱兜底）
        if has_test_files:
            return 0, "Test 完成 (兜底: 测试文件创建)"

        return 1, "Test 未完成: 无物理状态确认 / 测试痕迹"

    # --------------------------------------------------
    #  Review 阶段检测
    # --------------------------------------------------

    def _check_review(self) -> tuple:
        """
        Review 完成条件（防御性检测链）：

        第一道防线：TaskStorage 物理状态（绝对真理）
        第二道防线：CLI 会话日志中 --issues / 审查关键词 / 完成文本
        第三道防线：无（Review 阶段必须有明确证据）
        """
        # 第一道防线：TaskStorage 绝对真理
        if self._storage.is_stage_complete(self.task_id, "review"):
            app_logger.debug(f"[第一防线] TaskStorage 确认 review 完成: {self.task_id}")
            return 0, "Review 完成 (TaskStorage 物理状态确认)"

        # 第二道防线：CLI 会话日志
        sessions = self._get_recent_sessions()
        has_issues = False
        has_test_results = False
        review_kw_count = 0
        has_completion_text = False

        completion_patterns = [
            r"审查完成|review.*完成|review\s+done|review\s+complete",
            r"阶段已完成|任务已完成|已标记为完成",
            r"通过审查|符合.*规范|验收通过",
            r"所有验收标准.*已满足",
            r"任务状态.*已完成|Review.*已通过",
        ]

        for f in sessions:
            output = self._load_output(f)
            params = self._detect_cli_params(output)
            if params["issues_reported"]:
                has_issues = True
            if params["test_results_provided"]:
                has_test_results = True

            review_info = self._detect_review_keywords(output)
            if review_info["review_keyword_found"]:
                review_kw_count += 1
            if review_info["quality_assessment"]:
                review_kw_count += 1
            if review_info["inspection_found"]:
                review_kw_count += 1

            for pat in completion_patterns:
                if re.search(pat, output, re.IGNORECASE):
                    has_completion_text = True
                    break

        score = 0
        labels = []
        if has_issues:
            score += 1; labels.append("--issues 调用")
        if has_test_results:
            score += 1; labels.append("--test-results 调用")
        if review_kw_count >= 2:
            score += 1; labels.append("审查关键词")
        if has_completion_text:
            score += 1; labels.append("完成文本匹配")

        # 第二道防线至少满足 1 项
        if score >= 1:
            # 再次验证 TaskStorage
            if self._storage.is_stage_complete(self.task_id, "review"):
                return 0, f"Review 完成 (TaskStorage 确认 + {score} 项日志证据)"
            return 0, f"Review 完成 (日志证据): {score} 项 - {'; '.join(labels)}"

        return 1, "Review 未完成: 无物理状态确认 / 审查痕迹"

    # --------------------------------------------------
    #  检测辅助方法
    # --------------------------------------------------

    def _get_recent_sessions(self) -> list:
        """获取最近的 CLI 会话文件"""
        if not self._cli_sessions_dir.exists():
            return []

        files = []
        for f in self._cli_sessions_dir.glob("*_output.txt"):
            try:
                files.append((f, f.stat().st_mtime))
            except OSError:
                continue

        files.sort(key=lambda x: x[1], reverse=True)
        return [f[0] for f in files[:self.RECENT_SESSIONS_COUNT]]

    @staticmethod
    def _load_output(path: Path) -> str:
        """加载会话输出"""
        try:
            return path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return ""

    @staticmethod
    def _detect_cli_params(output: str) -> dict:
        """检测 CLI 参数调用痕迹"""
        return {
            "mark_stage_called": bool(
                re.search(r"--action\s+mark-stage|mark-stage", output, re.I)
            ),
            "test_results_provided": bool(
                re.search(r"--test-results", output, re.I)
            ),
            "issues_reported": bool(
                re.search(r"--issues\b", output, re.I)
            ),
        }

    @staticmethod
    def _detect_test_execution(output: str) -> dict:
        """检测测试执行痕迹"""
        has_phpunit = bool(re.search(r"phpunit|php\s+.*phpunit", output, re.I))
        has_artisan = bool(re.search(r"php\s+artisan\s+test", output, re.I))
        has_pytest = bool(re.search(r"pytest|python.*-m\s+pytest", output, re.I))
        has_results = bool(re.search(
            r"\d+\s+test[s]?\s+(passed|failed)|Passed|FAILED|Ran\s+\d+\s+tests",
            output, re.I,
        ))
        has_created = bool(re.search(
            r"(creates?|新建|创建).*(Test\.php|Test\.py|_test\.py)",
            output, re.I,
        ))

        return {
            "test_command_found": has_phpunit or has_artisan or has_pytest,
            "test_file_created": has_created,
            "test_results_in_output": has_results,
        }

    @staticmethod
    def _detect_review_keywords(output: str) -> dict:
        """检测审查关键词"""
        lower = output.lower()
        keywords = ["review", "审查", "质量评估", "验收", "code review", "quality check"]
        has_review = any(kw in lower for kw in keywords)
        has_quality = bool(re.search(r"质量|coverage|覆盖率|test\s+result", lower))
        has_inspect = bool(re.search(r"检查|inspect|audit|验证", lower))

        return {
            "review_keyword_found": has_review,
            "quality_assessment": has_quality,
            "inspection_found": has_inspect,
        }

    @staticmethod
    def _detect_git_changes() -> tuple:
        """检测 Git 变更"""
        try:
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                capture_output=True, text=True,
                encoding="utf-8", errors="replace",
                timeout=10,
            )
            if result.returncode == 0 and result.stdout.strip():
                modified = []
                new_files = []
                for line in result.stdout.strip().split("\n"):
                    if len(line) >= 3:
                        status = line[:2]
                        fname = line[3:].strip()
                        if "??" in status or "A" in status:
                            new_files.append(fname)
                        else:
                            modified.append(fname)

                detail = f"{len(modified)} 修改, {len(new_files)} 新建"
                return True, detail

        except Exception:
            pass
        return False, ""

    def _has_artifacts(self) -> bool:
        """检查产出记录是否存在"""
        artifact_file = ARTIFACTS_DIR / f"{self.task_id}.json"
        if not artifact_file.exists():
            return False
        try:
            data = json.loads(artifact_file.read_text(encoding="utf-8"))
            return bool(data.get("files"))
        except Exception:
            return False
