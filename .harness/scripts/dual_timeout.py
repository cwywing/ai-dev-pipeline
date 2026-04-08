#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
双重超时机制执行器 - 跨平台统一抽象层
====================================

屏蔽 Unix (pty) 与 Windows (threading) 的底层差异，
对外暴露统一的 execute() 接口。

退出码约定:
    0    - 正常退出（由子进程返回）
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
import shutil
import subprocess
import sys
import threading
import time
from typing import List, Optional


# 路径注入
from pathlib import Path
_sys_init_dir = Path(__file__).parent.resolve()
sys.path.insert(0, str(_sys_init_dir.parent))

from scripts.logger import app_logger

_IS_WINDOWS = platform.system() == "Windows"


# ========================================
#  Unix 实现 (PTY)
# ========================================

class _UnixExecutor:
    """基于伪终端的执行器（Linux / macOS）"""

    def execute(self, cmd: list, input_content: str,
                hard_timeout: int, silence_timeout: int,
                verbose: bool = False) -> int:
        import pty
        import fcntl
        import select

        master_fd, slave_fd = pty.openpty()
        input_bytes = input_content.encode("utf-8") if input_content else b""
        proc = None

        try:
            proc = subprocess.Popen(
                cmd, stdin=subprocess.PIPE,
                stdout=slave_fd, stderr=slave_fd,
                text=False, close_fds=False,
            )
            os.close(slave_fd)

            flags = fcntl.fcntl(master_fd, fcntl.F_GETFL)
            fcntl.fcntl(master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

        except Exception as e:
            # 确保 fd 资源不泄露
            try:
                os.close(master_fd)
            except OSError:
                pass
            try:
                os.close(slave_fd)
            except OSError:
                pass
            if proc:
                try:
                    proc.kill()
                    proc.wait(timeout=2)
                except Exception:
                    pass
            app_logger.error(f"PTY 启动失败: {e}")
            return 1

        last_output_time = [time.time()]
        start_time = time.time()

        def write_input():
            try:
                if input_bytes:
                    proc.stdin.write(input_bytes)
                    proc.stdin.close()
            except OSError:
                pass

        threading.Thread(target=write_input, daemon=True).start()

        try:
            while True:
                if proc.poll() is not None:
                    # 进程结束，排空剩余输出
                    try:
                        while True:
                            chunk = os.read(master_fd, 4096)
                            if not chunk:
                                break
                            print(chunk.decode("utf-8", errors="replace"), end="")
                    except OSError:
                        pass
                    break

                readable, _, _ = select.select([master_fd], [], [], 0.1)

                if master_fd in readable:
                    try:
                        chunk = os.read(master_fd, 4096)
                        if chunk:
                            print(chunk.decode("utf-8", errors="replace"), end="")
                            last_output_time[0] = time.time()
                        else:
                            break
                    except OSError:
                        break

                now = time.time()
                elapsed = now - start_time
                silence = now - last_output_time[0]

                if silence > silence_timeout:
                    self._terminate(proc)
                    app_logger.warning(
                        f"Agent 卡死 ({silence_timeout}s 无输出)")
                    return 14

                if elapsed > hard_timeout:
                    self._kill(proc)
                    app_logger.warning(
                        f"Agent 硬超时 (超过 {hard_timeout}s)")
                    return 124

                time.sleep(0.05)

        except KeyboardInterrupt:
            self._kill(proc)
            raise

        finally:
            try:
                os.close(master_fd)
            except OSError:
                pass

        return proc.returncode

    @staticmethod
    def _terminate(proc):
        try:
            proc.terminate()
            proc.wait(timeout=3)
        except Exception:
            proc.kill()

    @staticmethod
    def _kill(proc):
        try:
            proc.kill()
            proc.wait(timeout=1)
        except Exception:
            pass


# ========================================
#  Windows 实现 (threading + subprocess)
# ========================================

class _WindowsExecutor:
    """基于 threading 的执行器（Windows）"""

    def execute(self, cmd: list, input_content: str,
                hard_timeout: int, silence_timeout: int,
                verbose: bool = False) -> int:
        actual_cmd = self._resolve_cmd(cmd)
        input_bytes = input_content.encode("utf-8", errors="surrogateescape") \
            if input_content else b""

        try:
            proc = subprocess.Popen(
                actual_cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=False, bufsize=0,
            )
        except Exception as e:
            app_logger.error(f"进程启动失败: {e}")
            return 1

        last_output_time = [time.time()]
        start_time = time.time()
        output_buffer = []
        stop_event = threading.Event()
        stdin_closed = threading.Event()

        def read_output():
            try:
                while not stop_event.is_set():
                    try:
                        chunk = proc.stdout.read(4096)
                        if chunk:
                            output_buffer.append(chunk)
                            last_output_time[0] = time.time()
                        else:
                            break
                    except Exception:
                        break
                    time.sleep(0.01)
            except Exception:
                pass

        def write_input():
            try:
                if input_bytes:
                    proc.stdin.write(input_bytes)
            except OSError:
                pass
            finally:
                # 无论写入成功与否，必须关闭 stdin
                # 否则子进程可能因 stdin 管道打开而永远不退出
                try:
                    proc.stdin.close()
                except Exception:
                    pass
                stdin_closed.set()

        threading.Thread(target=read_output, daemon=True).start()
        threading.Thread(target=write_input, daemon=True).start()

        flush_idx = [0]

        def flush_loop():
            while not stop_event.is_set():
                end = len(output_buffer)
                if end > flush_idx[0]:
                    for i in range(flush_idx[0], end):
                        self._safe_print(output_buffer[i])
                    flush_idx[0] = end
                time.sleep(0.05)

        threading.Thread(target=flush_loop, daemon=True).start()

        try:
            while True:
                if proc.poll() is not None:
                    # 等待 read 线程将最后的数据写入 buffer
                    stop_event.set()
                    time.sleep(0.2)
                    # 排空全部残余（从 0 开始，而非 flush_idx）
                    for chunk in output_buffer[flush_idx[0]:]:
                        self._safe_print(chunk)
                    break

                now = time.time()
                elapsed = now - start_time
                silence = now - last_output_time[0]

                if silence > silence_timeout:
                    stop_event.set()
                    self._terminate(proc)
                    app_logger.warning(
                        f"Agent 卡死 ({silence_timeout}s 无输出)")
                    return 14

                if elapsed > hard_timeout:
                    stop_event.set()
                    self._kill(proc)
                    app_logger.warning(
                        f"Agent 硬超时 (超过 {hard_timeout}s)")
                    return 124

                time.sleep(0.1)

        except KeyboardInterrupt:
            stop_event.set()
            self._kill(proc)
            raise

        return proc.returncode

    @staticmethod
    def _resolve_cmd(cmd: list) -> list:
        """解析命令路径（Windows .CMD/.BAT 特殊处理）"""
        if not cmd:
            return cmd
        exe = shutil.which(cmd[0])
        if exe:
            if exe.lower().endswith((".cmd", ".bat")):
                return ["cmd", "/c", exe] + cmd[1:]
            return [exe] + cmd[1:]
        # shutil.which 未找到命令时保持原样，
        # 让 Popen 报出明确的 FileNotFoundError
        return cmd

    @staticmethod
    def _safe_print(chunk: bytes) -> None:
        for enc in ("utf-8", "gbk"):
            try:
                print(chunk.decode(enc, errors="replace"), end="", flush=True)
                return
            except Exception:
                continue

    @staticmethod
    def _terminate(proc):
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:
            proc.kill()

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

    自动根据运行平台选择底层实现。
    """

    def __init__(self, hard_timeout: int = 300,
                 silence_timeout: int = 120,
                 verbose: bool = False):
        """
        Args:
            hard_timeout: 硬超时上限（秒）
            silence_timeout: 活性超时（秒），无输出则终止
            verbose: 调试日志
        """
        self.hard_timeout = hard_timeout
        self.silence_timeout = silence_timeout
        self.verbose = verbose

        # 选择平台实现
        if _IS_WINDOWS:
            self._impl = _WindowsExecutor()
            if verbose:
                app_logger.debug("DualTimeout: 使用 Windows 实现")
        else:
            self._impl = _UnixExecutor()
            if verbose:
                app_logger.debug("DualTimeout: 使用 Unix PTY 实现")

    def execute(self, cmd: List[str], input_content: str) -> int:
        """
        执行命令

        Args:
            cmd: 命令及参数列表
            input_content: 通过 stdin 传入的内容

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
