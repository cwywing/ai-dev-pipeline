#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
 Satisfaction Validator - Claude Code CLI 模式独立验证脚本
用于验证 Dev Agent 的实现是否满足任务要求

功能：
- 调用 Claude Code CLI 进行交互式审查
- 像自动化脚本那样调用 Claude
- 你可以：
  a. 直接与 Claude 交互讨论代码
  b. 最终输入评估结果（JSON 格式）

使用示例：
    python3 .harness/scripts/validate_satisfaction.py --task-id API_Import_001

退出码：
    0 - 验证通过
    1 - 验证失败
    2 - 验证遇到错误
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Any, Optional

# 添加脚本目录到路径
SCRIPT_DIR = Path(__file__).parent.resolve()
HARNESS_DIR = SCRIPT_DIR.parent
PROJECT_ROOT = HARNESS_DIR.parent

# 导入项目工具
try:
    # 添加项目根目录到路径（用于导入 console_output 等模块）
    sys.path.insert(0, str(PROJECT_ROOT))
    sys.path.insert(0, str(SCRIPT_DIR))

    from console_output import success, error, warning, info
    from task_utils import TaskCodec
    # 尝试导入 TaskFileStorage（单文件模式）
    try:
        from task_file_storage import TaskFileStorage
        _storage_available = True
    except ImportError:
        _storage_available = False
        warning("无法导入 TaskFileStorage，单文件存储功能将不可用", file=sys.stderr)
except ImportError as e:
    print(f"[FAIL] 无法导入依赖模块: {e}", file=sys.stderr)
    print("[INFO] 请确保在 laravel 项目根目录下运行", file=sys.stderr)
    sys.exit(2)


# ==================== 实现检测模块 ====================

class ImplementationDetector:
    """实现文件检测器"""

    def __init__(self, project_root: Path = PROJECT_ROOT):
        self.project_root = project_root

    def detect_from_task(self, task: Dict[str, Any]) -> List[Dict[str, Any]]:
        """从任务中检测实现文件"""
        files = []

        if 'files' in task:
            for file_path in task['files']:
                file_info = self._analyze_file(file_path)
                if file_info:
                    files.append(file_info)
            return files

        files.extend(self._infer_files_from_acceptance(task.get('acceptance', [])))
        files.extend(self._infer_files_from_description(task.get('description', '')))

        return files

    def _analyze_file(self, file_path: str) -> Optional[Dict[str, Any]]:
        """分析单个文件"""
        full_path = self.project_root / file_path

        if not full_path.exists():
            return None

        file_type = self._classify_file(file_path)

        try:
            with open(full_path, 'r', encoding='utf-8') as f:
                content = f.read()

            return {
                "path": file_path,
                "type": file_type,
                "content_summary": self._summarize_content(file_type, content)
            }
        except Exception as e:
            return {
                "path": file_path,
                "type": file_type,
                "error": str(e)
            }

    def _classify_file(self, file_path: str) -> str:
        """分类文件类型"""
        path = Path(file_path)

        if 'Controller' in path.name:
            return 'controller'
        elif 'Request' in path.name:
            return 'form_request'
        elif 'Resource' in path.name:
            return 'resource'
        elif 'Model' in path.name:
            return 'model'
        elif 'Test.php' in path.name or 'Test.php' in str(path):
            return 'test'
        elif 'migration' in str(path).lower():
            return 'migration'
        elif 'routes' in str(path).lower() or path.name == 'api.php':
            return 'route'
        elif 'Service' in path.name:
            return 'service'
        else:
            return 'other'

    def _summarize_content(self, file_type: str, content: str) -> str:
        """摘要文件内容"""
        lines = content.strip().split('\n')[:20]
        summary = '\n'.join(lines)

        if len(content) > 1000:
            summary = summary + f"\n... (共 {len(content)} 字符，显示前 1000 字符)"

        return summary

    def _infer_files_from_acceptance(self, acceptance: List[str]) -> List[Dict[str, Any]]:
        """从验收标准中推断实现文件"""
        files = []
        patterns = {
            'Controller': r'(?:app/Http/Controllers/Api/(?:App|Admin)/[^ ]+Controller\.php)',
            'Request': r'(?:app/Http/Requests/(?:App|Admin)/[^ ]+Request\.php)',
            'Resource': r'(?:app/Http/Resources/(?:App|Admin)/[^ ]+Resource\.php)',
            'Model': r'(?:app/Models/[^ ]+\.php)',
            'Test': r'(?:tests/(?:Feature|Unit)/[^ ]+Test\.php)',
            'Migration': r'(?:database/migrations/[^ ]+\.php)',
            'Route': r'(?:routes/api\.php)',
            'Service': r'(?:app/Services/[^ ]+Service\.php)',
        }

        for criterion in acceptance:
            for file_type, pattern in patterns.items():
                matches = re.findall(pattern, criterion)
                for match in matches:
                    files.append({
                        "path": match,
                        "type": file_type.lower(),
                        "description": f"从验收标准推断: {criterion}"
                    })

        seen_paths = set()
        unique_files = []
        for file in files:
            if file['path'] not in seen_paths:
                seen_paths.add(file['path'])
                unique_files.append(file)

        return unique_files

    def _infer_files_from_description(self, description: str) -> List[Dict[str, Any]]:
        """从任务描述中推断实现文件"""
        files = []
        controller_pattern = r'(?:api/v1/.*?/|\s)(\w+?)Controller'
        matches = re.findall(controller_pattern, description)
        for match in matches:
            files.append({
                "path": f"app/Http/Controllers/Api/Admin/{match}Controller.php",
                "type": "controller",
                "description": f"从描述推断: {description}"
            })
        return files


