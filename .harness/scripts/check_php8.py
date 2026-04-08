#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PHP8 环境检查脚本
====================================

替代原有 Shell 脚本: check_php8.sh

功能:
- 检查 php8 命令是否可用
- 检查 Laravel artisan 文件是否存在
- 检查 vendor/autoload.php 是否存在
- 检查 PHP 版本

使用方式:
    python .harness/scripts/check_php8.py

====================================
"""

import sys
import platform
import shutil
import subprocess
from pathlib import Path

# Windows UTF-8 修复
if platform.system() == 'Windows':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except:
        pass

# 路径注入
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.config import PROJECT_ROOT
from scripts.logger import app_logger


def check_php_command():
    """检查 php8 命令是否可用"""
    app_logger.info("检查 php8 命令...")

    # 尝试多个 PHP 命令名
    php_commands = ["php8", "php"]

    for cmd in php_commands:
        if shutil.which(cmd):
            app_logger.success(f"找到 PHP 命令: {cmd}")

            # 获取版本信息
            try:
                result = subprocess.run(
                    [cmd, "--version"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                    cwd=PROJECT_ROOT
                )
                version_line = result.stdout.split("\n")[0]
                app_logger.info(f"PHP 版本: {version_line}")

                # 检查版本号
                version_parts = result.stdout.split()[1].split(".")
                major = int(version_parts[0])

                if major >= 8:
                    app_logger.success("PHP 版本 >= 8.0 OK")
                    return cmd
                else:
                    app_logger.warning(f"PHP 版本 {major}.x < 8.0，可能不支持部分特性")
                    return cmd

            except Exception as e:
                app_logger.warning(f"无法获取 PHP 版本: {e}")
                return cmd

    app_logger.error("未找到 php8 或 php 命令")
    app_logger.info("请确保 PHP 8 已安装并可在 PATH 中访问")
    return None


def check_artisan():
    """检查 Laravel artisan 文件"""
    app_logger.info("检查 artisan 文件...")

    artisan_path = PROJECT_ROOT / "artisan"

    if artisan_path.exists():
        app_logger.success(f"artisan 文件存在: {artisan_path}")
        return True
    else:
        app_logger.error(f"artisan 文件不存在")
        app_logger.info(f"   可能不是 Laravel 项目根目录: {PROJECT_ROOT}")
        return False


def check_vendor():
    """检查 vendor/autoload.php"""
    app_logger.info("检查 composer 依赖...")

    autoload_path = PROJECT_ROOT / "vendor" / "autoload.php"

    if autoload_path.exists():
        app_logger.success("composer 依赖已安装")
        return True
    else:
        app_logger.warning("vendor/autoload.php 不存在")
        app_logger.info("   需要先运行: composer install")
        return False


def check_laravel_installation():
    """检查 Laravel 核心文件"""
    app_logger.info("检查 Laravel 安装...")

    laravel_files = [
        "bootstrap/app.php",
        "config/app.php",
        "app/Http/Kernel.php"
    ]

    all_exist = True
    for file_path in laravel_files:
        full_path = PROJECT_ROOT / file_path
        if full_path.exists():
            app_logger.debug(f"存在: {file_path}")
        else:
            app_logger.warning(f"缺少: {file_path}")
            all_exist = False

    if all_exist:
        app_logger.success("Laravel 核心文件完整")
    else:
        app_logger.warning("部分 Laravel 核心文件缺失")

    return all_exist


def main():
    """主函数"""
    app_logger.info("=" * 60)
    app_logger.info("PHP8 环境检查")
    app_logger.info("=" * 60)
    app_logger.info(f"项目目录: {PROJECT_ROOT}")
    app_logger.info("")

    results = {}

    # 执行各项检查
    results["php"] = check_php_command()
    results["artisan"] = check_artisan()
    results["vendor"] = check_vendor()
    results["laravel"] = check_laravel_installation()

    # 汇总结果
    app_logger.info("")
    app_logger.info("=" * 60)
    app_logger.info("检查结果汇总")
    app_logger.info("=" * 60)

    all_passed = all(results.values())

    for name, result in results.items():
        status = "PASS" if result else "FAIL"
        app_logger.info(f"   {status} {name.upper()}")

    app_logger.info("")

    if all_passed:
        app_logger.success("环境检查全部通过！")
        return 0
    else:
        app_logger.warning("部分检查未通过，请修复后继续")
        return 1


if __name__ == "__main__":
    sys.exit(main())
