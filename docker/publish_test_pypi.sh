#!/bin/bash
# publish_test_pypi.sh — Build and publish bees-md to test.pypi with a unique dev version.
#
# Usage:
#   ./docker/publish_test_pypi.sh
#
# Outputs the published version string on the last line of stdout.
# Requires: poetry, twine, TestPyPI token in macOS Keychain.
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYPROJECT="${PROJECT_ROOT}/pyproject.toml"

# Read TestPyPI token from Keychain
TEST_PYPI_TOKEN=$(security find-generic-password -s "TestPyPI Token" -w 2>/dev/null || true)
if [[ -z "${TEST_PYPI_TOKEN}" ]]; then
  echo "ERROR: No TestPyPI token in Keychain."
  echo "Add one with: security add-generic-password -s 'TestPyPI Token' -a testpypi -w '<token>'"
  exit 1
fi

# Read current version from pyproject.toml
BASE_VERSION=$(grep -m1 '^version = ' "${PYPROJECT}" | sed 's/version = "//;s/"//')
DEV_VERSION="${BASE_VERSION}.dev$(date +%Y%m%d%H%M%S)"

echo "--- Publishing bees-md ${DEV_VERSION} to test.pypi ---"

# Patch pyproject.toml with dev version (both [project] and [tool.poetry] sections)
sed -i.bak "s/^version = \"${BASE_VERSION}\"/version = \"${DEV_VERSION}\"/" "${PYPROJECT}"

# Build
cd "${PROJECT_ROOT}"
rm -rf dist/
poetry build

# Revert pyproject.toml
mv "${PYPROJECT}.bak" "${PYPROJECT}"

# Upload to test.pypi
twine upload \
  --repository-url https://test.pypi.org/legacy/ \
  --username __token__ \
  --password "${TEST_PYPI_TOKEN}" \
  --non-interactive \
  dist/*

# Poll test.pypi simple index until the version appears (CDN propagation can take 2-3 min)
echo "Waiting for ${DEV_VERSION} on test.pypi simple index..."
for i in $(seq 1 30); do
  if curl -sf "https://test.pypi.org/simple/bees-md/" 2>/dev/null | grep -q "${DEV_VERSION}"; then
    echo "Available after $((i * 10))s"
    break
  fi
  if [[ $i -eq 30 ]]; then
    echo "ERROR: ${DEV_VERSION} not visible on test.pypi after 300s"
    exit 1
  fi
  sleep 10
done

# Output version for caller to capture
echo "${DEV_VERSION}"
