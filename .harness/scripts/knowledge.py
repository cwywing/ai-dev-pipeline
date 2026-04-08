#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

"""
Knowledge Manager - 全局知识库管理
====================================

基于原 knowledge.py 重构，接入 Phase 1 基座。

核心职责：
- 管理接口契约 (contracts.json)
- 管理全局约束 (constraints.json)
- 从任务产出自动同步到知识库 (sync_task_artifacts)
- 查询服务契约

使用方式:
    from scripts.knowledge import KnowledgeManager

    km = KnowledgeManager()
    km.sync_task_artifacts("OrderService_001")

    # CLI
    python .harness/scripts/knowledge.py --action sync --task-id Model_001
    python .harness/scripts/knowledge.py --action list

====================================
"""

import sys
import json
from pathlib import Path
from datetime import datetime
from typing import Any, Optional


# 路径注入
_scripts_dir = Path(__file__).parent.resolve()
sys.path.insert(0, str(_scripts_dir.parent))    # .harness/
sys.path.insert(0, str(_scripts_dir))            # .harness/scripts/

from scripts.config import KNOWLEDGE_DIR
from scripts.logger import app_logger


# ========================================
#  KnowledgeManager
# ========================================

class KnowledgeManager:
    """全局知识库管理器"""

    def __init__(self):
        self.contracts_file = KNOWLEDGE_DIR / "contracts.json"
        self.constraints_file = KNOWLEDGE_DIR / "constraints.json"

    # --------------------------------------------------
    #  文件读写
    # --------------------------------------------------

    def _load_json(self, file_path: Path) -> dict:
        """加载 JSON 文件，不存在或损坏返回空字典"""
        if not file_path.exists():
            return {}
        try:
            return json.loads(file_path.read_text(encoding="utf-8"))
        except Exception as e:
            app_logger.warning(f"加载 {file_path.name} 失败: {e}")
            return {}

    def _save_json(self, file_path: Path, data: dict) -> bool:
        """原子写入 JSON（temp + rename）"""
        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            data["updated_at"] = datetime.now().isoformat()

            tmp = file_path.with_suffix(".tmp")
            tmp.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            tmp.replace(file_path)
            return True
        except Exception as e:
            app_logger.error(f"保存 {file_path.name} 失败: {e}")
            return False

    # --------------------------------------------------
    #  契约管理
    # --------------------------------------------------

    def add_contract(self, service: str, method: str = "",
                     returns: str = "", params: list = None,
                     throws: list = None, signature: str = "",
                     source_task: str = "") -> bool:
        """
        添加或更新接口契约

        Args:
            service: 服务名称（如 OrderService）
            method: 方法名（如 create）
            returns: 返回类型
            params: 参数列表
            throws: 异常列表
            signature: 完整签名（如 create(array $data): Order）
            source_task: 来源任务 ID
        """
        contracts = self._load_json(self.contracts_file)

        if "services" not in contracts:
            contracts["services"] = {}

        if service not in contracts["services"]:
            contracts["services"][service] = {
                "source_task": source_task,
                "methods": [],
            }
        elif source_task:
            contracts["services"][service]["source_task"] = source_task

        if not method:
            return self._save_json(self.contracts_file, contracts)

        # 去重：按 method 名查找已有条目
        svc = contracts["services"][service]
        existing = None
        for m in svc["methods"]:
            if m.get("name") == method:
                existing = m
                break

        method_entry = {
            "name": method,
            "params": params or [],
            "returns": returns or "mixed",
            "throws": throws or [],
        }
        if signature:
            method_entry["signature"] = signature

        if existing:
            existing.update(method_entry)
            app_logger.debug(f"契约更新: {service}.{method}")
        else:
            svc["methods"].append(method_entry)
            app_logger.debug(f"契约新增: {service}.{method}")

        return self._save_json(self.contracts_file, contracts)

    # --------------------------------------------------
    #  约束管理
    # --------------------------------------------------

    def add_constraint(self, content: str, scope: str = "global",
                       module: str = "") -> bool:
        """
        添加约束条件（自动去重）

        Args:
            content: 约束文本
            scope: "global" 或 "per_module"
            module: 模块名（仅 per_module 时使用）
        """
        constraints = self._load_json(self.constraints_file)

        if scope == "global":
            bucket = constraints.setdefault("global", [])
            if content not in bucket:
                bucket.append(content)
                app_logger.debug(f"全局约束新增: {content}")
                return self._save_json(self.constraints_file, constraints)
            return True  # 已存在，跳过

        elif scope == "per_module":
            if not module:
                return False
            by_task = constraints.setdefault("by_task", {})
            mod_bucket = by_task.setdefault(module, [])
            if content not in mod_bucket:
                mod_bucket.append(content)
                app_logger.debug(f"模块约束新增 [{module}]: {content}")
                return self._save_json(self.constraints_file, constraints)
            return True

        return False

    # --------------------------------------------------
    #  核心同步方法
    # --------------------------------------------------

    def sync_task_artifacts(self, task_id: str) -> dict:
        """
        从任务产出同步到知识库

        通过 TaskStorage 读取 artifacts 中的
        interface_contracts 和 constraints，
        合并写入知识库 JSON 文件。

        Args:
            task_id: 任务 ID

        Returns:
            {
                "contracts_synced": int,
                "constraints_synced": int,
                "contracts_skipped": int,
                "constraints_skipped": int,
            }
        """
        from scripts.task_storage import TaskStorage

        artifacts = TaskStorage().get_task_artifacts(task_id)
        result = {
            "contracts_synced": 0,
            "constraints_synced": 0,
            "contracts_skipped": 0,
            "constraints_skipped": 0,
        }

        # ── 同步接口契约 ──
        contracts_raw = artifacts.get("interface_contracts", [])
        for c in contracts_raw:
            if isinstance(c, str):
                # 纯字符串格式，无法结构化入库
                result["contracts_skipped"] += 1
                continue

            service = c.get("service", c.get("name", ""))
            method = c.get("method", "")
            if not service:
                result["contracts_skipped"] += 1
                continue

            ok = self.add_contract(
                service=service,
                method=method,
                returns=c.get("returns", c.get("return_type", "")),
                params=c.get("params", []),
                throws=c.get("throws", []),
                signature=c.get("signature", ""),
                source_task=task_id,
            )
            if ok:
                result["contracts_synced"] += 1
            else:
                result["contracts_skipped"] += 1

        # ── 同步约束条件 ──
        constraints_raw = artifacts.get("constraints", [])
        for c in constraints_raw:
            if isinstance(c, str):
                content = c
                scope = "global"
                module = ""
            elif isinstance(c, dict):
                content = c.get("description", c.get("rule", c.get("content", "")))
                scope = c.get("scope", "global")
                module = c.get("module", c.get("scope_name", ""))
            else:
                result["constraints_skipped"] += 1
                continue

            if not content:
                result["constraints_skipped"] += 1
                continue

            ok = self.add_constraint(content=content, scope=scope, module=module)
            if ok:
                result["constraints_synced"] += 1
            else:
                result["constraints_skipped"] += 1

        # 汇总日志
        total = (result["contracts_synced"] + result["constraints_synced"])
        if total > 0:
            app_logger.info(
                f"[Knowledge] {task_id} 同步完成: "
                f"契约 +{result['contracts_synced']}, "
                f"约束 +{result['constraints_synced']}"
            )
        else:
            app_logger.debug(f"[Knowledge] {task_id} 无新增知识条目")

        return result

    # --------------------------------------------------
    #  查询
    # --------------------------------------------------

    def query_service(self, service: str) -> Optional[dict]:
        """查询指定服务的契约"""
        contracts = self._load_json(self.contracts_file)
        svc = contracts.get("services", {}).get(service)
        return svc

    def list_all_services(self) -> list[str]:
        """列出所有已注册服务名"""
        contracts = self._load_json(self.contracts_file)
        return list(contracts.get("services", {}).keys())

    def list_all_constraints(self, scope: str = "global") -> list[str]:
        """列出约束"""
        constraints = self._load_json(self.constraints_file)
        if scope == "global":
            return constraints.get("global", [])
        # per_module: 聚合所有模块
        result = []
        for module, items in constraints.get("by_task", {}).items():
            for item in items:
                result.append(f"[{module}] {item}")
        return result


