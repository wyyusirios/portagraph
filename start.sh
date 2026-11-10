#!/usr/bin/env bash
# Запуск PortaGraph на macOS / Linux: ./start.sh
set -e
cd "$(dirname "$0")"
PY=${PYTHON:-python3}
if [ ! -d .venv ]; then
  echo "Создаю виртуальное окружение…"
  $PY -m venv .venv
fi
. .venv/bin/activate
pip install -q -r requirements.txt
python run.py
