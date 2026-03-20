# Harness 四维连贯性保障系统设计

## 概述

针对当前系统连贯性不足的问题，设计四维保障机制：

| 维度 | 目标 | 核心机制 |
|-----|------|---------|
| **A. 依赖管理** | 任务有序执行 | `depends_on` + 产出可见 |
| **B. 上下文传递** | 知识连续传递 | `context` + 决策记录 |
| **C. 系统集成验证** | 整体正确性 | E2E Test + 流程验证 |
| **D. 接口契约强制** | 接口一致性 | Contract + 自动校验 |

---

## A. 依赖管理系统

### 任务格式扩展

```json
{
  "id": "SIM_API_Order_011",
  "category": "controller",
  "priority": "P0",

  "depends_on": {
    "required": [
      {
        "task_id": "SIM_DB_002",
        "stage": "dev",
        "reason": "需要 orders 表结构"
      },
      {
        "task_id": "SIM_Model_003",
        "stage": "dev",
        "reason": "需要 Order 模型"
      }
    ],
    "optional": [
      {
        "task_id": "SIM_SF_007",
        "reason": "顺丰API用于后续物流跟踪"
      }
    ],
    "runtime": [
      {
        "task_id": "SIM_Data_023",
        "reason": "需要种子数据运行测试"
      }
    ]
  },

  "description": "实现订单管理接口"
}
```

### 依赖类型说明

| 类型 | 说明 | 失败行为 | 使用场景 |
|-----|------|---------|---------|
| `required` | 必须完成指定阶段 | 阻塞执行 | 数据结构、模型定义 |
| `optional` | 建议完成 | 仅警告，继续执行 | 可选功能依赖 |
| `runtime` | 运行时需要 | 测试时检查 | 种子数据、配置 |

### 实现逻辑

```python
# next_stage.py 增强逻辑

def check_dependencies(task_id, task):
    """检查任务依赖是否满足"""
    dependencies = task.get('depends_on', {})

    # 检查必需依赖
    for dep in dependencies.get('required', []):
        dep_task = load_task(dep['task_id'])
        required_stage = dep.get('stage', 'dev')

        if not is_stage_completed(dep_task, required_stage):
            return {
                'satisfied': False,
                'reason': f"依赖任务 {dep['task_id']} 的 {required_stage} 阶段未完成",
                'blocking_dep': dep
            }

    # 检查可选依赖（仅警告）
    warnings = []
    for dep in dependencies.get('optional', []):
        dep_task = load_task(dep['task_id'])
        if not is_task_completed(dep_task):
            warnings.append(f"可选依赖 {dep['task_id']} 未完成: {dep.get('reason', '')}")

    return {
        'satisfied': True,
        'warnings': warnings
    }
```

### 产出可见机制

```python
def get_dependency_context(task_id, task):
    """获取依赖任务的产出和上下文"""
    dependencies = task.get('depends_on', {}).get('required', [])
    context = {
        'artifacts': {},      # 文件产出
        'decisions': {},      # 设计决策
        'interfaces': {}      # 接口定义
    }

    for dep in dependencies:
        dep_task_id = dep['task_id']

        # 获取产出文件
        artifacts = load_artifacts(dep_task_id)
        if artifacts:
            context['artifacts'][dep_task_id] = artifacts

        # 获取设计决策
        dep_task = load_task(dep_task_id)
        if dep_task.get('context', {}).get('decisions'):
            context['decisions'][dep_task_id] = dep_task['context']['decisions']

        # 获取接口定义
        if dep_task.get('contracts'):
            context['interfaces'][dep_task_id] = dep_task['contracts']

    return context
```

---

## B. 上下文传递系统

### 任务格式扩展