# ========================================
#  CLI 入口
# ========================================

def main():
    """命令行入口"""
    import argparse

    parser = argparse.ArgumentParser(
        description="全局知识库管理",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python .harness/scripts/knowledge.py --action sync --task-id Model_001
  python .harness/scripts/knowledge.py --action list
  python .harness/scripts/knowledge.py --action query --service OrderService
        """,
    )
    parser.add_argument(
        "--action", required=True,
        choices=["sync", "list", "query", "add-contract", "add-constraint"],
        help="操作类型",
    )
    parser.add_argument("--task-id", help="任务 ID (sync 用)")
    parser.add_argument("--service", help="服务名 (query/add-contract 用)")
    parser.add_argument("--method", help="方法名")
    parser.add_argument("--returns", help="返回类型")
    parser.add_argument("--params", nargs="+", help="参数列表")
    parser.add_argument("--scope", choices=["global", "per_module"], help="约束范围")
    parser.add_argument("--content", help="约束内容")
    parser.add_argument("--module", help="模块名")

    args = parser.parse_args()
    km = KnowledgeManager()

    if args.action == "sync":
        if not args.task_id:
            app_logger.error("sync 需要 --task-id")
            return 1
        result = km.sync_task_artifacts(args.task_id)
        print(f"Synced: contracts={result['contracts_synced']}, "
              f"constraints={result['constraints_synced']}")
        return 0

    elif args.action == "list":
        services = km.list_all_services()
        constraints = km.list_all_constraints()
        print(f"Services ({len(services)}):")
        for s in services:
            print(f"  - {s}")
        print(f"Global constraints ({len(constraints)}):")
        for c in constraints:
            print(f"  - {c}")
        return 0

    elif args.action == "query":
        if not args.service:
            app_logger.error("query 需要 --service")
            return 1
        svc = km.query_service(args.service)
        if svc:
            print(json.dumps(svc, indent=2, ensure_ascii=False))
        else:
            app_logger.warning(f"未找到服务: {args.service}")
        return 0

    elif args.action == "add-contract":
        if not args.service:
            app_logger.error("需要 --service")
            return 1
        km.add_contract(
            service=args.service,
            method=args.method,
            returns=args.returns,
            params=args.params,
        )
        return 0

    elif args.action == "add-constraint":
        if not args.content:
            app_logger.error("需要 --content")
            return 1
        km.add_constraint(
            content=args.content,
            scope=args.scope or "global",
            module=args.module,
        )
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
