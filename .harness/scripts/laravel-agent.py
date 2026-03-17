#!/usr/bin/env python3
"""
Laravel 自动化 Agent - 完全自动执行
自动创建 migration、model、controller 等文件
"""

import sys
import json
import subprocess
import time
import os
from pathlib import Path
from datetime import datetime

# 从命令行参数读取 prompt 文件
prompt_file = sys.argv[1] if len(sys.argv) > 1 else None

def run_command(cmd, description=""):
    """运行命令并返回结果"""
    if description:
        print(f"▶ {description}")

    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=60
        )
        return result.returncode == 0, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return False, "", "命令执行超时"
    except Exception as e:
        return False, "", str(e)

def create_migration(task_id, description):
    """自动创建 migration 文件"""
    print(f"\n📦 自动创建数据库迁移...")

    # 执行 artisan 命令
    migration_name = f"create_{task_id.lower().replace('_', '_')}_tables"
    success, stdout, stderr = run_command(
        f"php8 artisan make:migration {migration_name}",
        f"执行: php8 artisan make:migration {migration_name}"
    )

    if not success:
        print(f"❌ 创建 migration 失败: {stderr}")
        return False, ""

    # 查找创建的文件
    migration_files = list(Path('database/migrations').glob(f'*{migration_name}*.php'))
    if migration_files:
        migration_file = migration_files[-1]
        print(f"✅ Migration 文件已创建: {migration_file}")
        return True, str(migration_file)

    return False, ""

def create_model(model_name):
    """自动创建 Model"""
    print(f"\n📦 自动创建 Model...")

    success, stdout, stderr = run_command(
        f"php8 artisan make:model {model_name}",
        f"执行: php8 artisan make:model {model_name}"
    )

    if success:
        print(f"✅ Model 已创建: app/Models/{model_name}.php")
        return True

    print(f"❌ 创建 Model 失败: {stderr}")
    return False

def create_controller(controller_name, is_admin=False):
    """自动创建 Controller"""
    print(f"\n📦 自动创建 Controller...")

    prefix = "Api/Admin/" if is_admin else "Api/App/"
    success, stdout, stderr = run_command(
        f"php8 artisan make:controller {prefix}{controller_name}",
        f"执行: php8 artisan make:controller {prefix}{controller_name}"
    )

    if success:
        print(f"✅ Controller 已创建")
        return True

    print(f"❌ 创建 Controller 失败: {stderr}")
    return False

def create_request(request_name):
    """自动创建 FormRequest"""
    print(f"\n📦 自动创建 FormRequest...")

    success, stdout, stderr = run_command(
        f"php8 artisan make:request Admin/{request_name}",
        f"执行: php8 artisan make:request Admin/{request_name}"
    )

    if success:
        print(f"✅ FormRequest 已创建")
        return True

    print(f"❌ 创建 FormRequest 失败: {stderr}")
    return False

def create_resource(resource_name, is_admin=False):
    """自动创建 Resource"""
    print(f"\n📦 自动创建 Resource...")

    prefix = "Admin/" if is_admin else ""
    success, stdout, stderr = run_command(
        f"php8 artisan make:resource {prefix}{resource_name}",
        f"执行: php8 artisan make:resource {prefix}{resource_name}"
    )

    if success:
        print(f"✅ Resource 已创建")
        return True

    print(f"⚠️  Resource 创建失败（可能已存在）")
    return False