```json
{
  "id": "SIM_Model_003",
  "category": "model",

  "context": {
    "input_context": {
      "from_task": "SIM_DB_002",
      "received": {
        "migrations": ["orders", "users", "addresses"],
        "schema_decisions": ["使用软删除", "订单状态用枚举"]
      }
    },

    "decisions": [
      {
        "decision": "Order模型使用HasStates trait管理状态",
        "reason": "状态机模式更适合复杂的订单状态流转",
        "alternatives": ["直接用status字段", "用状态模式"],
        "impact": ["OrderService需要适配", "状态变更会自动记录日志"],
        "made_by": "dev_agent",
        "made_at": "2026-03-17T15:53:00"
      },
      {
        "decision": "使用多态关联存储地址",
        "reason": "User和Order都需要地址，避免重复表",
        "alternatives": ["独立的地址表"],
        "impact": ["查询稍复杂", "需要addressable_type字段"],
        "made_by": "dev_agent",
        "made_at": "2026-03-17T15:45:00"
      }
    ],

    "implementation_notes": [
      "Order::status 使用 Spatie\ModelStates",
      "状态枚举定义在 app/States/Order/",
      "状态转换规则在 Order::registerStates()"
    ],

    "gotchas": [
      "Order::create() 时必须提供 status 初始值",
      "软删除订单不影响用户余额"
    ]
  }
}
```

### Agent Prompt 注入

```
## 📚 前置任务上下文

### 依赖任务产出

**SIM_DB_002 (数据库迁移)** 产出文件：
- database/migrations/2026_03_17_create_orders_table.php
- database/migrations/2026_03_17_create_users_table.php

**SIM_DB_002 设计决策**：
1. ✅ 使用软删除 - 数据可恢复，满足审计需求
2. ✅ 订单状态用枚举 - 避免无效状态值
3. ✅ 分离地址表 - 用户可有多个地址

### 关键实现说明

⚠️ **注意点**：
- Order创建时必须设置初始状态为 `pending`
- 用户余额变更必须通过 UserBalanceLog 记录
- 地址软删除后仍可被历史订单引用

### 接口契约

**SIM_DB_002 提供的数据结构**：
```php
// orders 表
Schema::create('orders', function (Blueprint $table) {
    $table->id();
    $table->string('order_no', 32)->unique();
    $table->foreignId('user_id')->constrained();
    $table->enum('status', ['pending', 'approved', ...]);
    $table->decimal('estimated_amount', 10, 2)->default(0);
    // ...
});
```
```

### 实现脚本

```python
# scripts/context_manager.py

class ContextManager:
    """管理任务上下文的传递和继承"""

    def build_agent_context(self, task_id: str, stage: str) -> dict:
        """为 Agent 构建完整的上下文"""
        task = self.storage.load_task(task_id)

        context = {
            'dependencies': self._get_dependency_context(task),
            'project_context': self._get_project_context(),
            'stage_context': self._get_stage_context(task, stage),
            'contracts': self._get_applicable_contracts(task)
        }

        return context

    def record_decision(self, task_id: str, decision: dict):
        """记录设计决策"""
        task = self.storage.load_task(task_id)

        if 'context' not in task:
            task['context'] = {}

        if 'decisions' not in task['context']:
            task['context']['decisions'] = []

        decision['made_at'] = datetime.now().isoformat()
        decision['made_by'] = 'agent'  # 或具体 agent 类型

        task['context']['decisions'].append(decision)
        self.storage.save_task(task)

    def record_gotcha(self, task_id: str, gotcha: str):
        """记录注意事项/陷阱"""
        task = self.storage.load_task(task_id)

        if 'context' not in task:
            task['context'] = {}

        if 'gotchas' not in task['context']:
            task['context']['gotchas'] = []

        task['context']['gotchas'].append(gotcha)
        self.storage.save_task(task)
```

---

## C. 系统集成验证

### E2E 测试任务定义

