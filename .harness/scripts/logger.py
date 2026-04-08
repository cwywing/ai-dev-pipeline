"""
Harness 日志系统
====================================

替代原有 Shell 的粗糙日志方案

核心特性:
- 自动轮转: 每天00:00创建新文件
- 自动压缩: 轮转后自动 gzip 压缩
- 终端彩色: 方便实时观察 Agent 状态
- 多级日志: DEBUG/INFO/WARNING/ERROR/SUCCESS
- 异常追踪: 完整堆栈信息

使用方式:
    from scripts.logger import app_logger

    app_logger.info("开始执行任务")
    app_logger.success("任务完成")
    app_logger.error("发生错误")
    app_logger.exception("异常详情")

替代内容:
- logging_config.sh
- cleanup.sh 中的 gzip 压缩逻辑

====================================
"""

import sys
import platform
from pathlib import Path
from datetime import datetime
from typing import Optional

# Windows UTF-8 修复
if platform.system() == 'Windows':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except:
        pass

# 尝试导入 loguru，如果未安装则使用标准 logging
try:
    from loguru import logger as _logger
    LOGURU_AVAILABLE = True
except ImportError:
    import logging
    _logger = logging.getLogger("harness")
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(message)s"
    ))
    _logger.addHandler(handler)
    _logger.setLevel(logging.INFO)
    LOGURU_AVAILABLE = False

from .config import LOG_DIR

# ==========================================
# 日志配置类
# ==========================================

class LogConfig:
    """日志系统配置类"""

    # ANSI 颜色代码
    COLORS = {
        "reset": "\033[0m",
        "black": "\033[30m",
        "red": "\033[31m",
        "green": "\033[32m",
        "yellow": "\033[33m",
        "blue": "\033[34m",
        "magenta": "\033[35m",
        "cyan": "\033[36m",
        "white": "\033[37m"
    }

    @staticmethod
    def setup(
        rotation: str = "00:00",
        retention: str = "30 days",
        compression: str = "gz",
        console_level: str = "INFO",
        file_level: str = "DEBUG"
    ):
        """
        初始化日志系统

        Args:
            rotation: 轮转策略，默认每天午夜
            retention: 保留策略，默认30天
            compression: 压缩格式，默认 gzip
            console_level: 终端日志级别
            file_level: 文件日志级别
        """
        if not LOGURU_AVAILABLE:
            print("⚠️  loguru 未安装，使用基础日志")
            return

        # 移除默认 handler
        _logger.remove()

        # 确保日志目录存在
        LOG_DIR.mkdir(parents=True, exist_ok=True)

        # 获取当前年月用于子目录
        current_year = datetime.now().strftime("%Y")
        current_month = datetime.now().strftime("%m")
        log_subdir = LOG_DIR / current_year / current_month
        log_subdir.mkdir(parents=True, exist_ok=True)

        # 1. 终端输出 - 彩色
        _logger.add(
            sys.stdout,
            format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
            level=console_level,
            colorize=True,
            enqueue=True,  # 多线程安全
            backtrace=False
        )

        # 2. 主日志文件 - 每日轮转
        log_file = log_subdir / "automation_{time:YYYY-MM-DD}.log"
        _logger.add(
            str(log_file),
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{line} | {message}",
            level=file_level,
            rotation=rotation,
            retention=retention,
            compression=compression,
            enqueue=True,
            encoding="utf-8",
            serialize=False,
            backtrace=True,
            diagnose=True
        )

        # 3. 错误日志 - 单独记录
        error_file = log_subdir / "errors_{time:YYYY-MM-DD}.log"
        _logger.add(
            str(error_file),
            format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {name}:{function}:{line}\n{message}\n{exception}",
            level="ERROR",
            rotation="1 week",
            retention="90 days",
            enqueue=True,
            encoding="utf-8",
            backtrace=True,
            diagnose=True
        )

        return log_file

    @staticmethod
    def get_logger():
        """获取 logger 实例"""
        return _logger

    @staticmethod
    def cleanup_old_logs(days: int = 90):
        """
        清理旧日志文件（手动触发）

        Args:
            days: 保留天数
        """
        import time
        from pathlib import Path

        cutoff = time.time() - (days * 86400)
        removed = 0

        for log_file in LOG_DIR.rglob("*.log*"):
            if log_file.stat().st_mtime < cutoff:
                log_file.unlink()
                removed += 1

        return removed


class WindowsEncodingFix:
    """Windows 编码问题修复"""

    @staticmethod
    def apply():
        """应用 Windows 编码修复"""
        if platform.system() == "Windows":
            try:
                # 设置控制台 UTF-8 模式
                import subprocess
                subprocess.run(["chcp", "65001"], shell=True, check=False)

                # 重新配置 stdout/stderr
                if hasattr(sys.stdout, 'reconfigure'):
                    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
                if hasattr(sys.stderr, 'reconfigure'):
                    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

                _logger.debug("Windows UTF-8 编码已应用")
            except Exception as e:
                _logger.warning(f"Windows 编码修复失败: {e}")


class LoggerWrapper:
    """
    日志包装类 - 确保 API 一致性

    无论使用 loguru 还是标准 logging，
    都提供相同的接口：info, debug, warning, error, success
    """

    def __init__(self, logger):
        self._logger = logger
        self._setup_done = False

    def _ensure_setup(self):
        """确保日志系统已初始化"""
        if not self._setup_done:
            WindowsEncodingFix.apply()
            if LOGURU_AVAILABLE:
                LogConfig.setup()
            self._setup_done = True

    def debug(self, message: str):
        self._ensure_setup()
        self._logger.debug(message)

    def info(self, message: str):
        self._ensure_setup()
        self._logger.info(message)

    def warning(self, message: str):
        self._ensure_setup()
        self._logger.warning(message)

    def error(self, message: str):
        self._ensure_setup()
        self._logger.error(message)

    def success(self, message: str):
        """成功日志 - 统一前缀"""
        self._ensure_setup()
        # loguru 有 success 级别，标准 logging 需要手动处理
        if LOGURU_AVAILABLE:
            self._logger.success(message)
        else:
            self._logger.info(f"✅ {message}")

    def exception(self, message: str):
        self._ensure_setup()
        self._logger.exception(message)

    # 标准 logging 接口
    def log(self, level, message):
        self._ensure_setup()
        self._logger.log(level, message)


# ==========================================
# 全局 logger 实例
# ==========================================

# 初始化时自动设置日志系统
app_logger = LoggerWrapper(_logger)


def get_logger():
    """获取已初始化的 logger（确保配置已应用）"""
    app_logger._ensure_setup()
    return app_logger


if __name__ == "__main__":
    # 测试日志系统
    app_logger._ensure_setup()

    print("\n" + "=" * 60)
    print("Harness 日志系统测试")
    print("=" * 60 + "\n")

    app_logger.debug("这是调试信息")
    app_logger.info("这是普通信息")
    app_logger.warning("这是警告信息")
    app_logger.error("这是错误信息")
    app_logger.success("操作成功完成！")

    print("\n" + "-" * 60)

    try:
        1 / 0
    except Exception as e:
        app_logger.exception("捕获到异常")

    print("\n" + "=" * 60)
    print(f"✅ 日志文件位置: {LOG_DIR}")
    print("=" * 60 + "\n")
