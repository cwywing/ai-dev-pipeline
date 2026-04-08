#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

"""
API 全流程测试
====================================

替代原有 api_flow_test.sh，使用 Python requests 库实现。

功能：
- 读取知识库中的 API 契约和标准
- 对指定 Base URL 执行全流程测试
- 支持 Bearer Token 认证
- 输出结构化测试报告

使用方式:
    # 基本用法
    python .harness/scripts/api_flow_test.py http://localhost:8000

    # 带 Token
    python .harness/scripts/api_flow_test.py http://localhost:8000 \
        --token "Bearer xxx"

    # 指定超时
    python .harness/scripts/api_flow_test.py http://localhost:8000 \
        --timeout 10

====================================
"""

import json
import os
import sys
import argparse
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime


# 路径注入
_scripts_dir = Path(__file__).parent.resolve()
sys.path.insert(0, str(_scripts_dir.parent))    # .harness/
sys.path.insert(0, str(_scripts_dir))            # .harness/scripts/

from scripts.config import HARNESS_DIR, KNOWLEDGE_DIR
from scripts.logger import app_logger


# ========================================
#  配置
# ========================================

DEFAULT_TIMEOUT = 15  # 秒
DEFAULT_HEADERS = {
    "Accept": "application/json",
    "Content-Type": "application/json",
}

# 预定义的通用健康检查端点
HEALTH_ENDPOINTS = ["/", "/api", "/health", "/api/health", "/ping"]


# ========================================
#  测试结果数据结构
# ========================================

class TestResult:
    """单个接口测试结果"""

    def __init__(self, endpoint: str, method: str = "GET"):
        self.endpoint = endpoint
        self.method = method
        self.status_code: Optional[int] = None
        self.response_time: float = 0.0
        self.success: bool = False
        self.error: str = ""
        self.response_body: Any = None
        self.expected_status: Optional[int] = None

    def to_dict(self) -> dict:
        return {
            "endpoint": self.endpoint,
            "method": self.method,
            "status_code": self.status_code,
            "response_time_ms": round(self.response_time * 1000, 1),
            "success": self.success,
            "error": self.error,
            "expected_status": self.expected_status,
        }


# ========================================
#  核心测试引擎
# ========================================

