#!/usr/bin/env python3
"""
Knowledge Manager - 全局知识库管理脚本

功能：
1. 管理接口契约 (contracts.json)
2. 管理全局约束 (constraints.json)
3. 从任务产出同步到知识库
4. 查询服务契约

使用示例：
    # 添加接口契约
    python3 .harness/scripts/knowledge.py --action add-contract \\
        --service UserService --method find --returns "User|null"

    # 添加全局约束
    python3 .harness/scripts/knowledge.py --action add-constraint \\
        --scope global --content "所有 API 必须使用 API Resource"

    # 查询服务契约
    python3 .harness/scripts/knowledge.py --action query --service UserService

    # 从任务产出同步到知识库
    python3 .harness/scripts/knowledge.py --action sync --task-id Model_001
"""

import sys
import argparse
import json
from pathlib import Path
from datetime import datetime

from console_output import success, error, warning, info


class KnowledgeManager:
    """全局知识库管理器"""

    def __init__(self, harness_dir: Path = None):
        if harness_dir is None:
            # 获取脚本所在目录的父目录（.harness）
            harness_dir = Path(__file__).resolve().parent.parent

        self.harness_dir = Path(harness_dir)
        self.knowledge_dir = self.harness_dir / 'knowledge'
        self.contracts_file = self.knowledge_dir / 'contracts.json'
        self.constraints_file = self.knowledge_dir / 'constraints.json'
        self.artifacts_dir = self.harness_dir / 'artifacts'

    def _load_json(self, file_path: Path) -> dict:
        """加载 JSON 文件"""
        if not file_path.exists():
            return {}
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            error(f"加载文件失败 {file_path}: {e}")
            return {}

    def _save_json(self, file_path: Path, data: dict):
        """保存 JSON 文件"""
        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            data['updated_at'] = datetime.now().isoformat()
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            error(f"保存文件失败 {file_path}: {e}")
            return False

    def add_contract(self, service: str, method: str = None, returns: str = None,
                     params: list = None, throws: list = None, file_path: str = None,
                     source_task: str = None):
        """
        添加接口契约

        Args:
            service: 服务名称
            method: 方法名
            returns: 返回类型
            params: 参数列表
            throws: 异常列表
            file_path: 文件路径
            source_task: 来源任务ID
        """
        contracts = self._load_json(self.contracts_file)

        if 'services' not in contracts:
            contracts['services'] = {}

        if service not in contracts['services']:
            contracts['services'][service] = {
                'file': file_path or '',
                'source_task': source_task or '',
                'methods': []
            }

        if file_path:
            contracts['services'][service]['file'] = file_path
        if source_task:
            contracts['services'][service]['source_task'] = source_task

        if method:
            # 检查方法是否已存在
            existing = None
            for m in contracts['services'][service]['methods']:
                if m['name'] == method:
                    existing = m
                    break

            method_info = {
                'name': method,
                'params': params or [],
                'returns': returns or 'mixed',
                'throws': throws or []
            }

            if existing:
                # 更新现有方法
                existing.update(method_info)
                info(f"已更新服务 {service} 的方法 {method}")
            else:
                # 添加新方法
                contracts['services'][service]['methods'].append(method_info)
                info(f"已添加服务 {service} 的方法 {method}")

        if self._save_json(self.contracts_file, contracts):
            success(f"契约已保存到 {self.contracts_file}")
            return True
        return False

    def add_constraint(self, scope: str, content: str, module: str = None):
        """
        添加约束条件

        Args:
            scope: 范围 (global/per_module)
            content: 约束内容
            module: 模块名（仅 scope=per_module 时需要）
        """
        constraints = self._load_json(self.constraints_file)

        if scope == 'global':
            if 'global' not in constraints:
                constraints['global'] = []
            if content not in constraints['global']:
                constraints['global'].append(content)
                info(f"已添加全局约束: {content}")
            else:
                warning(f"全局约束已存在: {content}")

        elif scope == 'per_module':
            if not module:
                error("per_module 范围需要指定 --module 参数")
                return False
            if 'per_module' not in constraints:
                constraints['per_module'] = {}
            if module not in constraints['per_module']:
                constraints['per_module'][module] = []
            if content not in constraints['per_module'][module]:
                constraints['per_module'][module].append(content)
                info(f"已添加模块 {module} 的约束: {content}")
            else:
                warning(f"模块 {module} 的约束已存在: {content}")

        if self._save_json(self.constraints_file, constraints):
            success(f"约束已保存到 {self.constraints_file}")
            return True
        return False

    def query(self, service: str = None, scope: str = None):
        """
        查询知识库

        Args:
            service: 服务名称
            scope: 约束范围 (global/per_module)
        """
        if service:
            contracts = self._load_json(self.contracts_file)
            if 'services' in contracts and service in contracts['services']:
                info(f"\n{'='*60}")
                info(f"服务: {service}")
                info(f"{'='*60}")
                svc = contracts['services'][service]
                if svc.get('file'):
                    info(f"文件: {svc['file']}")
                if svc.get('source_task'):
                    info(f"来源任务: {svc['source_task']}")
                info(f"\n方法列表:")
                for method in svc.get('methods', []):
                    params_str = ', '.join(method.get('params', []))
                    info(f"  - {method['name']}({params_str}) -> {method.get('returns', 'mixed')}")
                    if method.get('throws'):
                        info(f"    抛出: {', '.join(method['throws'])}")
                return True
            else:
                warning(f"未找到服务: {service}")
                return False

        if scope:
            constraints = self._load_json(self.constraints_file)
            if scope == 'global':
                info(f"\n全局约束:")
                for c in constraints.get('global', []):
                    info(f"  - {c}")
            elif scope == 'per_module':
                info(f"\n模块约束:")
                for module, cons in constraints.get('per_module', {}).items():
                    info(f"\n  [{module}]")
                    for c in cons:
                        info(f"    - {c}")
            return True

        # 无参数时显示所有服务
        contracts = self._load_json(self.contracts_file)
        info(f"\n已注册服务:")
        for svc_name in contracts.get('services', {}).keys():
            info(f"  - {svc_name}")
        return True

    def sync(self, task_id: str):
        """
        从任务产出同步到知识库

        Args:
            task_id: 任务ID
        """
        artifact_file = self.artifacts_dir / f'{task_id}.json'

        if not artifact_file.exists():
            warning(f"任务产出文件不存在: {artifact_file}")
            return False

        artifact = self._load_json(artifact_file)
        if not artifact:
            return False

        sync_count = 0

        # 同步接口契约
        contracts = artifact.get('interface_contracts', [])
        for contract in contracts:
            service = contract.get('service')
            method = contract.get('method')
            returns = contract.get('returns')
            params = contract.get('params', [])
            throws = contract.get('throws', [])

            if service and method:
                if self.add_contract(
                    service=service,
                    method=method,
                    returns=returns,
                    params=params,
                    throws=throws,
                    source_task=task_id
                ):
                    sync_count += 1

        # 同步约束条件
        task_constraints = artifact.get('constraints', [])
        for constraint in task_constraints:
            # 解析约束，尝试识别模块
            if self.add_constraint(scope='global', content=constraint):
                sync_count += 1

        if sync_count > 0:
            success(f"从任务 {task_id} 同步了 {sync_count} 条记录到知识库")
        else:
            info(f"任务 {task_id} 无需同步的契约或约束")

        return True

    def list_all(self):
        """列出所有知识库内容"""
        contracts = self._load_json(self.contracts_file)
        constraints = self._load_json(self.constraints_file)

        info(f"\n{'='*60}")
        info(f"知识库概览")
        info(f"{'='*60}")

        # 服务列表
        info(f"\n已注册服务 ({len(contracts.get('services', {}))} 个):")
        for svc_name, svc_data in contracts.get('services', {}).items():
            method_count = len(svc_data.get('methods', []))
            info(f"  - {svc_name} ({method_count} 个方法)")

        # API 响应格式
        info(f"\nAPI 响应格式:")
        for name, data in contracts.get('api_responses', {}).items():
            info(f"  - {name}")

        # 全局约束
        info(f"\n全局约束 ({len(constraints.get('global', []))} 条):")
        for c in constraints.get('global', []):
            info(f"  - {c}")

        # 模块约束
        if constraints.get('per_module'):
            info(f"\n模块约束:")
            for module, cons in constraints.get('per_module', {}).items():
                info(f"  [{module}] ({len(cons)} 条)")

        return True


