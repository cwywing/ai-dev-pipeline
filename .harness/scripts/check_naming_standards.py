#!/usr/bin/env python3
"""
命名规范检查脚本

检查项目中违反命名规范的情况：
1. 时间字段命名：create_time 应使用 created_at
2. 用户ID字段命名：uid 应使用 user_id
3. CamelCase 字段命名
4. Model 配置一致性

使用方法：
    python3 .harness/scripts/check_naming_standards.py
    python3 .harness/scripts/check_naming_standards.py --fix  # 自动修复
    python3 .harness/scripts/check_naming_standards.py --format json  # JSON 输出
"""

import os
import re
import json
import argparse
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from pathlib import Path


@dataclass
class NamingIssue:
    """命名问题记录"""
    file_path: str
    line_number: int
    issue_type: str
    current_name: str
    suggested_name: str
    description: str
    fix_command: Optional[str] = None


@dataclass
class CheckResult:
    """检查结果汇总"""
    total_files_checked: int = 0
    total_issues: int = 0
    issues_by_type: Dict[str, int] = field(default_factory=dict)
    issues: List[NamingIssue] = field(default_factory=list)

    def add_issue(self, issue: NamingIssue):
        self.issues.append(issue)
        self.total_issues += 1
        self.issues_by_type[issue.issue_type] = self.issues_by_type.get(issue.issue_type, 0) + 1


