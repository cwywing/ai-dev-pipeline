#!/bin/bash

echo "=========================================="
echo "验收标准检查 - SIM_Auth_001"
echo "=========================================="
echo ""

# 检查 1: bootstrap/app.php 包含 EnsureFrontendRequestsAreStateful
if grep -q "EnsureFrontendRequestsAreStateful" bootstrap/app.php; then
    echo "✅ 1. bootstrap/app.php 包含 EnsureFrontendRequestsAreStateful"
else
    echo "❌ 1. bootstrap/app.php 缺少 EnsureFrontendRequestsAreStateful"
fi

# 检查 2: config/sanctum.php 存在并配置
if [ -f "config/sanctum.php" ]; then
    echo "✅ 2. config/sanctum.php 存在"
    # 检查关键配置项
    if grep -q "stateful" config/sanctum.php && \
       grep -q "guard" config/sanctum.php && \
       grep -q "expiration" config/sanctum.php; then
        echo "    ✅ config/sanctum.php 配置完整"
    else
        echo "    ❌ config/sanctum.php 配置不完整"
    fi
else
    echo "❌ 2. config/sanctum.php 不存在"
fi

# 检查 3: User 模型使用 HasApiTokens trait
if grep -q "use HasApiTokens" app/Models/User.php && \
   grep -q "Laravel\\\Sanctum\\\HasApiTokens" app/Models/User.php; then
    echo "✅ 3. User 模型使用 HasApiTokens trait"
else
    echo "❌ 3. User 模型未使用 HasApiTokens trait"
fi

# 检查 4: config/auth.php 配置 sanctum guard
if grep -q "'sanctum'" config/auth.php && \
   grep -q "'driver' => 'sanctum'" config/auth.php; then
    echo "✅ 4. config/auth.php 配置 sanctum guard"
else
    echo "❌ 4. config/auth.php 未配置 sanctum guard"
fi

# 检查测试文件
echo ""
echo "额外创建的文件："
echo "  - tests/Feature/SanctumAuthConfigTest.php"
if [ -f "tests/Feature/SanctumAuthConfigTest.php" ]; then
    echo "    ✅ 存在"
else
    echo "    ❌ 不存在"
fi

echo ""
echo "=========================================="
echo "代码风格检查"
echo "=========================================="
./vendor/bin/pint --test
if [ $? -eq 0 ]; then
    echo "✅ 代码风格检查通过"
else
    echo "❌ 代码风格检查未通过"
fi

echo ""
echo "=========================================="
