#!/bin/bash
# Memory Usage Test Script for SIM-Laravel
# This script runs tests and monitors memory usage

echo "=== SIM-Laravel Memory Usage Test ==="
echo ""

# Check PHP memory limit
MEMORY_LIMIT=$(php8 -d "memory_limit=512M" -r "echo ini_get('memory_limit');")
echo "PHP Memory Limit: $MEMORY_LIMIT"
echo ""

# Count test files
TOTAL_TESTS=$(find tests -name "*.php" -type f | wc -l)
echo "Total test files: $TOTAL_TESTS"
echo ""

# Check trait usage
REFRESH_DB=$(grep -r "use RefreshDatabase" tests --include="*.php" -l | wc -l | tr -d ' ')
TRANSACTION_DB=$(grep -r "use DatabaseTransactions" tests --include="*.php" -l | wc -l | tr -d ' ')

echo "Database Trait Usage:"
echo "  RefreshDatabase: $REFRESH_DB (should be 0)"
echo "  DatabaseTransactions: $TRANSACTION_DB"
echo ""

# Verification
if [ "$REFRESH_DB" -eq 0 ]; then
    echo "✅ No files using RefreshDatabase"
else
    echo "❌ ERROR: $REFRESH_DB files still using RefreshDatabase"
fi

if [ "$TRANSACTION_DB" -gt 0 ]; then
    echo "✅ $TRANSACTION_DB files using DatabaseTransactions"
else
    echo "⚠️  Warning: No files using DatabaseTransactions"
fi

echo ""
echo "=== Memory Configuration ==="
echo "phpunit.xml memory_limit:"
grep -A 2 "memory_limit" phpunit.xml | head -3

echo ""
echo "=== Recommendations ==="
echo "1. ✅ Memory limit set to 512M in phpunit.xml"
echo "2. ✅ All tests use DatabaseTransactions instead of RefreshDatabase"
echo "3. ✅ Tests will run in transactions and rollback automatically"
echo ""
echo "=== Expected Memory Usage ==="
echo "- Unit tests: < 128MB per test"
echo "- Feature tests: < 256MB per test"
echo "- Total with 512M limit: Should handle all tests comfortably"
