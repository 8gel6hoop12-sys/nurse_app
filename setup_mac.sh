#!/usr/bin/env bash
set -e
cd "$(dirname "$0")/.."

# 1) Python
if ! command -v python3 >/dev/null 2>&1; then
  echo "[INFO] Installing Python with Homebrew..."
  if ! command -v brew >/dev/null 2>&1; then
    echo "[ERROR] Homebrew がありません。https://brew.sh/ を参照してインストールしてください。"
    exit 1
  fi
  brew install python
fi

# 2) venv
if [ ! -d ".venv" ]; then
  echo "[INFO] Creating venv..."
  python3 -m venv .venv
fi

# 3) pip & requirements
"./.venv/bin/python" -m pip install -U pip
if [ -f requirements.txt ]; then
  "./.venv/bin/python" -m pip install -r requirements.txt
fi

# 4) Ollama
if ! command -v ollama >/dev/null 2>&1; then
  echo "[INFO] Installing Ollama..."
  brew install --cask ollama
fi

# 5) モデル
AI_MODEL="qwen2.5:7b-instruct"
if ! ollama list | grep -qi "$AI_MODEL"; then
  echo "[INFO] Pulling $AI_MODEL ..."
  ollama pull "$AI_MODEL"
fi

# 6) 起動
export AI_PROVIDER=ollama
export AI_MODEL="qwen2.5:7b-instruct"
export OLLAMA_HOST="http://127.0.0.1:11434"
export AI_LOG_DISABLE=1

"./.venv/bin/python" nurse_server.py --port 8787 &
sleep 1
open "http://127.0.0.1:8787/"
echo "起動しました。"

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