```json
{
  "id": "SIM_E2E_OrderFlow_031",
  "category": "e2e",
  "priority": "P0",
  "trigger": "on_all_tasks_complete",

  "depends_on": {
    "required": [
      {"task_id": "SIM_API_Auth_009", "reason": "需要认证功能"},
      {"task_id": "SIM_API_Order_011", "reason": "需要订单功能"},
      {"task_id": "SIM_API_User_012", "reason": "需要用户功能"},
      {"task_id": "SIM_Job_014", "reason": "需要队列任务"}
    ]
  },

  "description": "端到端订单流程验证",
  "test_scenarios": [
    {
      "name": "完整回收流程",
      "steps": [
        "用户微信登录",
        "创建/选择地址",
        "提交回收订单",
        "管理员审核订单",
        "顺丰取件",
        "订单结算",
        "用户提现"
      ],
      "assertions": [
        "订单状态流转正确",
        "余额计算准确",
        "日志记录完整"
      ]
    },
    {
      "name": "助力回收流程",
      "steps": [
        "用户A提交订单",
        "用户B助力",
        "订单审核",
        "结算时助力生效"
      ]
    }
  ],

  "acceptance": [
    "tests/E2E/OrderFlowTest.php 存在",
    "php artisan test --group=e2e 全部通过",
    "测试覆盖所有核心业务流程"
  ]
}
```

### E2E 测试文件示例

