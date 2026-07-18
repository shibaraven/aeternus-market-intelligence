#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

echo "=========================================="
echo "  Aeternus Market Intelligence - Source Start"
echo "=========================================="

if [ ! -f "backend/app.py" ]; then
  echo "[ERROR] backend/app.py does not exist. Please extract/copy the complete project folder first."
  exit 1
fi

if [ ! -f "backend/main.py" ]; then
  echo "[ERROR] backend/main.py does not exist. Please copy the fixed backend/main.py into the backend folder."
  exit 1
fi

if [ ! -f "frontend/index.html" ]; then
  echo "[ERROR] frontend/index.html does not exist. Please extract/copy the complete project folder first."
  exit 1
fi

PY_BOOT=""
if command -v python3.13 >/dev/null 2>&1; then
  PY_BOOT="python3.13"
elif command -v python3.12 >/dev/null 2>&1; then
  PY_BOOT="python3.12"
elif command -v python3 >/dev/null 2>&1; then
  PY_BOOT="python3"
elif command -v python >/dev/null 2>&1; then
  PY_BOOT="python"
else
  echo "[ERROR] Python not found. Please install Python 3.12 or 3.13."
  exit 1
fi

echo "[OK] Python command: $PY_BOOT"

if [ ! -x ".venv/bin/python" ]; then
  echo "[1/4] Creating local virtual environment..."
  "$PY_BOOT" -m venv .venv
fi

PY_EXE="$(pwd)/.venv/bin/python"

echo "[2/4] Installing packages..."
"$PY_EXE" -m pip install --upgrade pip --disable-pip-version-check
"$PY_EXE" -m pip install -r backend/requirements.txt --disable-pip-version-check

mkdir -p data/reports
export AETERNUS_DATA="$(pwd)/data"
export AETERNUS_FRONTEND="$(pwd)/frontend"

echo "[3/4] Starting server..."
echo "[4/4] Browser will open at http://127.0.0.1:5000"

if [[ "$OSTYPE" == "darwin"* ]]; then
  (sleep 2 && open "http://127.0.0.1:5000") >/dev/null 2>&1 &
elif command -v xdg-open >/dev/null 2>&1; then
  (sleep 2 && xdg-open "http://127.0.0.1:5000") >/dev/null 2>&1 &
fi

echo "Press Ctrl+C to stop the server."
"$PY_EXE" backend/main.py