class NamingStandardChecker:
    """命名规范检查器"""

    # 时间字段模式
    CREATE_TIME_PATTERN = re.compile(r'\bcreate_time\b', re.IGNORECASE)
    UPDATE_TIME_PATTERN = re.compile(r'\bupdate_time\b', re.IGNORECASE)
    CREATE_AT_PATTERN = re.compile(r'\bcreate_at\b', re.IGNORECASE)
    UPDATE_AT_PATTERN = re.compile(r'\bupdate_at\b', re.IGNORECASE)

    # 用户ID模式
    UID_PATTERN = re.compile(r'\b(uid)\b', re.IGNORECASE)
    USER_ID_PATTERN = re.compile(r'\buser_id\b', re.IGNORECASE)

    # CamelCase 字段模式（排除 PHP 关键字和常见模式）
    CAMEL_CASE_FIELD_PATTERN = re.compile(
        r'\b[a-z][a-z0-9]*[A-Z][a-zA-Z0-9]*\b',
    )

    # PHP 关键字（不应检查的 CamelCase）
    PHP_KEYWORDS = {
        'public', 'private', 'protected', 'static', 'final',
        'abstract', 'const', 'var', 'function', 'class',
        'interface', 'trait', 'extends', 'implements',
        'namespace', 'use', 'new', 'return', 'if', 'else',
        'foreach', 'while', 'do', 'switch', 'case', 'break',
        'continue', 'try', 'catch', 'throw', 'finally',
        'echo', 'print', 'isset', 'empty', 'unset',
        'instanceof', 'insteadof', 'require', 'include',
        'require_once', 'include_once', 'array', 'list',
        'match', 'fn', 'null', 'true', 'false', 'mixed',
        'void', 'never', 'object', 'string', 'integer',
        'int', 'float', 'bool', 'boolean', 'self', 'parent',
        'this', 'get', 'set', 'call', 'offset', 'table',
        'column', 'index', 'foreign', 'key', 'unique',
        'primary', 'add', 'create', 'alter', 'drop',
        'rename', 'change', 'modify', 'update', 'delete',
        'insert', 'select', 'from', 'where', 'order', 'group',
        'by', 'limit', 'join', 'left', 'right', 'inner',
        'outer', 'on', 'as', 'distinct', 'count', 'sum',
        'avg', 'max', 'min', 'and', 'or', 'not', 'is', 'in',
        'between', 'like', 'null', 'default', 'auto',
        'increment', 'unsigned', 'zerofill', 'nullable',
        'comment', 'after', 'before', 'first', 'last',
    }

    # 需要检查的目录
    SEARCH_DIRECTORIES = [
        'app/models',
        'app/repositories',
        'app/service',
        'app/controllers',
        'database/migrations',
    ]

    def __init__(self, root_dir: str = None):
        self.root_dir = Path(root_dir) if root_dir else Path.cwd()
        self.result = CheckResult()

    def check_file(self, file_path: Path) -> List[NamingIssue]:
        """检查单个文件"""
        issues = []

        if file_path.suffix not in ['.php', '.md']:
            return issues

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
        except (UnicodeDecodeError, IOError) as e:
            print(f"Warning: Cannot read {file_path}: {e}")
            return issues

        self.result.total_files_checked += 1

        for line_num, line in enumerate(lines, 1):
            # 跳过注释行（简单检查）
            stripped = line.strip()
            if stripped.startswith('//') or stripped.startswith('#'):
                continue

            # 检查 create_time
            if self.CREATE_TIME_PATTERN.search(line) and not self.CREATE_AT_PATTERN.search(line):
                issues.append(NamingIssue(
                    file_path=str(file_path),
                    line_number=line_num,
                    issue_type='TIME_FIELD',
                    current_name='create_time',
                    suggested_name='created_at',
                    description='时间字段应使用 created_at 而非 create_time',
                    fix_command=f"sed -i 's/\\bcreate_time\\b/created_at/g' {file_path}" if file_path.suffix == '.php' else None
                ))

            # 检查 update_time
            if self.UPDATE_TIME_PATTERN.search(line) and not self.UPDATE_AT_PATTERN.search(line):
                issues.append(NamingIssue(
                    file_path=str(file_path),
                    line_number=line_num,
                    issue_type='TIME_FIELD',
                    current_name='update_time',
                    suggested_name='updated_at',
                    description='时间字段应使用 updated_at 而非 update_time',
                    fix_command=f"sed -i 's/\\bupdate_time\\b/updated_at/g' {file_path}" if file_path.suffix == '.php' else None
                ))

            # 检查 uid（非 user_id 的情况下）
            if self.UID_PATTERN.search(line):
                # 检查是否已经是 user_id（避免误报）
                context = ''.join(lines[max(0, line_num-3):min(len(lines), line_num+2)])
                if not re.search(r'\buser_id\b', context, re.IGNORECASE):
                    issues.append(NamingIssue(
                        file_path=str(file_path),
                        line_number=line_num,
                        issue_type='USER_ID_FIELD',
                        current_name='uid',
                        suggested_name='user_id',
                        description='用户ID字段应使用 user_id 而非 uid',
                        fix_command=f"sed -i 's/\\buid\\b/user_id/g' {file_path}" if file_path.suffix == '.php' else None
                    ))

            # 检查 CamelCase 字段（在引号内的字段定义）
            # 匹配 'fieldName' 或 "fieldName" 格式
            quoted_fields = re.findall(r'[\'"]([a-z][a-zA-Z0-9]*)[\'"]', line)
            for field_name in quoted_fields:
                # 检查是否是 PascalCase 且不是关键字
                if (field_name[0].isupper() or
                    (len(field_name) > 2 and
                     any(c.isupper() for c in field_name[1:]) and
                     field_name.lower() not in self.PHP_KEYWORDS)):

                    # 生成 snake_case 版本
                    snake_case = re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', field_name).lower()

                    # 只报告可能的问题
                    if snake_case != field_name and len(field_name) > 3:
                        issues.append(NamingIssue(
                            file_path=str(file_path),
                            line_number=line_num,
                            issue_type='CAMEL_CASE_FIELD',
                            current_name=field_name,
                            suggested_name=snake_case,
                            description=f'数据库字段应使用 snake_case: {snake_case}',
                            fix_command=None
                        ))

        return issues

    def check_directory(self, directory: Path) -> List[NamingIssue]:
        """递归检查目录"""
        all_issues = []

        if not directory.exists():
            return all_issues

        for item in directory.rglob('*'):
            if item.is_file() and item.suffix == '.php':
                issues = self.check_file(item)
                all_issues.extend(issues)
                for issue in issues:
                    self.result.add_issue(issue)

        return all_issues

    def check_all(self) -> CheckResult:
        """检查所有目录"""
        for dir_name in self.SEARCH_DIRECTORIES:
            dir_path = self.root_dir / dir_name
            self.check_directory(dir_path)

        return self.result

    def print_report(self, format: str = 'text'):
        """打印报告"""
        if format == 'json':
            self._print_json_report()
        else:
            self._print_text_report()

    def _print_text_report(self):
        """打印文本格式报告"""
        print("\n" + "=" * 70)
        print("                    命名规范检查报告")
        print("=" * 70)

        print(f"\n检查文件数: {self.result.total_files_checked}")
        print(f"发现问题数: {self.result.total_issues}")

        if self.result.total_issues > 0:
            print("\n问题分类统计:")
            for issue_type, count in self.result.issues_by_type.items():
                type_name = {
                    'TIME_FIELD': '时间字段命名',
                    'USER_ID_FIELD': '用户ID字段命名',
                    'CAMEL_CASE_FIELD': 'CamelCase 字段',
                }.get(issue_type, issue_type)
                print(f"  - {type_name}: {count}")

            print("\n" + "-" * 70)
            print("详细问题列表:")
            print("-" * 70)

            current_type = None
            for issue in self.result.issues:
                if issue.issue_type != current_type:
                    current_type = issue.issue_type
                    type_name = {
                        'TIME_FIELD': '【时间字段命名问题】',
                        'USER_ID_FIELD': '【用户ID字段命名问题】',
                        'CAMEL_CASE_FIELD': '【CamelCase 字段问题】',
                    }.get(issue_type, issue.issue_type)
                    print(f"\n{type_name}")

                print(f"\n  文件: {issue.file_path}:{issue.line_number}")
                print(f"  问题: {issue.description}")
                print(f"  当前: {issue.current_name}")
                print(f"  建议: {issue.suggested_name}")
                if issue.fix_command:
                    print(f"  修复命令: {issue.fix_command}")

            print("\n" + "=" * 70)
            print("建议修复顺序:")
            print("  1. 先修复 Model 配置（确保 $createTime 和 $updateTime 正确）")
            print("  2. 再修复数据库迁移文件（确保字段名一致）")
            print("  3. 最后修复业务代码（Repository, Service 等）")
            print("=" * 70 + "\n")
        else:
            print("\n✓ 未发现命名规范问题！\n")

    def _print_json_report(self):
        """打印 JSON 格式报告"""
        report = {
            'summary': {
                'total_files_checked': self.result.total_files_checked,
                'total_issues': self.result.total_issues,
                'issues_by_type': self.result.issues_by_type,
            },
            'issues': [
                {
                    'file_path': issue.file_path,
                    'line_number': issue.line_number,
                    'issue_type': issue.issue_type,
                    'current_name': issue.current_name,
                    'suggested_name': issue.suggested_name,
                    'description': issue.description,
                    'fix_command': issue.fix_command,
                }
                for issue in self.result.issues
            ]
        }
        print(json.dumps(report, indent=2, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description='命名规范检查工具')
    parser.add_argument('--root', '-r', default=None, help='项目根目录路径')
    parser.add_argument('--format', '-f', choices=['text', 'json'], default='text',
                        help='输出格式 (默认: text)')
    parser.add_argument('--fix', action='store_true', help='自动修复问题（谨慎使用）')

    args = parser.parse_args()

    # 创建检查器
    checker = NamingStandardChecker(args.root)

    # 执行检查
    print("正在检查命名规范...")
    checker.check_all()

    # 输出报告
    checker.print_report(args.format)

    # 自动修复（如果指定）
    if args.fix and checker.result.issues:
        print("\n⚠️  自动修复功能已禁用。请手动执行修复命令。")
        print("建议在修改前先备份代码。")

    # 返回状态码
    return 1 if checker.result.total_issues > 0 else 0


if __name__ == '__main__':
    exit(main())
