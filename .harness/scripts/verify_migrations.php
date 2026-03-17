<?php

require __DIR__.'/../vendor/autoload.php';

$app = require_once __DIR__.'/../bootstrap/app.php';
$app->make(Illuminate\Contracts\Console\Kernel::class)->bootstrap();

use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

echo "=== SIM_Foundation_001 Migration Test Report ===\n\n";

// Test 1: Check tables exist
echo "1. Tables Existence Check:\n";
echo "   - tenants table: " . (Schema::hasTable('tenants') ? '✓ EXISTS' : '✗ MISSING') . "\n";
echo "   - users table: " . (Schema::hasTable('users') ? '✓ EXISTS' : '✗ MISSING') . "\n";
echo "   - approval_requests table: " . (Schema::hasTable('approval_requests') ? '✓ EXISTS' : '✗ MISSING') . "\n\n";

// Test 2: Check tenants columns
echo "2. Tenants Table Columns:\n";
$tenantsColumns = DB::select('DESCRIBE tenants');
$tenantsColumnNames = array_map(fn($col) => $col->Field, $tenantsColumns);
$requiredTenantsColumns = ['id', 'name', 'code', 'type', 'parent_id', 'balance', 'credit_limit', 'api_secret', 'branding_config', 'status'];
foreach ($requiredTenantsColumns as $col) {
    $exists = in_array($col, $tenantsColumnNames);
    echo "   - " . ($exists ? '✓' : '✗') . " {$col}\n";
}
echo "\n";

// Test 3: Check users columns
echo "3. Users Table Columns:\n";
$usersColumns = DB::select('DESCRIBE users');
$usersColumnNames = array_map(fn($col) => $col->Field, $usersColumns);
$requiredUsersColumns = ['id', 'tenant_id', 'username', 'password_hash', 'approval_level', 'is_mfa_enabled'];
foreach ($requiredUsersColumns as $col) {
    $exists = in_array($col, $usersColumnNames);
    echo "   - " . ($exists ? '✓' : '✗') . " {$col}\n";
}
echo "\n";

// Test 4: Check approval_requests columns
echo "4. Approval_Requests Table Columns:\n";
$approvalColumns = DB::select('DESCRIBE approval_requests');
$approvalColumnNames = array_map(fn($col) => $col->Field, $approvalColumns);
$requiredApprovalColumns = ['id', 'tenant_id', 'requester_id', 'approver_id', 'target_type', 'target_id', 'payload_json', 'status', 'audit_comment'];
foreach ($requiredApprovalColumns as $col) {
    $exists = in_array($col, $approvalColumnNames);
    echo "   - " . ($exists ? '✓' : '✗') . " {$col}\n";
}
echo "\n";

// Test 5: Check indexes
echo "5. Indexes Check:\n";
$tenantsIndexes = DB::select("SHOW INDEX FROM tenants WHERE Key_name != 'PRIMARY'");
echo "   - tenants table indexes:\n";
foreach ($tenantsIndexes as $idx) {
    echo "     ✓ {$idx->Key_name} on {$idx->Column_name}\n";
}

$usersIndexes = DB::select("SHOW INDEX FROM users WHERE Key_name != 'PRIMARY'");
echo "   - users table indexes:\n";
foreach ($usersIndexes as $idx) {
    echo "     ✓ {$idx->Key_name} on {$idx->Column_name}\n";
}

$approvalIndexes = DB::select("SHOW INDEX FROM approval_requests WHERE Key_name != 'PRIMARY'");
echo "   - approval_requests table indexes:\n";
foreach ($approvalIndexes as $idx) {
    echo "     ✓ {$idx->Key_name} on {$idx->Column_name}\n";
}
echo "\n";

// Test 6: Check data types
echo "6. Critical Column Data Types:\n";
$tenantsTypeMap = [];
foreach ($tenantsColumns as $col) {
    $tenantsTypeMap[$col->Field] = $col->Type;
}
echo "   - tenants.code: {$tenantsTypeMap['code']} (expected: varchar(50))\n";
echo "   - tenants.type: {$tenantsTypeMap['type']} (expected: varchar(20))\n";
echo "   - tenants.api_secret: {$tenantsTypeMap['api_secret']} (expected: varchar(64))\n";

$usersTypeMap = [];
foreach ($usersColumns as $col) {
    $usersTypeMap[$col->Field] = $col->Type;
}
echo "   - users.username: {$usersTypeMap['username']} (expected: varchar(50))\n";
echo "   - users.password_hash: {$usersTypeMap['password_hash']} (expected: varchar(255))\n";
echo "\n";

echo "=== Test Complete ===\n";
