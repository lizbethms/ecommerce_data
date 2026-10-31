#!/usr/bin/env bash
# Ejemplo: bash scripts/ejemplos/generar_1M.sh --output data/prepared/otra_1M
# CONFIG y PYTHON_BIN permiten seleccionar configuración e intérprete.
set -euo pipefail

PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
# Busca el venv en .venv/bin (Linux/macOS) o .venv/Scripts (Windows); si no, usa python3 o python.
if [[ -n "${PYTHON_BIN:-}" ]]; then
  PYTHON_EXEC="$PYTHON_BIN"
elif [[ -x "$PROJECT_ROOT/.venv/bin/python" ]]; then
  PYTHON_EXEC="$PROJECT_ROOT/.venv/bin/python"
elif [[ -x "$PROJECT_ROOT/.venv/Scripts/python.exe" ]]; then
  PYTHON_EXEC="$PROJECT_ROOT/.venv/Scripts/python.exe"
elif python3 -c '' >/dev/null 2>&1; then
  PYTHON_EXEC=python3
else
  PYTHON_EXEC=python
fi

exec "$PYTHON_EXEC" "$PROJECT_ROOT/scripts/data_pipeline.py" \
  --config "${CONFIG:-$PROJECT_ROOT/configs/prepare.json}" \
  prepare --profile 1M \
  --source "$PROJECT_ROOT/10M.csv" \
  --output "$PROJECT_ROOT/data/prepared/perfil_1M" \
  "$@"