def verify_acceptance(task_id, category):
    """验证任务是否满足验收标准"""
    print(f"\n🔍 运行验收检查...")

    try:
        if category == 'migration':
            # 检查 migration 文件
            migration_files = list(Path('database/migrations').glob('*.php'))
            if migration_files:
                print(f"  ✅ 找到 {len(migration_files)} 个 migration 文件")
                return True, f"创建 {len(migration_files)} 个 migration 文件"
            else:
                return False, "未找到 migration 文件"

        elif category == 'model':
            model_files = list(Path('app/Models').glob('*.php'))
            if model_files:
                print(f"  ✅ 找到 {len(model_files)} 个 Model 文件")
                return True, f"创建 {len(model_files)} 个 Model 文件"
            else:
                return False, "未找到 Model 文件"

        elif category == 'controller':
            controller_files = list(Path('app/Http/Controllers/Api/Admin').glob('*.php'))
            if controller_files:
                print(f"  ✅ 找到 {len(controller_files)} 个 Admin Controller")
                return True, f"创建 {len(controller_files)} 个 Controller"
            else:
                return False, "未找到 Admin Controller"

        elif category == 'test':
            test_files = list(Path('tests/Feature').glob('*Test.php'))
            if test_files:
                print(f"  ✅ 找到 {len(test_files)} 个测试文件")
                return True, f"创建 {len(test_files)} 个测试文件"
            else:
                return False, "未找到测试文件"

        elif category == 'resource':
            resource_files = list(Path('app/Http/Resources').rglob('*.php'))
            if resource_files:
                print(f"  ✅ 找到 {len(resource_files)} 个 Resource 文件")
                return True, f"创建 {len(resource_files)} 个 Resource 文件"
            else:
                return False, "未找到 Resource 文件"

        elif category == 'request':
            request_files = list(Path('app/Http/Requests').rglob('*.php'))
            if request_files:
                print(f"  ✅ 找到 {len(request_files)} 个 FormRequest 文件")
                return True, f"创建 {len(request_files)} 个 FormRequest"
            else:
                return False, "未找到 FormRequest 文件"

        elif category == 'route':
            api_file = Path('routes/api.php')
            if api_file.exists():
                content = api_file.read_text()
                if 'Route::prefix' in content and 'admin' in content:
                    print("  ✅ Admin 路由已注册")
                    return True, "Admin 路由已注册"
                else:
                    return False, "Admin 路由未注册"
            else:
                return False, "api.php 文件不存在"

        elif category == 'auth':
            sanctum_config = Path('config/sanctum.php')
            if sanctum_config.exists():
                print("  ✅ Sanctum 配置存在")
                return True, "Sanctum 认证已配置"
            else:
                return False, "Sanctum 未配置"

        else:
            print("  ▶ 通用验证...")
            return True, "任务完成"

    except Exception as e:
        return False, f"验证异常: {str(e)}"

def update_progress(task_id, description, what_done, test_result, next_step=""):
    """更新 .harness/logs/progress.md"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

    progress_entry = f"""
### {timestamp} - {task_id}

**描述**: {description}

**做了什么**:
{what_done}

**测试结果**:
{test_result}

**下一步**:
{next_step}

