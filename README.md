# Ecommerce: etapa 0 — ingesta y buffer

Implementación de la primera etapa de [Plan_proyecto.md](Plan_proyecto.md), con Python 3.11 o superior y biblioteca estándar. Incluye preparación de datos, escenarios reproducibles, reproducción asíncrona y una FIFO acotada. Las etapas 1–9 quedan pendientes; el consumidor actual persiste sobres para que la futura etapa 1 pueda recibirlos.

## Ejecutar

Desde la raíz del proyecto, con `10M.csv` disponible localmente:

```sh
python3 -m unittest discover -s tests -v
python3 scripts/stage0.py prepare --size 1000 --output data/prepared/1K
python3 scripts/stage0.py prepare --size 10000 --output data/prepared/10K
python3 scripts/stage0.py replay --events data/prepared/1K/events.jsonl --output results/demo.jsonl --metrics results/demo_metrics.json --mode constant
```

La preparación requiere un directorio de salida nuevo; la reproducción requiere archivos de salida nuevos. Los comandos no sobrescriben ejecuciones anteriores. Las versiones 1K y 10K ya se generaron y verificaron en esta entrega; para repetirlas utiliza otra carpeta. No se necesita instalar paquetes. El notebook de demostración requiere Jupyter en el entorno del usuario.

```sh
# Otras escalas: comandos disponibles, todavía sin ejecutar/verificar.
python3 scripts/stage0.py prepare --size 100000 --output data/prepared/100K
python3 scripts/stage0.py prepare --size 1000000 --output data/prepared/1M
python3 scripts/stage0.py prepare --size 10000000 --output data/prepared/10M
# Maestro: conserva TODAS las filas originales y añade los escenarios.
python3 scripts/stage0.py prepare --all-source --output data/prepared/master
```

Cada versión de tamaño N contiene N−13 filas originales del prefijo temporal y 13 eventos reservados. El maestro conserva los 10 millones originales y añade 13 eventos. El CSV original permanece intacto. La selección queda explícita en cada manifiesto; las versiones pequeñas no pretenden representar todo el periodo ni su distribución global.

## Archivos y configuración

- `src/data/`: contrato, validación, preparación con SQLite y manifiestos.
- `src/simulation/`: modos `constant`, `burst`, `historical` y `unlimited`.
- `src/structures/fifo.py`: FIFO basada en `asyncio.Queue`, con capacidad obligatoria.
- `src/pipeline/stage0.py`: lectura por bloques, productor, buffer y sumidero de sobres.
- `configs/stage0.json`: semilla, bloque, ventana de órdenes y reproducción. Para usar otra configuración: `python3 scripts/stage0.py --config ruta.json ...`.
- `notebooks/00_etapa0.ipynb`: inspección de resultados persistidos y ejecución local de la etapa 0.
- `tests/`: invariantes de datos, reproducibilidad, errores y contrapresión.
- `docs/etapa0.md`: decisiones de modelado, contrato, complejidad y límites.

Cada carpeta preparada contiene `events.jsonl`, `entities.sqlite` y `manifest.json`. SQLite mantiene catálogo, órdenes, compras, inventario sintético, pagos y tablas auxiliares de preparación. Los manifiestos registran SHA-256 del CSV completo y de los artefactos, semilla, configuración, composición, reglas, entorno y validaciones. El hash `code_sha256` identifica el módulo de preparación; no sustituye una versión Git del repositorio. Esta carpeta aún no es un repositorio Git.

Los datos locales y los sobres voluminosos están excluidos mediante `.gitignore`. La fuente debe obtenerse por el mecanismo de distribución permitido para REES46; el proyecto utiliza el archivo local entregado, sin descargar ni redistribuir el dataset.

## Reproducción y contrapresión

```sh
python3 scripts/stage0.py replay --events data/prepared/1K/events.jsonl --output results/slow.jsonl --metrics results/slow_metrics.json --mode burst --capacity 8 --consumer-delay 0.001
python3 scripts/stage0.py replay --events data/prepared/1K/events.jsonl --output results/historical.jsonl --metrics results/historical_metrics.json --mode historical
```

`constant` limita a la tasa configurada; `burst` libera grupos en intervalos; `historical` acelera las diferencias del tiempo del evento; `unlimited` reproduce tan rápido como permita el consumidor. La contrapresión puede reducir la velocidad efectiva. `event_time` conserva el tiempo histórico y `ingested_at` refleja la recepción real en UTC. Las etiquetas de evaluación no determinan la prioridad.

Las métricas incluyen conteos, throughput, espera del productor, latencia, ocupación máxima, bloqueos y memoria Python/proceso. La latencia comienza antes del `put` y termina al consumir el evento: incluye la espera por capacidad y el retardo simulado, pero excluye el vaciado posterior del bloque a disco. El throughput sí incluye escritura y pacing; no incluye preparación. La ocupación de la cola no incluye los bloques de lectura y escritura.

## Estado de la entrega

Se verificaron 1K y 10K con el CSV entregado, además de contrapresión con capacidad 8 y consumidor lento. Consulta [results/verification.json](results/verification.json) para los conteos y [docs/verificacion_etapa0.md](docs/verificacion_etapa0.md) para los resultados. No se han ejecutado benchmarks de 100K–10M ni etapas posteriores.

| Responsabilidad | Estado |
|---|---|
| Esquema, preparación y escenarios | Implementados en esta entrega; responsable del equipo por asignar |
| Reproducción, FIFO y coordinación | Implementados en esta entrega; responsable del equipo por asignar |
| Etapas 1–9 y experimentación completa | Pendientes |

La asignación nominal de integrantes y el historial de contribuciones se completarán cuando se cree el repositorio compartido.
