#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

echo "[1/4] venv 準備..."
python3 -m venv .venv

echo "[2/4] pip アップグレード..."
./.venv/bin/python -m pip install -U pip

echo "[3/4] 依存インストール..."
./.venv/bin/python -m pip install -r requirements.txt

echo "[4/4] サーバ起動..."
./.venv/bin/python nurse_server.py --port 8787
