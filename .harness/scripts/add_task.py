#!/usr/bin/env python3
"""
添加新任务到单文件存储系统
使用示例：
    python3 .harness/scripts/add_task.py --id SIM_New_001 \
        --category feature \
        --desc "实现新功能" \
        --priority P1 \
        --acceptance "标准1" "标准2" "标准3"
"""

import sys
import argparse
from pathlib import Path
from datetime import datetime

from console_output import success, error, warning, info

# 导入任务编解码器
from task_utils import TaskCodec

# 导入单文件存储系统
try:
    from task_file_storage import TaskFileStorage
except ImportError:
    error("无法导入 TaskFileStorage")
    sys.exit(1)


def create_task_template(task_id, category, description, priority, acceptance,
                         notes=None, validation_enabled=False,
                         validation_threshold=0.8, validation_max_retries=3):
    """创建任务模板"""
    validation_config = None
    if validation_enabled:
        validation_config = {
            "enabled": True,
            "threshold": validation_threshold,
            "max_retries": validation_max_retries
        }

    return {
        "id": task_id,
        "category": category,
        "description": description,
        "acceptance": acceptance,
        "passes": False,
        "priority": priority,
        "notes": notes or "",
        "validation": validation_config,  # 新增：满意度验证配置
        "stages": {
            "dev": {
                "completed": False,
                "completed_at": None,
                "issues": []
            },
            "test": {
                "completed": False,
                "completed_at": None,
                "issues": [],
                "test_results": {}
            },
            "review": {
                "completed": False,
                "completed_at": None,
                "issues": [],
                "risk_level": None
            }
        },
        "complexity": "medium"
    }


def action_add_task(args):
    """添加新任务"""
    # 验证必需参数
    if not args.id:
        error("需要提供 --id 参数")
        return 1

    if not args.desc:
        error("需要提供 --desc 参数")
        return 1

    if not args.acceptance:
        error("需要提供至少一个 --acceptance 参数")
        return 1

    # 初始化存储
    storage = TaskFileStorage()
    storage.initialize()

    # 检查任务 ID 是否已存在
    all_tasks = storage.load_all_tasks()
    for task in all_tasks:
        if task['id'] == args.id:
            error(f"任务 ID {args.id} 已存在")
            return 1

    # 创建新任务
    new_task = create_task_template(
        task_id=args.id,
        category=args.category or 'feature',
        description=args.desc,
        priority=args.priority or 'P2',
        acceptance=args.acceptance,
        notes=args.notes,
        validation_enabled=args.validation_enabled,
        validation_threshold=args.validation_threshold,
        validation_max_retries=args.validation_max_retries
    )

    # 直接保存到单文件存储
    if storage.save_task(new_task):
        success(f"任务 {args.id} 已添加")
        info(f"   描述: {args.desc}")
        info(f"   类别: {args.category or 'feature'}")
        info(f"   优先级: {args.priority or 'P2'}")
        info(f"   验收标准: {len(args.acceptance)} 项")
        return 0
    else:
        error(f"保存任务 {args.id} 失败")
        return 1


def main():
    parser = argparse.ArgumentParser(
        description='添加新任务到 task.json',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
使用示例
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

【示例 1】添加简单任务（无需满意度验证）
  python3 .harness/scripts/add_task.py --id SIM_Simple_001 \\
    --category feature --desc "实现基础功能" \\
    --priority P2 \\
    --acceptance "文件存在" "方法已实现" "测试通过"

【示例 2】添加中等复杂度任务（启用满意度验证，阈值 0.6）
  python3 .harness/scripts/add_task.py --id SIM_Medium_001 \\
    --category route --desc "注册用户管理路由（10条）" \\
    --priority P0 \\
    --acceptance "routes/api.php 包含 GET /users" "routes/api.php 包含 POST /users" \\
    --validation-enabled \\
    --validation-threshold 0.6 \\
    --validation-max-retries 2 \\
    --notes "中等复杂度，10条路由需要验证映射关系"

【示例 3】添加复杂任务（启用满意度验证，阈值 0.8）
  python3 .harness/scripts/add_task.py --id SIM_Complex_001 \\
    --category test --desc "运行完整测试套件" \\
    --priority P0 \\
    --acceptance "测试通过率 > 80%" "无 500 错误" "Allure 报告已生成" \\
    --validation-enabled \\
    --validation-threshold 0.8 \\
    --validation-max-retries 3 \\
    --notes "复杂任务，需综合评估测试结果、错误分析、报告完整性"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📋 满意度验证使用指南
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

何时启用满意度验证：
  🟢 简单任务 → 不启用 validation
     - 验收标准明确，易于自动验证
     - 示例：备份文件、清除缓存、运行单一命令

  🟡 中等任务 → 启用 validation，threshold: 0.6
     - 需要一定的判断和验证
     - 示例：注册路由（5-10条）、修改配置、数据迁移

  🔴 复杂任务 → 启用 validation，threshold: 0.8-0.9
     - 涉及多个子任务、需要综合评估
     - 示例：完整测试运行、项目最终验收、多模块集成

参数说明：
  --validation-enabled
      启用满意度验证（默认不启用）
      启用后，Review 阶段会调用 Claude 独立评估任务完成质量

  --validation-threshold (0.0-1.0，默认 0.8)
      验证通过阈值
      计算公式：满意度 = 通过的验收标准数 / 总验收标准数
      如果满意度 ≥ threshold → 验证通过
      如果满意度 < threshold → 返回 Dev 阶段重试

  --validation-max-retries (默认 3)
      验证失败后最大重试次数
      达到最大次数仍未通过 → 任务标记为失败

评估流程：
  1. 任务进入 Review 阶段
  2. 系统自动调用 Claude 进行独立评估
  3. Claude 逐一验证 acceptance 标准
  4. 计算满意度并判断是否通过
  5. 通过 → 标记任务完成
  6. 不通过 → 返回 Dev 阶段重试（最多 max_retries 次）
"""
    )

    parser.add_argument('--id', required=True, help='任务 ID (如 SIM_New_001)')
    parser.add_argument('--category', choices=['feature', 'fix', 'controller', 'model', 'migration', 'test', 'style', 'documentation', 'route'],
                        help='任务类别 (feature/fix/controller/model/migration/test/style/documentation/route)')
    parser.add_argument('--desc', required=True, help='任务描述')
    parser.add_argument('--priority', choices=['P0', 'P1', 'P2', 'P3'], help='优先级')
    parser.add_argument('--acceptance', nargs='+', required=True, help='验收标准列表')
    parser.add_argument('--notes', help='备注信息')
    # 新增：满意度验证配置参数
    parser.add_argument('--validation-enabled', action='store_true',
                        help='启用 satisfaction 验证（需在 Review 后调用 Claude 独立评估）')
    parser.add_argument('--validation-threshold', type=float, default=0.8,
                        help='验证通过阈值（0.0-1.0，默认 0.8）')
    parser.add_argument('--validation-max-retries', type=int, default=3,
                        help='验证失败后最大重试次数（默认 3）')

    args = parser.parse_args()

    return action_add_task(args)


if __name__ == '__main__':
    sys.exit(main())
