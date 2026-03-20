#!/usr/bin/env python3
"""
代码规范自动检查脚本

检测 ThinkPHP 8 项目中的常见代码规范问题：
1. 路由顺序问题 (:id 覆盖具体路由)
2. 时间字段命名问题 (应使用 created_at/updated_at/deleted_at)
3. user_id 类型问题
4. 分层违规 (Controller 直接调用 Model/Repository)

使用示例：
    python3 .harness/scripts/check_code_standards.py
    python3 .harness/scripts/check_code_standards.py --path app/
    python3 .harness/scripts/check_code_standards.py --fix
"""

import argparse
import re
import sys
import os
from pathlib import Path
from typing import List, Dict, Tuple

# 颜色输出
class Colors:
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    END = '\033[0m'

def print_error(msg):
    print(f"{Colors.RED}[ERROR]{Colors.END} {msg}")

def print_warning(msg):
    print(f"{Colors.YELLOW}[WARN]{Colors.END} {msg}")

def print_info(msg):
    print(f"{Colors.BLUE}[INFO]{Colors.END} {msg}")

def print_success(msg):
    print(f"{Colors.GREEN}[OK]{Colors.END} {msg}")


class CodeStandardsChecker:
    """代码规范检查器"""

    def __init__(self, base_path: str = '.'):
        self.base_path = Path(base_path)
        self.issues: List[Dict] = []
        self.stats = {
            'route_issues': 0,
            'time_field_issues': 0,
            'user_id_issues': 0,
            'layer_violations': 0,
        }

    def check_all(self) -> int:
        """执行所有检查"""
        print_info("开始代码规范检查...")
        print()

        self.check_route_order()
        self.check_time_field_naming()
        self.check_user_id_type()
        self.check_layer_violations()

        self.print_summary()
        return len(self.issues)

    def add_issue(self, category: str, file: str, line: int, message: str, code_snippet: str = ""):
        """添加问题"""
        self.issues.append({
            'category': category,
            'file': file,
            'line': line,
            'message': message,
            'code': code_snippet
        })
        if category == 'route':
            self.stats['route_issues'] += 1
        elif category == 'time_field':
            self.stats['time_field_issues'] += 1
        elif category == 'user_id':
            self.stats['user_id_issues'] += 1
        elif category == 'layer_violation':
            self.stats['layer_violations'] += 1

    def check_route_order(self):
        """检查路由顺序问题 - :id 覆盖具体路由"""
        print_info("检查路由顺序问题...")

        route_file = self.base_path / 'route' / 'app.php'
        if not route_file.exists():
            print_warning(f"路由文件不存在: {route_file}")
            return

        content = route_file.read_text(encoding='utf-8')

        # 提取所有路由定义（带嵌套组信息）
        routes = self.extract_routes_with_nesting(content)

        # 检查 :id 参数路由是否覆盖了更具体的路由
        issues = self.detect_route_order_issues(routes)

        if issues:
            for issue in issues:
                self.add_issue('route', 'route/app.php', issue['line'], issue['message'], issue.get('code', ''))
        else:
            print_success("路由顺序检查通过")

    def extract_routes_with_nesting(self, content: str) -> List[Dict]:
        """提取路由定义并保留嵌套组信息"""
        routes = []
        lines = content.split('\n')
        group_stack = []  # 栈结构追踪嵌套组

        for i, line in enumerate(lines, 1):
            # 检测 Route::group 开始（通过函数调用和大括号）
            # 匹配: Route::group('prefix', function () {
            group_match = re.search(r"Route::group\s*\(['\"]([^'\"]+)['\"]", line)
            if group_match:
                group_stack.append({
                    'name': group_match.group(1),
                    'line': i
                })

            # 检测大括号闭合（组结束）
            open_braces = line.count('{')
            close_braces = line.count('}')

            # 如果在 Route::group 行，不处理闭合（因为组刚开始）
            if group_match:
                open_braces -= 1

            # 弹出结束的组
            for _ in range(close_braces - open_braces):
                if group_stack:
                    group_stack.pop()

            # 提取路由定义
            match = re.search(r"Route::(\w+)\(['\"]([^'\"]+)['\"]", line)
            if match:
                method = match.group(1)
                path = match.group(2)
                routes.append({
                    'line': i,
                    'method': method,
                    'path': path,
                    'group_path': '/'.join([g['name'] for g in group_stack]),  # 完整组路径
                    'raw': line.strip()
                })

        return routes

    def detect_route_order_issues(self, routes: List[Dict]) -> List[Dict]:
        """检测路由顺序问题"""
        issues = []

        # 按 (group_path, method) 分组
        route_groups = {}
        for route in routes:
            key = (route['group_path'], route['method'])
            if key not in route_groups:
                route_groups[key] = []
            route_groups[key].append(route)

        # 检查每个组内的路由顺序
        for (group_path, method), group_routes in route_groups.items():
            # 按行号排序
            group_routes.sort(key=lambda x: x['line'])

            for i, route in enumerate(group_routes):
                # 检查是否是参数路由（:id, :cate_id 等）
                if re.search(r':\w+', route['path']):
                    # 提取参数路由的前缀（去掉参数部分）
                    # 例如: 'category/:cate_id' -> 'category/'
                    # 例如: ':id' -> ''
                    param_pattern = re.sub(r':\w+', '', route['path']).rstrip('/')

                    # 检查后面是否有更具体的路由被覆盖
                    for j in range(i + 1, len(group_routes)):
                        later_route = group_routes[j]

                        # 检查是否是具体路由（不包含参数）
                        if not re.search(r':\w+', later_route['path']):
                            # 检查是否会被参数路由覆盖
                            # 情况1: 参数路由有前缀，后面的路由以相同前缀开头
                            # 例如: 'category/:cate_id' 会覆盖 'category/special'
                            if param_pattern and later_route['path'].startswith(param_pattern + '/'):
                                issues.append({
                                    'line': route['line'],
                                    'message': f"参数路由 '{route['path']}' 会覆盖后面的具体路由 '{later_route['path']}'，应将具体路由定义在前",
                                    'code': route['raw']
                                })

                            # 情况2: 参数路由没有前缀（如 ':id'），后面的任何具体路由都会被覆盖
                            # 例如: ':id' 会覆盖 'search', 'stats' 等
                            if not param_pattern:
                                issues.append({
                                    'line': route['line'],
                                    'message': f"参数路由 '{route['path']}' 会覆盖后面的具体路由 '{later_route['path']}'，应将具体路由 '{later_route['path']}' 定义在 '{route['path']}' 之前",
                                    'code': route['raw']
                                })

        return issues

    def get_route_context(self, routes: List[Dict], line: int) -> str:
        """获取路由所在的上下文（组信息）- 保留用于兼容"""
        context_lines = []
        for route in routes:
            if route['line'] < line:
                context_lines.append(route)
        return '\n'.join([r['raw'] for r in context_lines])

    def check_time_field_naming(self):
        """检查时间字段命名问题"""
        print_info("检查时间字段命名...")

        model_files = list(self.base_path.glob('app/models/*.php'))

        if not model_files:
            print_warning("未找到模型文件")
            return

        issues_found = False
        for model_file in model_files:
            content = model_file.read_text(encoding='utf-8')
            lines = content.split('\n')

            for i, line in enumerate(lines, 1):
                # 项目规范: created_at, updated_at, deleted_at (业界通用惯例)
                # 错误命名: create_time, update_time, delete_time (ThinkPHP默认但本项目不采用)

                # 检查是否使用了 ThinkPHP 默认命名而非项目规范
                if re.search(r'\$createTime\s*=\s*[\'"]create_time[\'"]', line):
                    self.add_issue(
                        'time_field',
                        str(model_file.relative_to(self.base_path)),
                        i,
                        f"时间字段配置不符合项目规范: \$createTime 应为 'created_at' 而非 'create_time'",
                        line.strip()
                    )
                    issues_found = True

                if re.search(r'\$updateTime\s*=\s*[\'"]update_time[\'"]', line):
                    self.add_issue(
                        'time_field',
                        str(model_file.relative_to(self.base_path)),
                        i,
                        f"时间字段配置不符合项目规范: \$updateTime 应为 'updated_at' 而非 'update_time'",
                        line.strip()
                    )
                    issues_found = True

                if re.search(r'\$deleteTime\s*=\s*[\'"]delete_time[\'"]', line):
                    self.add_issue(
                        'time_field',
                        str(model_file.relative_to(self.base_path)),
                        i,
                        f"时间字段配置不符合项目规范: \$deleteTime 应为 'deleted_at' 而非 'delete_time'",
                        line.strip()
                    )
                    issues_found = True

        if not issues_found:
            print_success("时间字段命名检查通过")

    def check_user_id_type(self):
        """检查 user_id 类型问题"""
        print_info("检查 user_id 类型问题...")

        # 检查所有 PHP 文件
        php_files = list(self.base_path.glob('app/**/*.php'))

        issues_found = False
        for php_file in php_files:
            content = php_file.read_text(encoding='utf-8')
            lines = content.split('\n')

            for i, line in enumerate(lines, 1):
                # 检查 user_id 相关的类型问题

                # 检查 user_id 与字符串比较 (常见问题: === "1" 而不是 === 1)
                if 'user_id' in line and re.search(r'user_id\s*(===|==|!==|!=)\s*["\']', line):
                    self.add_issue(
                        'user_id',
                        str(php_file.relative_to(self.base_path)),
                        i,
                        f"user_id 类型问题: 避免与字符串直接比较",
                        line.strip()
                    )
                    issues_found = True

                # 检查 user_id 作为字符串类型的使用
                if 'user_id' in line and re.search(r'\$user_id\s*=\s*["\']', line):
                    # 可能是字符串赋值，检查是否有 intval 或 (int) 转换
                    prev_lines = '\n'.join(lines[max(0, i-3):i+1])
                    if 'intval' not in prev_lines and '(int)' not in prev_lines:
                        self.add_issue(
                            'user_id',
                            str(php_file.relative_to(self.base_path)),
                            i,
                            f"user_id 可能是字符串类型，应转换为整数",
                            line.strip()
                        )
                        issues_found = True

        if not issues_found:
            print_success("user_id 类型检查通过")

    def check_layer_violations(self):
        """检查分层违规 - Controller 直接调用 Model/Repository"""
        print_info("检查分层违规 (Controller 直接调用 Model/Repository)...")

        controller_files = list(self.base_path.glob('app/controller/**/*.php'))

        if not controller_files:
            print_warning("未找到控制器文件")
            return

        issues_found = False
        for controller_file in controller_files:
            content = controller_file.read_text(encoding='utf-8')
            lines = content.split('\n')

            # 检查是否直接使用了 Model:: 或 Repository::
            for i, line in enumerate(lines, 1):
                # 跳过注释
                if re.match(r'^\s*//', line) or re.match(r'^\s*/\*', line):
                    continue

                # 检查 use 语句（这是允许的）
                if re.match(r'^\s*use\s+', line):
                    continue

                # 检查是否在方法内直接调用 Model
                # 例如: User::where(...), Role::find(...), etc.
                model_match = re.search(r'(\w+)::(where|find|select|create|save|delete|field|count|sum|avg|max|min|paginate|with|all|first)', line)
                if model_match:
                    model_name = model_match.group(1)
                    method_name = model_match.group(2)

                    # 检查是否是模型（首字母大写）
                    if model_name[0].isupper() and model_name not in ['Route', 'Request', 'Response', 'Validate', 'Db', 'Cache']:
                        # 检查是否在 use 语句中导入
                        if not self.is_model_imported(content, model_name):
                            self.add_issue(
                                'layer_violation',
                                str(controller_file.relative_to(self.base_path)),
                                i,
                                f"分层违规: Controller 直接调用 Model ({model_name}::{method_name}())，应通过 Service 层",
                                line.strip()
                            )
                            issues_found = True

                # 检查是否直接调用 Repository
                repo_match = re.search(r'\$this->(\w+Repository|\w+Repo)->', line)
                if repo_match:
                    # 这种情况实际上是允许的（通过依赖注入）
                    pass

                # 检查是否直接实例化 Repository
                if re.search(r'new\s+(\w+Repository|\w+Repo)\s*\(', line):
                    # 检查 use 语句
                    if not self.is_repo_imported(content, line):
                        self.add_issue(
                            'layer_violation',
                            str(controller_file.relative_to(self.base_path)),
                            i,
                            f"分层违规: Controller 直接实例化 Repository，应通过 Service 层",
                            line.strip()
                        )
                        issues_found = True

                # 检查是否直接使用 DB::
                if re.search(r'Db::', line):
                    self.add_issue(
                        'layer_violation',
                        str(controller_file.relative_to(self.base_path)),
                        i,
                        f"分层违规: Controller 直接使用 Db 类，应通过 Repository 层",
                        line.strip()
                    )
                    issues_found = True

        if not issues_found:
            print_success("分层违规检查通过")

    def is_model_imported(self, content: str, model_name: str) -> bool:
        """检查模型是否通过 use 语句导入"""
        use_pattern = r'^\s*use\s+.*\\' + model_name + r'\s*;'
        return bool(re.search(use_pattern, content, re.MULTILINE))

    def is_repo_imported(self, content: str, line: str) -> bool:
        """检查 Repository 是否通过 use 语句导入"""
        # 提取类名
        match = re.search(r'new\s+(\w+Repository|\w+Repo)\s*\(', line)
        if match:
            repo_name = match.group(1)
            use_pattern = r'^\s*use\s+.*\\' + repo_name + r'\s*;'
            return bool(re.search(use_pattern, content, re.MULTILINE))
        return False

    def print_summary(self):
        """打印检查摘要"""
        print()
        print("=" * 60)
        print("代码规范检查结果")
        print("=" * 60)

        if not self.issues:
            print_success("所有检查通过！未发现问题")
            return

        print_error(f"发现 {len(self.issues)} 个问题")
        print()

        # 按类别分组显示
        categories = {
            'route': '路由顺序问题',
            'time_field': '时间字段命名问题',
            'user_id': 'user_id 类型问题',
            'layer_violation': '分层违规问题',
        }

        for cat_key, cat_name in categories.items():
            cat_issues = [i for i in self.issues if i['category'] == cat_key]
            if cat_issues:
                print(f"\n{Colors.YELLOW}{cat_name} ({len(cat_issues)} 个){Colors.END}")
                print("-" * 50)
                for issue in cat_issues:
                    print(f"  {Colors.RED}[x]{Colors.END} {issue['file']}:{issue['line']}")
                    print(f"    {issue['message']}")
                    if issue['code']:
                        print(f"    代码: {issue['code'][:60]}...")
                    print()

        print()
        print("统计:")
        print(f"  路由顺序问题: {self.stats['route_issues']}")
        print(f"  时间字段命名问题: {self.stats['time_field_issues']}")
        print(f"  user_id 类型问题: {self.stats['user_id_issues']}")
        print(f"  分层违规问题: {self.stats['layer_violations']}")
        print("=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description='代码规范自动检查脚本',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  python3 .harness/scripts/check_code_standards.py
  python3 .harness/scripts/check_code_standards.py --path app/
  python3 .harness/scripts/check_code_standards.py --fix

检查项:
  1. 路由顺序问题 - :id 参数路由是否覆盖更具体的路由
  2. 时间字段命名 - 应使用 created_at/updated_at/deleted_at (项目规范)
  3. user_id 类型问题 - 避免字符串与整数比较
  4. 分层违规 - Controller 应通过 Service 层调用 Model，不应直接调用
        """
    )

    parser.add_argument('--path', default='.', help='检查路径 (默认: 当前目录)')
    parser.add_argument('--fix', action='store_true', help='自动修复 (暂不支持)')

    args = parser.parse_args()

    # 检查脚本存在
    script_path = Path(__file__).parent / 'check_code_standards.py'
    if not script_path.exists():
        print_error(f"检查脚本不存在: {script_path}")
        sys.exit(1)

    # 执行检查
    checker = CodeStandardsChecker(args.path)
    issue_count = checker.check_all()

    # 返回退出码
    sys.exit(1 if issue_count > 0 else 0)


if __name__ == '__main__':
    main()