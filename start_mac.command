#!/usr/bin/env bash
cd "$(dirname "$0")" || exit 1

# venvがあれば優先（任意）
if [ -x "./venv/bin/python3" ]; then
  ./venv/bin/python3 -X utf8 nurse_app.py
  exit $?
fi

python3 -X utf8 nurse_app.py