# ==================== 输出格式化模块 ====================

class OutputFormatter:
    """输出格式化器"""

    @staticmethod
    def format_markdown(result: Dict[str, Any], task_id: str, task_desc: str) -> str:
        """格式化为 Markdown"""
        lines = []

        status = result.get('overall_assessment', '未知')
        status_text = OutputFormatter._get_status_text(status)

        lines.append(f"# 验证结果: {status_text} {status}")
        lines.append("")
        lines.append(f"**任务 ID**: {task_id}")
        lines.append(f"**任务描述**: {task_desc}")
        lines.append(f"**评估时间**: {OutputFormatter._get_timestamp()}")
        lines.append("")

        score = result.get('satisfaction_score', 0)
        lines.append(f"## 满意度评分: {score}/100")
        lines.append("")

        coverage = result.get('acceptance_coverage', {})
        lines.append("## 验收标准覆盖")
        lines.append("")

        passed = coverage.get('passed', [])
        failed = coverage.get('failed', [])
        partial = coverage.get('partial', [])

        if passed:
            lines.append(f"### [OK] 通过 ({len(passed)})")
            for idx in passed:
                try:
                    idx_int = int(idx)
                    lines.append(f"- 验收标准 #{idx_int + 1}")
                except (ValueError, TypeError):
                    lines.append(f"- 验收标准 #{idx}")
        if partial:
            lines.append(f"### [WARN] 部分通过 ({len(partial)})")
            for idx in partial:
                try:
                    idx_int = int(idx)
                    lines.append(f"- 验收标准 #{idx_int + 1}")
                except (ValueError, TypeError):
                    lines.append(f"- 验收标准 #{idx}")
        if failed:
            lines.append(f"### [FAIL] 未通过 ({len(failed)})")
            for idx in failed:
                try:
                    idx_int = int(idx)
                    lines.append(f"- 验收标准 #{idx_int + 1}")
                except (ValueError, TypeError):
                    lines.append(f"- 验收标准 #{idx}")
        if not passed and not partial and not failed:
            lines.append("### 无验收标准或无法匹配")
        lines.append("")

        code_quality = result.get('code_quality', {})
        lines.append("## 代码质量检查")
        lines.append("")
        lines.append("| 检查项 | 状态 |")
        lines.append("|--------|------|")
        lines.append(f"| 遵循约定 | {'[OK]' if code_quality.get('follows_conventions', False) else '[FAIL]'} |")
        lines.append(f"| 使用 Resources | {'[OK]' if code_quality.get('uses_resources', False) else '[FAIL]'} |")
        lines.append(f"| 使用 Requests | {'[OK]' if code_quality.get('uses_requests', False) else '[FAIL]'} |")
        lines.append(f"| 有测试 | {'[OK]' if code_quality.get('has_tests', False) else '[FAIL]'} |")
        lines.append("")

        issues = result.get('issues', [])
        if issues:
            lines.append("## 发现的问题")
            lines.append("")
            for i, issue in enumerate(issues, 1):
                lines.append(f"{i}. {issue}")
            lines.append("")

        recommendations = result.get('recommendations', [])
        if recommendations:
            lines.append("## 改进建议")
            lines.append("")
            for i, rec in enumerate(recommendations, 1):
                lines.append(f"{i}. {rec}")
            lines.append("")

        reasoning = result.get('reasoning', '')
        if reasoning:
            lines.append("## 详细推理")
            lines.append("")
            lines.append("```")
            lines.append(reasoning)
            lines.append("```")
            lines.append("")

        return '\n'.join(lines)

    @staticmethod
    def _get_status_text(status: str) -> str:
        """获取状态对应的文本"""
        status_lower = status.lower()
        # 检查"不通过"或"fail"在前
        if '不通过' in status or 'fail' in status_lower:
            return '[FAIL]'
        elif '部分' in status or 'partial' in status_lower:
            return '[WARN]'
        elif '通过' in status or 'pass' in status_lower:
            return '[OK]'
        else:
            return '[UNKNOWN]'

    @staticmethod
    def _get_timestamp() -> str:
        """获取当前时间戳"""
        from datetime import datetime
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ==================== 主流程 ====================