```php
<?php

namespace Tests\E2E;

use Tests\TestCase;
use App\Models\User;
use App\Models\Address;
use App\Models\Category;
use App\Models\Admin;
use Illuminate\Support\Facades\Queue;
use Illuminate\Foundation\Testing\DatabaseTransactions;

class OrderFlowTest extends TestCase
{
    use DatabaseTransactions;

    /**
     * @group e2e
     * 完整回收流程端到端测试
     */
    public function test_complete_recycling_flow(): void
    {
        Queue::fake();

        // ========== Phase 1: 用户端操作 ==========

        // 1.1 用户登录（模拟微信登录）
        $user = User::factory()->create([
            'openid' => 'test_openid_123',
            'balance' => 0,
        ]);
        $this->actingAs($user, 'sanctum');

        // 1.2 创建地址
        $address = Address::factory()->create([
            'user_id' => $user->id,
            'is_default' => true,
        ]);

        // 1.3 获取品类列表
        $categories = Category::factory()->count(3)->create([
            'is_active' => true,
            'base_price' => 5.00,
        ]);

        // 1.4 提交订单
        $submitResponse = $this->postJson('/api/v1/app/order/submit', [
            'address_id' => $address->id,
            'category_ids' => $categories->pluck('id')->toArray(),
            'remark' => 'E2E测试订单',
            'booking_time' => now()->addDays(2)->format('Y-m-d H:i:s'),
        ]);

        $submitResponse->assertStatus(200)
            ->assertJsonStructure(['data' => ['order_no']]);

        $orderNo = $submitResponse->json('data.order_no');

        // 验证：订单已创建，状态为 pending
        $this->assertDatabaseHas('orders', [
            'order_no' => $orderNo,
            'user_id' => $user->id,
            'status' => 'pending',
        ]);

        // ========== Phase 2: 管理员审核 ==========

        $admin = Admin::factory()->create(['is_active' => true]);
        $this->actingAs($admin, 'admin');

        // 2.1 审核通过订单
        $order = \App\Models\Order::where('order_no', $orderNo)->first();

        $approveResponse = $this->putJson("/api/v1/admin/orders/{$order->id}/approve", [
            'approved' => true,
            'remark' => '审核通过',
        ]);

        $approveResponse->assertStatus(200);

        // 验证：状态变更为 approved
        $this->assertDatabaseHas('orders', [
            'order_no' => $orderNo,
            'status' => 'approved',
        ]);

        // ========== Phase 3: 顺丰取件 ==========

        // 3.1 模拟顺丰回调 - 取件成功
        $sfCallback = $this->postJson('/api/callback/sf/express', [
            'mailno' => 'SF123456789',
            'orderid' => $orderNo,
            'accept_result' => 'SUCCESS',
        ]);

        $sfCallback->assertStatus(200);

        // 验证：订单有快递单号
        $order->refresh();
        $this->assertEquals('SF123456789', $order->mail_no);

        // ========== Phase 4: 订单结算 ==========

        $this->actingAs($user, 'sanctum');

        // 4.1 结算订单
        $settleResponse = $this->postJson("/api/v1/app/order/{$order->id}/settle", [
            'items' => [
                ['category_id' => $categories[0]->id, 'net_weight' => 2.5],
                ['category_id' => $categories[1]->id, 'net_weight' => 1.8],
            ],
        ]);

        $settleResponse->assertStatus(200);

        // 验证：用户余额增加
        $user->refresh();
        $expectedBalance = (2.5 * 5.00) + (1.8 * 5.00); // 21.5
        $this->assertEquals($expectedBalance, $user->balance);

        // 验证：余额变更日志
        $this->assertDatabaseHas('user_balance_logs', [
            'user_id' => $user->id,
            'type' => 'income',
            'amount' => $expectedBalance,
        ]);

        // ========== Phase 5: 用户提现 ==========

        // 5.1 提交提现申请
        $withdrawResponse = $this->postJson('/api/v1/app/user/withdraw', [
            'account_type' => 'wechat',
            'amount' => 20.00,
        ]);

        $withdrawResponse->assertStatus(200);

        // 验证：提现记录已创建
        $this->assertDatabaseHas('withdraws', [
            'user_id' => $user->id,
            'amount' => 20.00,
            'status' => 'pending',
        ]);

        // 验证：用户余额已扣除
        $user->refresh();
        $this->assertEquals(1.5, $user->balance); // 21.5 - 20.00

        // ========== Phase 6: 提现打款 ==========

        $this->actingAs($admin, 'admin');

        // 6.1 审核提现
        $withdraw = \App\Models\Withdraw::where('user_id', $user->id)->first();

        $processWithdraw = $this->putJson("/api/v1/admin/withdraws/{$withdraw->id}/process", [
            'action' => 'approve',
        ]);

        $processWithdraw->assertStatus(200);

        // 6.2 模拟队列执行打款
        $job = new \App\Jobs\ProcessWithdrawJob($withdraw->id);
        $job->handle(app(\App\Services\WechatPaymentService::class));

        // 验证：提现状态变更为成功
        $withdraw->refresh();
        $this->assertEquals('success', $withdraw->status);

        // ========== 最终验证 ==========

        // 验证整个流程的日志完整性
        $this->assertDatabaseHas('order_logs', [
            'order_id' => $order->id,
            'action' => 'created',
        ]);

        $this->assertDatabaseHas('order_logs', [
            'order_id' => $order->id,
            'action' => 'approved',
        ]);

        $this->assertDatabaseHas('order_logs', [
            'order_id' => $order->id,
            'action' => 'settled',
        ]);
    }

    /**
     * @group e2e
     * 助力回收流程测试
     */
    public function test_boost_order_flow(): void
    {
        // 用户A创建订单
        $userA = User::factory()->create();
        $order = \App\Models\Order::factory()->create([
            'user_id' => $userA->id,
            'status' => 'pending',
            'boost_target' => 5, // 目标5次助力
        ]);

        // 用户B助力
        $userB = User::factory()->create();
        $this->actingAs($userB, 'sanctum');

        $boostResponse = $this->postJson('/api/v1/app/share/boost', [
            'order_id' => $order->id,
        ]);

        $boostResponse->assertStatus(200);

        // 验证：助力记录
        $this->assertDatabaseHas('share_logs', [
            'order_id' => $order->id,
            'user_id' => $userB->id,
            'action' => 'boost',
        ]);

        // 验证：订单boost_count增加
        $order->refresh();
        $this->assertEquals(1, $order->boost_count);

        // 结算时验证助力效果
        // ... 更多断言
    }
}
```

### 触发机制

