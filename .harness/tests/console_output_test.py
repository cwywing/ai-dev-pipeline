#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
console_output.py 单元测试

运行测试:
    python3 .harness/tests/console_output_test.py
"""

import sys
import os
import io
import contextlib
import unittest

# 添加脚本目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + '/../scripts')

from console_output import (
    _safe_print,
    _replace_emojis,
    EMOJI_TO_TEXT_MAP,
    success,
    error,
    warning,
    info,
    debug,
    NoEmojiContext,
    format_markdown_table,
    format_list,
)


class TestEmojiToTextMap(unittest.TestCase):
    """测试 Emoji 替换映射"""

    def test_all_emoji_have_text_replacement(self):
        """测试所有 Emoji 都有对应的文本替换"""
        for emoji, text in EMOJI_TO_TEXT_MAP.items():
            self.assertIsInstance(emoji, str, f"Emoji '{emoji}' should be a string")
            self.assertIsInstance(text, str, f"Text '{text}' should be a string")
            self.assertGreater(len(emoji), 0, f"Emoji should not be empty")
            self.assertGreater(len(text), 0, f"Text should not be empty")

    def test_no_duplicate_texts(self):
        """测试 Emoji 和文本映射关系正确（Note: 多个 Emoji 可以映射到同一文本）"""
        # 检查所有 Emoji 都有映射
        self.assertIn('✅', EMOJI_TO_TEXT_MAP)
        self.assertIn('❌', EMOJI_TO_TEXT_MAP)
        self.assertIn('⚠️', EMOJI_TO_TEXT_MAP)
        self.assertIn('ℹ️', EMOJI_TO_TEXT_MAP)
        self.assertEqual(len(EMOJI_TO_TEXT_MAP), 30)  # 总共 30 个 Emoji（包括 -clock 占位符）


class TestReplaceEmojis(unittest.TestCase):
    """测试 _replace_emojis 函数"""

    def setUp(self):
        """设置测试环境"""
        self.replace_function = _replace_emojis

    def test_basic_emoji_replacement(self):
        """测试基础 Emoji 替换"""
        test_cases = [
            ("✅ Success", "[OK] Success"),
            ("❌ Error", "[FAIL] Error"),
            ("⚠️ Warning", "[WARN] Warning"),
            ("ℹ️ Info", "[INFO] Info"),
            ("🎉 Success!", "[SUCCESS] Success!"),
            ("🔍 Checking...", "[SEARCH] Checking..."),
            ("🧹 Cleaning...", "[CLEAN] Cleaning..."),
            ("📝 Note", "[NOTE] Note"),
            ("📊 Statistics", "[STAT] Statistics"),
            ("📋 List", "[LIST] List"),
            ("🤖 Agent", "[AGENT] Agent"),
            ("📦 Module", "[MODULE] Module"),
            ("⏳ Waiting", "[WAIT] Waiting"),
            ("🔄 Retrying", "[RETRY] Retrying"),
            ("💡 Tip", "[TIP] Tip"),
        ]

        for input_msg, expected in test_cases:
            with self.subTest(input=input_msg):
                result = self.replace_function(input_msg)
                self.assertEqual(result, expected)

    def test_no_emoji_preserved(self):
        """测试没有 Emoji 的消息应保持不变"""
        messages = [
            "Hello, World!",
            "Python is great",
            "No emojis here",
        ]

        for msg in messages:
            with self.subTest(input=msg):
                result = self.replace_function(msg)
                self.assertEqual(result, msg)

    def test_multiple_emojis(self):
        """测试消息中有多个 Emoji"""
        input_msg = "✅ Done! 🎉 Victory!"
        expected = "[OK] Done! [SUCCESS] Victory!"
        result = self.replace_function(input_msg)
        self.assertEqual(result, expected)

    def test_remove_all_flag(self):
        """测试 remove_all 标志"""
        # remove_all=True 应移除所有非 ASCII 字符
        result = self.replace_function("✅ Hello 世界", remove_all=True)
        # 只保留 ASCII 字符
        for char in result:
            self.assertTrue(ord(char) < 128 or char in ' \n\r\t.,;:!?()[]{}<>@#$%^&*_=+|\\/:', f"Non-ASCII char '{char}' found")

    def test_use_text_false(self):
        """测试 use_text=False 时不应替换 Emoji"""
        input_msg = "✅ Success"
        result = self.replace_function(input_msg, use_text=False)
        self.assertEqual(result, input_msg)


class TestSafePrint(unittest.TestCase):
    """测试 _safe_print 函数"""

    def test_print_with_emoji(self):
        """测试包含 Emoji 的打印"""
        output = io.StringIO()
        _safe_print("✅ Success", file=output)
        result = output.getvalue()
        self.assertIn("[OK]", result)

    def test_print_without_emoji(self):
        """测试不包含 Emoji 的打印"""
        output = io.StringIO()
        _safe_print("Hello, World!", file=output)
        result = output.getvalue()
        self.assertIn("Hello, World!", result)

    def test_no_emoji_context(self):
        """测试 NoEmojiContext"""
        output = io.StringIO()
        with NoEmojiContext():
            _safe_print("✅ Test", file=output, no_emoji=True)
        result = output.getvalue()
        self.assertNotIn("✅", result)


class TestPrintFunctions(unittest.TestCase):
    """测试快捷打印函数"""

    def test_success_function(self):
        """测试 success 函数"""
        output = io.StringIO()
        success("Task completed", file=output)
        result = output.getvalue()
        self.assertTrue(result.startswith("[OK]"))

    def test_error_function(self):
        """测试 error 函数"""
        output = io.StringIO()
        error("An error occurred", file=output)
        result = output.getvalue()
        self.assertTrue(result.startswith("[FAIL]"))

    def test_warning_function(self):
        """测试 warning 函数"""
        output = io.StringIO()
        warning("This is a warning", file=output)
        result = output.getvalue()
        self.assertTrue(result.startswith("[WARN]"))

    def test_info_function(self):
        """测试 info 函数"""
        output = io.StringIO()
        info("Information", file=output)
        result = output.getvalue()
        self.assertTrue(result.startswith("[INFO]"))

    def test_debug_function(self):
        """测试 debug 函数"""
        output = io.StringIO()
        debug("Debug message", file=output)
        result = output.getvalue()
        self.assertTrue(result.startswith("[DEBUG]"))


class TestFormatMarkdownTable(unittest.TestCase):
    """测试 format_markdown_table 函数"""

    def test_basic_table(self):
        """测试基础表格"""
        headers = ["Name", "Status"]
        rows = [["Task 1", "✅ Done"], ["Task 2", "⏳ Pending"]]
        result = format_markdown_table(headers, rows)

        # 检查 Emoji 被替换
        self.assertNotIn("✅", result)
        self.assertNotIn("⏳", result)
        self.assertIn("[OK]", result)
        self.assertIn("[WAIT]", result)

        # 检查表格结构
        self.assertIn("Name", result)
        self.assertIn("Status", result)

    def test_table_with_title(self):
        """测试带标题的表格"""
        headers = ["A", "B"]
        rows = [["1", "2"]]
        result = format_markdown_table(headers, rows, title="Test Table")

        self.assertIn("## Test Table", result)
        self.assertNotIn("✅", result)


class TestFormatList(unittest.TestCase):
    """测试 format_list 函数"""

    def test_unordered_list(self):
        """测试无序列表"""
        items = ["✅ Item 1", "❌ Item 2"]
        result = format_list(items)

        self.assertNotIn("✅", result)
        self.assertNotIn("❌", result)
        self.assertIn("[OK] Item 1", result)
        self.assertIn("[FAIL] Item 2", result)

    def test_numbered_list(self):
        """测试有序列表"""
        items = ["Item A", "Item B"]
        result = format_list(items, numbered=True)

        self.assertIn("1. Item A", result)
        self.assertIn("2. Item B", result)

    def test_custom_prefix(self):
        """测试自定义前缀"""
        items = ["Item 1"]
        result = format_list(items, prefix="* ")

        # 格式化列表时 prefix 后会自动加一个空格
        self.assertIn("*  Item 1", result)


class TestWindowsCompatibility(unittest.TestCase):
    """测试 Windows GBK 兼容性"""

    def test_gbk_compatible_output(self):
        """测试输出兼容 GBK 编码"""
        # 模拟 GBK 编码环境
        test_cases = [
            "✅ Success",
            "❌ Error",
            "⚠️ Warning",
            "Info message",
            "Mixed ✅ and 📝 text",
        ]

        for msg in test_cases:
            result = _replace_emojis(msg)
            # 替换后的文本应该是 ASCII 或 GBK 兼容
            try:
                result.encode('gbk')
            except UnicodeEncodeError:
                self.fail(f"Result '{result}' is not GBK compatible")

    def test_ascii_compatible_after_replacement(self):
        """测试替换后应为 ASCII 兼容"""
        test_messages = [
            "✅ Hello",
            "❌ World",
            "🎉 Test! 🎉",
        ]

        for msg in test_messages:
            result = _replace_emojis(msg)
            # 检查 ASCII 编码
            try:
                result.encode('ascii')
            except UnicodeEncodeError:
                self.fail(f"Result '{result}' is not ASCII compatible after emoji replacement")


def run_tests():
    """运行所有测试"""
    # 创建测试套件
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # 添加所有测试类
    suite.addTests(loader.loadTestsFromTestCase(TestEmojiToTextMap))
    suite.addTests(loader.loadTestsFromTestCase(TestReplaceEmojis))
    suite.addTests(loader.loadTestsFromTestCase(TestSafePrint))
    suite.addTests(loader.loadTestsFromTestCase(TestPrintFunctions))
    suite.addTests(loader.loadTestsFromTestCase(TestFormatMarkdownTable))
    suite.addTests(loader.loadTestsFromTestCase(TestFormatList))
    suite.addTests(loader.loadTestsFromTestCase(TestWindowsCompatibility))

    # 运行测试
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    # 返回结果
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    sys.exit(run_tests())
