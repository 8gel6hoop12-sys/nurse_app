#!/usr/bin/env bash
set -e
cd "$(dirname "$0")/.."

if [ ! -x "./.venv/bin/python" ]; then
  echo "[ERROR] .venv がありません。先に scripts/setup_mac.sh を実行してください。"
  exit 1
fi

export AI_PROVIDER=ollama
export AI_MODEL="qwen2.5:7b-instruct"
export OLLAMA_HOST="http://127.0.0.1:11434"
export AI_LOG_DISABLE=1

"./.venv/bin/python" nurse_server.py --port 8787 &
sleep 1
open "http://127.0.0.1:8787/"