class APIFlowTester:
    """API 全流程测试器"""

    def __init__(self, base_url: str, token: str = "",
                 timeout: int = DEFAULT_TIMEOUT):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.results: List[TestResult] = []

        # 构建 headers
        self.headers = dict(DEFAULT_HEADERS)
        if token:
            self.headers["Authorization"] = token

        # 加载知识库
        self.contracts = self._load_json(KNOWLEDGE_DIR / "contracts.json")
        self.constraints = self._load_json(KNOWLEDGE_DIR / "constraints.json")
        self.api_standards = self._load_json(
            KNOWLEDGE_DIR / "api_standards.json"
        )

    def run_all(self) -> dict:
        """执行全流程测试"""
        app_logger.info(f"API 全流程测试开始: {self.base_url}")

        # 1. 健康检查
        app_logger.info("[1/4] 执行健康检查...")
        self._check_health()

        # 2. 基于 API 标准的通用测试
        if self.api_standards:
            app_logger.info("[2/4] 执行 API 标准测试...")
            self._test_api_standards()
        else:
            app_logger.info("[2/4] 跳过 API 标准测试（无 api_standards.json）")

        # 3. 基于契约的接口测试
        if self.contracts:
            app_logger.info("[3/4] 执行契约接口测试...")
            self._test_contracts()
        else:
            app_logger.info("[3/4] 跳过契约测试（无 contracts.json）")

        # 4. 基于约束的验证
        if self.constraints:
            app_logger.info("[4/4] 执行约束验证...")
            self._test_constraints()
        else:
            app_logger.info("[4/4] 跳过约束验证（无 constraints.json）")

        # 汇总报告
        return self._generate_report()

    def _check_health(self) -> None:
        """健康检查：尝试常见端点"""
        for endpoint in HEALTH_ENDPOINTS:
            result = self._request(endpoint)
            if result.success:
                app_logger.success(
                    f"  健康检查通过: {endpoint} "
                    f"({result.status_code}, "
                    f"{result.response_time * 1000:.0f}ms)"
                )
                return

        app_logger.warning("  健康检查: 所有端点均无响应")

    def _test_api_standards(self) -> None:
        """基于 API 标准的测试"""
        standards = self.api_standards
        if not isinstance(standards, dict):
            return

        # 测试标准中定义的接口
        endpoints = standards.get("endpoints", [])
        for ep in endpoints:
            if isinstance(ep, str):
                result = self._request(ep)
                self.results.append(result)
                self._log_result(result)
            elif isinstance(ep, dict):
                method = ep.get("method", "GET").upper()
                path = ep.get("path", ep.get("endpoint", ""))
                expected = ep.get("expected_status", 200)
                result = self._request(path, method=method,
                                       expected_status=expected)
                self.results.append(result)
                self._log_result(result)

    def _test_contracts(self) -> None:
        """基于 Service 契约的接口测试"""
        contracts = self.contracts
        if not isinstance(contracts, dict):
            return

        # 遍历契约中定义的接口
        for service_name, service_data in contracts.items():
            if not isinstance(service_data, dict):
                continue

            endpoints = service_data.get("endpoints", [])
            for ep in endpoints:
                if not isinstance(ep, dict):
                    continue

                method = ep.get("method", "GET").upper()
                path = ep.get("path", "")
                expected = ep.get("expected_status", 200)

                if not path:
                    continue

                result = self._request(path, method=method,
                                       expected_status=expected)
                result.endpoint = f"[{service_name}] {path}"
                self.results.append(result)
                self._log_result(result)

    def _test_constraints(self) -> None:
        """基于全局约束的响应验证"""
        constraints = self.constraints
        if not isinstance(constraints, dict):
            return

        # 获取需要测试的 URL 列表
        test_urls = constraints.get("test_urls", [])
        if not test_urls:
            # 从已有结果中提取成功的端点进行约束验证
            test_urls = [
                r.endpoint for r in self.results if r.success
            ]

        for url in test_urls:
            if isinstance(url, str) and url.startswith("/"):
                result = self._request(url)
                if result.success and result.response_body:
                    self._validate_constraints(
                        result.response_body, constraints
                    )

    def _validate_constraints(self, body: Any,
                              constraints: dict) -> None:
        """验证响应体是否满足约束"""
        rules = constraints.get("response_rules", [])
        for rule in rules:
            if not isinstance(rule, dict):
                continue

            field = rule.get("field", "")
            rule_type = rule.get("type", "")
            description = rule.get("description", "")

            # 从响应体中提取字段值
            value = self._extract_field(body, field)
            if value is None:
                app_logger.warning(
                    f"  约束验证: 字段 '{field}' 不存在 "
                    f"({description})"
                )
                continue

            # 类型检查
            if rule_type == "integer" and not isinstance(value, int):
                app_logger.error(
                    f"  约束失败: '{field}' 应为整数，"
                    f"实际为 {type(value).__name__}"
                )
            elif rule_type == "string" and not isinstance(value, str):
                app_logger.error(
                    f"  约束失败: '{field}' 应为字符串，"
                    f"实际为 {type(value).__name__}"
                )
            elif rule_type == "array" and not isinstance(value, list):
                app_logger.error(
                    f"  约束失败: '{field}' 应为数组，"
                    f"实际为 {type(value).__name__}"
                )

    @staticmethod
    def _extract_field(body: Any, field: str) -> Any:
        """从嵌套结构中提取字段值（支持 dot notation）"""
        parts = field.split(".")
        current = body
        for part in parts:
            if isinstance(current, dict):
                current = current.get(part)
            else:
                return None
            if current is None:
                return None
        return current

    def _request(self, path: str, method: str = "GET",
                 expected_status: int = 200) -> TestResult:
        """执行 HTTP 请求"""
        result = TestResult(path, method)
        result.expected_status = expected_status

        url = f"{self.base_url}{path}"

        try:
            import requests

            start = datetime.now()
            try:
                resp = requests.request(
                    method, url,
                    headers=self.headers,
                    timeout=self.timeout,
                )
            except requests.exceptions.Timeout:
                result.error = "请求超时"
                app_logger.warning(f"  超时: {method} {path}")
                return result
            except requests.exceptions.ConnectionError:
                result.error = "连接失败"
                return result

            elapsed = (datetime.now() - start).total_seconds()
            result.response_time = elapsed
            result.status_code = resp.status_code

            # 解析响应
            try:
                result.response_body = resp.json()
            except (json.JSONDecodeError, ValueError):
                result.response_body = resp.text[:500]

            result.success = (resp.status_code == expected_status)

            if not result.success:
                result.error = (
                    f"期望 {expected_status}，"
                    f"实际 {resp.status_code}"
                )

        except ImportError:
            result.error = "requests 库未安装 (pip install requests)"
            app_logger.error(result.error)

        return result

    def _log_result(self, result: TestResult) -> None:
        """输出单个结果"""
        if result.success:
            app_logger.success(
                f"  {result.method} {result.endpoint} -> "
                f"{result.status_code} "
                f"({result.response_time * 1000:.0f}ms)"
            )
        else:
            app_logger.error(
                f"  {result.method} {result.endpoint} -> "
                f"{result.error or 'FAIL'}"
            )

    def _generate_report(self) -> dict:
        """生成测试报告"""
        total = len(self.results)
        passed = sum(1 for r in self.results if r.success)
        failed = total - passed

        report = {
            "base_url": self.base_url,
            "timestamp": datetime.now().isoformat(),
            "total": total,
            "passed": passed,
            "failed": failed,
            "pass_rate": round(passed / total * 100, 1) if total else 0,
            "results": [r.to_dict() for r in self.results],
        }

        # 输出摘要
        print("\n" + "=" * 60)
        print(f"API 全流程测试报告")
        print("=" * 60)
        print(f"  Base URL:  {self.base_url}")
        print(f"  总计:      {total} 个接口")
        print(f"  通过:      {passed}")
        print(f"  失败:      {failed}")
        print(f"  通过率:    {report['pass_rate']}%")
        print("=" * 60 + "\n")

        # 保存报告
        report_dir = HARNESS_DIR / "reports"
        report_dir.mkdir(parents=True, exist_ok=True)
        report_file = report_dir / f"api_test_{datetime.now():%Y%m%d_%H%M%S}.json"
        report_file.write_text(
            json.dumps(report, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        app_logger.info(f"报告已保存: {report_file}")

        return report

    @staticmethod
    def _load_json(path: Path) -> Optional[dict]:
        """加载 JSON 文件"""
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            app_logger.warning(f"加载 {path.name} 失败: {e}")
            return None


# ========================================
#  CLI 入口
# ========================================

def main():
    parser = argparse.ArgumentParser(
        description="API 全流程测试",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python .harness/scripts/api_flow_test.py http://localhost:8000
  python .harness/scripts/api_flow_test.py http://localhost:8000 --token "Bearer xxx"
  python .harness/scripts/api_flow_test.py http://localhost:8000 --timeout 10
        """,
    )
    parser.add_argument(
        "base_url",
        help="API Base URL (e.g. http://localhost:8000)",
    )
    parser.add_argument(
        "--token", "-t",
        default=os.getenv("API_TEST_TOKEN", ""),
        help="Bearer Token (或设置 API_TEST_TOKEN 环境变量)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT,
        help=f"请求超时秒数 (默认 {DEFAULT_TIMEOUT})",
    )

    args = parser.parse_args()

    tester = APIFlowTester(
        base_url=args.base_url,
        token=args.token,
        timeout=args.timeout,
    )
    report = tester.run_all()

    # 退出码：全部通过返回 0
    sys.exit(0 if report["failed"] == 0 else 1)


if __name__ == "__main__":
    main()
