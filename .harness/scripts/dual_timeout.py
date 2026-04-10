#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
双重超时机制执行器 - Node.js 桥接架构
====================================

通过 Node.js 桥接层 (runner.js) 统一所有平台的 Claude CLI 调用，
解决 Windows 下的缓冲/编码/命令行长度限制问题。

架构:
    Python (DualTimeoutExecutor)
        → 写入 prompt 到临时文件
        → 启动 node runner.js (stdin pipe 桥接)
        → 后台线程实时读取 stdout (流式输出)
        → 活性超时 / 硬超时 / 正常退出

退出码约定:
    0    - 正常退出
    14   - 活性超时（SILENCE_TIMEOUT 无输出）
    124  - 硬超时（HARD_TIMEOUT 上限）
    1    - 启动失败 / 其他异常

使用方式:
    from scripts.dual_timeout import DualTimeoutExecutor

    executor = DualTimeoutExecutor(hard_timeout=300, silence_timeout=120)
    exit_code = executor.execute(cmd, prompt)

====================================
"""

import os
import platform
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import List, Optional


# 路径注入
_sys_init_dir = Path(__file__).parent.resolve()
sys.path.insert(0, str(_sys_init_dir.parent))

from scripts.config import CLI_IO_DIR
from scripts.logger import app_logger


# ========================================
#  Runner.js 路径
# ========================================

RUNNER_JS = _sys_init_dir / "runner.js"


def _check_runner_available() -> bool:
    """检查 runner.js 和 node 是否可用"""
    if not RUNNER_JS.exists():
        return False
    # 检查 node 是否可用
    try:
        result = subprocess.run(
            ["node", "--version"],
            capture_output=True, timeout=5
        )
        return result.returncode == 0
    except Exception:
        return False


_RUNNER_AVAILABLE = None


def is_runner_available() -> bool:
    """延迟检测 runner 可用性（带缓存）"""
    global _RUNNER_AVAILABLE
    if _RUNNER_AVAILABLE is None:
        _RUNNER_AVAILABLE = _check_runner_available()
    return _RUNNER_AVAILABLE


# ========================================
#  统一执行器 (Node.js stdin pipe 桥接)
# ========================================

class _BridgeExecutor:
    """
    通过 runner.js 执行 Claude CLI

    runner.js 使用 child_process.spawn + stdin pipe 传入 prompt，
    避开 Windows 命令行长度限制（~8191 字符）。
    """

    def __init__(self, cwd: Optional[Path] = None):
        self.cwd = cwd

    def execute(self, cmd: list, input_content: str,
                hard_timeout: int, silence_timeout: int,
                verbose: bool = False) -> int:
        """
        通过 Node.js 桥接层执行 Claude CLI

        Args:
            cmd: 原始命令列表（仅用于日志，实际由 runner.js 构建）
            input_content: Prompt 文本
            hard_timeout: 硬超时上限（秒）
            silence_timeout: 活性超时（秒）
            verbose: 调试日志

        Returns:
            退出码 (0 / 14 / 124 / 1)
        """
        # 1. 写入 prompt 到临时文件
        prompt_file = CLI_IO_DIR / "current_prompt.md"
        try:
            prompt_file.write_text(input_content, encoding="utf-8")
        except Exception as e:
            app_logger.error(f"写入 prompt 文件失败: {e}")
            return 1

        # 2. 构建命令：node runner.js <prompt_file>
        bridge_cmd = [
            "node",
            str(RUNNER_JS),
            str(prompt_file),
        ]

        # 3. 启动子进程
        env = os.environ.copy()
        env.update({
            "NO_COLOR": "1",
            "FORCE_COLOR": "0",
            "PYTHONUNBUFFERED": "1",
            "CI": "true",
            "ANTHROPIC_LOG": "error",
        })

        try:
            proc = subprocess.Popen(
                bridge_cmd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                cwd=str(self.cwd) if self.cwd else None,
                env=env,
            )
        except FileNotFoundError:
            app_logger.error(
                "runner.js 未找到。请确保 .harness/scripts/runner.js 存在"
            )
            return 1
        except Exception as e:
            app_logger.error(f"进程启动失败: {e}")
            return 1

        # 4. 后台线程实时读取输出
        last_output_time = [time.time()]
        output_buffer = []
        stop_event = threading.Event()

        def read_output():
            try:
                while not stop_event.is_set():
                    chunk = os.read(proc.stdout.fileno(), 4096)
                    if chunk:
                        output_buffer.append(chunk)
                        last_output_time[0] = time.time()
                        # 实时打印
                        try:
                            text = chunk.decode("utf-8", errors="replace")
                            print(text, end="", flush=True)
                        except Exception:
                            pass
                    else:
                        break
            except Exception:
                pass

        reader_thread = threading.Thread(target=read_output, daemon=True)
        reader_thread.start()

        # 5. 主循环：超时检测
        start_time = time.time()
        last_heartbeat = [0.0]

        try:
            while True:
                if proc.poll() is not None:
                    # 进程结束，等待 reader 线程排空
                    stop_event.set()
                    reader_thread.join(timeout=1.0)
                    app_logger.info("Agent 思考完成，输出已捕获！")
                    break

                now = time.time()
                elapsed = now - start_time

                # CI + --print 模式下 Claude CLI 在生成完毕前几乎无输出，
                # 因此 _BridgeExecutor 不设 silence_timeout，仅靠 hard_timeout 兜底。
                if elapsed > hard_timeout:
                    stop_event.set()
                    self._kill(proc)
                    app_logger.warning(
                        f"Agent 硬超时 (超过 {hard_timeout}s)")
                    return 124

                # 心跳提示：每 15 秒打印一次
                if elapsed - last_heartbeat[0] >= 15:
                    last_heartbeat[0] = elapsed
                    app_logger.info(
                        f"Agent 正在思考中... (已耗时 {int(elapsed)}s)")

                time.sleep(0.1)

        except KeyboardInterrupt:
            stop_event.set()
            self._kill(proc)
            raise

        return proc.returncode

    @staticmethod
    def _kill(proc):
        try:
            proc.kill()
            proc.wait(timeout=2)
        except Exception:
            pass


# ========================================
#  Fallback: 原生 subprocess (无 node 时)
# ========================================

class _FallbackExecutor:
    """
    Fallback 执行器（无 node 时使用原生 subprocess）

    使用 subprocess.communicate() 方案，
    不支持实时输出，不支持活性超时。
    """

    def __init__(self, cwd: Optional[Path] = None):
        self.cwd = cwd

    def execute(self, cmd: list, input_content: str,
                hard_timeout: int, silence_timeout: int,
                verbose: bool = False) -> int:
        app_logger.warning(
            "Node.js 不可用，使用 Fallback 执行器"
        )

        # Windows: shutil.which 解析 .cmd 后缀
        if platform.system() == "Windows":
            import shutil
            resolved = shutil.which(cmd[0])
            if resolved:
                cmd = [resolved] + cmd[1:]

        env = os.environ.copy()
        env.update({
            "NO_COLOR": "1",
            "FORCE_COLOR": "0",
            "PYTHONUNBUFFERED": "1",
            "CI": "true",
            "ANTHROPIC_LOG": "error",
        })

        try:
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                cwd=str(self.cwd) if self.cwd else None,
                env=env,
            )
        except Exception as e:
            app_logger.error(f"进程启动失败: {e}")
            return 1

        # 后台线程：写入 stdin（prompt），避免大内容阻塞主线程
        def write_stdin():
            try:
                if input_content:
                    proc.stdin.write(
                        input_content.encode("utf-8", errors="replace")
                    )
                proc.stdin.close()
            except Exception:
                try:
                    proc.stdin.close()
                except Exception:
                    pass

        threading.Thread(target=write_stdin, daemon=True).start()

        # 后台线程：实时读取 stdout 并打印
        stop_event = threading.Event()

        def read_output():
            try:
                while not stop_event.is_set():
                    chunk = os.read(proc.stdout.fileno(), 4096)
                    if chunk:
                        try:
                            text = chunk.decode("utf-8", errors="replace")
                            print(text, end="", flush=True)
                        except Exception:
                            pass
                    else:
                        break
            except Exception:
                pass

        reader_thread = threading.Thread(target=read_output, daemon=True)
        reader_thread.start()

        # 主循环：仅靠 hard_timeout 兜底
        start_time = time.time()
        last_heartbeat = [0.0]

        try:
            while True:
                if proc.poll() is not None:
                    stop_event.set()
                    reader_thread.join(timeout=1.0)
                    app_logger.info("Agent 思考完成，输出已捕获！")
                    break

                if time.time() - start_time > hard_timeout:
                    stop_event.set()
                    self._kill(proc)
                    app_logger.warning(
                        f"Agent 硬超时 (超过 {hard_timeout}s)")
                    return 124

                # 心跳提示：每 15 秒打印一次，消除黑盒等待感
                now = time.time()
                elapsed = now - start_time
                if elapsed - last_heartbeat[0] >= 15:
                    last_heartbeat[0] = elapsed
                    app_logger.info(
                        f"Agent 正在思考中... (已耗时 {int(elapsed)}s)")

                time.sleep(0.1)

        except KeyboardInterrupt:
            stop_event.set()
            self._kill(proc)
            raise

        return proc.returncode

    @staticmethod
    def _kill(proc):
        try:
            proc.kill()
            proc.wait(timeout=2)
        except Exception:
            pass


# ========================================
#  统一对外接口
# ========================================

class DualTimeoutExecutor:
    """
    双重超时机制执行器

    优先使用 Node.js 桥接层（实时输出 + stdin pipe），
    不可用时降级到 Fallback（无实时输出）。
    """

    def __init__(self, hard_timeout: int = 300,
                 silence_timeout: int = 120,
                 verbose: bool = False,
                 cwd: Optional[Path] = None):
        self.hard_timeout = hard_timeout
        self.silence_timeout = silence_timeout
        self.verbose = verbose
        self.cwd = cwd

        if is_runner_available():
            self._impl = _BridgeExecutor(cwd=cwd)
            app_logger.info("DualTimeout: 使用 Node.js 桥接层")
        else:
            self._impl = _FallbackExecutor(cwd=cwd)
            app_logger.warning("DualTimeout: Node.js 不可用，降级到 Fallback")

    def execute(self, cmd: List[str], input_content: str) -> int:
        """
        执行命令

        Args:
            cmd: 命令及参数列表
            input_content: Prompt 文本

        Returns:
            退出码 (0 / 14 / 124 / 1)
        """
        if self.verbose:
            app_logger.debug(
                f"DualTimeout.execute: cmd={cmd[:2]}... "
                f"hard={self.hard_timeout}s silence={self.silence_timeout}s"
            )
        return self._impl.execute(
            cmd=cmd,
            input_content=input_content,
            hard_timeout=self.hard_timeout,
            silence_timeout=self.silence_timeout,
            verbose=self.verbose,
        )
