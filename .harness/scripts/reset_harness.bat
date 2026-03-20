@echo off
REM ###############################################################################
REM Harness 系统重置脚本 (Windows版本)
REM 用途：将 Harness 系统恢复到初始状态，清空所有历史数据和任务
REM 使用：cd .harness && scripts\reset_harness.bat
REM ###############################################################################

setlocal enabledelayedexpansion

echo ===================================
echo    Harness 系统重置
echo ===================================
echo.

REM 确认操作
set /p confirm="警告: 此操作将清空所有任务和历史数据，是否继续？(yes/no): "
if not "%confirm%"=="yes" (
    echo 操作已取消
    exit /b 1
)

echo.
echo [1/6] 清空任务数据...
if exist "tasks\pending\*.json" del /q "tasks\pending\*.json" 2>nul
if exist "tasks\completed\" rd /s /q "tasks\completed" 2>nul
echo       √ 已清空 tasks\pending 和 tasks\completed

echo [2/6] 清空运行日志...
if exist "logs\automation\" rd /s /q "logs\automation" 2>nul
if exist "logs\progress.md" del /q "logs\progress.md" 2>nul
echo       √ 已清空 logs 目录

echo [3/6] 清空CLI会话...
if exist "cli-io\current.json" del /q "cli-io\current.json" 2>nul
if exist "cli-io\sessions\" rd /s /q "cli-io\sessions" 2>nul
echo       √ 已清空 cli-io 目录

echo [4/6] 清空产出记录...
if exist "artifacts\" rd /s /q "artifacts" 2>nul
if exist "reports\" rd /s /q "reports" 2>nul
echo       √ 已清空 artifacts 和 reports 目录

echo [5/8] 重置任务索引...
set /p PROJECT_NAME="请输入项目名称: "

REM 使用Python生成新的task-index.json
python -c "import json; from datetime import datetime; data = {'version': 1, 'storage_mode': 'single_file', 'project': '%PROJECT_NAME%', 'created_at': datetime.now().isoformat(), 'updated_at': datetime.now().isoformat(), 'total_tasks': 0, 'pending': 0, 'completed': 0, 'index': {}, 'modules': {}, 'priorities': {}}; f = open('task-index.json', 'w', encoding='utf-8'); json.dump(data, f, indent=2, ensure_ascii=False); f.close(); print('  √ 已创建新的 task-index.json')"

echo [6/8] 初始化知识库...
if not exist "knowledge" mkdir "knowledge"

REM 创建 contracts.json
echo {"version": 1, "services": {}} > knowledge\contracts.json
echo       √ 已创建 knowledge\contracts.json

REM 创建 constraints.json
echo {"version": 1, "global": [], "by_task": {}} > knowledge\constraints.json
echo       √ 已创建 knowledge\constraints.json

echo [7/8] 创建必要的目录结构...
if not exist "tasks\pending" mkdir "tasks\pending"
for /f "tokens=2 delims==" %%I in ('wmic os get localdatetime /value') do set datetime=%%I
set year=%datetime:~0,4%
set month=%datetime:~4,2%
if not exist "tasks\completed\%year%\%month%" mkdir "tasks\completed\%year%\%month%"
if not exist "logs\automation\%year%\%month%" mkdir "logs\automation\%year%\%month%"
if not exist "cli-io\sessions" mkdir "cli-io\sessions"
if not exist "artifacts" mkdir "artifacts"
if not exist "reports" mkdir "reports"
if not exist "knowledge" mkdir "knowledge"
echo       √ 已创建必要的目录

echo [8/8] 验证初始化...
python -c "import json; f=open('task-index.json','r',encoding='utf-8'); d=json.load(f); print('  √ task-index.json 格式正确'); print('  √ 项目名称:', d.get('project','N/A')); print('  √ 版本:', d.get('version','N/A'))"
if exist "knowledge\contracts.json" echo   √ knowledge\contracts.json 已创建
if exist "knowledge\constraints.json" echo   √ knowledge\constraints.json 已创建

echo.
echo ===================================
echo    重置完成！
echo ===================================
echo 项目名称: %PROJECT_NAME%
echo.
echo 已初始化的目录：
echo   - tasks\pending, tasks\completed  (任务存储)
echo   - knowledge\                       (全局知识库)
echo   - artifacts\                       (产出记录)
echo   - logs\                            (运行日志)
echo.
echo 下一步操作：
echo   1. 使用 add_task.py 创建新任务
echo   2. 运行 run-automation.sh 启动自动化
echo.

endlocal