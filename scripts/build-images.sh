#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

echo "==> Building taskboard:v1.0.0 (Clean/Working Version)..."
docker build \
  --build-arg APP_VERSION=v1.0.0 \
  -t taskboard:v1.0.0 \
  "${ROOT_DIR}/taskboard"

echo "==> Building taskboard:v1.1.0 (Planted Bug Version)..."
docker build \
  --build-arg APP_VERSION=v1.1.0 \
  -t taskboard:v1.1.0 \
  "${ROOT_DIR}/taskboard"

echo "==> Successfully built taskboard:v1.0.0 and taskboard:v1.1.0"
docker images | grep taskboard
