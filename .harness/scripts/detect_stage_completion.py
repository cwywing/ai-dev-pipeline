#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
混合模式阶段完成检测脚本 (Unix/Mac 版本)

功能：
- 检测 Dev/Test/Review 阶段是否完成
- 支持三种退出码：0（完成）、1（未完成）、2（无法确定）
- 混合检测模式：主动检测 + 被动检测 + 旁路检测

使用示例：
    python3 .harness/scripts/detect_stage_completion.py \
        --id SIM_Test_Fix_Compatibility_001 \
        --stage test

退出码说明：
    0 - 阶段已完成（自动进入下一阶段）
    1 - 阶段未完成（继续等待/重试）
    2 - 无法确定（触发人工审查）
"""

import sys
import os
import re
import json
import argparse
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple

# 添加脚本目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from task_utils import TaskCodec, load_tasks
from console_output import success, error, warning, info


class DetectStageCompletion:
    """混合模式阶段完成检测器"""

    # CLI I/O 目录
    CLI_IO_DIR = ".harness/cli-io/sessions"

    # 最近的会话文件数量（用于分析）
    RECENT_SESSIONS_COUNT = 5

    def __init__(self, task_id: str, stage: str):
        """
        初始化检测器

        Args:
            task_id: 任务 ID
            stage: 阶段名称 (dev/test/review)
        """
        self.task_id = task_id
        self.stage = stage.lower()
        self._cli_io_dir = Path(self.CLI_IO_DIR)

    def _safe_print(self, message: str, file=sys.stdout):
        """安全打印，使用 console_output 模块的 _safe_print"""
        try:
            # 直接使用 console_output._safe_print，避免双重包装
            from console_output import _safe_print as console_safe_print
            console_safe_print(message, file=file)
        except Exception:
            # 如果出错，尝试直接打印
            print(message, file=file)

    def _get_task_data(self) -> Optional[Dict[str, Any]]:
        """获取任务数据"""
        try:
            # 优先使用 TaskFileStorage
            try:
                from task_file_storage import TaskFileStorage
                storage = TaskFileStorage()
                task = storage.load_task(self.task_id)
                if task:
                    return task
            except Exception:
                pass

            # 回退到旧的 load_tasks 方法
            data = load_tasks()
            for task in data.get('tasks', []):
                if task.get('id') == self.task_id:
                    return task
            return None
        except Exception as e:
            self._safe_print(f"[ERROR] 加载任务数据失败: {e}", file=sys.stderr)
            return None

    def _get_cli_sessions(self) -> List[Path]:
        """获取最近的 CLI 会话文件（不依赖任务 ID 匹配）"""
        if not self._cli_io_dir.exists():
            return []

        # 获取所有会话文件，按时间排序
        session_files = []
        for f in self._cli_io_dir.glob('*_output.txt'):
            try:
                session_files.append((f, f.stat().st_mtime))
            except Exception:
                continue

        # 按时间排序，返回最近的 N 个
        session_files.sort(key=lambda x: x[1], reverse=True)
        return [f[0] for f in session_files[:self.RECENT_SESSIONS_COUNT]]

    def _load_session_output(self, session_file: Path) -> str:
        """加载会话输出内容"""
        try:
            with open(session_file, 'r', encoding='utf-8', errors='ignore') as f:
                return f.read()
        except Exception:
            return ""

    def detect_cli_parameters(self, output: str) -> Dict[str, bool]:
        """
        检测 CLI 参数调用痕迹

        检查 CLI 输出中是否包含结构化参数调用：
        - --test-results: 测试结果提交
        - --issues: 问题报告
        - --action mark-stage: 主动标记完成

        Args:
            output: CLI 输出内容

        Returns:
            字典包含各检测项结果
        """
        results = {
            'mark_stage_called': False,
            'test_results_provided': False,
            'issues_reported': False,
        }

        # 检测 mark-stage 调用
        if re.search(r'(--action\s+mark-stage|mark-stage)', output, re.IGNORECASE):
            results['mark_stage_called'] = True

        # 检测 --test-results 参数
        if re.search(r'(--test-results|--test-results\s*=)', output, re.IGNORECASE):
            results['test_results_provided'] = True

        # 检测 --issues 参数
        if re.search(r'(--issues\b)', output, re.IGNORECASE):
            results['issues_reported'] = True

        return results

    def detect_test_execution(self, output: str) -> Dict[str, bool]:
        """
        检测测试执行痕迹

        Args:
            output: CLI 输出内容

        Returns:
            字典包含各检测项结果
        """
        results = {
            'test_command_found': False,
            'phpunit_found': False,
            'artisan_test_found': False,
            'pytest_found': False,
            'test_file_created': False,
            'test_results_in_output': False,
        }

        output_lower = output.lower()

        # 检测测试命令
        if re.search(r'(phpunit|php\s+\.\/vendor\/bin\/phpunit)', output, re.IGNORECASE):
            results['phpunit_found'] = True
            results['test_command_found'] = True

        if re.search(r'(php\s+artisan\s+test|php artisan test)', output, re.IGNORECASE):
            results['artisan_test_found'] = True
            results['test_command_found'] = True

        if re.search(r'(pytest|python.*-m\s+pytest)', output, re.IGNORECASE):
            results['pytest_found'] = True
            results['test_command_found'] = True

        # 检测测试文件创建
        if re.search(r'(creates?|新建|创建).*(Test\.php|Test\.cpp|_test\.py)', output, re.IGNORECASE):
            results['test_file_created'] = True

        # 检测测试结果输出
        test_result_patterns = [
            r'(\d+\s+test[s]?\s+(passed|failed))',
            r'( Passed | Failed | FAILED | PASSED )',
            r'(Ran\s+\d+\s+tests?)',
        ]
        for pattern in test_result_patterns:
            if re.search(pattern, output, re.IGNORECASE):
                results['test_results_in_output'] = True
                break

        return results

    def detect_review_keywords(self, output: str) -> Dict[str, bool]:
        """
        检测审查关键词

        Args:
            output: CLI 输出内容

        Returns:
            字典包含各检测项结果
        """
        results = {
            'review_keyword_found': False,
            'quality_assessment': False,
            'inspection_found': False,
        }

        output_lower = output.lower()

        # 审查相关关键词
        review_keywords = [
            r'review',
            r'审查',
            r'质量评估',
            r'验收',
            r'sign-off',
            r'code review',
            r'quality check',
        ]

        for keyword in review_keywords:
            if re.search(keyword, output_lower):
                results['review_keyword_found'] = True
                break

        # 质量评估相关
        if re.search(r'(质量|coverage|覆盖率|test\s+result)', output_lower):
            results['quality_assessment'] = True

        # 检查/审查相关
        if re.search(r'(检查|inspect|audit|验证)', output_lower):
            results['inspection_found'] = True

        return results

    def detect_git_changes(self) -> Dict[str, bool]:
        """
        检测 Git 变更

        Returns:
            字典包含各检测项结果
        """
        results = {
            'git_changes_detected': False,
            'files_modified': [],
            'new_files': [],
        }

        try:
            import subprocess
            result = subprocess.run(
                ['git', 'status', '--porcelain'],
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.returncode == 0 and result.stdout.strip():
                results['git_changes_detected'] = True

                # 解析 git status 输出
                for line in result.stdout.strip().split('\n'):
                    if not line:
                        continue
                    # 格式: XY filename
                    # X = 工作区变更, Y = 暂存区变更
                    if len(line) >= 3:
                        status = line[:2]
                        filename = line[3:].strip()

                        if '??' in status or 'A' in status:
                            results['new_files'].append(filename)
                        else:
                            results['files_modified'].append(filename)

        except (subprocess.TimeoutExpired, Exception) as e:
            self._safe_print(f"[ERROR] 检测 Git 变更失败: {e}", file=sys.stderr)

        return results

    def check_test_stage(self) -> Tuple[int, str]:
        """
        检测 Test 阶段完成条件

        满足以下任意条件视为完成：
        1. --test-results 参数调用 (高权重)
        2. --issues 参数调用 (高权重，报告问题也算完成)
        3. 测试执行痕迹 + 测试文件创建 (中高权重)
        4. 退出码 0 且有测试相关输出

        Returns:
            (exit_code, message) 元组
        """
        sessions = self._get_cli_sessions()
        if not sessions:
            return (
                1,
                "Test 阶段未完成: 未找到 CLI 会话输出，无法确认测试执行情况"
            )

        # 分析最近的会话
        test_results_provided = False
        issues_reported = False
        test_execution_found = False
        test_files_created = False

        for session_file in sessions:
            output = self._load_session_output(session_file)

            # 检测 CLI 参数
            cli_params = self.detect_cli_parameters(output)
            if cli_params['test_results_provided']:
                test_results_provided = True
            if cli_params['issues_reported']:
                issues_reported = True

            # 检测测试执行
            test_exec = self.detect_test_execution(output)
            if test_exec['test_command_found']:
                test_execution_found = True
            if test_exec['test_file_created']:
                test_files_created = True

        # 判断逻辑：满足任意两种条件
        passed_conditions = 0
        conditions = []

        if test_results_provided:
            passed_conditions += 1
            conditions.append("--test-results 参数调用")

        if issues_reported:
            passed_conditions += 1
            conditions.append("--issues 参数调用(问题报告)")

        if test_execution_found:
            passed_conditions += 1
            conditions.append("测试执行痕迹")

        if test_files_created:
            passed_conditions += 1
            conditions.append("测试文件创建")

        if passed_conditions >= 2:
            return (
                0,
                f"Test 阶段完成: 检测到 {passed_conditions} 项完成条件 - {'; '.join(conditions)}"
            )
        elif passed_conditions == 1:
            return (
                2,
                f"无法确定: 仅检测到 1 项完成条件 - {'; '.join(conditions)}。需要至少 2 项匹配"
            )
        else:
            return (
                1,
                "Test 阶段未完成: 未检测到足够的测试执行痕迹"
            )

    def check_review_stage(self) -> Tuple[int, str]:
        """
        检测 Review 阶段完成条件

        满足以下任意两种视为完成：
        1. --issues 参数调用 (高权重)
        2. --test-results 参数调用 (中权重)
        3. 审查关键词 (中权重)
        4. 完成状态文本匹配 (中权重) - 新增，检测"已完成"文本

        Returns:
            (exit_code, message) 元组
        """
        sessions = self._get_cli_sessions()
        if not sessions:
            return (
                1,
                "Review 阶段未完成: 未找到 CLI 会话输出，无法确认审查执行情况"
            )

        # 分析最近的会话
        issues_reported = False
        test_results_provided = False
        review_keywords_found = 0
        completion_text_found = False

        # 完成状态文本模式（放宽匹配条件）
        completion_patterns = [
            r'(审查完成|review.*完成|review\s+done|review\s+complete)',
            r'(阶段已完成|任务已完成|已标记为完成)',
            r'(通过审查|符合.*规范|验收通过)',
            r'(✅.*审查|✓.*审查|✓.*完成)',
            r'(所有验收标准.*已满足|所有.*标准.*已满足)',
            r'(任务状态.*已完成|Review 阶段.*已通过)',
            r'(代码质量优秀|可以安全.*继续)',
        ]

        for session_file in sessions:
            output = self._load_session_output(session_file)

            # 检测 CLI 参数
            cli_params = self.detect_cli_parameters(output)
            if cli_params['issues_reported']:
                issues_reported = True
            if cli_params['test_results_provided']:
                test_results_provided = True

            # 检测审查关键词
            review = self.detect_review_keywords(output)
            if review['review_keyword_found']:
                review_keywords_found += 1
            if review['quality_assessment']:
                review_keywords_found += 1
            if review['inspection_found']:
                review_keywords_found += 1

            # 检测完成状态文本（新增）
            for pattern in completion_patterns:
                if re.search(pattern, output, re.IGNORECASE):
                    completion_text_found = True
                    break

        # 判断逻辑：满足任意两种条件
        passed_conditions = 0
        conditions = []

        if issues_reported:
            passed_conditions += 1
            conditions.append("--issues 参数调用(问题报告)")

        if test_results_provided:
            passed_conditions += 1
            conditions.append("--test-results 参数调用")

        if review_keywords_found >= 2:
            passed_conditions += 1
            conditions.append("审查关键词匹配")

        if completion_text_found:
            passed_conditions += 1
            conditions.append("完成状态文本匹配")

        if passed_conditions >= 2:
            return (
                0,
                f"Review 阶段完成: 检测到 {passed_conditions} 项完成条件 - {'; '.join(conditions)}"
            )
        elif passed_conditions == 1:
            return (
                2,
                f"无法确定: 仅检测到 1 项完成条件 - {'; '.join(conditions)}。需要至少 2 项匹配"
            )
        else:
            return (
                1,
                "Review 阶段未完成: 未检测到审查或质量评估痕迹"
            )

    def check_dev_stage(self) -> Tuple[int, str]:
        """
        检测 Dev 阶段完成条件

        满足以下任意条件视为完成：
        1. mark-stage 调用 (高权重) - 主动标记
        2. Git 变更 (中权重) - 有实际产出
        3. 产出记录文件存在 (中权重) - files 字段非空

        Returns:
            (exit_code, message) 元组
        """
        # 检查 mark-stage 是否调用
        sessions = self._get_cli_sessions()
        mark_stage_called = False

        for session_file in sessions:
            output = self._load_session_output(session_file)
            cli_params = self.detect_cli_parameters(output)
            if cli_params['mark_stage_called']:
                mark_stage_called = True
                break

        # 检查 Git 变更
        git_changes = self.detect_git_changes()
        has_git_changes = git_changes['git_changes_detected']

        # 检查产出记录
        artifacts_file = Path(f".harness/artifacts/{self.task_id}.json")
        has_artifacts = False
        if artifacts_file.exists():
            try:
                with open(artifacts_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                files = data.get('files', [])
                if files:
                    has_artifacts = True
            except Exception:
                pass

        # 判断逻辑：满足任意条件
        passed_conditions = 0
        conditions = []

        if mark_stage_called:
            passed_conditions += 1
            conditions.append("mark-stage 主动调用")

        if has_git_changes:
            passed_conditions += 1
            conditions.append(f"Git 变更检测 ({len(git_changes['files_modified'])} 修改, {len(git_changes['new_files'])} 新建)")

        if has_artifacts:
            passed_conditions += 1
            conditions.append("产出记录存在")

        if passed_conditions >= 1:
            return (
                0,
                f"Dev 阶段完成: 检测到 {passed_conditions} 项完成条件 - {'; '.join(conditions)}"
            )
        else:
            return (
                1,
                "Dev 阶段未完成: 未检测到 mark-stage 调用、Git 变更或产出记录"
            )

    def detect(self) -> Tuple[int, str]:
        """
        执行混合模式阶段完成检测

        Returns:
            (exit_code, message) 元组
            exit_code: 0(完成), 1(未完成), 2(无法确定)
        """
        self._safe_print(f"[INFO] 开始混合模式检测: 任务 {self.task_id}, 阶段 {self.stage}")

        # 检查任务是否存在
        task_data = self._get_task_data()
        if not task_data:
            return (
                2,
                f"无法确定: 未找到任务 {self.task_id}"
            )

        # 根据阶段调用对应的检测逻辑
        if self.stage == 'dev':
            return self.check_dev_stage()
        elif self.stage == 'test':
            return self.check_test_stage()
        elif self.stage == 'review':
            return self.check_review_stage()
        else:
            return (
                2,
                f"无法确定: 未知阶段 '{self.stage}'"
            )


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description='混合模式阶段完成检测脚本 (Unix/Mac)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
    # 检测 Test 阶段
    python3 .harness/scripts/detect_stage_completion.py \\
        --id SIM_Test_Fix_Compatibility_001 \\
        --stage test

    # 检测 Review 阶段
    python3 .harness/scripts/detect_stage_completion.py \\
        --id SIM_Test_Fix_Compatibility_001 \\
        --stage review

    # 检测 Dev 阶段
    python3 .harness/scripts/detect_stage_completion.py \\
        --id SIM_Foundation_001 \\
        --stage dev

退出码:
    0 - 阶段已完成
    1 - 阶段未完成
    2 - 无法确定（需要人工审查）
        """
    )

    parser.add_argument('--id', required=True, help='任务 ID')
    parser.add_argument('--stage', required=True, choices=['dev', 'test', 'review'],
                        help='要检测的阶段')

    args = parser.parse_args()

    # 创建检测器并执行
    detector = DetectStageCompletion(args.id, args.stage)
    exit_code, message = detector.detect()

    # 输出结果
    detector._safe_print(message)

    # 返回 Exit Code
    sys.exit(exit_code)


if __name__ == '__main__':
    main()
