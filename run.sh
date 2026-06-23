#!/usr/bin/env bash
# ----------------------------------------------------------------------------
# CK360 - Script de arranque del panel web
# Uso:  ./run.sh            (host 0.0.0.0, puerto 8000)
#       HOST=127.0.0.1 PORT=8080 ./run.sh
# ----------------------------------------------------------------------------
set -euo pipefail

cd "$(dirname "$0")"

# Activa el entorno virtual si existe
if [ -d "venv" ]; then
  # shellcheck disable=SC1091
  source venv/bin/activate
fi

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"

echo "==> CK360 escuchando en http://${HOST}:${PORT}"
exec uvicorn app.main:app --host "${HOST}" --port "${PORT}"
