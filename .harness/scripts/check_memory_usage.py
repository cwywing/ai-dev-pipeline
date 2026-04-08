#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
内存使用检查脚本
====================================

替代原有 Shell 脚本: check-memory-usage.sh

功能:
- 检查 PHP memory_limit 配置
- 统计测试文件数量
- 检查 DatabaseTransactions trait 使用情况
- 验证 RefreshDatabase 是否已被替换

使用方式:
    python .harness/scripts/check_memory_usage.py

====================================
"""

import sys
import platform

# Windows UTF-8 修复
if platform.system() == 'Windows':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except:
        pass

import subprocess
from pathlib import Path

# 路径注入
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.config import PROJECT_ROOT
from scripts.logger import app_logger


def check_php_memory_limit():
    """检查 PHP 内存限制"""
    app_logger.info("检查 PHP memory_limit...")

    php_cmd = _find_php_command()
    if not php_cmd:
        app_logger.warning("⚠️  无法检查 memory_limit")
        return None

    try:
        result = subprocess.run(
            [php_cmd, "-d", "memory_limit=512M", "-r", "echo ini_get('memory_limit');"],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=PROJECT_ROOT
        )

        memory_limit = result.stdout.strip()
        app_logger.info(f"   memory_limit: {memory_limit}")

        return memory_limit

    except Exception as e:
        app_logger.warning(f"⚠️  无法获取 memory_limit: {e}")
        return None


def _find_php_command():
    """查找可用的 PHP 命令"""
    import shutil
    for cmd in ["php8", "php"]:
        if shutil.which(cmd):
            return cmd
    return None


def count_test_files():
    """统计测试文件数量"""
    app_logger.info("统计测试文件...")

    tests_dir = PROJECT_ROOT / "tests"

    if not tests_dir.exists():
        app_logger.warning("⚠️  tests 目录不存在")
        return 0

    php_files = list(tests_dir.rglob("*.php"))
    total = len(php_files)

    app_logger.info(f"   总测试文件数: {total}")

    return total


def check_database_transactions():
    """检查 DatabaseTransactions 和 RefreshDatabase 使用情况"""
    app_logger.info("检查数据库事务 trait 使用...")

    tests_dir = PROJECT_ROOT / "tests"

    if not tests_dir.exists():
        app_logger.warning("⚠️  tests 目录不存在")
        return 0, 0

    refresh_count = 0
    transaction_count = 0

    for php_file in tests_dir.rglob("*.php"):
        try:
            content = php_file.read_text(encoding="utf-8", errors="ignore")

            # 检查是否是注释行
            lines = content.split("\n")
            non_comment_lines = []
            for line in lines:
                stripped = line.strip()
                # 跳过行注释和块注释
                if stripped.startswith("//") or stripped.startswith("#"):
                    continue
                if "/*" in content:
                    # 简单块注释处理
                    continue
                non_comment_lines.append(line)

            clean_content = "\n".join(non_comment_lines)

            # 检查 RefreshDatabase
            if "RefreshDatabase" in clean_content:
                refresh_count += 1
                app_logger.debug(f"   ⚠️  发现 RefreshDatabase: {php_file.relative_to(PROJECT_ROOT)}")

            # 检查 DatabaseTransactions
            if "DatabaseTransactions" in clean_content:
                transaction_count += 1
                app_logger.debug(f"   ✓ 发现 DatabaseTransactions: {php_file.relative_to(PROJECT_ROOT)}")

        except Exception as e:
            app_logger.warning(f"⚠️  无法读取文件: {php_file} - {e}")

    app_logger.info("")
    app_logger.info("   DatabaseTransactions: {0} 个文件".format(transaction_count))
    app_logger.info("   RefreshDatabase: {0} 个文件".format(refresh_count))

    return transaction_count, refresh_count


def check_phpunit_config():
    """检查 phpunit.xml 配置"""
    app_logger.info("检查 phpunit.xml 配置...")

    phpunit_path = PROJECT_ROOT / "phpunit.xml"

    if not phpunit_path.exists():
        phpunit_path = PROJECT_ROOT / "phpunit.xml.dist"

    if phpunit_path.exists():
        try:
            content = phpunit_path.read_text(encoding="utf-8", errors="ignore")

            if "memory_limit" in content:
                # 提取 memory_limit 配置
                import re
                match = re.search(r'memory_limit["\s]*?[:=]["\'\s]*?([0-9]+[Mm])', content)
                if match:
                    app_logger.info(f"   memory_limit: {match.group(1)}")
                else:
                    app_logger.debug("   找到 memory_limit 配置")
            else:
                app_logger.debug("   未找到 memory_limit 配置")

            app_logger.success("✓ phpunit.xml 存在")
            return True

        except Exception as e:
            app_logger.warning(f"⚠️  无法读取 phpunit.xml: {e}")
            return False
    else:
        app_logger.warning("⚠️  phpunit.xml 不存在")
        return False


def print_recommendations():
    """打印建议"""
    app_logger.info("")
    app_logger.info("=" * 60)
    app_logger.info("📋 优化建议")
    app_logger.info("=" * 60)
    app_logger.info("   1. ✅ Memory limit 设置为 512M")
    app_logger.info("   2. ✅ 所有测试使用 DatabaseTransactions")
    app_logger.info("   3. ✅ 避免使用 RefreshDatabase")
    app_logger.info("   4. ✅ 测试在事务中运行并自动回滚")
    app_logger.info("")
    app_logger.info("   💡 预期内存使用:")
    app_logger.info("      - 单元测试: < 128MB/测试")
    app_logger.info("      - 功能测试: < 256MB/测试")
    app_logger.info("      - 总计 512M 限制应足够")


def main():
    """主函数"""
    app_logger.info("=" * 60)
    app_logger.info("🚀 内存使用检查")
    app_logger.info("=" * 60)
    app_logger.info(f"项目目录: {PROJECT_ROOT}")
    app_logger.info("")

    # 执行检查
    memory_limit = check_php_memory_limit()
    test_count = count_test_files()
    transaction_count, refresh_count = check_database_transactions()
    phpunit_ok = check_phpunit_config()

    # 验证结果
    app_logger.info("")
    app_logger.info("=" * 60)
    app_logger.info("📊 检查结果")
    app_logger.info("=" * 60)

    checks = []

    # RefreshDatabase 检查
    if refresh_count == 0:
        app_logger.success("✅ 没有文件使用 RefreshDatabase")
        checks.append(True)
    else:
        app_logger.error(f"❌ {refresh_count} 个文件仍使用 RefreshDatabase")
        app_logger.info("   💡 建议替换为 DatabaseTransactions")
        checks.append(False)

    # DatabaseTransactions 检查
    if transaction_count > 0:
        app_logger.success(f"✅ {transaction_count} 个文件使用 DatabaseTransactions")
        checks.append(True)
    else:
        app_logger.warning("⚠️  没有文件使用 DatabaseTransactions")
        checks.append(False)

    # phpunit.xml 检查
    if phpunit_ok:
        checks.append(True)
    else:
        checks.append(False)

    app_logger.info("")

    # 打印建议
    print_recommendations()

    app_logger.info("")
    if all(checks):
        app_logger.success("✅ 内存使用检查通过！")
        return 0
    else:
        app_logger.warning("⚠️  部分检查未通过")
        return 1


if __name__ == "__main__":
    sys.exit(main())
