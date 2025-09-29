#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

if [ ! -x ".venv/bin/python" ]; then
  echo "初回セットアップが必要です。setup_mac.sh を先に実行してください。"
  exit 1
fi

open "http://127.0.0.1:8787/"
./.venv/bin/python nurse_server.py --port 8787
