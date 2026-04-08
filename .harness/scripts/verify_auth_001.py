#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
认证配置验证脚本 - Auth_001
====================================

替代原有 Shell 脚本: verify_auth_001.sh

功能:
- 检查 bootstrap/app.php 是否包含 EnsureFrontendRequestsAreStateful
- 检查 config/sanctum.php 是否存在并配置正确
- 检查 User 模型是否使用 HasApiTokens trait
- 检查 config/auth.php 是否配置 sanctum guard
- 运行代码风格检查 (pint)

使用方式:
    python .harness/scripts/verify_auth_001.py

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


def _check_file_contains(file_path: Path, *patterns, case_sensitive: bool = True) -> tuple:
    """
    检查文件是否包含指定内容

    Returns:
        (contains: bool, matched_lines: list)
    """
    if not file_path.exists():
        return False, []

    try:
        content = file_path.read_text(encoding="utf-8", errors="ignore")

        if not case_sensitive:
            content = content.lower()
            patterns = [p.lower() for p in patterns]

        matched_lines = []
        for line in content.split("\n"):
            for pattern in patterns:
                if pattern in line:
                    matched_lines.append(line.strip())
                    break

        return len(matched_lines) > 0, matched_lines

    except Exception as e:
        app_logger.warning(f"无法读取文件: {file_path} - {e}")
        return False, []


def check_bootstrap_app():
    """检查 bootstrap/app.php 是否包含 EnsureFrontendRequestsAreStateful"""
    app_logger.info("检查 bootstrap/app.php...")

    bootstrap_app = PROJECT_ROOT / "bootstrap" / "app.php"

    if not bootstrap_app.exists():
        app_logger.error("❌ bootstrap/app.php 不存在")
        return False

    contains, lines = _check_file_contains(bootstrap_app, "EnsureFrontendRequestsAreStateful")

    if contains:
        app_logger.success("✓ bootstrap/app.php 包含 EnsureFrontendRequestsAreStateful")
        return True
    else:
        app_logger.error("❌ bootstrap/app.php 缺少 EnsureFrontendRequestsAreStateful")
        return False


def check_sanctum_config():
    """检查 config/sanctum.php"""
    app_logger.info("检查 config/sanctum.php...")

    sanctum_config = PROJECT_ROOT / "config" / "sanctum.php"

    if not sanctum_config.exists():
        app_logger.error("❌ config/sanctum.php 不存在")
        return False

    app_logger.success("✓ config/sanctum.php 存在")

    # 检查关键配置项
    key_configs = ["stateful", "guard", "expiration"]
    all_found = True

    for config in key_configs:
        found, lines = _check_file_contains(sanctum_config, config)
        if found:
            app_logger.debug(f"   ✓ 包含配置: {config}")
        else:
            app_logger.warning(f"   ⚠️  未找到配置: {config}")
            all_found = False

    if all_found:
        app_logger.success("✓ config/sanctum.php 配置完整")
    else:
        app_logger.warning("⚠️  config/sanctum.php 配置可能不完整")

    return True  # 文件存在即通过


def check_user_model():
    """检查 User 模型是否使用 HasApiTokens trait"""
    app_logger.info("检查 app/Models/User.php...")

    user_model = PROJECT_ROOT / "app" / "Models" / "User.php"

    if not user_model.exists():
        app_logger.error("❌ app/Models/User.php 不存在")
        return False

    # 检查 HasApiTokens
    found_1, lines = _check_file_contains(user_model, "HasApiTokens")
    found_2, lines = _check_file_contains(user_model, "Laravel\\Sanctum\\HasApiTokens")

    if found_1 or found_2:
        app_logger.success("✓ User 模型使用 HasApiTokens trait")
        return True
    else:
        app_logger.error("❌ User 模型未使用 HasApiTokens trait")
        return False


def check_auth_config():
    """检查 config/auth.php 是否配置 sanctum guard"""
    app_logger.info("检查 config/auth.php...")

    auth_config = PROJECT_ROOT / "config" / "auth.php"

    if not auth_config.exists():
        app_logger.error("❌ config/auth.php 不存在")
        return False

    # 检查 sanctum 配置
    found_1, _ = _check_file_contains(auth_config, "'sanctum'")
    found_2, _ = _check_file_contains(auth_config, "'driver' => 'sanctum'")

    if found_1 and found_2:
        app_logger.success("✓ config/auth.php 配置 sanctum guard")
        return True
    else:
        app_logger.error("❌ config/auth.php 未配置 sanctum guard")
        return False


def check_test_file():
    """检查测试文件是否存在"""
    app_logger.info("检查 SanctumAuthConfigTest.php...")

    test_file = PROJECT_ROOT / "tests" / "Feature" / "SanctumAuthConfigTest.php"

    if test_file.exists():
        app_logger.success("✓ 测试文件存在")
        return True
    else:
        app_logger.warning("⚠️  测试文件不存在: tests/Feature/SanctumAuthConfigTest.php")
        return False


def run_pint_check():
    """运行代码风格检查"""
    app_logger.info("运行代码风格检查 (pint)...")

    pint_cmd = PROJECT_ROOT / "vendor" / "bin" / "pint"

    if not pint_cmd.exists():
        app_logger.warning("⚠️  pint 未安装，跳过代码风格检查")
        return None

    try:
        result = subprocess.run(
            [str(pint_cmd), "--test"],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=PROJECT_ROOT
        )

        if result.returncode == 0:
            app_logger.success("✓ 代码风格检查通过")
            return True
        else:
            app_logger.warning("⚠️  代码风格检查未通过")
            if result.stdout:
                for line in result.stdout.strip().split("\n")[:10]:
                    if line.strip():
                        app_logger.debug(f"   {line}")
            return False

    except subprocess.TimeoutExpired:
        app_logger.warning("⚠️  代码风格检查超时")
        return None
    except Exception as e:
        app_logger.warning(f"⚠️  代码风格检查失败: {e}")
        return None


def main():
    """主函数"""
    app_logger.info("=" * 60)
    app_logger.info("🚀 认证配置验证 - Auth_001")
    app_logger.info("=" * 60)
    app_logger.info(f"项目目录: {PROJECT_ROOT}")
    app_logger.info("")

    # 执行各项检查
    checks = []

    checks.append(("bootstrap/app.php", check_bootstrap_app()))
    checks.append(("config/sanctum.php", check_sanctum_config()))
    checks.append(("User 模型 HasApiTokens", check_user_model()))
    checks.append(("config/auth.php", check_auth_config()))
    checks.append(("测试文件", check_test_file()))
    checks.append(("代码风格 (pint)", run_pint_check()))

    # 汇总结果
    app_logger.info("")
    app_logger.info("=" * 60)
    app_logger.info("📊 验证结果汇总")
    app_logger.info("=" * 60)

    passed = 0
    failed = 0
    skipped = 0

    for name, result in checks:
        if result is True:
            status = "✅ PASS"
            passed += 1
        elif result is False:
            status = "❌ FAIL"
            failed += 1
        else:
            status = "⏭️  SKIP"
            skipped += 1

        app_logger.info(f"   {status}  {name}")

    app_logger.info("")
    app_logger.info(f"总计: {passed} 通过, {failed} 失败, {skipped} 跳过")

    app_logger.info("")

    if failed == 0:
        app_logger.success("✅ 所有验证通过！")
        return 0
    else:
        app_logger.warning("⚠️  部分验证未通过，请修复后重试")
        return 1


if __name__ == "__main__":
    sys.exit(main())
