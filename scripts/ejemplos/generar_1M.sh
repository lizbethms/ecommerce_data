#!/usr/bin/env bash
# Ejemplo: bash scripts/ejemplos/generar_1M.sh --output data/prepared/otra_1M
# CONFIG y PYTHON_BIN permiten seleccionar configuración e intérprete.
set -euo pipefail

PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
PYTHON_EXEC="${PYTHON_BIN:-$PROJECT_ROOT/.venv/bin/python}"
if [[ -z "${PYTHON_BIN:-}" && ! -x "$PYTHON_EXEC" ]]; then
  PYTHON_EXEC=python3
fi

exec "$PYTHON_EXEC" "$PROJECT_ROOT/scripts/data_pipeline.py" \
  --config "${CONFIG:-$PROJECT_ROOT/configs/prepare.json}" \
  prepare --profile 1M \
  --source "$PROJECT_ROOT/10M.csv" \
  --output "$PROJECT_ROOT/data/prepared/perfil_1M" \
  "$@"
