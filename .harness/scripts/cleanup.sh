#!/bin/bash
# Harness 清理脚本
# 清理备份文件和整理日志文件

set -e

echo "🧹 Harness 清理脚本"
echo "=================="

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

HARNESS_DIR="$(pwd)"

if [ "$1" = "--dry-run" ]; then
    DRY_RUN=true
    echo "🔍 模拟模式（不会实际删除文件）"
else
    DRY_RUN=false
fi

# ============================================================================
# 1. 清理备份文件
# ============================================================================

echo ""
echo "📦 1. 清理备份文件"
echo "-------------------"

# 创建备份目录
BACKUP_DIR="$HARNESS_DIR/.harness/backups"
mkdir -p "$BACKUP_DIR"

echo "📂 备份目录: $BACKUP_DIR"

# 统计旧的 task.json 备份（遗留文件）
backup_count=$(ls $HARNESS_DIR/.harness/task.json.* 2>/dev/null | wc -l)
if [ $backup_count -gt 0 ]; then
    backup_size=$(du -sh $HARNESS_DIR/.harness/task.json.* 2>/dev/null | tail -1 | cut -f1)
    echo "   发现旧 task.json 备份文件: $backup_count 个（总大小: $backup_size）"
    echo "   ℹ️  这些是单文件存储系统迁移前的遗留文件"
else
    echo "   ✅ 没有旧备份文件需要清理"
fi

# 统计 task-index.json 备份
index_backup_count=$(ls $HARNESS_DIR/.harness/task-index.json.* 2>/dev/null | wc -l)
if [ $index_backup_count -gt 0 ]; then
    index_backup_size=$(du -sh $HARNESS_DIR/.harness/task-index.json.* 2>/dev/null | tail -1 | cut -f1)
    echo "   task-index.json 备份文件: $index_backup_count 个（总大小: $index_backup_size）"
fi

# 保留最重要的备份
echo ""
if [ "$DRY_RUN" = false ]; then
    echo "💾 保留重要备份到 backups/ 目录..."

    # 保留 task-index.json 最新备份（如果存在）
    if [ -f "$HARNESS_DIR/.harness/task-index.json.backup" ]; then
        cp "$HARNESS_DIR/.harness/task-index.json.backup" \
           "$BACKUP_DIR/task-index.json.$(date +%Y%m%d_%H%M%S).backup"
        echo "   ✅ 已保留: task-index.json.backup"
    fi

    echo ""
    echo "🗑️  删除旧备份文件..."

    # 删除旧的 task.json 备份（单文件存储系统迁移前的遗留文件）
    if [ $backup_count -gt 0 ]; then
        rm -f $HARNESS_DIR/.harness/task.json.backup_20*
        echo "   ✅ 删除: task.json.backup_20* ($(ls $HARNESS_DIR/.harness/task.json.backup_20* 2>/dev/null | wc -l) 个)"

        rm -f $HARNESS_DIR/.harness/task.json.before_*
        echo "   ✅ 删除: task.json.before_* ($(ls $HARNESS_DIR/.harness/task.json.before_* 2>/dev/null | wc -l) 个)"

        rm -f $HARNESS_DIR/.harness/task.json.backup2
        echo "   ✅ 删除: task.json.backup2"

        rm -f $HARNESS_DIR/.harness/task.json.backup
        echo "   ✅ 删除: task.json.backup（旧文件）"

        rm -f $HARNESS_DIR/.harness/task.json.*
        echo "   ✅ 删除: task.json.* (所有遗留备份)"
    fi

    # 删除旧的 task-index.json 备份（保留最新的）
    rm -f $HARNESS_DIR/.harness/task-index.json.backup_20*
    echo "   ✅ 删除: task-index.json.backup_20* ($(ls $HARNESS_DIR/.harness/task-index.json.backup_20* 2>/dev/null | wc -l) 个)"

    echo ""
    echo "✅ 备份清理完成！"
else
    echo "⚠️  模拟模式：跳过实际删除"
fi

# ============================================================================
# 2. 整理日志文件
# ============================================================================

echo ""
echo "📋 2. 整理日志文件"
echo "-------------------"

# 创建自动化日志目录
AUTOMATION_LOG_DIR="$HARNESS_DIR/.harness/logs/automation"
mkdir -p "$AUTOMATION_LOG_DIR"

# 按年/月创建子目录
CURRENT_YEAR=$(date +%Y)
CURRENT_MONTH=$(date +%m)
mkdir -p "$AUTOMATION_LOG_DIR/$CURRENT_YEAR/$CURRENT_MONTH"

echo "📂 自动化日志目录: $AUTOMATION_LOG_DIR"

