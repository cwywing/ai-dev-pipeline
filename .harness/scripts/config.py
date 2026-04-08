"""
Harness Python 架构配置中心
====================================

此文件是整个 Python 架构的"真理之源"

替代内容:
- logging_config.sh
- .env.example
- 分散在各处的环境变量读取

使用方式:
    from scripts.config import HARNESS_DIR, PERMISSION_MODE, BASE_SILENCE_TIMEOUT
    from scripts.logger import app_logger

====================================
"""

import os
import sys
from pathlib import Path
from typing import Optional

# ==========================================
# 1. 路径定义 (Path Definitions)
# ==========================================

# 自动定位项目根目录 (假设此文件在 .harness/scripts/ 下)
SCRIPTS_DIR = Path(__file__).parent.resolve()

HARNESS_DIR = SCRIPTS_DIR.parent

PROJECT_ROOT = HARNESS_DIR.parent

# 核心数据与日志目录
LOG_DIR = HARNESS_DIR / "logs" / "automation"
CLI_IO_DIR = HARNESS_DIR / "cli-io"
TASKS_DIR = HARNESS_DIR / "tasks"
KNOWLEDGE_DIR = HARNESS_DIR / "knowledge"
ARTIFACTS_DIR = HARNESS_DIR / "artifacts"
TEMPLATES_DIR = HARNESS_DIR / "templates"
DOCS_DIR = HARNESS_DIR / "docs"

