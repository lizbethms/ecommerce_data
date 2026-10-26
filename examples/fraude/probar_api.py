"""Ejecutar contra un servidor con historial nuevo: python examples/fraude/probar_api.py."""
import csv
import json
from pathlib import Path
import sys
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
BASE = sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:8000'


def send(path, payload, method='POST'):
    request = Request(BASE + path, data=json.dumps(payload).encode(), method=method,
                      headers={'Content-Type': 'application/json'})
    with urlopen(request) as response:
        return json.load(response)


with (ROOT / 'entidades.csv').open(encoding='utf-8') as stream:
    for row in csv.DictReader(stream):
        send(f"/fraude/entidades/{row['tipo']}/{row['identificador']}", {'motivo': row['motivo']}, 'PUT')
expected = json.loads((ROOT / 'resultados_esperados.json').read_text())
events = [json.loads(line) for line in (ROOT / 'eventos.jsonl').read_text().splitlines()]
assert len(events) == len(expected)
for event, wanted in zip(events, expected):
    result = send('/fraude/eventos', {'evento': event})
    signals = result['senales_riesgo']
    actual = dict(evento_id=result['evento_id'], estado=result['estado'], decision=signals['decision'],
                  estimacion=signals['frecuencia']['estimacion'], conteo_exacto=signals['frecuencia']['conteo_exacto'])
    assert actual == wanted, (actual, wanted)
    print(json.dumps(actual))
print(f'{len(events)} respuestas verificadas')
