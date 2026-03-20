#!/usr/bin/env python3
"""
上下文管理器 - 管理任务上下文的传递和继承
"""

import json
import sys
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

# 添加脚本目录到路径
script_dir = Path(__file__).parent
sys.path.insert(0, str(script_dir))

from console_output import success, error, warning, info
from task_file_storage import TaskFileStorage


class ContextManager:
    """管理任务上下文的传递和继承"""

    def __init__(self):
        self.storage = TaskFileStorage()
        self.storage.initialize()
        self.harness_dir = Path(__file__).parent.parent

    def build_agent_context(self, task_id: str, stage: str) -> Dict[str, Any]:
        """为 Agent 构建完整的上下文"""
        task = self.storage.load_task(task_id)
        if not task:
            return {}

        context = {
            'task_id': task_id,
            'stage': stage,
            'dependencies': self._get_dependency_context(task),
            'project_context': self._get_project_context(),
            'contracts': self._get_applicable_contracts(task),
            'previous_decisions': self._get_previous_decisions(task)
        }

        return context

    def _get_dependency_context(self, task: Dict) -> Dict[str, Any]:
        """获取依赖任务的上下文"""
        dependencies = task.get('depends_on', {})
        context = {
            'artifacts': {},       # 文件产出
            'decisions': [],       # 设计决策
            'interfaces': []       # 接口定义
        }

        # 处理必需依赖
        for dep in dependencies.get('required', []):
            dep_task_id = dep['task_id'] if isinstance(dep, dict) else dep
            dep_context = self._load_dependency_info(dep_task_id)
            if dep_context:
                context['artifacts'][dep_task_id] = dep_context.get('artifacts', [])
                context['decisions'].extend(dep_context.get('decisions', []))

        # 处理可选依赖
        for dep in dependencies.get('optional', []):
            dep_task_id = dep['task_id'] if isinstance(dep, dict) else dep
            dep_context = self._load_dependency_info(dep_task_id)
            if dep_context:
                context['artifacts'][dep_task_id] = dep_context.get('artifacts', [])

        return context

    def _load_dependency_info(self, task_id: str) -> Optional[Dict]:
        """加载依赖任务的信息"""
        task = self.storage.load_task(task_id)
        if not task:
            return None

        info = {
            'artifacts': [],
            'decisions': task.get('context', {}).get('decisions', []),
            'contracts': task.get('contracts', {})
        }

        # 加载产出文件
        artifacts_file = self.harness_dir / 'artifacts' / f'{task_id}.json'
        if artifacts_file.exists():
            with open(artifacts_file, 'r', encoding='utf-8') as f:
                artifacts_data = json.load(f)
                info['artifacts'] = artifacts_data.get('files', [])

        return info

    def _get_project_context(self) -> Dict[str, Any]:
        """获取项目全局上下文"""
        return {
            'php_version': '8.2',
            'laravel_version': '11',
            'database': 'mysql',
            'key_patterns': {
                'order_no': 'DD + YYMMDDHHMMSS + 6位随机',
                'withdraw_no': 'WD + YYMMDDHHMMSS + 6位随机'
            }
        }

    def _get_applicable_contracts(self, task: Dict) -> Dict[str, Any]:
        """获取适用的契约"""
        contracts = {}
        implements = task.get('contracts', {}).get('implements', [])

        contracts_dir = self.harness_dir / 'contracts'
        for contract_name in implements:
            contract_file = contracts_dir / f'{contract_name}.json'
            if contract_file.exists():
                with open(contract_file, 'r', encoding='utf-8') as f:
                    contracts[contract_name] = json.load(f)

        return contracts

    def _get_previous_decisions(self, task: Dict) -> List[Dict]:
        """获取之前的设计决策"""
        return task.get('context', {}).get('decisions', [])

    def record_decision(self, task_id: str, decision: str, reason: str = '',
                        alternatives: List[str] = None, impact: List[str] = None):
        """记录设计决策"""
        task = self.storage.load_task(task_id)
        if not task:
            error(f"任务 {task_id} 不存在", file=sys.stderr)
            return False

        if 'context' not in task:
            task['context'] = {}

        if 'decisions' not in task['context']:
            task['context']['decisions'] = []

        decision_record = {
            'decision': decision,
            'reason': reason,
            'alternatives': alternatives or [],
            'impact': impact or [],
            'made_by': 'agent',
            'made_at': datetime.now().isoformat()
        }

        task['context']['decisions'].append(decision_record)
        self.storage.save_task(task)

        success(f"已记录决策: {decision}", file=sys.stderr)
        return True

    def record_gotcha(self, task_id: str, gotcha: str):
        """记录注意事项"""
        task = self.storage.load_task(task_id)
        if not task:
            return False

        if 'context' not in task:
            task['context'] = {}

        if 'gotchas' not in task['context']:
            task['context']['gotchas'] = []

        task['context']['gotchas'].append(gotcha)
        self.storage.save_task(task)

        return True

    def format_context_for_prompt(self, context: Dict) -> str:
        """格式化上下文为 Prompt 格式"""
        if not context:
            return ""

        lines = []
        lines.append("## 📚 任务上下文")
        lines.append("")

        # 依赖产出
        deps = context.get('dependencies', {})
        if deps.get('artifacts'):
            lines.append("### 依赖任务产出")
            for dep_id, files in deps['artifacts'].items():
                if files:
                    lines.append(f"\n**{dep_id}** 产出文件：")
                    for f in files:
                        lines.append(f"- {f}")
            lines.append("")

        # 设计决策
        decisions = deps.get('decisions', [])
        if decisions:
            lines.append("### 前置设计决策")
            for i, dec in enumerate(decisions[:5], 1):  # 最多显示5个
                lines.append(f"{i}. ✅ {dec.get('decision', '')}")
                if dec.get('reason'):
                    lines.append(f"   - 原因: {dec['reason']}")
            lines.append("")

        # 契约
        contracts = context.get('contracts', {})
        if contracts:
            lines.append("### 适用契约")
            for contract_name in contracts.keys():
                lines.append(f"- {contract_name}")
            lines.append("")

        return "\n".join(lines)


