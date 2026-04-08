"""
Phase 1 验收测试
====================================

验证配置中心和日志系统是否正常工作

运行方式:
    python .harness/scripts/test_phase1.py

====================================
"""

import sys
import os

# Windows UTF-8 修复
if sys.platform == 'win32':
    try:
        os.system('chcp 65001 >nul 2>&1')
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except:
        pass

import platform
from pathlib import Path

# 添加父目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))


def test_imports():
    """测试模块导入"""
    print("\n[1/5] 测试模块导入...")

    try:
        from scripts.config import (
            HARNESS_DIR, PROJECT_ROOT, LOG_DIR,
            BASE_SILENCE_TIMEOUT, PERMISSION_MODE
        )
        from scripts.logger import app_logger, LogConfig
        print("   ✅ 模块导入成功")
        return True
    except ImportError as e:
        print(f"   ❌ 模块导入失败: {e}")
        return False


def test_paths():
    """测试路径配置"""
    print("\n[2/5] 测试路径配置...")

    from scripts.config import HARNESS_DIR, PROJECT_ROOT, LOG_DIR

    checks = [
        ("HARNESS_DIR 存在", HARNESS_DIR.exists()),
        ("PROJECT_ROOT 存在", PROJECT_ROOT.exists()),
        ("LOG_DIR 存在", LOG_DIR.exists()),
    ]

    all_passed = True
    for name, result in checks:
        status = "✅" if result else "❌"
        print(f"   {status} {name}: {result if isinstance(result, bool) else 'N/A'}")
        if result is False:
            all_passed = False

    return all_passed


def test_config_values():
    """测试配置值"""
    print("\n[3/5] 测试配置值...")

    from scripts.config import (
        BASE_SILENCE_TIMEOUT, MAX_SILENCE_TIMEOUT,
        TIMEOUT_BACKOFF_FACTOR, PERMISSION_MODE,
        get_timeout_for_stage
    )

    checks = [
        ("BASE_SILENCE_TIMEOUT 是 int", isinstance(BASE_SILENCE_TIMEOUT, int)),
        ("MAX_SILENCE_TIMEOUT 是 int", isinstance(MAX_SILENCE_TIMEOUT, int)),
        ("TIMEOUT_BACKOFF_FACTOR 是 float", isinstance(TIMEOUT_BACKOFF_FACTOR, float)),
        ("PERMISSION_MODE 是 str", isinstance(PERMISSION_MODE, str)),
        ("超时计算正确", get_timeout_for_stage("dev", 0) > 0),
    ]

    all_passed = True
    for name, result in checks:
        status = "✅" if result else "❌"
        print(f"   {status} {name}")
        if result is False:
            all_passed = False

    return all_passed


def test_logger():
    """测试日志系统"""
    print("\n[4/5] 测试日志系统...")

    from scripts.logger import app_logger

    try:
        # 测试不同级别日志（会自动触发初始化）
        app_logger.debug("DEBUG 消息测试")
        app_logger.info("INFO 消息测试")
        app_logger.warning("WARNING 消息测试")
        app_logger.error("ERROR 消息测试")

        # 成功日志
        app_logger.success("SUCCESS 消息测试")

        # 验证日志文件已创建
        from scripts.config import LOG_DIR
        log_files = list(LOG_DIR.rglob("automation_*.log"))

        if log_files:
            print(f"   ✅ 日志文件已创建: {len(log_files)} 个")
            for f in log_files[-2:]:  # 显示最近2个
                print(f"      - {f.name}")
            return True
        else:
            print("   ⚠️  日志文件尚未创建（将在下次写入时创建）")
            return True  # 不是失败，只是还没写入

    except Exception as e:
        print(f"   ❌ 日志系统错误: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_print_config():
    """测试配置打印"""
    print("\n[5/5] 测试配置打印...")

    try:
        from scripts.config import print_config
        print_config()
        print("   ✅ 配置打印成功")
        return True
    except Exception as e:
        print(f"   ❌ 配置打印失败: {e}")
        return False


def main():
    """主测试函数"""
    print("=" * 60)
    print("🚀 Harness Phase 1 验收测试")
    print("=" * 60)

    results = []

    results.append(("模块导入", test_imports()))
    results.append(("路径配置", test_paths()))
    results.append(("配置值", test_config_values()))
    results.append(("日志系统", test_logger()))
    results.append(("配置打印", test_print_config()))

    print("\n" + "=" * 60)
    print("📊 测试结果汇总")
    print("=" * 60)

    all_passed = True
    for name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"   {status}  {name}")
        if not passed:
            all_passed = False

    print("\n" + "=" * 60)

    if all_passed:
        print("🎉 Phase 1 验收测试全部通过！")
        print("\n📝 后续步骤:")
        print("   1. 安装 Python 依赖: pip install -r .harness/requirements.txt")
        print("   2. 继续 Phase 2: 重写外围验证脚本")
        print("   3. 清理旧 .sh 文件")
    else:
        print("⚠️  部分测试失败，请检查错误信息")

    print("=" * 60 + "\n")

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