def main():
    parser = argparse.ArgumentParser(
        description='全局知识库管理脚本',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  # 添加接口契约
  python3 .harness/scripts/knowledge.py --action add-contract \\
    --service UserService --method find --returns "User|null"

  # 添加全局约束
  python3 .harness/scripts/knowledge.py --action add-constraint \\
    --scope global --content "所有 API 必须使用 API Resource"

  # 查询服务
  python3 .harness/scripts/knowledge.py --action query --service UserService

  # 从任务同步
  python3 .harness/scripts/knowledge.py --action sync --task-id Model_001

  # 列出所有
  python3 .harness/scripts/knowledge.py --action list
        """
    )

    parser.add_argument('--action', required=True,
                        choices=['add-contract', 'add-constraint', 'query', 'sync', 'list'],
                        help='操作类型')

    # add-contract 参数
    parser.add_argument('--service', help='服务名称')
    parser.add_argument('--method', help='方法名')
    parser.add_argument('--returns', help='返回类型')
    parser.add_argument('--params', nargs='+', help='参数列表')
    parser.add_argument('--throws', nargs='+', help='异常列表')

    # add-constraint 参数
    parser.add_argument('--scope', choices=['global', 'per_module'],
                        help='约束范围')
    parser.add_argument('--content', help='约束内容')
    parser.add_argument('--module', help='模块名')

    # sync 参数
    parser.add_argument('--task-id', help='任务ID')

    args = parser.parse_args()

    manager = KnowledgeManager()

    if args.action == 'add-contract':
        if not args.service:
            error("add-contract 需要 --service 参数")
            return 1
        return 0 if manager.add_contract(
            service=args.service,
            method=args.method,
            returns=args.returns,
            params=args.params,
            throws=args.throws
        ) else 1

    elif args.action == 'add-constraint':
        if not args.scope or not args.content:
            error("add-constraint 需要 --scope 和 --content 参数")
            return 1
        return 0 if manager.add_constraint(
            scope=args.scope,
            content=args.content,
            module=args.module
        ) else 1

    elif args.action == 'query':
        return 0 if manager.query(service=args.service, scope=args.scope) else 1

    elif args.action == 'sync':
        if not args.task_id:
            error("sync 需要 --task-id 参数")
            return 1
        return 0 if manager.sync(task_id=args.task_id) else 1

    elif args.action == 'list':
        return 0 if manager.list_all() else 1

    return 0


if __name__ == '__main__':
    sys.exit(main())