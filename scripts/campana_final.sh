#!/usr/bin/env bash
# Campaña final en una sola máquina, en secuencia (sin pasos en paralelo, para no distorsionar tiempos).
# Reanudable: un paso con la marca <salida>/.ok se salta; uno incompleto se borra y se repite.
# Si un paso falla, se registra y la campaña sigue con el siguiente.
# Para detenerla: taskkill //PID $(cat results/campana_final.pid) //T //F
cd "$(dirname "$0")/.."
PY=.venv/Scripts/python.exe
[ -x "$PY" ] || PY=.venv/bin/python
LOG=results/campana_final.log
ESCALAS="1K 10K 100K 1M 10M"
DATOS=$(for s in $ESCALAS; do printf 'data/prepared/perfil_%s ' "$s"; done)
cat /proc/$$/winpid > results/campana_final.pid 2>/dev/null || echo $$ > results/campana_final.pid

paso() {
  local nombre="$1" salida="$2"; shift 2
  if [ -e "$salida/.ok" ]; then
    echo "$(date '+%F %T') SALTA $nombre (ya completo)" >> "$LOG"
    return
  fi
  rm -rf "$salida"
  local inicio=$(date +%s)
  echo "$(date '+%F %T') INICIO $nombre" >> "$LOG"
  "$@" >> "results/campana_$nombre.out" 2>&1
  local estado=$?
  [ $estado -eq 0 ] && mkdir -p "$salida" && touch "$salida/.ok"
  echo "$(date '+%F %T') FIN $nombre (código $estado, $(( $(date +%s) - inicio )) s)" >> "$LOG"
}

echo "$(date '+%F %T') Campaña final: $ESCALAS" >> "$LOG"
for s in $ESCALAS; do
  paso "informe_$s" "results/flujo_$s/informe" env PYTHONHASHSEED=2026 "$PY" scripts/demo_tecnica.py \
    --datos "data/prepared/perfil_$s" --salida "results/flujo_$s/informe" --semilla 2026
done
paso tiempos results/experimentos/tiempos_01 \
  "$PY" scripts/benchmark_tiempos.py --datos $DATOS --salida results/experimentos/tiempos_01
paso memoria results/experimentos/memoria_completa_01 \
  "$PY" scripts/benchmark_memoria.py --datos $DATOS --salida results/experimentos/memoria_completa_01 --repeticiones 3
paso graficas results/experimentos/graficas "$PY" scripts/graficar_informe_final.py
echo "$(date '+%F %T') Campaña terminada" >> "$LOG"
rm -f results/campana_final.pid
