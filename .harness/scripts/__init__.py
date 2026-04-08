# Harness Python Scripts Package
# 此目录包含所有 Python 自动化脚本

from .config import (
    HARNESS_DIR,
    PROJECT_ROOT,
    LOG_DIR,
    CLI_IO_DIR,
    TASKS_DIR,
    KNOWLEDGE_DIR,
    ARTIFACTS_DIR,
    PERMISSION_MODE,
    BASE_SILENCE_TIMEOUT,
    MAX_SILENCE_TIMEOUT,
    TIMEOUT_BACKOFF_FACTOR,
    MAX_TIMEOUT_RETRIES,
    LOOP_SLEEP,
    MAX_RETRIES,
    CLAUDE_CMD,
    PYTHON_CMD,
    ENABLE_AUTO_VALIDATION,
    SKIP_PHP_CHECK
)

from .logger import app_logger, LogConfig

__all__ = [
    "HARNESS_DIR",
    "PROJECT_ROOT",
    "LOG_DIR",
    "CLI_IO_DIR",
    "TASKS_DIR",
    "KNOWLEDGE_DIR",
    "ARTIFACTS_DIR",
    "PERMISSION_MODE",
    "BASE_SILENCE_TIMEOUT",
    "MAX_SILENCE_TIMEOUT",
    "TIMEOUT_BACKOFF_FACTOR",
    "MAX_TIMEOUT_RETRIES",
    "LOOP_SLEEP",
    "MAX_RETRIES",
    "CLAUDE_CMD",
    "PYTHON_CMD",
    "ENABLE_AUTO_VALIDATION",
    "SKIP_PHP_CHECK",
    "app_logger",
    "LogConfig"
]
