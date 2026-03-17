#!/bin/bash

# Swagger/OpenAPI Documentation Generation Script
# This script generates API documentation automatically

set -e

echo "========================================="
echo "Generating Swagger/OpenAPI Documentation"
echo "========================================="

# Change to project directory
cd "$(dirname "$0")/.."

# Run the Laravel Swagger generation command
echo "Running: php8 artisan l5-swagger:generate"
php8 artisan l5-swagger:generate

echo ""
echo "Documentation generated successfully!"
echo "Swagger UI available at: /api/documentation"
echo "JSON docs at: storage/api-docs/api-docs.json"
echo "YAML docs at: storage/api-docs/api-docs.yaml"
