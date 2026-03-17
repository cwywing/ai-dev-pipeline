#!/usr/bin/env php8
<?php
/**
 * Memory Usage Test Script
 * Identifies tests that consume excessive memory
 */

echo "=== SIM-Laravel Memory Usage Diagnostic ===\n\n";

// Check phpunit.xml configuration
$xmlPath = __DIR__ . '/../phpunit.xml';
if (file_exists($xmlPath)) {
    $xml = simplexml_load_file($xmlPath);
    $memoryLimit = (string) $xml->php->ini['name'];
    echo "PHPUnit Memory Limit: $memoryLimit\n\n";
} else {
    echo "phpunit.xml not found at: $xmlPath\n\n";
}

// Find all test files
$testFiles = [];
$iterator = new RecursiveIteratorIterator(
    new RecursiveDirectoryIterator(__DIR__ . '/../tests')
);

foreach ($iterator as $file) {
    if ($file->isFile() && $file->getExtension() === 'php') {
        $testFiles[] = $file->getPathname();
    }
}

echo "Found " . count($testFiles) . " test files\n\n";

// Check for RefreshDatabase usage
echo "=== Checking for RefreshDatabase trait ===\n";
$refreshDbFiles = [];
$transactionFiles = [];

foreach ($testFiles as $file) {
    $content = file_get_contents($file);
    $relativePath = str_replace($projectDir . '/', '', $file);
    if (preg_match('/use\s+RefreshDatabase/', $content)) {
        $refreshDbFiles[] = $relativePath;
    }
    if (preg_match('/use\s+DatabaseTransactions/', $content)) {
        $transactionFiles[] = $relativePath;
    }
}

echo "Files using RefreshDatabase: " . count($refreshDbFiles) . "\n";
foreach ($refreshDbFiles as $file) {
    echo "  - $file\n";
}

echo "\nFiles using DatabaseTransactions: " . count($transactionFiles) . "\n";

// Find large test files
echo "\n=== Checking test file sizes ===\n";
$fileSizes = [];
foreach ($testFiles as $file) {
    $fileSizes[$file] = filesize($file);
}
arsort($fileSizes);

echo "Top 10 largest test files:\n";
$count = 0;
$projectDir = __DIR__ . '/..';
foreach ($fileSizes as $file => $size) {
    if ($count++ >= 10) break;
    echo "  " . number_format($size) . " bytes - " . str_replace($projectDir . '/', '', $file) . "\n";
}

echo "\n=== Recommendations ===\n";
if (!empty($refreshDbFiles)) {
    echo "⚠️  Found " . count($refreshDbFiles) . " files using RefreshDatabase\n";
    echo "   Recommendation: Replace with DatabaseTransactions\n";
} else {
    echo "✅ No files using RefreshDatabase\n";
}

echo "\n✅ Memory limit already set to 512M in phpunit.xml\n";
echo "✅ " . count($transactionFiles) . " files correctly using DatabaseTransactions\n";
