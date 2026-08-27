#!/bin/sh
set -eu

cd "$(dirname "$0")"

find_python() {
  for candidate in python3.14 python3.13 python3.12 python3 python; do
    if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c \
      'import sys; raise SystemExit(sys.version_info < (3, 12))' >/dev/null 2>&1; then
      printf '%s' "$candidate"
      return 0
    fi
  done
  return 1
}

PYTHON="$(find_python || true)"
if [ -z "$PYTHON" ]; then
  printf '\nОшибка: нужен Python 3.12 или новее.\n'
  printf 'Установите Python с https://www.python.org/downloads/ и повторите запуск.\n'
  exit 1
fi

printf 'Создание изолированного окружения HAT...\n'
"$PYTHON" -m venv .hat-runtime
.hat-runtime/bin/python -m pip install --disable-pip-version-check --upgrade pip
.hat-runtime/bin/python -m pip install --disable-pip-version-check ./app
mkdir -p runs local_inputs
printf '\nHAT установлен. Запустите ./start.sh\n'