class SatisfactionValidator:
    """满意度验证器主类"""

    def __init__(self, task_id: str):
        self.task_id = task_id
        self.task_codec = TaskCodec
        self.implementation_detector = ImplementationDetector()
        self.task = None
        self.result = None
        self.validation_config = {}

    def load_task(self) -> bool:
        """加载任务数据"""
        try:
            if _storage_available:
                storage = TaskFileStorage()
                self.task = storage.load_task(self.task_id)
                if self.task:
                    info(f"已加载任务 (单文件模式): {self.task_id}")
                    # 读取 validation 配置
                    self.validation_config = self.task.get('validation', {})
                    info(f"验证配置: enabled={self.validation_config.get('enabled', False)}, threshold={self.validation_config.get('threshold', 0.8)}")
                    return True
                warning(f"单文件模式未找到任务 {self.task_id}，尝试旧模式...")

            index_path = HARNESS_DIR / 'task-index.json'
            if not index_path.exists():
                error(f"任务索引文件不存在: {index_path}")
                return False

            with open(index_path, 'r', encoding='utf-8') as f:
                index = json.load(f)

            task_info = index.get('index', {}).get(self.task_id)
            if not task_info:
                error(f"未找到任务 {self.task_id}")
                return False

            self.task = self.task_codec.load_tasks(str(index_path))

            found = False
            for t in self.task.get('tasks', []):
                task_id = t.get('i') or t.get('id')
                if task_id == self.task_id:
                    self.task = t
                    found = True
                    break

            if not found:
                error(f"未在任务列表中找到 {self.task_id}")
                return False

            info(f"已加载任务: {self.task_id}")
            # 读取 validation 配置
            self.validation_config = self.task.get('validation', {})
            info(f"验证配置: enabled={self.validation_config.get('enabled', False)}, threshold={self.validation_config.get('threshold', 0.8)}")
            return True

        except Exception as e:
            error(f"加载任务失败: {e}")
            return False

    def validate(self) -> bool:
        """执行验证"""
        if not self.task:
            error("任务未加载，请先调用 load_task()")
            return False

        try:
            description = self.task.get('d') or self.task.get('description', '')
            acceptance_raw = self.task.get('a') or self.task.get('acceptance', [])
            acceptance = [acc if isinstance(acc, str) else str(acc) for acc in acceptance_raw]

            scenarios = self.task.get('scenarios', [])
            implementation_files = self.implementation_detector.detect_from_task(self.task)

            prompt = self._build_prompt(description, acceptance, scenarios, implementation_files)

            self.description = description
            self.acceptance = acceptance
            self.prompt = prompt

            # 调用 Claude CLI
            info(f"正在调用 Claude Code CLI 进行评估...")

            # 从 task 中提取 files 信息
            if 'files' in self.task:
                info(f"检测到 {len(self.task['files'])} 个实现文件")

            return True

        except Exception as e:
            self.result = {
                "success": False,
                "error": str(e),
                "reasoning": f"验证过程发生错误: {e}"
            }
            return False

    def _build_prompt(self, description: str, acceptance: List[str],
                      scenarios: Optional[List[Dict[str, Any]]],
                      implementation_files: List[Dict[str, Any]]) -> str:
        """构建判断提示词"""
        files_info = ""
        for file in implementation_files:
            files_info += f"\n### {file.get('path', 'Unknown')}\n"
            if file.get('type'):
                files_info += f"类型: {file['type']}\n"
            if file.get('content_summary'):
                files_info += f"内容摘要: {file['content_summary'][:500]}\n"

        scenarios_info = ""
        if scenarios:
            scenarios_info = "\n\n## 场景要求\n"
            for i, scenario in enumerate(scenarios, 1):
                scenarios_info += f"\n### 场景 {i}: {scenario.get('name', f'Scenario {i}')}\n"
                if 'description' in scenario:
                    scenarios_info += f"描述: {scenario['description']}\n"
                if 'steps' in scenario:
                    scenarios_info += f"步骤:\n"
                    for step in scenario['steps']:
                        scenarios_info += f"- {step}\n"
                if 'expected' in scenario:
                    scenarios_info += f"预期结果: {scenario['expected']}\n"

        acceptance_formatted = "\n".join(f"- {item}" for item in acceptance)

        prompt = f"""你是一位专业的 Laravel 后端架构师审核员。请独立评估 Dev Agent 的实现是否满足任务要求。

## 任务描述
{description}

## 验收标准
{acceptance_formatted}

## 实现文件
{files_info}

{scenarios_info}

## 评估要求

请基于以下维度进行评估：

1. **功能完整性**: 所有验收标准是否全部实现
2. **代码质量**: 代码是否符合 Laravel 最佳实践
3. **测试覆盖**: 是否有适当的测试覆盖
4. **架构合理性**: 模型、控制器、Request、Resource 的组织是否合理

## 你的任务

1. 首先，阅读任务描述和验收标准，理解原始意图
2. 然后，阅读实现文件，分析代码是否真的满足了原始意图
3. 最后，给出你的独立评估

## 输出格式

请以 JSON 格式输出评估结果，必须包含以下字段：

```json
{{
    "overall_assessment": "通过/部分通过/不通过",
    "satisfaction_score": 0-100的整数,
    "acceptance_coverage": {{
        "passed": ["匹配的验收标准索引列表"],
        "failed": ["未满足的验收标准索引列表"],
        "partial": ["部分满足的验收标准索引列表"]
    }},
    "code_quality": {{
        "follows_conventions": true/false,
        "uses_resources": true/false,
        "uses_requests": true/false,
        "has_tests": true/false
    }},
    "issues": ["发现的问题列表"],
    "recommendations": ["改进建议列表"],
    "reasoning": "详细推理说明"
}}
```

## 重要提示

- 这是一个独立的评估环节，你不应该修改任何代码
- 请基于原始任务意图来判断实现是否真正满足需求
- 只输出 JSON，不要输出额外的 Markdown 格式
"""
        return prompt

    def get_exit_code(self) -> int:
        """获取退出码"""
        if not self.result:
            return 2

        # 检查是否有解析错误
        if self.result.get('success') == False:
            # 如果是 JSON 解析失败，返回 2
            if '无法解析 JSON 输出' in str(self.result.get('error', '')) or 'JSON 解析失败' in str(self.result.get('error', '')):
                return 2
            # 其他情况（如评估结果为不通过）返回 1
            return 1

        assessment = self.result.get('overall_assessment', '').lower()
        # 检查"不通过"在前
        if '不通过' in self.result.get('overall_assessment', '') or 'fail' in assessment:
            return 1
        elif '通过' in self.result.get('overall_assessment', '') or 'pass' in assessment:
            return 0
        else:
            return 2