# 统计
log_count=$(ls $HARNESS_DIR/.harness/automation_*.log 2>/dev/null | wc -l)
log_size=$(du -sh $HARNESS_DIR/.harness/automation_*.log 2>/dev/null | tail -1 | cut -f1)

echo "   当前日志文件: $log_count 个"
echo "   总大小: $log_size"

if [ "$DRY_RUN" = false ]; then
    echo ""
    echo "📦 移动日志文件到按月归档..."

    # 移动当前月份的日志
    current_month_logs=0
    for log_file in $HARNESS_DIR/.harness/automation_*.log; do
        # 提取日期（文件名格式：automation_YYYYMMDD_HHMMSS.log）
        if [[ $log_file =~ automation_([0-9]{6}) ]]; then
            log_date=${BASH_REMATCH[1]:0:6}  # YYYYMM
            log_year=${log_date:0:4}
            log_month=${log_date:4:2}

            # 确定目标目录
            if [ "$log_year" = "$CURRENT_YEAR" ] && [ "$log_month" = "$CURRENT_MONTH" ]; then
                # 当前月份
                target_dir="$AUTOMATION_LOG_DIR/$CURRENT_YEAR/$CURRENT_MONTH"
            else
                # 归档
                target_dir="$AUTOMATION_LOG_DIR/archive"
                mkdir -p "$target_dir"
            fi

            # 移动文件
            mv "$log_file" "$target_dir/"
            ((current_month_logs++))
        fi
    done

    echo "   ✅ 已移动: $current_month_logs 个日志文件"

    # 压缩归档日志（可选）
    echo ""
    echo "🗜️  压缩归档日志..."
    if [ -d "$AUTOMATION_LOG_DIR/archive" ]; then
        archive_count=$(ls $AUTOMATION_LOG_DIR/archive/*.log 2>/dev/null | wc -l)
        if [ $archive_count -gt 0 ]; then
            cd "$AUTOMATION_LOG_DIR/archive"
            # 按月份分组压缩
            for log_file in *.log; do
                if [[ $log_file =~ automation_([0-9]{6}) ]]; then
                    log_month=${BASH_REMATCH[1]:0:6}
                    gzip -c "$log_file" > "${log_month}.log.gz" 2>/dev/null || true
                    rm -f "$log_file"
                fi
            done
            echo "   ✅ 已压缩归档日志"
        fi
    fi

    echo ""
    echo "✅ 日志整理完成！"
else
    echo "⚠️  模拟模式：跳过实际移动"
fi

# ============================================================================
# 3. 清理其他临时文件
# ============================================================================

echo ""
echo "🧹 3. 清理临时文件"
echo "-------------------"

temp_count=0

# 清理 .tmp 文件
for tmp_file in $(find $HARNESS_DIR/.harness -name "*.tmp" -type f 2>/dev/null); do
    if [ "$DRY_RUN" = false ]; then
        rm -f "$tmp_file"
        echo "   ✅ 删除: $tmp_file"
    fi
    ((temp_count++))
done

echo "   临时文件: $temp_count 个"

# ============================================================================
# 4. 生成清理报告
# ============================================================================

echo ""
echo "📊 清理报告"
echo "==========="

# 统计备份文件
backup_count=$(ls $HARNESS_DIR/.harness/task.json.* 2>/dev/null | wc -l)
backup_size=$(du -sh $HARNESS_DIR/.harness/task.json.* 2>/dev/null | tail -1 | cut -f1)

# 统计日志文件
log_count=$(ls $HARNESS_DIR/.harness/automation_*.log 2>/dev/null | wc -l)

echo "备份文件: $backup_count 个 (剩余)"
echo "日志文件: $log_count 个 (待移动)"

# 统计新的日志目录
if [ -d "$AUTOMATION_LOG_DIR" ]; then
    new_log_count=$(find $AUTOMATION_LOG_DIR -name "*.log" -type f 2>/dev/null | wc -l)
    new_log_size=$(du -sh $AUTOMATION_LOG_DIR 2>/dev/null | tail -1 | cut -f1)
    echo "已整理日志: $new_log_count 个 ($new_log_size)"
fi

echo ""
if [ "$DRY_RUN" = false ]; then
    echo "✅ 清理完成！"
else
    echo "⚠️  模拟模式完成，未实际删除文件"
    echo ""
    echo "💡 执行实际清理，请运行："
    echo "   bash .harness/scripts/cleanup.sh"
fi

echo ""
echo "💡 提示："
echo "   - 重要备份已保存到: .harness/backups/"
echo "   - 自动化日志已归档到: .harness/logs/automation/"
echo "   - 定期清理旧日志（保留最近 3 个月）"
