#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
双重超时机制执行器（Windows 版本）
- Windows: 使用 subprocess + threading 实现等效功能
- 活性超时：指定时间无输出 → 认为卡死
- 硬超时：超过硬上限 → 强制结束
"""

import os
import shutil
import subprocess
import sys
import threading
import time
from typing import List

from console_output import success, error, warning, info

# ============================================================================
#                      操作系统检测
# ============================================================================
IS_WINDOWS = os.name == 'nt'


# ============================================================================
#                      Windows 版本实现
# ============================================================================
class DualTimeoutExecutor:
    """双重超时机制执行器（Windows 版本）"""

    SILENCE_TIMEOUT = 180  # 3分钟

    def __init__(self, hard_timeout: int, verbose: bool = False):
        self.hard_timeout = hard_timeout
        self.verbose = verbose

    def execute(self, cmd: List[str], input_content: str) -> int:
        input_bytes = input_content.encode('utf-8', errors='surrogateescape') if input_content else b''

        # Windows 上查找命令完整路径
        actual_cmd = cmd.copy()
        use_shell = False
        if cmd:
            cmd_exe = shutil.which(cmd[0])
            if cmd_exe:
                # Windows 上 .CMD/.BAT 文件需要特殊处理
                if cmd_exe.lower().endswith(('.cmd', '.bat')):
                    # 使用 cmd /c 来调用 .cmd 文件，但不使用 shell=True
                    actual_cmd = ['cmd', '/c', cmd_exe] + cmd[1:]
                    use_shell = False  # 不使用 shell=True，避免输出重定向问题
                else:
                    actual_cmd[0] = cmd_exe
                    use_shell = False

        try:
            proc = subprocess.Popen(
                actual_cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=False,
                bufsize=0,
                shell=use_shell
            )

            if self.verbose:
                info(f'Process started: PID={proc.pid}, shell={use_shell}')

        except FileNotFoundError as e:
            error(f'启动进程失败: {e}')
            error(f'命令: {actual_cmd}')
            return 1
        except Exception as e:
            error(f'启动进程失败: {e}')
            return 1

        # 监控变量
        last_output_time = [time.time()]
        start_time = time.time()
        output_buffer = []
        stop_event = threading.Event()

        def read_output():
            bytes_read = 0
            try:
                while not stop_event.is_set():
                    try:
                        chunk = proc.stdout.read(4096)  # 改用 read() 而不是 read1()
                        if chunk:
                            output_buffer.append(chunk)
                            last_output_time[0] = time.time()
                            bytes_read += len(chunk)
                            if self.verbose:
                                info(f'Read {len(chunk)} bytes (total: {bytes_read})')
                        else:
                            if self.verbose:
                                info(f'EOF reached, total bytes: {bytes_read}')
                            break
                    except Exception as e:
                        if self.verbose:
                            info(f'Read exception: {e}')
                        break
                    time.sleep(0.01)
            except Exception as e:
                if self.verbose:
                    info(f'读取输出异常: {e}')

        def write_input():
            try:
                if input_bytes:
                    proc.stdin.write(input_bytes)
                    proc.stdin.close()
            except Exception as e:
                if self.verbose:
                    info(f'写入输入失败: {e}')

        read_thread = threading.Thread(target=read_output, daemon=True)
        write_thread = threading.Thread(target=write_input, daemon=True)
        read_thread.start()
        write_thread.start()

        last_flush_index = [0]

        def flush_output():
            while not stop_event.is_set():
                current_index = len(output_buffer)
                if current_index > last_flush_index[0]:
                    for i in range(last_flush_index[0], current_index):
                        try:
                            output = output_buffer[i].decode('utf-8', errors='surrogateescape')
                            print(output, end='', flush=True)
                        except:
                            try:
                                output = output_buffer[i].decode('gbk', errors='replace')
                                print(output, end='', flush=True)
                            except:
                                pass
                    last_flush_index[0] = current_index
                time.sleep(0.05)

        flush_thread = threading.Thread(target=flush_output, daemon=True)
        flush_thread.start()

        try:
            last_debug_output = 0

            while True:
                poll_result = proc.poll()
                if poll_result is not None:
                    time.sleep(0.1)
                    stop_event.set()

                    for chunk in output_buffer[last_flush_index[0]:]:
                        try:
                            output = chunk.decode('utf-8', errors='surrogateescape')
                            print(output, end='', flush=True)
                        except:
                            try:
                                output = chunk.decode('gbk', errors='replace')
                                print(output, end='', flush=True)
                            except:
                                pass
                    break

                current_time = time.time()
                elapsed = current_time - start_time
                silence_duration = current_time - last_output_time[0]

                if silence_duration > self.SILENCE_TIMEOUT:
                    stop_event.set()
                    try:
                        proc.terminate()
                        proc.wait(timeout=5)
                    except:
                        try:
                            proc.kill()
                        except:
                            pass

                    warning(f'Agent 卡死（{self.SILENCE_TIMEOUT}秒无输出）')
                    warning(f'最后输出: {int(silence_duration)}秒前')
                    return 14

                if elapsed > self.hard_timeout:
                    stop_event.set()
                    try:
                        proc.kill()
                        proc.wait(timeout=2)
                    except:
                        pass

                    warning(f'Agent 硬超时（超过 {self.hard_timeout}秒）')
                    warning(f'总运行时间: {int(elapsed)}秒')
                    return 124

                if self.verbose and int(elapsed) - last_debug_output >= 30:
                    info(f'运行中: {int(elapsed)}秒, 静默: {int(silence_duration)}秒')
                    last_debug_output = int(elapsed)

                time.sleep(0.1)

        except KeyboardInterrupt:
            stop_event.set()
            try:
                proc.kill()
            except:
                pass
            raise
        except Exception as e:
            stop_event.set()
            try:
                proc.kill()
            except:
                pass
            error(f'执行器异常: {e}')
            return 1

        return proc.returncode


def main():
    """命令行入口"""
    import argparse

    parser = argparse.ArgumentParser(description='双重超时机制执行器（Windows 版本）')
    parser.add_argument('--hard-timeout', type=int, required=True,
                        help='硬超时时间（秒）')
    parser.add_argument('--silence-timeout', type=int, default=180,
                        help='活性超时时间（秒），默认180')
    parser.add_argument('--claude-cmd', type=str, required=True,
                        help='Claude 命令路径')
    parser.add_argument('--permission-mode', type=str, default='bypassPermissions',
                        help='权限模式，默认bypassPermissions')
    parser.add_argument('--verbose', action='store_true',
                        help='输出调试信息')

    args = parser.parse_args()

    # 从标准输入读取内容（使用二进制模式）
    try:
        input_bytes = sys.stdin.buffer.read()
        try:
            input_content = input_bytes.decode('utf-8')
        except UnicodeDecodeError:
            input_content = input_bytes.decode('gbk', errors='replace')
    except:
        input_content = sys.stdin.read()

    # 构建命令
    cmd = [args.claude_cmd, '--print', '--permission-mode', args.permission_mode]

    # 创建执行器
    executor = DualTimeoutExecutor(
        hard_timeout=args.hard_timeout,
        verbose=args.verbose
    )
    executor.SILENCE_TIMEOUT = args.silence_timeout

    # 执行命令
    exit_code = executor.execute(cmd, input_content)
    sys.exit(exit_code)


if __name__ == '__main__':
    main()
