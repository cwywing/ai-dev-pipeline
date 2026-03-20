#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
API Flow Test Script - 用户端 API 全流程测试
功能：按流程顺序调用所有用户端接口，自动处理 token 存储
用法：python api_flow_test.py [BASE_URL]
"""

import sys
import os
import json
import re
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Tuple

try:
    import requests
except ImportError:
    print("错误: 需要安装 requests 库")
    print("请运行: pip install requests")
    sys.exit(1)

# 配置输出编码（Windows 兼容）
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# 颜色定义
class Colors:
    RED = '\033[0;31m'
    GREEN = '\033[0;32m'
    YELLOW = '\033[1;33m'
    BLUE = '\033[0;34m'
    NC = '\033[0m'  # No Color

    @classmethod
    def disable(cls):
        """禁用颜色（Windows 兼容）"""
        cls.RED = ''
        cls.GREEN = ''
        cls.YELLOW = ''
        cls.BLUE = ''
        cls.NC = ''

# Windows 环境下禁用颜色和特殊字符
if sys.platform == 'win32':
    Colors.disable()


class APIFlowTest:
    """API 流程测试类"""

    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url.rstrip('/')
        self.token_file = ".harness/.api_token"
        self.token: Optional[str] = None
        self.pass_count = 0
        self.fail_count = 0
        self.address_id: Optional[int] = None
        self.order_id: Optional[int] = None

    def print_header(self, title: str):
        """打印标题"""
        print()
        print(f"{Colors.BLUE}{'=' * 63}{Colors.NC}")
        print(f"{Colors.BLUE}  {title}{Colors.NC}")
        print(f"{Colors.BLUE}{'=' * 63}{Colors.NC}")

    def print_test(self, method: str, endpoint: str, description: str):
        """打印测试信息"""
        print(f"\n{Colors.YELLOW}>> {method} {endpoint} - {description}{Colors.NC}")
        print(f"  URL: {self.base_url}{endpoint}")

    def print_result(self, success: bool, message: str):
        """打印测试结果"""
        if success:
            print(f"  {Colors.GREEN}[OK] {message}{Colors.NC}")
            self.pass_count += 1
        else:
            print(f"  {Colors.RED}[FAIL] {message}{Colors.NC}")
            self.fail_count += 1

    def print_detail(self, message: str, success: bool = True):
        """打印详细信息"""
        color = Colors.GREEN if success else Colors.YELLOW
        print(f"    {color}  - {message}{Colors.NC}")

    def save_token(self, token: str):
        """保存 token 到文件"""
        os.makedirs(os.path.dirname(self.token_file), exist_ok=True)
        with open(self.token_file, 'w') as f:
            f.write(token)
        print(f"  {Colors.GREEN}[OK] Token 已存储到 {self.token_file}{Colors.NC}")

    def load_token(self) -> Optional[str]:
        """从文件加载 token"""
        if os.path.exists(self.token_file):
            with open(self.token_file, 'r') as f:
                return f.read().strip()
        return None

    def get_headers(self, with_auth: bool = False) -> Dict[str, str]:
        """获取请求头"""
        headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/json'
        }
        if with_auth and self.token:
            headers['Authorization'] = f'Bearer {self.token}'
        return headers

    def http_get(self, endpoint: str, with_auth: bool = False) -> Tuple[int, Dict[str, Any]]:
        """发送 GET 请求"""
        url = f"{self.base_url}{endpoint}"
        try:
            response = requests.get(url, headers=self.get_headers(with_auth), timeout=10)
            try:
                body = response.json()
            except:
                body = {"raw": response.text}
            return response.status_code, body
        except requests.exceptions.RequestException as e:
            return 0, {"error": str(e)}

    def http_post(self, endpoint: str, data: Dict[str, Any], with_auth: bool = False) -> Tuple[int, Dict[str, Any]]:
        """发送 POST 请求"""
        url = f"{self.base_url}{endpoint}"
        try:
            response = requests.post(url, json=data, headers=self.get_headers(with_auth), timeout=10)
            try:
                body = response.json()
            except:
                body = {"raw": response.text}
            return response.status_code, body
        except requests.exceptions.RequestException as e:
            return 0, {"error": str(e)}

    def test_public_endpoints(self):
        """测试公共接口"""
        self.print_header("阶段 1: 公共接口测试")

        # 1.1 首页配置
        self.print_test("GET", "/api/v1/app/home/index", "首页配置")
        status, body = self.http_get("/api/v1/app/home/index")

        if status == 200:
            self.print_result(True, f"HTTP {status} - 首页配置获取成功")
            if 'data' in body and 'categories' in str(body):
                self.print_detail("返回数据包含 categories")
        else:
            self.print_result(False, f"HTTP {status} - 请求失败")

        # 1.2 预约时间段
        self.print_test("GET", "/api/v1/app/booking-days", "预约时间段")
        status, body = self.http_get("/api/v1/app/booking-days")

        if status == 200:
            self.print_result(True, f"HTTP {status} - 预约时间段获取成功")
            if 'data' in body and 'dateStr' in str(body):
                self.print_detail("返回数据包含预约日期")
        else:
            self.print_result(False, f"HTTP {status} - 请求失败")

    def test_auth_endpoints(self):
        """测试认证接口"""
        self.print_header("阶段 2: 认证接口测试")

        # 2.1 登录 (使用 platform=2 Alipay 测试模式)
        self.print_test("POST", "/api/v1/app/auth/login", "用户登录")
        login_data = {
            "code": "test_code_13111111111",
            "platform": 2  # 使用 Alipay 平台（有测试模式）
        }
        status, body = self.http_post("/api/v1/app/auth/login", login_data)

        if status == 200:
            self.print_result(True, f"HTTP {status} - 登录成功")
            # 提取 token
            if 'data' in body and 'token' in body.get('data', {}):
                self.token = body['data']['token']
                self.save_token(self.token)
        elif status == 422:
            self.print_result(False, f"HTTP {status} - 验证失败（可能需要真实登录凭证）")
            # 使用模拟 token 继续测试
            self.token = "mock_test_token_for_api_flow_test"
            self.save_token(self.token)
            print(f"  {Colors.YELLOW}[!] 使用模拟 token 继续测试{Colors.NC}")
        else:
            self.print_result(False, f"HTTP {status} - 登录失败")
            # 使用模拟 token 继续测试
            self.token = "mock_test_token_for_api_flow_test"
            self.save_token(self.token)
            print(f"  {Colors.YELLOW}[!] 使用模拟 token 继续测试{Colors.NC}")

        # 加载保存的 token
        if not self.token:
            self.token = self.load_token()

        if self.token:
            print(f"{Colors.GREEN}当前 Token: {self.token[:20]}...{Colors.NC}")
        else:
            print(f"{Colors.RED}错误: 无法获取 token，后续认证测试将失败{Colors.NC}")
            return False

        return True

    def test_address_endpoints(self):
        """测试地址接口"""
        self.print_header("阶段 3: 地址接口测试")

        # 3.1 地址列表
        self.print_test("GET", "/api/v1/app/address/list", "地址列表")
        status, body = self.http_get("/api/v1/app/address/list", with_auth=True)

        if status == 200:
            self.print_result(True, f"HTTP {status} - 地址列表获取成功")
            # 尝试从列表获取地址ID
            if 'data' in body:
                data = body['data']
                if isinstance(data, list) and len(data) > 0:
                    self.address_id = data[0].get('id')
                elif isinstance(data, dict) and 'list' in data:
                    items = data['list']
                    if isinstance(items, list) and len(items) > 0:
                        self.address_id = items[0].get('id')
        elif status == 401:
            self.print_result(False, f"HTTP {status} - 认证失败（token 无效）")
        else:
            self.print_result(False, f"HTTP {status} - 请求失败")

        # 3.2 保存地址
        self.print_test("POST", "/api/v1/app/address/save", "保存地址")
        address_data = {
            "name": "测试用户",
            "phone": "13800138000",
            "province": "广东省",
            "city_id": 440100,
            "city": "广州市",
            "district": "天河区",
            "detail": "天河路123号",
            "is_default": 1
        }
        status, body = self.http_post("/api/v1/app/address/save", address_data, with_auth=True)

        if status == 200:
            self.print_result(True, f"HTTP {status} - 地址保存成功")
            if 'data' in body and 'id' in body.get('data', {}):
                self.address_id = body['data']['id']
                self.print_detail(f"地址ID: {self.address_id}")
        elif status == 401:
            self.print_result(False, f"HTTP {status} - 认证失败")
        elif status == 422:
            self.print_result(False, f"HTTP {status} - 验证失败")
            if 'errors' in body:
                self.print_detail(f"错误: {body.get('errors')}", False)
        else:
            self.print_result(False, f"HTTP {status} - 请求失败")

    def test_order_endpoints(self):
        """测试订单接口"""
        self.print_header("阶段 4: 订单接口测试")

        # 4.1 提交订单
        self.print_test("POST", "/api/v1/app/order/submit", "提交订单")

        # 生成预约时间
        tomorrow = datetime.now() + timedelta(days=1)
        reserve_time = tomorrow.strftime("%Y-%m-%d") + " 08:00-11:00"

        # 如果没有地址ID，使用默认值
        address_id = self.address_id or 1

        order_data = {
            "address_id": address_id,
            "category_id": 1,
            "est_weight": "1-5kg",
            "reserve_time": reserve_time,
            "remark": "API流程测试订单"
        }
        status, body = self.http_post("/api/v1/app/order/submit", order_data, with_auth=True)

        if status == 200:
            self.print_result(True, f"HTTP {status} - 订单提交成功")
            if 'data' in body and 'order_id' in body.get('data', {}):
                self.order_id = body['data']['order_id']
                self.print_detail(f"订单ID: {self.order_id}")
        elif status == 401:
            self.print_result(False, f"HTTP {status} - 认证失败")
        elif status == 422:
            self.print_result(False, f"HTTP {status} - 验证失败")
            if 'errors' in body:
                self.print_detail(f"错误: {body.get('errors')}", False)
        else:
            self.print_result(False, f"HTTP {status} - 请求失败")

        # 4.2 订单列表
        self.print_test("GET", "/api/v1/app/order/list", "订单列表")
        status, body = self.http_get("/api/v1/app/order/list", with_auth=True)

        if status == 200:
            self.print_result(True, f"HTTP {status} - 订单列表获取成功")
            # 尝试从列表获取订单ID
            if not self.order_id and 'data' in body:
                data = body['data']
                if isinstance(data, dict) and 'list' in data:
                    items = data['list']
                    if isinstance(items, list) and len(items) > 0:
                        self.order_id = items[0].get('id')
                        if self.order_id:
                            self.print_detail(f"从列表获取订单ID: {self.order_id}")
        elif status == 401:
            self.print_result(False, f"HTTP {status} - 认证失败")
        else:
            self.print_result(False, f"HTTP {status} - 请求失败")

    def test_user_endpoints(self):
        """测试用户接口"""
        self.print_header("阶段 5: 用户接口测试")

        # 5.1 用户信息
        self.print_test("GET", "/api/v1/app/user/info", "用户信息")
        status, body = self.http_get("/api/v1/app/user/info", with_auth=True)

        if status == 200:
            self.print_result(True, f"HTTP {status} - 用户信息获取成功")
            if 'data' in body and 'balance' in str(body):
                self.print_detail("返回数据包含用户余额")
        elif status == 401:
            self.print_result(False, f"HTTP {status} - 认证失败")
        else:
            self.print_result(False, f"HTTP {status} - 请求失败")

        # 5.2 余额流水
        self.print_test("GET", "/api/v1/app/user/bill_list", "余额流水")
        status, body = self.http_get("/api/v1/app/user/bill_list", with_auth=True)

        if status == 200:
            self.print_result(True, f"HTTP {status} - 余额流水获取成功")
        elif status == 401:
            self.print_result(False, f"HTTP {status} - 认证失败")
        else:
            self.print_result(False, f"HTTP {status} - 请求失败")

    def test_share_endpoints(self):
        """测试助力接口"""
        self.print_header("阶段 6: 助力接口测试")

        # 6.1 助力访问
        self.print_test("POST", "/api/v1/app/share/visit", "助力访问")

        # 如果没有订单ID，使用默认值
        order_id = self.order_id or 1

        share_data = {"order_id": order_id}
        status, body = self.http_post("/api/v1/app/share/visit", share_data, with_auth=True)

        if status == 200:
            self.print_result(True, f"HTTP {status} - 助力访问成功")
        elif status == 401:
            self.print_result(False, f"HTTP {status} - 认证失败")
        elif status == 422:
            self.print_result(False, f"HTTP {status} - 验证失败（订单可能不存在）")
        else:
            self.print_result(False, f"HTTP {status} - 请求失败")

    def print_summary(self):
        """打印测试总结"""
        self.print_header("测试结果汇总")

        total = self.pass_count + self.fail_count
        print()
        print(f"{Colors.BLUE}总计测试: {total}{Colors.NC}")
        print(f"{Colors.GREEN}通过: {self.pass_count}{Colors.NC}")
        print(f"{Colors.RED}失败: {self.fail_count}{Colors.NC}")
        print()

        if self.fail_count == 0:
            print(f"{Colors.GREEN}[OK] 所有测试通过！{Colors.NC}")
            return 0
        else:
            print(f"{Colors.YELLOW}[!] 部分测试失败，请检查日志{Colors.NC}")
            return 1

    def run(self):
        """运行所有测试"""
        self.print_header("API 全流程测试")

        print(f"{Colors.BLUE}测试环境:{Colors.NC} {self.base_url}")
        print(f"{Colors.BLUE}Token 文件:{Colors.NC} {self.token_file}")
        print()

        # 按顺序执行测试
        self.test_public_endpoints()

        if not self.test_auth_endpoints():
            # 如果认证失败，仍然继续测试其他端点（可能会失败）
            pass

        self.test_address_endpoints()
        self.test_order_endpoints()
        self.test_user_endpoints()
        self.test_share_endpoints()

        # 打印总结
        return self.print_summary()


def main():
    """主函数"""
    # 获取基础 URL
    base_url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"

    # 创建测试实例并运行
    tester = APIFlowTest(base_url)
    exit_code = tester.run()

    sys.exit(exit_code)


if __name__ == "__main__":
    main()