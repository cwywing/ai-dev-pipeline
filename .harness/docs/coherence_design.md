# Harness 连贯性保障机制设计

## 问题分析

### 当前系统的局限性

```
┌─────────────────────────────────────────────────────────────┐
│                   当前执行模式                               │
├─────────────────────────────────────────────────────────────┤
│  任务A ─────► 任务B ─────► 任务C ─────► 任务D              │
│    ↓           ↓           ↓           ↓                   │
│ 单元测试    单元测试     单元测试     单元测试              │
│    ✓          ✓           ✓           ✓                    │
│                                                             │
│  问题：各自独立，无法保证组合正确性                          │
└─────────────────────────────────────────────────────────────┘
```

### 连贯性风险矩阵

| 风险类型 | 描述 | 检测难度 | 影响范围 |
|---------|------|---------|---------|
| 数据模型不一致 | Model关系定义与实际使用不匹配 | 高 | 全局 |
| 业务流程断裂 | 单个功能正常，组合流程失败 | 中 | 核心业务 |
| 接口契约漂移 | 不同版本/模块接口格式不一致 | 低 | API层 |
| 状态机不一致 | 订单等状态在不同地方定义不同 | 中 | 数据层 |
| 配置依赖缺失 | 功能A依赖配置B，但未声明 | 高 | 运行时 |

---

## 解决方案

### 1. 任务依赖声明（depends_on）

```json
{
  "id": "SIM_API_Order_011",
  "depends_on": ["SIM_DB_002", "SIM_Model_003", "SIM_Arch_004"],
  "category": "controller",
  "description": "实现订单管理接口"
}
```

**执行逻辑**：
- 前置任务未完成时，自动跳过当前任务
- 支持可选依赖（`"optional": true`）
- 支持阶段级依赖（`"stage": "dev"`）

### 2. 业务流程测试（E2E Test）

```
┌─────────────────────────────────────────────────────────────┐
│                   业务流程测试                               │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  用户注册 ──► 微信登录 ──► 创建地址 ──► 提交订单           │
│                              │                              │
│                              ▼                              │
│  余额变动 ◄── 订单结算 ◄── 顺丰取件 ◄── 订单审核           │
│                              │                              │
│                              ▼                              │
│                        提现申请 ──► 打款处理                │
│                                                             │
│  ✓ 完整业务链路验证                                        │
│  ✓ 跨模块数据一致性验证                                    │
│  ✓ 状态流转正确性验证                                      │
└─────────────────────────────────────────────────────────────┘
```

### 3. 集成测试套件（Integration Test）

| 测试层级 | 测试内容 | 执行时机 |
|---------|---------|---------|
| Model Integration | Model关系、Scope、Accessor | 每个Model任务完成后 |
| Service Integration | Service间调用、数据流 | 每个Service任务完成后 |
| Controller Integration | API响应格式、中间件 | 每个Controller任务完成后 |
| Feature Integration | 完整功能流程 | 相关任务全部完成后 |

### 4. 全局验收测试（Global Acceptance）

在所有任务完成后执行：

```bash
# 1. 运行完整测试套件
php artisan test

# 2. 检查API文档一致性
php artisan api:validate-docs

# 3. 检查数据库一致性
php artisan db:check-integrity

# 4. 检查代码风格
./vendor/bin/pint --test

# 5. 运行端到端测试
php artisan test --group=e2e
```

---

## 任务文件格式增强

### 新增字段

```json
{
  "id": "SIM_API_Order_011",
  "category": "controller",

  "depends_on": {
    "required": ["SIM_DB_002", "SIM_Model_003"],
    "optional": ["SIM_SF_007"]
  },

  "business_flow": {
    "flows": ["order_create", "order_settle", "order_complete"],
    "test_coverage": "full"
  },

  "integration_test": {
    "enabled": true,
    "test_files": [
      "tests/Feature/Integration/OrderFlowTest.php"
    ]
  },

  "contracts": {
    "input": {
      "address_id": "required|exists:addresses,id",
      "category_ids": "required|array"
    },
    "output": {
      "order_no": "string",
      "status": "string"
    }
  }
}
```

### 依赖类型

| 类型 | 说明 | 失败行为 |
|-----|------|---------|
| `required` | 必须完成 | 阻塞执行 |
| `optional` | 建议完成 | 仅警告 |
| `stage_required` | 特定阶段必须完成 | 阶段阻塞 |

---

## 实施方案

### Phase 1: 依赖声明系统

1. 扩展任务JSON格式，支持 `depends_on`
2. 修改 `next_stage.py`，检查依赖完成状态
3. 生成依赖关系图（可视化）

### Phase 2: 集成测试框架

1. 创建 `tests/Feature/Integration/` 目录
2. 编写核心业务流程测试
3. 集成到自动化流程

### Phase 3: 端到端测试

1. 编写完整业务链路测试
2. 创建测试数据工厂
3. 配置CI/CD流水线

### Phase 4: 全局验收

1. 创建全局验收任务
2. 自动生成测试报告
3. 质量门禁机制

---

## 示例：订单业务流程测试

```php
<?php

namespace Tests\Feature\Integration;

use Tests\TestCase;
use App\Models\User;
use App\Models\Address;
use App\Models\Category;
use Illuminate\Foundation\Testing\DatabaseTransactions;

class OrderBusinessFlowTest extends TestCase
{
    use DatabaseTransactions;

    /**
     * 测试完整订单流程
     */
    public function test_complete_order_flow(): void
    {
        // 1. 用户注册/登录
        $user = User::factory()->create();
        $this->actingAs($user);

        // 2. 创建地址
        $address = Address::factory()->create(['user_id' => $user->id]);

        // 3. 获取品类列表
        $categories = Category::factory()->count(3)->create(['is_active' => true]);

        // 4. 提交订单
        $response = $this->postJson('/api/app/order/submit', [
            'address_id' => $address->id,
            'category_ids' => $categories->pluck('id')->toArray(),
            'remark' => '测试订单',
        ]);

        $response->assertStatus(200)
            ->assertJsonStructure(['data' => ['order_no']]);

        $orderNo = $response->json('data.order_no');

        // 5. 验证订单状态
        $this->assertDatabaseHas('orders', [
            'order_no' => $orderNo,
            'user_id' => $user->id,
            'status' => 'pending',
        ]);

        // 6. 模拟顺丰取件回调
        // ... 后续流程测试
    }
}
```

---

## 质量保障矩阵

| 阶段 | 测试类型 | 覆盖率目标 | 执行频率 |
|-----|---------|-----------|---------|
| 单任务 | 单元测试 | 80%+ | 每次提交 |
| 跨任务 | 集成测试 | 70%+ | 任务完成后 |
| 业务流程 | E2E测试 | 核心流程100% | 每日/发布前 |
| 全局验收 | 全量测试 | 全部通过 | 发布前 |

---

## 总结

### 增强前 vs 增强后

| 维度 | 增强前 | 增强后 |
|-----|-------|-------|
| 任务关系 | 无依赖 | 显式依赖声明 |
| 测试覆盖 | 单元测试 | 单元+集成+E2E |
| 业务验证 | 无 | 流程测试套件 |
| 一致性保证 | 无 | 契约验证 |
| 质量门禁 | 无 | 全局验收 |

### 预期效果

- **Bug发现率**: 60% → 90%+
- **回归风险**: 高 → 低
- **集成成本**: 高 → 低
- **发布信心**: 中 → 高