```python
# scripts/trigger_e2e.py

class E2ETrigger:
    """检测并触发E2E测试"""

    def check_and_trigger_e2e(self):
        """检查是否所有核心任务已完成，触发E2E测试"""
        storage = TaskFileStorage()
        all_tasks = storage.load_all_pending_tasks()

        # 检查是否有 E2E 任务
        e2e_tasks = [t for t in all_tasks if t.get('category') == 'e2e']

        for e2e_task in e2e_tasks:
            # 检查依赖是否全部完成
            dependencies = e2e_task.get('depends_on', {}).get('required', [])

            all_deps_complete = all(
                self._is_task_complete(dep['task_id'])
                for dep in dependencies
            )

            if all_deps_complete:
                self._trigger_e2e_test(e2e_task)

    def _trigger_e2e_test(self, e2e_task):
        """执行E2E测试"""
        import subprocess

        result = subprocess.run(
            ['php', 'artisan', 'test', '--group=e2e'],
            capture_output=True,
            text=True
        )

        if result.returncode == 0:
            # 标记E2E任务完成
            self._mark_e2e_complete(e2e_task['id'])
        else:
            # 记录失败原因
            self._record_e2e_failure(e2e_task['id'], result.stderr)
```

---

## D. 接口契约强制

### 全局契约定义

```json
// .harness/contracts/api_standards.json
{
  "version": "1.0.0",
  "updated_at": "2026-03-17",

  "response_format": {
    "success": {
      "code": 0,
      "message": "success",
      "data": {}
    },
    "error": {
      "code": "int > 0",
      "message": "string",
      "errors": "optional|array"
    },
    "pagination": {
      "code": 0,
      "message": "success",
      "data": {
        "list": "array",
        "pagination": {
          "current_page": "int",
          "per_page": "int",
          "total": "int",
          "last_page": "int"
        }
      }
    }
  },

  "status_codes": {
    "200": "成功",
    "201": "创建成功",
    "400": "请求参数错误",
    "401": "未认证",
    "403": "无权限",
    "404": "资源不存在",
    "422": "验证失败",
    "500": "服务器错误"
  },

  "common_fields": {
    "timestamp": "ISO 8601 format",
    "request_id": "UUID v4"
  }
}
```

### 任务契约声明

```json
{
  "id": "SIM_API_Order_011",
  "category": "controller",

  "contracts": {
    "implements": ["api_standards"],

    "endpoints": [
      {
        "method": "POST",
        "path": "/api/v1/app/order/submit",
        "description": "提交回收订单",

        "request": {
          "headers": {
            "Authorization": "Bearer {token}",
            "Content-Type": "application/json"
          },
          "body": {
            "address_id": "required|integer|exists:addresses,id",
            "category_ids": "required|array|min:1",
            "category_ids.*": "integer|exists:categories,id",
            "remark": "nullable|string|max:500",
            "booking_time": "required|date|after:now"
          }
        },

        "responses": {
          "200": {
            "description": "提交成功",
            "body": {
              "code": 0,
              "message": "订单提交成功",
              "data": {
                "order_no": "string",
                "status": "string",
                "created_at": "datetime"
              }
            }
          },
          "422": {
            "description": "验证失败",
            "body": {
              "code": 422,
              "message": "验证失败",
              "errors": {
                "address_id": ["地址不存在"]
              }
            }
          }
        }
      },

      {
        "method": "GET",
        "path": "/api/v1/app/order/list",
        "description": "订单列表",

        "request": {
          "query": {
            "status": "nullable|string|in:pending,approved,completed",
            "page": "nullable|integer|min:1",
            "per_page": "nullable|integer|min:1|max:100"
          }
        },

        "responses": {
          "200": {
            "description": "成功",
            "body": {
              "code": 0,
              "message": "success",
              "data": {
                "list": [
                  {
                    "order_no": "string",
                    "status": "string",
                    "status_text": "string",
                    "estimated_amount": "decimal",
                    "created_at": "datetime"
                  }
                ],
                "pagination": {
                  "current_page": "int",
                  "per_page": "int",
                  "total": "int"
                }
              }
            }
          }
        }
      }
    ]
  }
}
```

### 契约验证器

