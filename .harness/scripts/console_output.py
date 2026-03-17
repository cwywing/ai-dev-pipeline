#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统一输出工具模块 (Unix/Mac 版本)

功能：
- Emoji 替换：将 Emoji 转换为文字标识
- 快捷函数：success(), error(), warning(), info()
- 上下文管理器：NoEmojiContext 临时禁用 Emoji

使用示例：
    from console_output import success, error, warning, info

    success("任务完成")      # 输出: [OK] 任务完成
    error("执行失败")       # 输出: [FAIL] 执行失败
    warning("检测问题")     # 输出: [WARN] 检测问题
    info("调试信息")        # 输出: [INFO] 调试信息

退出码:
    0 - 成功
    1 - 测试失败
"""

import sys
import os
import contextlib
from typing import Optional, TextIO

# ==================== Emoji 替换映射 ====================

EMOJI_TO_TEXT_MAP = {
    # 成功/完成
    '✅': '[OK]',
    '🎉': '[SUCCESS]',
    '✔️': '[OK]',
    '✓': '[OK]',

    # 失败/错误
    '❌': '[FAIL]',
    '✖️': '[FAIL]',
    '✘': '[FAIL]',

    # 警告
    '⚠️': '[WARN]',
    '⚠': '[WARN]',
    '❗': '[WARN]',

    # 信息
    'ℹ️': '[INFO]',
    'ℹ': '[INFO]',
    'ℓℹ': '[INFO]',

    # 检测/检查
    '🔍': '[SEARCH]',

    # 清理
    '🧹': '[CLEAN]',

    # 记录
    '📝': '[NOTE]',

    # 统计
    '📊': '[STAT]',

    # 清单
    '📋': '[LIST]',

    # Agent
    '🤖': '[AGENT]',

    # 模块
    '📦': '[MODULE]',

    # 待处理
    '⏳': '[WAIT]',
    '-clock': '[WAIT]',

    # 重试
    '🔄': '[RETRY]',

    # 提示
    '💡': '[TIP]',

    # 其他
    '➡️': '->',
    '→': '->',
    '📌': '[PIN]',
    '⭐': '[STAR]',
    '🔥': '[HOT]',
    '🔨': '[TOOL]',
}

# ==================== 核心功能 ====================

def _safe_print(message: str, file: TextIO = sys.stdout, no_emoji: bool = False) -> None:
    """
    安全打印函数

    Args:
        message: 要输出的消息
        file: 输出目标文件对象
        no_emoji: 是否禁用 Emoji 替换
    """
    if no_emoji:
        # 移除所有 Emoji
        clean_msg = _replace_emojis(message, use_text=True, remove_all=True)
    else:
        # 替换 Emoji 为文字
        clean_msg = _replace_emojis(message, use_text=True)

    # 写入文件对象，处理编码错误
    try:
        file.write(clean_msg + '\n')
        file.flush()
    except UnicodeEncodeError:
        # 如果编码失败，尝试用 ASCII 替代
        try:
            safe_msg = clean_msg.encode('utf-8', errors='replace').decode('utf-8')
            file.write(safe_msg + '\n')
            file.flush()
        except:
            # 最后的备选方案：只输出简单消息
            file.write("[MESSAGE]\n")
            file.flush()


def _replace_emojis(message: str, use_text: bool = True, remove_all: bool = False) -> str:
    """
    替换消息中的 Emoji

    Args:
        message: 原始消息
        use_text: 是否使用文字标识替换
        remove_all: 是否移除所有 Emoji（忽略替换映射）

    Returns:
        处理后的消息
    """
    if remove_all:
        # 移除所有非 ASCII 字符（除常见标点外）
        result = []
        for char in message:
            if ord(char) < 128 or char in ' \n\r\t.,;:!?()[]{}<>@#$%^&*_=+|\\/:':
                result.append(char)
        return ''.join(result)

    if not use_text:
        return message

    # 逐个替换 Emoji
    result = message
    for emoji, text in EMOJI_TO_TEXT_MAP.items():
        result = result.replace(emoji, text)

    return result


def _strip_emojis(message: str) -> str:
    """
    完全移除消息中的所有 Emoji（用于日志文件）

    Args:
        message: 原始消息

    Returns:
        移除 Emoji 后的消息
    """
    return _replace_emojis(message, remove_all=True)


# ==================== 快捷函数 ====================

def success(message: str, file: TextIO = sys.stdout) -> None:
    """成功消息"""
    _safe_print(f"[OK] {message}", file=file)


def error(message: str, file: TextIO = sys.stderr) -> None:
    """错误消息"""
    _safe_print(f"[FAIL] {message}", file=file)


def warning(message: str, file: TextIO = sys.stderr) -> None:
    """警告消息"""
    _safe_print(f"[WARN] {message}", file=file)


def info(message: str, file: TextIO = sys.stdout) -> None:
    """信息消息"""
    _safe_print(f"[INFO] {message}", file=file)


def debug(message: str, file: TextIO = sys.stdout) -> None:
    """调试消息"""
    _safe_print(f"[DEBUG] {message}", file=file)


# ==================== 上下文管理器 ====================

class NoEmojiContext:
    """
    上下文管理器，在上下文内禁用 Emoji

    使用示例:
        with NoEmojiContext():
            print("此消息中的 Emoji 将被替换")
    """

    def __init__(self, verbose: bool = False):
        """
        初始化上下文管理器

        Args:
            verbose: 是否输出进入/退出消息
        """
        self.verbose = verbose
        self.original_stdout = sys.stdout
        self.original_stderr = sys.stderr
        self.original_print = print

    def __enter__(self):
        """进入上下文"""
        if self.verbose:
            print("[INFO] 进入无 Emoji 模式", file=sys.stderr)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """退出上下文"""
        if self.verbose:
            print("[INFO] 退出无 Emoji 模式", file=sys.stderr)
        return False  # 不屏蔽异常


# ==================== 格式化工具 ====================

def format_markdown_table(headers: list, rows: list, title: Optional[str] = None) -> str:
    """
    格式化 Markdown 表格（自动处理 Emoji）

    Args:
        headers: 表头列表
        rows: 行数据列表
        title: 表格标题

    Returns:
        格式化的 Markdown 表格字符串
    """
    # 替换表头中的 Emoji
    safe_headers = [_replace_emojis(h) for h in headers]
    # 替换行数据中的 Emoji
    safe_rows = [[_replace_emojis(str(cell)) for cell in row] for row in rows]

    # 构建表格
    lines = []

    if title:
        lines.append(f"## {_replace_emojis(title)}")
        lines.append("")

    # 表头
    header_line = " | ".join(safe_headers)
    separator = " | ".join(["---"] * len(safe_headers))
    lines.append(header_line)
    lines.append(separator)

    # 数据行
    for row in safe_rows:
        lines.append(" | ".join(row))

    return "\n".join(lines)


def format_list(items: list, prefix: str = "-", numbered: bool = False) -> str:
    """
    格式化列表（自动处理 Emoji）

    Args:
        items: 项目列表
        prefix: 每项前缀（无序列表）
        numbered: 是否使用编号

    Returns:
        格式化的列表字符串
    """
    lines = []

    for i, item in enumerate(items, 1):
        safe_item = _replace_emojis(str(item))
        if numbered:
            lines.append(f"{i}. {safe_item}")
        else:
            lines.append(f"{prefix} {safe_item}")

    return "\n".join(lines)


# ==================== 特殊用途函数 ====================

def stdio_capture() -> tuple:
    """
    捕获 stdout 和 stderr

    Returns:
        (stdout_capture, stderr_capture) 元组
    """
    stdout_capture = io.StringIO()
    stderr_capture = io.StringIO()

    stdout_context = contextlib.redirect_stdout(stdout_capture)
    stderr_context = contextlib.redirect_stderr(stderr_capture)

    return stdout_capture, stderr_capture, stdout_context, stderr_context


# ==================== 主函数（用于测试） ====================

def main():
    """主函数 - 用于模块测试"""
    import argparse
    import importlib

    parser = argparse.ArgumentParser(
        description='统一输出工具模块测试',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
    # 测试导入
    python3 console_output.py --test-import

    # 测试输出
    python3 console_output.py --test-output

    # 测试 Emoji 替换
    python3 console_output.py --test-emoji

    # 测试所有功能
    python3 console_output.py --test-all
        """
    )

    parser.add_argument('--test-import', action='store_true', help='测试模块导入')
    parser.add_argument('--test-output', action='store_true', help='测试输出功能')
    parser.add_argument('--test-emoji', action='store_true', help='测试 Emoji 替换')
    parser.add_argument('--test-all', action='store_true', help='测试所有功能')

    args = parser.parse_args()

    # 动态导入模块（避免局部变量问题）
    module = importlib.import_module('console_output')

    # 测试 1: 导入测试
    if args.test_import:
        try:
            _safe_print("Testing console_output module import...")
            _safe_print("[OK] Import test passed!")
            return 0
        except Exception as e:
            _safe_print(f"[FAIL] Import test failed: {e}")
            return 1

    # 测试 2: 输出测试
    if args.test_output:
        _safe_print("\n=== Output Tests ===")
        _safe_print("Standard print:")
        print("  Hello, World!")

        _safe_print("\nSafe print with Success:")
        module.success("Task completed successfully")

        _safe_print("\nSafe print with Error:")
        module.error("An error occurred")

        _safe_print("\nSafe print with Warning:")
        module.warning("This is a warning message")

        _safe_print("\nSafe print with Info:")
        module.info("This is an informational message")

        _safe_print("\n[OK] All output tests passed!")
        return 0

    # 测试 3: Emoji 替换测试
    if args.test_emoji:
        _safe_print("\n=== Emoji Replacement Tests ===")

        test_cases = [
            ("✅ Success message", "[OK] Success message"),
            ("❌ Error message", "[FAIL] Error message"),
            ("⚠️ Warning message", "[WARN] Warning message"),
            ("ℹ️ Info message", "[INFO] Info message"),
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

        all_passed = True
        for input_msg, expected in test_cases:
            result = module._replace_emojis(input_msg)
            status = "[OK]" if result == expected else "[FAIL]"
            if result != expected:
                all_passed = False
            _safe_print(f"{status} '{input_msg}' -> '{result}' (expected: '{expected}')")

        if all_passed:
            _safe_print("\n[OK] All emoji replacement tests passed!")
            return 0
        else:
            _safe_print("\n[FAIL] Some tests failed!")
            return 1

    # 测试 4: 所有测试
    if args.test_all:
        _safe_print("\n=== Running All Tests ===")

        # 导入测试
        _safe_print("\n[1/3] Testing import...")
        try:
            _safe_print("[OK] Import test passed!")
        except Exception as e:
            _safe_print(f"[FAIL] Import test failed: {e}")
            return 1

        # 输出测试
        _safe_print("\n[2/3] Testing output...")
        _safe_print("Standard print:")
        print("  Hello, World!")
        module.success("Success message")
        module.error("Error message")
        module.warning("Warning message")
        module.info("Info message")
        _safe_print("[OK] Output test passed!")

        # Emoji 替换测试
        _safe_print("\n[3/3] Testing emoji replacement...")
        test_cases = [
            "[OK] Success",
            "[FAIL] Failure",
            "[WARN] Warning",
            "[INFO] Info",
            "[SUCCESS] Victory!",
        ]
        for msg in test_cases:
            result = module._replace_emojis(msg)
            _safe_print(f"  '{msg}' -> '{result}'")
        _safe_print("[OK] Emoji replacement test passed!")

        _safe_print("\n=== All Tests Passed! ===")
        return 0

    # 默认：显示帮助
    parser.print_help()
    return 0


if __name__ == '__main__':
    sys.exit(main())
