# Verificación de la etapa 0

Fecha: 24 de octubre de 2026 (America/Lima). Fuente: `10M.csv` local.

Las siete pruebas automatizadas pasaron. Se verificaron los hashes de artefactos y la igualdad del contenido y del orden de entrada y salida en las tres reproducciones.

| Dataset | Filas originales | Eventos sintéticos, incluido reenvío | Total | Referencias inválidas |
|---|---:|---:|---:|---:|
| 1K | 987 | 13 | 1000 | 0 |
| 10K | 9987 | 13 | 10000 | 0 |

En 10K se conservaron cuatro posibles duplicados de origen y once eventos con precio cero. Ambos datasets contienen un reenvío controlado de compra, con la misma identidad que su original. No se duplicaron sus efectos sobre inventario.

| Reproducción | Eventos | Capacidad | Pico FIFO | Esperas por cola llena | Eventos/s |
|---|---:|---:|---:|---:|---:|
| constant | 1000 | 128 | 1 | 0 | 4730.0 |
| unlimited | 10000 | 128 | 128 | 74 | 6314.8 |
| burst | 1000 | 8 | 8 | 992 | 725.9 |

El caso `burst` utilizó un consumidor con retardo de 1 ms: la capacidad de 8 se respetó y el productor esperó. Todos los eventos se emitieron y la cola terminó vacía.

Son ejecuciones individuales, realizadas concurrentemente para verificar funcionamiento, con `tracemalloc` activo. Los tiempos no constituyen benchmarks comparables entre modos ni resultados estadísticos. Las escalas 100K, 1M y 10M no se han ejecutado.

Comando para repetir la verificación sobre los artefactos existentes (usar una salida nueva):

```sh
python3 scripts/verify_stage0.py --prepared data/prepared/1K data/prepared/10K --metrics results/stage0_1K_metrics.json results/stage0_10K_metrics.json results/stage0_backpressure_metrics.json --output results/verification_repeat.json
```

