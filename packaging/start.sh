#!/bin/sh
set -eu
cd "$(dirname "$0")"

if [ ! -x .hat-runtime/bin/python ]; then
  printf 'HAT ещё не установлен. Запускаю установку...\n'
  ./install.sh
fi

open_browser() {
  sleep 2
  if command -v xdg-open >/dev/null 2>&1; then xdg-open http://127.0.0.1:8765/ >/dev/null 2>&1 || true
  elif command -v open >/dev/null 2>&1; then open http://127.0.0.1:8765/ >/dev/null 2>&1 || true
  fi
}
open_browser &
exec .hat-runtime/bin/python -m uvicorn hierarchy_account_transfer.api:app \
  --host 127.0.0.1 --port 8765