def check_dependencies(storage: TaskFileStorage, task: Dict) -> Dict[str, Any]:
    """检查任务依赖是否满足"""
    dependencies = task.get('depends_on', {})

    result = {
        'satisfied': True,
        'blocking_deps': [],
        'warnings': []
    }

    # 检查必需依赖
    for dep in dependencies.get('required', []):
        dep_task_id = dep['task_id'] if isinstance(dep, dict) else dep
        required_stage = dep.get('stage', 'dev') if isinstance(dep, dict) else 'dev'

        dep_task = storage.load_task(dep_task_id)
        if not dep_task:
            result['satisfied'] = False
            result['blocking_deps'].append({
                'task_id': dep_task_id,
                'reason': f"依赖任务不存在"
            })
            continue

        # 检查阶段是否完成
        stages = dep_task.get('stages', {})
        stage_info = stages.get(required_stage, {})
        if not stage_info.get('completed') and not dep_task.get('p', False):
            result['satisfied'] = False
            reason = dep.get('reason', '') if isinstance(dep, dict) else ''
            result['blocking_deps'].append({
                'task_id': dep_task_id,
                'stage': required_stage,
                'reason': reason
            })

    # 检查可选依赖（仅警告）
    for dep in dependencies.get('optional', []):
        dep_task_id = dep['task_id'] if isinstance(dep, dict) else dep
        dep_task = storage.load_task(dep_task_id)

        if not dep_task or not (dep_task.get('p', False) or
            all(dep_task.get('stages', {}).get(s, {}).get('completed')
                for s in ['dev', 'test', 'review'])):
            reason = dep.get('reason', '') if isinstance(dep, dict) else ''
            result['warnings'].append(
                f"可选依赖 {dep_task_id} 未完成" + (f": {reason}" if reason else "")
            )

    return result


def main():
    """主函数 - 用于命令行调用"""
    import argparse

    # 设置 UTF-8 编码（Windows 兼容）
    if sys.platform == 'win32':
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

    parser = argparse.ArgumentParser(description='上下文管理器')
    parser.add_argument('--task-id', required=True, help='任务ID')
    parser.add_argument('--stage', default='dev', help='当前阶段')
    parser.add_argument('--record-decision', help='记录设计决策')
    parser.add_argument('--reason', default='', help='决策原因')
    parser.add_argument('--format', action='store_true', help='输出格式化的上下文')

    args = parser.parse_args()

    manager = ContextManager()

    if args.record_decision:
        manager.record_decision(args.task_id, args.record_decision, args.reason)
        return

    if args.format:
        context = manager.build_agent_context(args.task_id, args.stage)
        prompt = manager.format_context_for_prompt(context)
        print(prompt)
        return

    # 默认：检查依赖
    storage = TaskFileStorage()
    storage.initialize()
    task = storage.load_task(args.task_id)

    if not task:
        error(f"任务 {args.task_id} 不存在", file=sys.stderr)
        sys.exit(1)

    result = check_dependencies(storage, task)

    if not result['satisfied']:
        error(f"\n依赖检查失败：", file=sys.stderr)
        for dep in result['blocking_deps']:
            error(f"  ❌ {dep['task_id']} ({dep.get('stage', 'dev')} 阶段未完成)", file=sys.stderr)
            if dep.get('reason'):
                info(f"     原因: {dep['reason']}", file=sys.stderr)
        sys.exit(1)

    if result['warnings']:
        warning("\n依赖警告：", file=sys.stderr)
        for w in result['warnings']:
            warning(f"  ⚠️  {w}", file=sys.stderr)

    success("\n✅ 依赖检查通过", file=sys.stderr)


if __name__ == '__main__':
    main()