#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Swagger/OpenAPI 文档生成脚本
====================================

替代原有 Shell 脚本: generate-swagger.sh

功能:
- 运行 Laravel l5-swagger 文档生成命令
- 检查 storage/api-docs 目录
- 验证生成的文档文件

使用方式:
    python .harness/scripts/generate_swagger.py

依赖:
    - Laravel l5-swagger 扩展包
    - php8 或 php 命令

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


def _find_php_command():
    """查找可用的 PHP 命令"""
    import shutil
    for cmd in ["php8", "php"]:
        if shutil.which(cmd):
            return cmd
    return None


def check_l5_swagger_installed():
    """检查 l5-swagger 是否安装"""
    app_logger.info("检查 l5-swagger 扩展包...")

    composer_lock = PROJECT_ROOT / "composer.lock"

    if not composer_lock.exists():
        app_logger.warning("⚠️  composer.lock 不存在")
        return False

    try:
        content = composer_lock.read_text(encoding="utf-8", errors="ignore")

        if "l5-swagger" in content or "swagger" in content.lower():
            app_logger.success("✓ l5-swagger 已安装")
            return True
        else:
            app_logger.warning("⚠️  未检测到 l5-swagger")
            return False

    except Exception as e:
        app_logger.warning(f"⚠️  无法检查 l5-swagger: {e}")
        return False


def check_swagger_config():
    """检查 Swagger 配置"""
    app_logger.info("检查 Swagger 配置...")

    config_files = [
        PROJECT_ROOT / "config" / "l5-swagger.php",
        PROJECT_ROOT / "config" / "swagger.php"
    ]

    for config_file in config_files:
        if config_file.exists():
            app_logger.success(f"✓ 配置文件存在: {config_file.name}")
            return True

    app_logger.warning("⚠️  未找到 Swagger 配置文件")
    return False


def check_storage_directories():
    """检查 storage 目录"""
    app_logger.info("检查 storage 目录...")

    storage_dir = PROJECT_ROOT / "storage"
    api_docs_dir = storage_dir / "api-docs"

    if storage_dir.exists():
        app_logger.success("✓ storage 目录存在")
    else:
        app_logger.warning("⚠️  storage 目录不存在")
        return False

    if api_docs_dir.exists():
        existing_files = list(api_docs_dir.glob("*"))
        app_logger.info(f"   已有的文档文件: {len(existing_files)} 个")
    else:
        app_logger.info("   api-docs 目录将在生成时创建")

    return True


def generate_documentation():
    """生成 Swagger 文档"""
    app_logger.info("=" * 60)
    app_logger.info("📝 生成 Swagger 文档")
    app_logger.info("=" * 60)

    php_cmd = _find_php_command()

    if not php_cmd:
        app_logger.error("❌ 未找到 PHP 命令")
        return False

    try:
        app_logger.info(f"执行: {php_cmd} artisan l5-swagger:generate")

        result = subprocess.run(
            [php_cmd, "artisan", "l5-swagger:generate"],
            capture_output=True,
            text=True,
            timeout=120,  # 2 分钟超时
            cwd=PROJECT_ROOT
        )

        if result.returncode == 0:
            app_logger.success("✓ 文档生成成功")
            if result.stdout:
                for line in result.stdout.strip().split("\n")[-5:]:
                    if line.strip():
                        app_logger.debug(f"   {line}")
            return True
        else:
            app_logger.error(f"❌ 文档生成失败 (exit code: {result.returncode})")
            if result.stderr:
                app_logger.error("错误信息:")
                for line in result.stderr.strip().split("\n")[:10]:
                    if line.strip():
                        app_logger.error(f"   {line}")
            return False

    except subprocess.TimeoutExpired:
        app_logger.error("❌ 文档生成超时 (120秒)")
        return False
    except Exception as e:
        app_logger.error(f"❌ 执行失败: {e}")
        return False


def verify_generated_files():
    """验证生成的文档文件"""
    app_logger.info("验证生成的文档...")

    api_docs_dir = PROJECT_ROOT / "storage" / "api-docs"

    if not api_docs_dir.exists():
        app_logger.warning("⚠️  api-docs 目录不存在")
        return False

    # 检查常见文档格式
    doc_files = []

    for pattern in ["*.json", "*.yaml", "*.yml"]:
        doc_files.extend(api_docs_dir.glob(pattern))

    if doc_files:
        app_logger.success(f"✓ 生成 {len(doc_files)} 个文档文件:")
        for f in doc_files:
            size = f.stat().st_size
            size_str = f"{size / 1024:.1f} KB" if size > 1024 else f"{size} B"
            app_logger.info(f"   - {f.name} ({size_str})")
        return True
    else:
        app_logger.warning("⚠️  未找到生成的文档文件")
        return False


def print_access_info():
    """打印访问信息"""
    app_logger.info("")
    app_logger.info("=" * 60)
    app_logger.info("📋 文档访问方式")
    app_logger.info("=" * 60)
    app_logger.info("   Swagger UI: http://localhost:8000/api/documentation")
    app_logger.info("   JSON 文档:  storage/api-docs/api-docs.json")
    app_logger.info("   YAML 文档:  storage/api-docs/api-docs.yaml")
    app_logger.info("")


def main():
    """主函数"""
    app_logger.info("=" * 60)
    app_logger.info("🚀 Swagger/OpenAPI 文档生成")
    app_logger.info("=" * 60)
    app_logger.info(f"项目目录: {PROJECT_ROOT}")
    app_logger.info("")

    # 前置检查
    checks = []

    checks.append(("l5-swagger", check_l5_swagger_installed()))
    checks.append(("Swagger 配置", check_swagger_config()))
    checks.append(("Storage 目录", check_storage_directories()))

    if not all(result for _, result in checks if result is not False):
        app_logger.warning("⚠️  前置检查未通过，部分功能可能异常")

    app_logger.info("")

    # 生成文档
    generate_ok = generate_documentation()

    # 验证结果
    if generate_ok:
        verify_ok = verify_generated_files()
    else:
        verify_ok = False

    # 输出访问信息
    print_access_info()

    # 最终结果
    app_logger.info("=" * 60)

    if generate_ok and verify_ok:
        app_logger.success("✅ Swagger 文档生成完成！")
        return 0
    elif generate_ok:
        app_logger.warning("⚠️  文档已生成但验证未完全通过")
        return 0
    else:
        app_logger.error("❌ Swagger 文档生成失败")
        return 1


if __name__ == "__main__":
    sys.exit(main())
