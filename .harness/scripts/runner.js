const fs = require('fs');
const path = require('path');
const os = require('os');
const { spawn } = require('child_process');

// 1. 读取 Python 传来的 Prompt 文件
const promptFile = process.argv[2];
if (!promptFile || !fs.existsSync(promptFile)) {
    console.error("Error: Prompt file not found.");
    process.exit(1);
}
const promptText = fs.readFileSync(promptFile, 'utf8');

// 2. 跨平台解析 Claude CLI 的绝对路径
const { execSync } = require('child_process');
const isWindows = os.platform() === 'win32';

function resolveClaudePath() {
    if (isWindows) {
        try {
            const result = execSync('where claude', { encoding: 'utf8' }).trim();
            const lines = result.split(/\r?\n/);
            const cmdLine = lines.find(l => l.endsWith('.cmd'));
            if (cmdLine && fs.existsSync(cmdLine)) {
                return cmdLine;
            }
            if (lines[0] && fs.existsSync(lines[0])) {
                return lines[0];
            }
        } catch (e) {
            console.error("Error: Cannot resolve claude.cmd path via 'where' command.");
            console.error(e.message);
            process.exit(1);
        }
    } else {
        try {
            return execSync('which claude', { encoding: 'utf8' }).trim();
        } catch (e) {
            console.error("Error: Cannot resolve claude path via 'which' command.");
            process.exit(1);
        }
    }
}

const claudeCmd = resolveClaudePath();
if (!fs.existsSync(claudeCmd)) {
    console.error("Error: Claude CLI not found at: " + claudeCmd);
    process.exit(1);
}

// 3. 启动 Claude CLI（不使用 PTY，用 pipe 传 stdin）
//    prompt 不作为命令行参数（Windows 8191 字符限制），
//    而是通过 stdin 管道传入
const env = Object.assign({}, process.env, {
    NO_COLOR: '1',
    FORCE_COLOR: '0',
    PYTHONUNBUFFERED: '1',
    CI: 'true',
    NODE_NO_WARNINGS: '1',
    ANTHROPIC_LOG: 'error',
});

// Windows 下 .cmd 文件必须通过 shell 启动
//    用命令字符串而非 args 数组，避免 DEP0190 警告
const useShell = isWindows;
const spawnCmd = isWindows
    ? `"${claudeCmd}" --print --permission-mode bypassPermissions`
    : claudeCmd;
const spawnArgs = isWindows
    ? []
    : ['--print', '--permission-mode', 'bypassPermissions'];

const child = spawn(spawnCmd, spawnArgs, {
    cwd: process.cwd(),
    env: env,
    stdio: ['pipe', 'pipe', 'pipe'],
    shell: useShell,
});

// 4. 实时流转发：Claude stdout -> Node.js stdout -> Python
child.stdout.on('data', (data) => {
    process.stdout.write(data);
});

// Claude stderr -> Node.js stderr
child.stderr.on('data', (data) => {
    process.stderr.write(data);
});

// 5. 通过 stdin 管道传入 prompt，然后关闭 stdin（触发 EOF）
child.stdin.write(promptText, () => {
    child.stdin.end();
});

// 6. 生命周期管理
child.on('close', (code) => {
    process.exit(code || 0);
});

child.on('error', (err) => {
    console.error("Error spawning Claude CLI:", err.message);
    process.exit(1);
});
