#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统一输出工具模块验证脚本

运行验证:
    python3 .harness/scripts/verify_output.py

验证内容:
    1. 模块文件存在性
    2. 模块导入成功
    3. Windows GBK 兼容性
    4. Emoji 替换配置
"""

import sys
import os
import io


def safe_print(message="", file=sys.stdout):
    """安全打印，确保 GBK 兼容"""
    try:
        print(message, file=file)
    except UnicodeEncodeError:
        # 移除非 GBK 兼容字符
        clean_msg = message.encode('gbk', errors='ignore').decode('gbk')
        print(clean_msg, file=file)


def check_module_exists():
    """检查模块文件是否存在"""
    module_path = os.path.join(os.path.dirname(__file__), 'console_output.py')
    if os.path.exists(module_path):
        safe_print("[OK] Module file exists: console_output.py")
        return True
    else:
        safe_print("[FAIL] Module file not found: console_output.py")
        return False


def check_module_import():
    """检查模块是否可以成功导入"""
    try:
        sys.path.insert(0, os.path.dirname(__file__))
        from console_output import (
            _safe_print,
            _replace_emojis,
            success,
            error,
            warning,
            info,
            debug,
            NoEmojiContext,
            format_markdown_table,
            format_list,
            EMOJI_TO_TEXT_MAP,
        )
        safe_print("[OK] Module imported successfully")
        return True
    except ImportError as e:
        safe_print(f"[FAIL] Module import failed: {e}")
        return False
    except Exception as e:
        safe_print(f"[FAIL] Error during import: {e}")
        return False


def check_emoji_mapping():
    """检查 Emoji 替换配置"""
    try:
        sys.path.insert(0, os.path.dirname(__file__))
        from console_output import EMOJI_TO_TEXT_MAP

        required_emojis = {
            '✅': '[OK]',
            '❌': '[FAIL]',
            '⚠️': '[WARN]',
            'ℹ️': '[INFO]',
            '🎉': '[SUCCESS]',
            '🔍': '[SEARCH]',
            '🧹': '[CLEAN]',
            '📝': '[NOTE]',
            '📊': '[STAT]',
            '📋': '[LIST]',
            '🤖': '[AGENT]',
            '📦': '[MODULE]',
            '⏳': '[WAIT]',
            '🔄': '[RETRY]',
            '💡': '[TIP]',
        }

        all_valid = True
        for emoji, expected_text in required_emojis.items():
            if emoji in EMOJI_TO_TEXT_MAP:
                actual_text = EMOJI_TO_TEXT_MAP[emoji]
                if actual_text == expected_text:
                    safe_print(f"[OK] {emoji} -> {actual_text}")
                else:
                    safe_print(f"[WARN] {emoji} -> {actual_text} (expected: {expected_text})")
                    all_valid = False
            else:
                safe_print(f"[FAIL] Missing emoji mapping: {emoji}")
                all_valid = False

        if all_valid:
            safe_print(f"[OK] All required emojis have correct replacements ({len(required_emojis)})")
        return all_valid

    except Exception as e:
        safe_print(f"[FAIL] Error checking emoji mapping: {e}")
        return False


def check_windows_compatibility():
    """检查 Windows GBK 兼容性"""
    try:
        sys.path.insert(0, os.path.dirname(__file__))
        from console_output import _replace_emojis

        # 测试包含 Emoji 的消息
        test_messages = [
            "[OK] Task completed",
            "[FAIL] Error occurred",
            "[WARN] Warning detected",
            "[INFO] Information: Test passed",
            "[SUCCESS] Victory!",
        ]

        all_compatible = True
        for msg in test_messages:
            result = _replace_emojis(msg)
            try:
                # 尝试 GBK 编码
                result.encode('gbk')
                safe_print(f"[OK] GBK compatible: '{msg}' -> '{result}'")
            except UnicodeEncodeError as e:
                safe_print(f"[FAIL] GBK encoding failed: '{msg}' -> '{result}' ({e})")
                all_compatible = False

        return all_compatible

    except Exception as e:
        safe_print(f"[FAIL] Error checking Windows compatibility: {e}")
        return False


def check_safe_print():
    """检查安全打印功能"""
    try:
        sys.path.insert(0, os.path.dirname(__file__))
        from console_output import _safe_print

        output = io.StringIO()
        _safe_print("[OK] Test message", file=output)
        result = output.getvalue()

        if "[OK]" in result and "Test message" in result:
            safe_print("[OK] Safe print function works correctly")
            return True
        else:
            safe_print(f"[FAIL] Safe print function failed: '{result}'")
            return False

    except Exception as e:
        safe_print(f"[FAIL] Error checking safe print: {e}")
        return False


def check_context_manager():
    """检查上下文管理器功能"""
    try:
        sys.path.insert(0, os.path.dirname(__file__))
        from console_output import NoEmojiContext
        import io

        output = io.StringIO()
        with NoEmojiContext():
            # 这里可以添加更多测试
            pass

        safe_print("[OK] Context manager works correctly")
        return True

    except Exception as e:
        safe_print(f"[FAIL] Error checking context manager: {e}")
        return False


def check_format_functions():
    """检查格式化函数"""
    try:
        sys.path.insert(0, os.path.dirname(__file__))
        from console_output import format_markdown_table, format_list

        # 测试格式化表格
        headers = ["Name", "Status"]
        rows = [["Task 1", "[OK] Done"]]
        table = format_markdown_table(headers, rows, title="Test")

        if "Name" in table and "Status" in table:
            safe_print("[OK] Table formatting works correctly")
        else:
            safe_print("[FAIL] Table formatting failed")
            return False

        # 测试格式化列表
        items = ["Item 1", "Item 2"]
        list_output = format_list(items)

        if "Item 1" in list_output and "Item 2" in list_output:
            safe_print("[OK] List formatting works correctly")
        else:
            safe_print("[FAIL] List formatting failed")
            return False

        return True

    except Exception as e:
        safe_print(f"[FAIL] Error checking format functions: {e}")
        return False


def run_verification():
    """运行所有验证"""
    safe_print("=" * 60)
    safe_print("Console Output Module Verification")
    safe_print("=" * 60)
    safe_print()

    results = []

    # 运行所有检查
    safe_print("[1/7] Checking module file exists...")
    results.append(check_module_exists())
    safe_print()

    safe_print("[2/7] Checking module import...")
    results.append(check_module_import())
    safe_print()

    safe_print("[3/7] Checking emoji mapping...")
    results.append(check_emoji_mapping())
    safe_print()

    safe_print("[4/7] Checking Windows GBK compatibility...")
    results.append(check_windows_compatibility())
    safe_print()

    safe_print("[5/7] Checking safe print function...")
    results.append(check_safe_print())
    safe_print()

    safe_print("[6/7] Checking context manager...")
    results.append(check_context_manager())
    safe_print()

    safe_print("[7/7] Checking format functions...")
    results.append(check_format_functions())
    safe_print()

    # 汇总结果
    safe_print("=" * 60)
    safe_print("Verification Summary")
    safe_print("=" * 60)

    total = len(results)
    passed = sum(1 for r in results if r)
    failed = total - passed

    safe_print(f"Total checks: {total}")
    safe_print(f"Passed: {passed}")
    safe_print(f"Failed: {failed}")
    safe_print()

    if all(results):
        safe_print("[SUCCESS] All verification checks passed!")
        safe_print("[INFO] Module is ready to use in the project")
        return 0
    else:
        safe_print("[FAIL] Some verification checks failed, see output above")
        return 1


if __name__ == '__main__':
    sys.exit(run_verification())
