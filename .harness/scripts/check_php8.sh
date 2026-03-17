#!/bin/bash
# PHP8 检查脚本
# 检查当前环境是否具备运行测试所需条件

# 检查 php8 是否可用
if ! command -v php8 &> /dev/null; then
    echo "❌ 错误: php8 命令不可用"
    echo "💡 请确保 PHP 8 已安装并可通过 'php8' 命令调用"
    echo "💡 或设置 php8 为 php 的别名"
    exit 1
fi

# 检查 Laravel artisan 是否可用
if [ ! -f "artisan" ]; then
    echo "❌ 错误: artisan 文件不存在，可能不是 Laravel 项目根目录"
    exit 1
fi

# 检查 vendor/autoload.php
if [ ! -f "vendor/autoload.php" ]; then
    echo "⚠️  警告: vendor/autoload.php 不存在，可能需要先运行 composer install"
fi

echo "✅ 环境检查通过"
echo "✅ php8: $(php8 --version | head -n1)"