# ==================== 命令行入口 ====================

def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description='LLM-as-a-judge满意度验证工具 (Claude Code CLI 模式)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
    python3 .harness/scripts/validate_satisfaction.py --task-id API_Import_001

提示:
    1. 脚本会加载任务信息并调用 Claude Code CLI
    2. 你可以与 Claude 交互讨论代码
    3. Claude 会输出 JSON 格式的评估结果
    4. 请确保 Claude 的输出以 JSON 代码块结尾

退出码:
    0 - 验证通过
    1 - 验证失败
    2 - 验证错误
        """
    )

    parser.add_argument(
        '--task-id',
        required=True,
        help='任务 ID (例如: API_Import_001)'
    )
    # 新增：支持手动提供评分（用于同步验证结果）
    parser.add_argument('--score', type=float, help='满意度评分（0.0-1.0，用于手动标记验证结果）')
    parser.add_argument('--tries', type=int, help='验证尝试次数（用于手动标记验证结果）')

    args = parser.parse_args()

    # 新增：支持手动提供评分（用于同步验证结果）
    manual_score = getattr(args, 'score', None)
    manual_tries = getattr(args, 'tries', 0)

    if not args.task_id:
        error("需要提供 --task-id 参数")
        sys.exit(2)

    validator = SatisfactionValidator(task_id=args.task_id)

    if not validator.load_task():
        sys.exit(2)

    if not validator.validate():
        error("验证过程失败")
        sys.exit(2)

    # 打印提示信息
    print("\n" + "="*70)
    print("正在调用 Claude Code CLI 进行评估...")
    print("="*70)
    print("\n提示：")
    print("1. Claude CLI 将启动并读取任务信息")
    print("2. 你可以与 Claude 交互讨论代码实现")
    print("3. Claude 应该输出 JSON 格式的评估结果（在代码块中）")
    print("="*70 + "\n")

    # 修复 Windows 终端编码问题
    try:
        if sys.platform == 'win32':
            import io
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    except:
        pass

    # 构建完整 prompt（包含任务信息和评估指令）
    full_prompt = f"""{validator.prompt}

