#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
双重超时机制执行器 (Unix/Mac 版本)
- 使用伪终端解决缓冲死锁问题
- 活性超时：指定时间无输出 → 认为卡死
- 硬超时：超过硬上限 → 强制结束
"""

import os
import pty
import subprocess
import sys
import fcntl
import select
import threading
import time
from typing import List

from console_output import success, error, warning, info


class DualTimeoutExecutor:
    """双重超时机制执行器（PTY 版本）"""

    SILENCE_TIMEOUT = 180  # 3分钟

    def __init__(self, hard_timeout: int, verbose: bool = False):
        self.hard_timeout = hard_timeout
        self.verbose = verbose

    def execute(self, cmd: List[str], input_content: str) -> int:
        # 创建伪终端
        master_fd, slave_fd = pty.openpty()

        if self.verbose:
            info(f'PTY created: master={master_fd}, slave={slave_fd}')

        input_bytes = input_content.encode('utf-8') if input_content else b''

        try:
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=slave_fd,
                stderr=slave_fd,
                text=False,
                close_fds=False
            )

            os.close(slave_fd)

            if self.verbose:
                info(f'Process started: PID={proc.pid}')

            # 设置非阻塞模式
            flags = fcntl.fcntl(master_fd, fcntl.F_GETFL)
            fcntl.fcntl(master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

        except Exception as e:
            os.close(master_fd)
            error(f'启动进程失败: {e}')
            return 1

        last_output_time = [time.time()]
        should_stop = threading.Event()
        start_time = time.time()

        def write_input():
            try:
                if input_bytes:
                    proc.stdin.write(input_bytes)
                    proc.stdin.close()
            except Exception as e:
                if self.verbose:
                    info(f'写入输入失败: {e}')

        write_thread = threading.Thread(target=write_input, daemon=True)
        write_thread.start()

        try:
            last_debug_output = 0

            while True:
                poll_result = proc.poll()
                if poll_result is not None:
                    try:
                        while True:
                            try:
                                chunk = os.read(master_fd, 4096)
                                if not chunk:
                                    break
                                output = chunk.decode('utf-8', errors='ignore')
                                print(output, end='')
                                last_output_time[0] = time.time()
                            except OSError:
                                break
                    except Exception as e:
                        if self.verbose:
                            info(f'读取剩余输出失败: {e}')
                    break

                readable, _, _ = select.select([master_fd], [], [], 0.1)

                if master_fd in readable:
                    try:
                        chunk = os.read(master_fd, 4096)
                        if chunk:
                            output = chunk.decode('utf-8', errors='ignore')
                            print(output, end='')
                            last_output_time[0] = time.time()
                        else:
                            break
                    except OSError:
                        break

                current_time = time.time()
                elapsed = current_time - start_time
                silence_duration = current_time - last_output_time[0]

                if silence_duration > self.SILENCE_TIMEOUT:
                    try:
                        proc.terminate()
                        proc.wait(timeout=2)
                    except:
                        proc.kill()

                    warning(f'Agent 卡死（{self.SILENCE_TIMEOUT}秒无输出）')
                    warning(f'最后输出: {int(silence_duration)}秒前')
                    os.close(master_fd)
                    return 14

                if elapsed > self.hard_timeout:
                    try:
                        proc.kill()
                        proc.wait(timeout=1)
                    except:
                        pass

                    warning(f'Agent 硬超时（超过 {self.hard_timeout}秒）')
                    warning(f'总运行时间: {int(elapsed)}秒')
                    os.close(master_fd)
                    return 124

                if self.verbose and int(elapsed) - last_debug_output >= 30:
                    info(f'运行中: {int(elapsed)}秒, 静默: {int(silence_duration)}秒')
                    last_debug_output = int(elapsed)

                time.sleep(0.05)

        except KeyboardInterrupt:
            proc.kill()
            should_stop.set()
            raise
        except Exception as e:
            proc.kill()
            should_stop.set()
            error(f'执行器异常: {e}')
            os.close(master_fd)
            return 1
        finally:
            try:
                os.close(master_fd)
            except:
                pass

        return proc.returncode


def main():
    """命令行入口"""
    import argparse

    parser = argparse.ArgumentParser(description='双重超时机制执行器 (Unix/Mac)')
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

    # 从标准输入读取内容
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