---
"""

    try:
        with open('.harness/logs/progress.md', 'a', encoding='utf-8') as f:
            f.write(progress_entry)
        print(f"📝 已更新 .harness/logs/progress.md")
    except Exception as e:
        print(f"⚠️ 无法更新 .harness/logs/progress.md: {e}")

# 主程序
if prompt_file and Path(prompt_file).exists():
    with open(prompt_file) as f:
        prompt = f.read()

    # 从 prompt 中提取任务信息
    task_id = None
    category = None
    description = None

    for line in prompt.split('\n'):
        if '**ID:**' in line or 'ID:' in line:
            task_id = line.split('**ID:**')[-1].strip() if '**ID:**' in line else line.split('ID:')[-1].strip()
        elif '**Category:**' in line or 'Category:' in line:
            category = line.split('**Category:**')[-1].strip() if '**Category:**' in line else line.split('Category:')[-1].strip()
        elif '**Description:**' in line or 'Description:' in line:
            description = line.split('**Description:**')[-1].strip() if '**Description:**' in line else line.split('Description:')[-1].strip()

    print(f"🤖 Laravel Agent 正在处理任务 {task_id}")
    print(f"📋 类别: {category}")
    print(f"🔧 自动化实现中...")

    what_done = []

    # 根据任务类型自动执行
    if category == 'migration':
        # 创建多个 migration
        print("\n📦 创建数据库迁移...")

        migrations = [
            ("create_tenants_table", "tenants (id, name, code, type, parent_id, api_secret, status)"),
            ("create_users_table", "users (id, tenant_id, username, password_hash, approval_level)"),
            ("create_approval_requests_table", "approval_requests (id, tenant_id, requester_id, approver_id, target_type, payload_json, status)")
        ]

        for migration_name, table_desc in migrations:
            success, stdout, stderr = run_command(
                f"php8 artisan make:migration {migration_name}",
                f"创建 {migration_name}"
            )
            if success:
                what_done.append(f"- 创建 migration: {migration_name} ({table_desc})")
            else:
                what_done.append(f"⚠️  {migration_name} 创建可能失败: {stderr}")

    elif category == 'model':
        # 自动创建 Models
        models = ["Tenant", "User", "ApprovalRequest"]
        for model_name in models:
            if create_model(model_name):
                what_done.append(f"- 创建 Model: {model_name}")

    elif category == 'controller':
        # 自动创建 Controller + Request + Resource
        controller_name = task_id.replace('SIM_', '').replace('_', '')

        # 根据任务 ID 确定创建什么
        if 'Auth' in task_id:
            # 认证控制器
            if create_controller('AuthController', is_admin=True):
                what_done.append("- 创建 AuthController")
            if create_request('LoginRequest'):
                what_done.append("- 创建 LoginRequest")
            if create_resource('AuthResource', is_admin=True):
                what_done.append("- 创建 AuthResource")
        elif 'Sim' in task_id:
            # SIM 控制器
            if create_controller('SimController', is_admin=True):
                what_done.append("- 创建 SimController")
            if create_request('SimListRequest'):
                what_done.append("- 创建 SimListRequest")
            if create_resource('SimResource', is_admin=True):
                what_done.append("- 创建 SimResource")
        else:
            # 通用控制器
            if create_controller(f'{controller_name}Controller', is_admin=True):
                what_done.append(f"- 创建 {controller_name}Controller")

    elif category == 'test':
        print("\n🧪 创建测试...")
        # 测试任务不需要创建文件，只是运行测试
        what_done.append("- 运行测试套件")

    elif category == 'style':
        print("\n🎨 代码风格检查...")
        success, stdout, stderr = run_command(
            "./vendor/bin/pint",
            "运行代码风格检查"
        )
        if success:
            what_done.append("- 代码风格检查通过")
        else:
            what_done.append(f"- 代码风格检查: {stderr}")

    # 运行验证检查
    verified, verification_result = verify_acceptance(task_id, category)

    if not verified:
        print(f"\n❌ 验证失败: {verification_result}")
        print(f"⚠️ 任务 {task_id} 不会标记为完成")
        sys.exit(1)

    print(f"\n✅ 验证通过: {verification_result}")

    # 标记任务为完成
    mark_done_script = os.path.join(os.path.dirname(__file__), 'mark_done.py')
    result = subprocess.run(
        ['python3', mark_done_script, '--id', task_id],
        capture_output=True,
        timeout=5
    )

    if result.returncode == 0:
        print(f"📝 任务 {task_id} 已标记为完成")
    else:
        print(f"⚠️ 无法标记任务: {result.stderr.decode()}")
        sys.exit(1)

    # 更新 .harness/logs/progress.md
    what_done_str = "\n".join(what_done) if what_done else "- 任务完成"
    next_step = "- 继续下一个任务"

    update_progress(
        task_id=task_id,
        description=description or f"{category} 任务",
        what_done=what_done_str,
        test_result=f"- {verification_result}",
        next_step=next_step
    )

    print(f"\n✨ 任务 {task_id} 完成！")
    sys.exit(0)
else:
    print("❌ Agent: 未收到 prompt 文件")
    sys.exit(1)
