#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if command -v python3.13 >/dev/null 2>&1; then
  PYTHON=python3.13
elif command -v python3.12 >/dev/null 2>&1; then
  PYTHON=python3.12
elif command -v python3.11 >/dev/null 2>&1; then
  PYTHON=python3.11
elif command -v python3.10 >/dev/null 2>&1; then
  PYTHON=python3.10
else
  PYTHON=python3
fi

echo "Using $($PYTHON --version)"
$PYTHON -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -e ".[tui]"

echo
echo "Virtual environment ready at $ROOT/.venv"
echo "Run one of:"
echo "  ./scripts/tnfs ls"
echo "  ./scripts/tnfs-shell"
echo "  ./scripts/tnfs-tui"