```php
<?php

namespace App\Console\Commands;

use Illuminate\Console\Command;
use Illuminate\Support\Facades\File;

class ValidateContracts extends Command
{
    protected $signature = 'contracts:validate';
    protected $description = '验证所有接口是否符合契约定义';

    public function handle()
    {
        $contractsPath = '.harness/contracts';
        $violations = [];

        // 1. 加载全局契约
        $globalContract = json_decode(
            File::get("$contractsPath/api_standards.json"),
            true
        );

        // 2. 遍历所有任务，检查契约
        $tasksPath = '.harness/tasks/completed';
        foreach (File::allFiles($tasksPath) as $taskFile) {
            $task = json_decode(File::get($taskFile), true);

            if (!isset($task['contracts'])) {
                continue;
            }

            // 3. 验证每个端点
            foreach ($task['contracts']['endpoints'] ?? [] as $endpoint) {
                $violations = array_merge(
                    $violations,
                    $this->validateEndpoint($endpoint, $globalContract)
                );
            }
        }

        // 4. 输出结果
        if (empty($violations)) {
            $this->info('✅ 所有接口契约验证通过');
            return 0;
        }

        $this->error('❌ 发现契约违规：');
        foreach ($violations as $violation) {
            $this->error("  - {$violation}");
        }

        return 1;
    }

    private function validateEndpoint(array $endpoint, array $globalContract): array
    {
        $violations = [];

        // 检查响应格式是否符合标准
        foreach ($endpoint['responses'] ?? [] as $code => $response) {
            // 检查必须包含 code 字段
            if (!isset($response['body']['code'])) {
                $violations[] = "{$endpoint['method']} {$endpoint['path']}: 响应缺少 code 字段";
            }

            // 检查必须包含 message 字段
            if (!isset($response['body']['message'])) {
                $violations[] = "{$endpoint['method']} {$endpoint['path']}: 响应缺少 message 字段";
            }

            // 检查 data 字段结构
            if (isset($response['body']['data'])) {
                // 检查分页格式
                if (isset($response['body']['data']['pagination'])) {
                    $paginationFields = ['current_page', 'per_page', 'total'];
                    foreach ($paginationFields as $field) {
                        if (!isset($response['body']['data']['pagination'][$field])) {
                            $violations[] = "{$endpoint['method']} {$endpoint['path']}: 分页缺少 {$field} 字段";
                        }
                    }
                }
            }
        }

        return $violations;
    }
}
```

### 自动化集成

```python
# 在 Test 阶段自动验证契约

def run_test_stage(task_id, task):
    """Test 阶段：运行测试并验证契约"""

    # 1. 运行常规测试
    test_result = run_phpunit_tests()

    # 2. 如果任务有契约定义，验证契约
    if task.get('contracts'):
        contract_result = validate_contracts(task)
        if not contract_result['valid']:
            return {
                'passed': False,
                'issues': contract_result['violations']
            }

    return test_result
```

---

## 实施路线图

### Phase 1: 依赖管理 (Week 1)

- [ ] 扩展任务 JSON 格式
- [ ] 修改 `next_stage.py` 检查依赖
- [ ] 增强 `mark-stage` 记录产出
- [ ] 更新 Agent Prompt 显示依赖上下文

### Phase 2: 上下文传递 (Week 2)

- [ ] 实现 `context` 字段记录
- [ ] 创建 `context_manager.py`
- [ ] 设计 Agent Prompt 模板注入
- [ ] 实现决策记录机制

### Phase 3: 契约强制 (Week 3)

- [ ] 定义全局 API 契约
- [ ] 创建契约验证命令
- [ ] 集成到 Test 阶段
- [ ] 创建契约文档生成器

### Phase 4: E2E 测试 (Week 4)

- [ ] 编写核心业务流程 E2E 测试
- [ ] 实现 E2E 任务触发机制
- [ ] 创建测试数据工厂
- [ ] 配置全局验收任务

---

## 预期效果

| 维度 | 增强前 | 增强后 |
|-----|-------|-------|
| **任务执行** | 仅按优先级 | 按依赖关系正确执行 |
| **知识传递** | 无 | 设计决策连续传递 |
| **接口一致性** | 无保障 | 契约强制验证 |
| **系统集成** | 无验证 | E2E 全流程验证 |
| **Bug 发现率** | ~60% | ~90%+ |
| **发布信心** | 中 | 高 |