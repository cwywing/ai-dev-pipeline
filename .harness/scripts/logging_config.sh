#!/bin/bash
# Logging Configuration for Harness Scripts
# 统一的日志文件路径配置

# 设置日志目录（按年/月组织）
LOG_DIR="${LOG_DIR:-.harness/logs/automation}"
CURRENT_YEAR="${CURRENT_YEAR:-$(date +%Y)}"
CURRENT_MONTH="${CURRENT_MONTH:-$(date +%m)}"
mkdir -p "$LOG_DIR/$CURRENT_YEAR/$CURRENT_MONTH"

# 日志文件路径
LOG_FILE="$LOG_DIR/$CURRENT_YEAR/$CURRENT_MONTH/automation$(date +%Y%m%d_%H%M%S).log"
PROGRESS_FILE=".harness/logs/progress.md"
