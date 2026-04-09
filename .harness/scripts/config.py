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

# 核心数据与日志目录 — 严格绑定在 HARNESS_DIR 下
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

# 引擎根目录：HARNESS_DIR 的父级（存放 .gitignore 等）
ENGINE_ROOT = HARNESS_DIR.parent

try:
    from dotenv import load_dotenv

    # 尝试多个 .env 位置 (按优先级)
    env_locations = [
        HARNESS_DIR / ".env",           # .harness/.env (最高优先级)
        HARNESS_DIR / ".env.example",   # .harness/.env.example
        ENGINE_ROOT / ".env",           # 引擎根目录 .env
        ENGINE_ROOT / ".env.example"    # 引擎根目录 .env.example
    ]

    loaded_count = 0
    for env_path in env_locations:
        if env_path.exists():
            load_dotenv(env_path, override=False)
            loaded_count += 1

    if loaded_count > 0:
        print(f"[Config] Loaded {loaded_count} .env file(s)")

except ImportError:
    # 后备：手动解析 .env 文件
    for _env_path in [HARNESS_DIR / ".env", ENGINE_ROOT / ".env"]:
        if _env_path.exists():
            for line in _env_path.read_text(encoding='utf-8', errors='replace').splitlines():
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                if '=' in line:
                    key, _, value = line.partition('=')
                    os.environ.setdefault(key.strip(), value.strip())
    print("WARNING: python-dotenv not installed, using manual .env parsing")


# ==========================================
# 3. PROJECT_ROOT 动态解析 (Workspace Isolation)
# ==========================================

# PROJECT_ROOT: Agent 读写业务代码的工作目录
# 通过 TARGET_WORKSPACE 环境变量指向外部项目
_workspace_raw = os.getenv("TARGET_WORKSPACE", "").strip()

if _workspace_raw:
    _resolved = Path(_workspace_raw).resolve()
    if _resolved.exists():
        PROJECT_ROOT = _resolved
    else:
        # 配置了但路径不存在，回退到 sandbox
        print(f"[Config] WARNING: TARGET_WORKSPACE='{_workspace_raw}' "
              f"does not exist, falling back to sandbox")
        PROJECT_ROOT = ENGINE_ROOT / "sandbox"
else:
    # 未配置，使用 sandbox 隔离
    PROJECT_ROOT = ENGINE_ROOT / "sandbox"

# 确保 sandbox 目录存在（无论是默认还是回退）
if not PROJECT_ROOT.exists():
    PROJECT_ROOT.mkdir(parents=True, exist_ok=True)

# 引擎内部资产路径 — 始终指向 HARNESS_DIR 内部
HARNESS_ASSET_DIR = HARNESS_DIR

# 项目配置文件：先在工作区找，找不到回退到引擎根目录
def _resolve_project_config_path() -> Path:
    """解析 project-config.json 的位置"""
    workspace_cfg = PROJECT_ROOT / "project-config.json"
    if workspace_cfg.exists():
        return workspace_cfg
    # 回退到引擎根目录（兼容现有项目）
    return ENGINE_ROOT / "project-config.json"


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
BASE_SILENCE_TIMEOUT = _get_int("BASE_SILENCE_TIMEOUT", 300)
"""基础活性超时（秒）- 无输出检测"""

MAX_SILENCE_TIMEOUT = _get_int("MAX_SILENCE_TIMEOUT", 600)
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
# 4. 项目配置 (Project Config)
# ==========================================

# 项目配置文件路径（先在工作区找，回退到引擎根目录）
PROJECT_CONFIG_PATH = _resolve_project_config_path()

# 运行时缓存
_project_config_cache: Optional[dict] = None


def get_project_config() -> dict:
    """
    加载并返回项目配置。

    读取 PROJECT_ROOT / project-config.json，
    如果文件不存在则返回空字典。

    首次调用后结果会被缓存，后续调用直接返回缓存。
    """
    global _project_config_cache

    if _project_config_cache is not None:
        return _project_config_cache

    if not PROJECT_CONFIG_PATH.exists():
        _project_config_cache = {}
        return _project_config_cache

    try:
        import json
        raw = PROJECT_CONFIG_PATH.read_text(encoding="utf-8")
        data = json.loads(raw)
        _project_config_cache = data if isinstance(data, dict) else {}
    except Exception:
        _project_config_cache = {}

    return _project_config_cache


def invalidate_project_config_cache() -> None:
    """清除项目配置缓存（配置文件被修改后调用）。"""
    global _project_config_cache
    _project_config_cache = None


def format_project_config_for_prompt(cfg: dict) -> str:
    """
    将项目配置转化为 LLM 友好的 Markdown 文本。

    只输出非空字段，过滤掉值为 None / 空字符串 / 空字典的条目，
    保持 Prompt 简洁。

    Args:
        cfg: get_project_config() 返回的字典

    Returns:
        格式化后的 Markdown 文本
    """
    if not cfg:
        return ""

    lines = ["# [PROJECT GLOBAL CONVENTIONS]", ""]
    has_content = False

    def _section(title: str, data: dict) -> None:
        nonlocal has_content
        section_lines = [f"## {title}", ""]
        for key, value in data.items():
            if isinstance(value, dict):
                # 过滤空值子项
                non_empty = {k: v for k, v in value.items()
                             if v is not None and v != "" and v != {}}
                if not non_empty:
                    continue
                section_lines.append(f"- **{key}**")
                for sk, sv in non_empty.items():
                    if isinstance(sv, dict):
                        sv_str = ", ".join(f"{k2}: {v2}" for k2, v2 in sv.items())
                        section_lines.append(f"  - {sk}: {sv_str}")
                    else:
                        section_lines.append(f"  - {sk}: {sv}")
            elif value is not None and value != "":
                section_lines.append(f"- **{key}**: {value}")
        if len(section_lines) > 2:
            lines.extend(section_lines)
            lines.append("")
            has_content = True

    # 按优先级输出各区块
    _section("Project", cfg.get("project", {}))
    _section("Tech Stack", cfg.get("tech_stack", {}))
    _section("Naming Conventions", cfg.get("naming_conventions", {}))
    _section("API Conventions", cfg.get("api_conventions", {}))
    _section("Database Conventions", cfg.get("database_conventions", {}))
    _section("Code Style", cfg.get("code_style", {}))
    _section("Testing", cfg.get("testing", {}))
    _section("Paths", cfg.get("paths", {}))
    _section("Commands", cfg.get("commands", {}))

    if not has_content:
        return ""

    lines.append("(Above conventions MUST be followed. Do NOT violate any of them.)")
    return "\n".join(lines)


# ==========================================
# 5. 便捷函数
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

    print(f"\n  Project Config: {PROJECT_CONFIG_PATH}")
    cfg = get_project_config()
    if cfg:
        name = cfg.get("project", {}).get("name", "")
        fw = cfg.get("tech_stack", {}).get("framework", "")
        print(f"   name={name or '(empty)'}, framework={fw or '(empty)'}")
    else:
        print("   (not configured)")

    print("\n" + "=" * 60 + "\n")


if __name__ == "__main__":
    # 直接运行此文件时打印配置
    print_config()
