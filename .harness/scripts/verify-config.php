#!/usr/bin/env php8
<?php

/**
 * SIM-Laravel Configuration Verification Script
 *
 * This script verifies that all PHP and testing configurations are properly set.
 * Usage: php8 .harness/scripts/verify-config.php
 */
echo 'SIM-Laravel Configuration Verification'.PHP_EOL;
echo str_repeat('=', 50).PHP_EOL.PHP_EOL;

$errors = [];
$warnings = [];

// Check Memory Limit
echo 'Checking PHP Memory Limit...'.PHP_EOL;
$memoryLimit = ini_get('memory_limit');
echo "  Current: $memoryLimit".PHP_EOL;
if ($memoryLimit !== '512M') {
    $errors[] = "Memory limit should be 512M, but is $memoryLimit";
    echo '  ❌ FAIL'.PHP_EOL;
} else {
    echo '  ✅ PASS'.PHP_EOL;
}
echo PHP_EOL;

// Check OPcache
echo 'Checking OPcache Configuration...'.PHP_EOL;
$opcacheEnabled = ini_get('opcache.enable');
echo '  OPcache Enabled: '.($opcacheEnabled ? 'Yes' : 'No').PHP_EOL;

if (! $opcacheEnabled) {
    $errors[] = 'OPcache is not enabled';
    echo '  ❌ FAIL'.PHP_EOL;
} else {
    echo '  ✅ PASS'.PHP_EOL;

    $opcacheMemory = ini_get('opcache.memory_consumption');
    echo '  OPcache Memory: '.($opcacheMemory ?: 'Not set').PHP_EOL;
    if ($opcacheMemory && $opcacheMemory < 128) {
        $warnings[] = "OPcache memory_consumption is low ($opcacheMemory), recommended 256";
        echo '  ⚠️  WARNING'.PHP_EOL;
    } else {
        echo '  ✅ PASS'.PHP_EOL;
    }
}
echo PHP_EOL;

// Check Realpath Cache
echo 'Checking Realpath Cache Configuration...'.PHP_EOL;
$realpathCacheSize = ini_get('realpath_cache_size');
$realpathCacheTtl = ini_get('realpath_cache_ttl');

echo '  Cache Size: '.($realpathCacheSize ?: 'Not set').PHP_EOL;
echo '  Cache TTL: '.($realpathCacheTtl ?: 'Not set').' seconds'.PHP_EOL;

if (! $realpathCacheSize || $realpathCacheSize < 4096) {
    $warnings[] = "realpath_cache_size is low ($realpathCacheSize), recommended 8192K";
    echo '  ⚠️  WARNING'.PHP_EOL;
} else {
    echo '  ✅ PASS'.PHP_EOL;
}
echo PHP_EOL;

// Check PHPUnit Configuration
echo 'Checking PHPUnit Configuration...'.PHP_EOL;
$phpunitXml = file_get_contents(__DIR__.'/../../phpunit.xml');
if (strpos($phpunitXml, 'memory_limit" value="512M"') !== false) {
    echo '  PHPUnit memory_limit: 512M'.PHP_EOL;
    echo '  ✅ PASS'.PHP_EOL;
} else {
    $errors[] = 'PHPUnit memory_limit not set to 512M in phpunit.xml';
    echo '  ❌ FAIL'.PHP_EOL;
}
echo PHP_EOL;

// Check .env Testing Configuration
echo 'Checking .env Testing Configuration...'.PHP_EOL;
$envFile = file_get_contents(__DIR__.'/../../.env');
if (strpos($envFile, 'Testing Environment Configuration') !== false) {
    echo '  Testing documentation found in .env'.PHP_EOL;
    echo '  ✅ PASS'.PHP_EOL;
} else {
    $warnings[] = 'Testing configuration documentation not found in .env';
    echo '  ⚠️  WARNING'.PHP_EOL;
}
echo PHP_EOL;

// Summary
echo str_repeat('=', 50).PHP_EOL;
echo 'Summary:'.PHP_EOL;
echo '  Errors: '.count($errors).PHP_EOL;
echo '  Warnings: '.count($warnings).PHP_EOL;
echo PHP_EOL;

if (! empty($errors)) {
    echo '❌ ERRORS:'.PHP_EOL;
    foreach ($errors as $error) {
        echo "  - $error".PHP_EOL;
    }
    echo PHP_EOL;
}

if (! empty($warnings)) {
    echo '⚠️  WARNINGS:'.PHP_EOL;
    foreach ($warnings as $warning) {
        echo "  - $warning".PHP_EOL;
    }
    echo PHP_EOL;
}

if (empty($errors)) {
    echo '✅ All critical configurations are verified!'.PHP_EOL;
    exit(0);
} else {
    echo '❌ Configuration verification failed. Please fix the errors above.'.PHP_EOL;
    exit(1);
}
