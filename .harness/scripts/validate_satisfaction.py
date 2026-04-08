#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

"""
Satisfaction Validator - LLM-as-a-Judge 满意度验证
==================================================

替代原有的空壳 validation 阶段，让大模型作为独立裁判
对 Dev 阶段的产出进行客观打分。

核心设计：
- 只读取 artifacts 中记录的变更文件（Token 优化）
- 构建严厉审查官 Prompt，逐条对比 AC 与实际代码
- 复用 DualTimeoutExecutor 执行裁判推理
- 输出末尾强制包含 <score>整数或一位小数</score>

使用方式:
    from scripts.validate_satisfaction import SatisfactionValidator

    validator = SatisfactionValidator(task_id)
    output_text, exit_code = validator.evaluate()

    # output_text 末尾包含 <score>85.5</score>
    # exit_code 0=成功, 14/124=超时, 其他=错误

==================================================
"""

import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple


# 路径注入
_scripts_dir = Path(__file__).parent.resolve()
sys.path.insert(0, str(_scripts_dir.parent))    # .harness/
sys.path.insert(0, str(_scripts_dir))            # .harness/scripts/

from scripts.config import (
    PROJECT_ROOT,
    HARNESS_DIR,
    CLI_IO_DIR,
    ARTIFACTS_DIR,
    BASE_SILENCE_TIMEOUT,
    MAX_SILENCE_TIMEOUT,
    TIMEOUT_BACKOFF_FACTOR,
)
from scripts.logger import app_logger
from scripts.task_storage import TaskStorage
from scripts.dual_timeout import DualTimeoutExecutor


# ========================================
#  代码文件读取器
# ========================================

# 单文件最大读取行数（防止意外读到巨型日志/二进制）
_MAX_FILE_LINES = 500

# 上下文窗口中代码部分的最大字符数（约 50KB，保守估算）
_MAX_CODE_CHARS = 50_000


class CodeReader:
    """
    精准代码提取器

    只读取 artifacts 中记录的变更文件，
    不扫描整个项目，避免 Token 浪费。
    """

    def __init__(self, project_root: Path = PROJECT_ROOT):
        self.project_root = project_root
        self.total_chars = 0

    def read_files(self, file_paths: List[str]) -> List[dict]:
        """
        读取文件列表，返回结构化的文件内容。

        每个元素:
        {
            "path": str,
            "exists": bool,
            "lines": int,
            "content": str,          # 截断后的内容
            "truncated": bool,
        }
        """
        results = []
        for fpath in file_paths:
            info = self._read_single(fpath)
            results.append(info)
        return results

    def _read_single(self, fpath: str) -> dict:
        """读取单个文件"""
        full_path = self.project_root / fpath
        result = {
            "path": fpath,
            "exists": False,
            "lines": 0,
            "content": "",
            "truncated": False,
        }

        if not full_path.exists():
            return result

        # 跳过二进制和超大文件
        try:
            stat = full_path.stat()
            if stat.st_size > 500_000:  # 500KB
                result["content"] = f"[File too large: {stat.st_size} bytes, skipped]"
                return result
        except OSError:
            return result

        try:
            text = full_path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            result["content"] = f"[Read error: {e}]"
            return result

        result["exists"] = True
        lines = text.split("\n")
        result["lines"] = len(lines)

        # 行数截断
        if len(lines) > _MAX_FILE_LINES:
            lines = lines[:_MAX_FILE_LINES]
            result["truncated"] = True
            text = "\n".join(lines) + f"\n... (truncated at {_MAX_FILE_LINES} lines)"

        # 总字符数截断
        if self.total_chars + len(text) > _MAX_CODE_CHARS:
            remaining = _MAX_CODE_CHARS - self.total_chars
            if remaining > 200:
                text = text[:remaining] + "\n... (code budget exhausted)"
                result["truncated"] = True
            else:
                text = "[Code budget exhausted, skipped]"
                result["truncated"] = True

        self.total_chars += len(text)
        result["content"] = text
        return result


# ========================================
#  SatisfactionValidator
# ========================================