# 确保必要的目录存在
for d in [LOG_DIR, CLI_IO_DIR, TASKS_DIR, KNOWLEDGE_DIR, ARTIFACTS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ==========================================
# 2. 环境变量加载 (Environment Variables)
# ==========================================

try:
    from dotenv import load_dotenv

    # 尝试多个 .env 位置 (按优先级)
    env_locations = [
        HARNESS_DIR / ".env",           # .harness/.env (最高优先级)
        HARNESS_DIR / ".env.example",   # .harness/.env.example
        PROJECT_ROOT / ".env",          # 项目根目录 .env
        PROJECT_ROOT / ".env.example"   # 项目根目录 .env.example
    ]

    loaded_count = 0
    for env_path in env_locations:
        if env_path.exists():
            load_dotenv(env_path, override=False)
            loaded_count += 1

    if loaded_count > 0:
        print(f"[Config] Loaded {loaded_count} .env file(s)")

except ImportError:
    # Windows UTF-8 修复
    import sys
    if sys.platform == 'win32':
        try:
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        except:
            pass
    print("WARNING: python-dotenv not installed, using default values")
    print("   Install: pip install -r .harness/requirements.txt")


# ==========================================
# 3. 配置项读取 (Configuration Variables)
# ==========================================

def _get_bool(key: str, default: bool) -> bool:
    """获取布尔值配置"""
    return os.getenv(key, str(default)).lower() in ("true", "1", "yes", "on")

def _get_int(key: str, default: int) -> int:
    """获取整数配置"""
    try:
        return int(os.getenv(key, str(default)))
    except ValueError:
        return default

def _get_float(key: str, default: float) -> float:
    """获取浮点数配置"""
    try:
        return float(os.getenv(key, str(default)))
    except ValueError:
        return default

def _get_str(key: str, default: str) -> str:
    """获取字符串配置"""
    return os.getenv(key, default)


# ==========================================
# 核心配置项
# ==========================================

# --- 验证相关 ---
ENABLE_AUTO_VALIDATION = _get_bool("ENABLE_AUTO_VALIDATION", False)
"""是否启用自动满意度验证"""

# --- Claude CLI 配置 ---
PERMISSION_MODE = _get_str("PERMISSION_MODE", "bypassPermissions")
"""Claude CLI 权限模式: bypassPermissions | acceptEdits | dontAsk"""

CLAUDE_CMD = _get_str("CLAUDE_CMD", "claude")
"""Claude CLI 命令"""

PYTHON_CMD = _get_str("PYTHON_CMD", sys.executable)
"""Python 解释器路径"""

# --- 超时配置 ---
BASE_SILENCE_TIMEOUT = _get_int("BASE_SILENCE_TIMEOUT", 60)
"""基础活性超时（秒）- 无输出检测"""

MAX_SILENCE_TIMEOUT = _get_int("MAX_SILENCE_TIMEOUT", 180)
"""最大活性超时（秒）- 防止无限递增"""

TIMEOUT_BACKOFF_FACTOR = _get_float("TIMEOUT_BACKOFF_FACTOR", 1.3)
"""超时递增因子 - 每次重试超时增加 1.3 倍"""

MAX_TIMEOUT_RETRIES = _get_int("MAX_TIMEOUT_RETRIES", 3)
"""最大超时重试次数"""

# --- 循环配置 ---
LOOP_SLEEP = _get_int("LOOP_SLEEP", 2)
"""主循环休眠间隔（秒）"""

MAX_RETRIES = _get_int("MAX_RETRIES", 3)
"""最大逻辑重试次数"""

# --- 跳过检查 ---
SKIP_PHP_CHECK = _get_bool("SKIP_PHP_CHECK", False)
"""跳过 PHP 环境检查"""

# ==========================================
# 4. 便捷函数
# ==========================================

def get_timeout_for_stage(stage: str, retry_count: int = 0) -> int:
    """
    获取指定阶段的超时时间

    Args:
        stage: 阶段名称 (dev|test|review|validation)
        retry_count: 重试次数

    Returns:
        超时时间（秒）
    """
    stage_multipliers = {
        "dev": 4.0,           # Dev 阶段最长
        "test": 3.0,
        "review": 2.0,
        "validation": 1.5
    }

    base = BASE_SILENCE_TIMEOUT
    multiplier = stage_multipliers.get(stage, 1.0)
    backoff = TIMEOUT_BACKOFF_FACTOR ** retry_count

    timeout = int(base * multiplier * backoff)

    # 确保不超过最大值
    return min(timeout, MAX_SILENCE_TIMEOUT)

def get_task_dir(task_id: str, completed: bool = False) -> Path:
    """
    获取任务目录路径

    Args:
        task_id: 任务 ID
        completed: 是否已完成

    Returns:
        任务文件目录
    """
    if completed:
        from datetime import datetime
        year = datetime.now().strftime("%Y")
        month = datetime.now().strftime("%m")
        return TASKS_DIR / "completed" / year / month
    return TASKS_DIR / "pending"

def get_task_file(task_id: str, completed: bool = False) -> Path:
    """
    获取任务文件路径

    Args:
        task_id: 任务 ID
        completed: 是否已完成

    Returns:
        任务 JSON 文件路径
    """
    return get_task_dir(task_id, completed) / f"{task_id}.json"

# ==========================================
# 5. 诊断信息
# ==========================================

def print_config():
    """打印当前配置（调试用）"""
    print("\n" + "=" * 60)
    print("Harness 配置信息")
    print("=" * 60)
    print(f"\n📁 路径配置:")
    print(f"   SCRIPTS_DIR:  {SCRIPTS_DIR}")
    print(f"   HARNESS_DIR:  {HARNESS_DIR}")
    print(f"   PROJECT_ROOT: {PROJECT_ROOT}")
    print(f"   LOG_DIR:      {LOG_DIR}")

    print(f"\n🔧 Claude CLI:")
    print(f"   CLAUDE_CMD:   {CLAUDE_CMD}")
    print(f"   PERMISSION:   {PERMISSION_MODE}")

    print(f"\n⏱️  超时配置:")
    print(f"   BASE:         {BASE_SILENCE_TIMEOUT}s")
    print(f"   MAX:          {MAX_SILENCE_TIMEOUT}s")
    print(f"   BACKOFF:      x{TIMEOUT_BACKOFF_FACTOR}")
    print(f"   MAX_RETRIES:  {MAX_TIMEOUT_RETRIES}")

    print(f"\n🔄 循环配置:")
    print(f"   LOOP_SLEEP:   {LOOP_SLEEP}s")
    print(f"   MAX_RETRIES:  {MAX_RETRIES}")

    print(f"\n✅ 验证配置:")
    print(f"   AUTO_VALIDATION: {ENABLE_AUTO_VALIDATION}")

    print("\n" + "=" * 60 + "\n")


if __name__ == "__main__":
    # 直接运行此文件时打印配置
    print_config()