--------
请基于以上任务信息进行评估，并以 JSON 格式输出结果。

--------
评估结果:"""

    # 调用 Claude Code CLI（使用与自动化脚本相同的方式）
    # 通过管道传递 prompt
    try:
        import platform
        system = platform.system()

        # Claude Code CLI 可执行文件路径
        claude_exe = 'claude'
        if system == 'Windows':
            # Windows 上尝试使用完整路径
            import shutil
            claude_exe = shutil.which('claude') or 'claude'

        # 保存 prompt 到临时文件
        prompt_fd, prompt_file = tempfile.mkstemp(suffix='.txt', text=True)
        try:
            os.close(prompt_fd)
            with open(prompt_file, 'w', encoding='utf-8') as f:
                f.write(full_prompt)

            # 读取 prompt 并通过管道传递给 claude
            with open(prompt_file, 'r', encoding='utf-8') as f:
                prompt_content = f.read()

            # 调用 claude，通过 stdin 传递 prompt
            if system == 'Windows':
                # Windows: 使用 cmd /c 调用以正确处理 .cmd 文件
                # 设置 shell=True 以使用 PATH 查找
                process = subprocess.Popen(
                    [claude_exe, '--permission-mode', 'bypassPermissions'],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding='utf-8',
                    shell=True  # Windows 特定：允许查找 .cmd 文件
                )
                stdout, _ = process.communicate(input=prompt_content)
            else:
                process = subprocess.Popen(
                    [claude_exe, '--permission-mode', 'bypassPermissions'],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding='utf-8'
                )
                stdout, _ = process.communicate(input=prompt_content)

            # 处理 Claude 输出的编码问题（Windows 下可能是 UTF-8）
            try:
                if isinstance(stdout, bytes):
                    stdout_str = stdout.decode('utf-8', errors='replace')
                else:
                    stdout_str = stdout
                print(stdout_str)
            except Exception:
                # 如果输出有问题，只显示基本信息
                print("[Claude 输出已接收，但无法显示]")

            # 解析 Claude 的输出
            result = _parse_claude_output(stdout)
            result['task_id'] = validator.task_id
            result['description'] = validator.description
            result['acceptance'] = validator.acceptance
            validator.result = result

            # 输出结果
            output_content = OutputFormatter.format_markdown(
                result,
                validator.task_id,
                validator.description
            )
            print("\n" + "="*70)
            print("评估结果")
            print("="*70)
            print(output_content)

            # 使用 print 替代 info 以避免编码问题
            print(f"验证完成")
            print(f"评估结果: {result.get('overall_assessment', '未知')}")
            print(f"满意度评分: {result.get('satisfaction_score', 0)}/100")

            # 写入验证结果到任务
            satisfaction_score = result.get('satisfaction_score', 0)
            # 转换为 0.0-1.0 范围（如果原始是 0-100）
            if satisfaction_score > 1.0:
                satisfaction_score = satisfaction_score / 100.0

            # 如果手动提供了 tries，使用手动值；否则使用 0（第一次尝试）
            tries = manual_tries if manual_tries > 0 else 0

            # 调用 harness-tools.py 写入结果
            _write_result_to_task(validator.task_id, satisfaction_score, tries)

        finally:
            try:
                if prompt_file and os.path.exists(prompt_file):
                    os.remove(prompt_file)
            except:
                pass

    except FileNotFoundError:
        error("Claude CLI 未找到，请确保已安装并添加到 PATH")
        sys.exit(2)
    except Exception as e:
        error(f"Claude CLI 调用失败: {e}")
        sys.exit(2)

    sys.exit(validator.get_exit_code())


def _write_result_to_task(task_id: str, score: float, tries: int) -> bool:
    """
    将验证结果写入任务（调用 harness-tools.py 标记 validation 完成）

    Args:
        task_id: 任务 ID
        score: 满意度评分 (0.0-1.0)
        tries: 尝试次数

    Returns:
        bool: 是否成功
    """
    try:
        import subprocess
        # 使用 harness-tools.py 的 mark-validation 动作
        result = subprocess.run(
            [
                'python3', '.harness/scripts/harness-tools.py',
                '--action', 'mark-validation',
                '--id', task_id,
                '--score', str(score),
                '--tries', str(tries)
            ],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            info(f"验证结果已写入任务 {task_id} (score: {score}, tries: {tries})")
            return True
        else:
            warning(f"写入验证结果失败: {result.stderr}")
            return False
    except Exception as e:
        warning(f"写入验证结果异常: {e}")
        return False


def _parse_claude_output(output: str) -> Dict[str, Any]:
    """解析 Claude 输出的 JSON 结果"""
    try:
        # 尝试查找 JSON 代码块
        import re
        match = re.search(r'```json\s*(.*?)\s*```', output, re.DOTALL)
        if match:
            return json.loads(match.group(1))

        # 尝试查找任意代码块
        match = re.search(r'```\s*(.*?)\s*```', output, re.DOTALL)
        if match:
            return json.loads(match.group(1))

        # 尝试直接解析整个输出
        if output.strip().startswith('{'):
            return json.loads(output)

        # 查找 JSON-like 内容
        json_start = output.find('{')
        json_end = output.rfind('}')
        if json_start >= 0 and json_end > json_start:
            json_str = output[json_start:json_end+1]
            return json.loads(json_str)

        return {
            "success": False,
            "error": "无法解析 JSON 输出",
            "raw_output": output,
            "reasoning": "Claude 的输出无法解析为有效的 JSON 格式"
        }
    except json.JSONDecodeError as e:
        error_msg = str(e)
        return {
            "success": False,
            "error": "JSON 解析失败: " + error_msg,
            "raw_output": output,
            "reasoning": "无法解析 LLM 响应为有效的 JSON 格式"
        }
    except TypeError as e:
        # 处理类型错误（如字符串和整数拼接）
        error_msg = str(e)
        return {
            "success": False,
            "error": "类型错误: " + error_msg,
            "raw_output": output,
            "reasoning": "解析过程中发生类型错误: " + error_msg
        }
    except Exception as e:
        # 捕获其他所有异常，避免程序崩溃
        error_msg = str(e)
        return {
            "success": False,
            "error": "解析异常: " + error_msg,
            "raw_output": output,
            "reasoning": "解析过程中发生未知错误: " + error_msg
        }


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        error("用户中断，退出程序")
        sys.exit(0)
    except Exception as e:
        error(f"程序异常: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