class SatisfactionValidator:
    """
    LLM 裁判 - 满意度验证器

    流程:
    1. 从 TaskStorage 读取任务描述和验收标准
    2. 从 artifacts 读取变更文件列表
    3. 用 CodeReader 精准提取变更文件内容
    4. 组装严厉审查官 Prompt
    5. 复用 DualTimeoutExecutor 执行裁判
    6. 返回包含 <score> 的裁判文本
    """

    def __init__(self, task_id: str):
        self.task_id = task_id
        self.storage = TaskStorage()
        self.reader = CodeReader()

    def evaluate(self) -> Tuple[str, int]:
        """
        执行满意度验证

        Returns:
            (output_text, exit_code)
            output_text: 裁判输出的完整文本（末尾含 <score>）
            exit_code: 0=成功, 14=活性超时, 124=硬超时, 1=启动失败
        """
        app_logger.info(f"[Validator] 开始评估任务 {self.task_id}")

        # 1. 加载任务信息
        task = self.storage.load_task(self.task_id)
        if not task:
            msg = f"[Validator] 任务 {self.task_id} 不存在"
            app_logger.error(msg)
            return msg, 1

        description = task.get("description", "")
        acceptance = task.get("acceptance", [])

        if not acceptance:
            msg = f"[Validator] 任务 {self.task_id} 无验收标准，无法评估"
            app_logger.warning(msg)
            return msg + "\n<score>0</score>", 0

        # 2. 读取变更文件
        artifacts = self.storage.get_task_artifacts(self.task_id)
        file_paths = artifacts.get("files", [])

        app_logger.info(
            f"[Validator] {self.task_id}: "
            f"acceptance={len(acceptance)}条, files={len(file_paths)}个"
        )

        code_sections = self.reader.read_files(file_paths)
        existing_files = [s for s in code_sections if s["exists"]]

        if not existing_files:
            msg = (
                f"[Validator] 任务 {self.task_id} 的变更文件均不存在于磁盘。"
                f"声明路径: {file_paths}"
            )
            app_logger.warning(msg)
            return msg + "\n<score>0</score>", 0

        app_logger.info(
            f"[Validator] 读取 {len(existing_files)}/{len(file_paths)} 个文件, "
            f"代码总量 {self.reader.total_chars // 1024}KB"
        )

        # 3. 组装 Judge Prompt
        prompt = self._build_judge_prompt(description, acceptance, existing_files)
        prompt_size = len(prompt.encode("utf-8"))
        app_logger.info(f"[Validator] Judge Prompt 组装完成: {prompt_size // 1024}KB")

        # 4. 执行裁判
        output_text = self._execute_judge(prompt, prompt_size)

        return output_text, 0

    def _build_judge_prompt(self, description: str,
                            acceptance: List[str],
                            code_sections: List[dict]) -> str:
        """
        组装严厉审查官 Prompt

        结构:
        1. 角色定义与审查指令
        2. 任务目标与验收标准
        3. 实际修改的文件与代码
        4. 评分指令（强制 <score> 格式）
        """
        # 验收标准
        ac_text = "\n".join(f"  {i + 1}. {ac}" for i, ac in enumerate(acceptance))

        # 代码文件
        code_text_parts = []
        for section in code_sections:
            header = f"### {section['path']}"
            meta = f"({section['lines']} lines"
            if section["truncated"]:
                meta += ", truncated"
            meta += ")"
            code_text_parts.append(f"{header} {meta}\n\n```\n{section['content']}\n```")

        code_text = "\n\n".join(code_text_parts)

        prompt = f"""You are a strict and impartial code quality auditor. Your job is to verify whether the implementation below satisfies EVERY acceptance criterion.

## Task Description

{description}

## Acceptance Criteria (MUST verify each one)

{ac_text}

## Implementation Files

{code_text}

## Your Task

1. For EACH acceptance criterion above, check the implementation files:
   - Does the code fully satisfy this criterion? (YES / PARTIAL / NO)
   - If NO or PARTIAL, explain exactly what is missing or wrong.

2. Pay special attention to:
   - Missing files that are referenced in the acceptance criteria
   - Incorrect logic or obvious bugs
   - Missing error handling
   - Violation of the task description requirements

3. Write your audit report in this format:

### Audit Report

**Criterion 1: [first criterion text]**
- Status: YES / PARTIAL / NO
- Evidence: (quote relevant code or explain what is missing)

**Criterion 2: [second criterion text]**
- Status: YES / PARTIAL / NO
- Evidence: ...

...

### Summary
- Total criteria: {len(acceptance)}
- Passed: (count)
- Partial: (count)
- Failed: (count)

### Verdict
(Brief explanation of your overall assessment)

## Scoring

Based on your audit, assign a satisfaction score:
- 90-100: All criteria met, code quality is excellent
- 80-89: All criteria met with minor issues
- 60-79: Most criteria met but has notable gaps
- 40-59: Significant issues or missing features
- 0-39: Major failures, implementation is fundamentally broken

You MUST output the score as the VERY LAST LINE in this exact format (nothing after it):

<score>YOUR_SCORE</score>

Where YOUR_SCORE is an integer or one decimal place number between 0 and 100."""

        return prompt

    def _execute_judge(self, prompt: str, prompt_size: int) -> str:
        """
        执行裁判推理

        复用 DualTimeoutExecutor，将输出重定向到临时文件。
        """
        from scripts.config import CLAUDE_CMD, PERMISSION_MODE

        # 计算超时：validation 阶段用 1.5x 基准
        base = int(BASE_SILENCE_TIMEOUT * 1.5)
        size_bonus = int(prompt_size / 1024 * 1.0)
        hard = min(base + size_bonus, MAX_SILENCE_TIMEOUT)
        silence = max(int(hard * 0.6), 30)
        silence = min(silence, hard - 5)

        app_logger.info(
            f"[Validator] 执行裁判: hard={hard}s, silence={silence}s"
        )

        cmd = [
            CLAUDE_CMD,
            "--print",
            "--permission-mode", PERMISSION_MODE,
        ]

        # 创建输出文件
        session_id = f"val_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{os.getpid()}"
        output_file = CLI_IO_DIR / "sessions" / f"{session_id}_output.txt"
        output_file.parent.mkdir(parents=True, exist_ok=True)

        # 写入会话元数据
        import json as _json
        meta_file = CLI_IO_DIR / "current.json"
        meta_file.write_text(
            _json.dumps({
                "session_id": session_id,
                "task_id": self.task_id,
                "stage": "validation",
                "start_time": datetime.now().isoformat(),
                "active": True,
                "prompt_size": prompt_size,
                "validator": True,
            }, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        # DualTimeoutExecutor 执行
        executor = DualTimeoutExecutor(
            hard_timeout=hard,
            silence_timeout=silence,
        )

        exit_code = executor.execute(cmd, prompt)

        # 更新元数据
        meta_file.write_text(
            _json.dumps({
                "session_id": session_id,
                "task_id": self.task_id,
                "stage": "validation",
                "end_time": datetime.now().isoformat(),
                "exit_code": exit_code,
                "active": False,
                "validator": True,
            }, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        is_timeout = exit_code in (14, 124)
        if is_timeout:
            label = "silence" if exit_code == 14 else "hard"
            app_logger.warning(f"[Validator] 裁判超时 ({label})")
            return f"[Validation timeout ({label}), {hard}s exceeded]\n<score>0</score>"

        if exit_code != 0:
            app_logger.warning(f"[Validator] 裁判异常退出: code={exit_code}")
            return f"[Validation error: exit code {exit_code}]\n<score>0</score>"

        # 读取输出文件
        if not output_file.exists():
            app_logger.warning("[Validator] 输出文件未生成")
            return "[Validation output file missing]\n<score>0</score>"

        output_text = output_file.read_text(encoding="utf-8", errors="replace")
        output_lines = output_text.strip().split("\n")

        # 检查 <score> 是否存在，缺失则追加默认分
        has_score = any(
            re.search(r"<score>\s*\d+(?:\.\d)?\s*</score>", line)
            for line in output_lines[-5:]  # 只检查最后 5 行
        )
        if not has_score:
            app_logger.warning("[Validator] 输出中缺少 <score> 标签，追加默认分 0")
            output_text += "\n<score>0</score>"

        app_logger.info(
            f"[Validator] 裁判完成: "
            f"output={len(output_text) // 1024}KB, exit={exit_code}"
        )

        return output_text


# ========================================
#  独立运行入口（手动验证用）
# ========================================

def main():
    """命令行入口 - 手动对指定任务执行满意度验证"""
    import argparse

    parser = argparse.ArgumentParser(
        description="LLM-as-a-Judge 满意度验证",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
    python .harness/scripts/validate_satisfaction.py --task-id Model_001
    python .harness/scripts/validate_satisfaction.py --task-id API_Import_001 --verbose
        """,
    )
    parser.add_argument("--task-id", required=True, help="任务 ID")
    parser.add_argument("-v", "--verbose", action="store_true", help="详细输出")

    args = parser.parse_args()

    validator = SatisfactionValidator(args.task_id)
    output_text, exit_code = validator.evaluate()

    print("\n" + "=" * 60)
    print(f"Validation Result: {args.task_id}")
    print("=" * 60)
    print(output_text)
    print("=" * 60)

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
