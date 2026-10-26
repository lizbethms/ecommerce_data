"""Historial CSV exclusivo, durable y verificable; compatible con macOS/Linux."""
import csv
import fcntl
import hashlib
import io
import json
import os
import sys
import time
from pathlib import Path


class PersistenceError(Exception):
    pass


class CSVHistory:
    fields = ['version', 'secuencia', 'operacion', 'contenido', 'sha256']

    def __init__(self, path):
        self.file = None
        self.failed = False
        self.sequence = 0
        self.write_seconds = 0.0
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.file = path.open('a+', newline='', encoding='utf-8')
            fcntl.flock(self.file, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.file.seek(0)
            self.records = []
            content = self.file.read()
            if content:
                if not content.endswith('\n'):
                    raise PersistenceError('Historial incompleto en la última fila')
                reader = csv.DictReader(io.StringIO(content), strict=True)
                csv.field_size_limit(sys.maxsize)
                if reader.fieldnames != self.fields:
                    raise PersistenceError('Cabecera del historial inválida: fila 1')
                for row in reader:
                    line = reader.line_num
                    try:
                        seq = self.sequence + 1
                        if set(row) != set(self.fields) or any(value is None for value in row.values()):
                            raise ValueError('Cantidad de columnas inválida')
                        if row['version'] != '1' or row['secuencia'] != str(seq):
                            raise ValueError('Versión o secuencia inválida')
                        if row['sha256'] != self.digest(seq, row['operacion'], row['contenido']):
                            raise ValueError('Checksum inválido')
                        payload = json.loads(row['contenido'])
                        self.records.append((row['operacion'], payload, line))
                        self.sequence = seq
                    except (ValueError, TypeError, KeyError) as exc:
                        raise PersistenceError(f'Historial corrupto en fila {line}: {exc}') from exc
                if not self.records:
                    raise PersistenceError('Falta configuración inicial en fila 2')
            else:
                csv.writer(self.file).writerow(self.fields)
                self.sync()
        except Exception as exc:
            self.close()
            if isinstance(exc, PersistenceError):
                raise
            if isinstance(exc, csv.Error):
                raise PersistenceError(f'CSV corrupto en fila {reader.line_num}: {exc}') from exc
            raise PersistenceError(f'No se pudo abrir el historial: {exc}') from exc

    @staticmethod
    def digest(sequence, operation, content):
        return hashlib.sha256(f'1\x1f{sequence}\x1f{operation}\x1f{content}'.encode()).hexdigest()

    def sync(self):
        self.file.flush()
        os.fsync(self.file.fileno())

    def append(self, operation, payload):
        if self.failed:
            raise PersistenceError('Historial no disponible; reinicie y verifique el archivo')
        started = time.perf_counter()
        try:
            content = json.dumps(payload, sort_keys=True, ensure_ascii=False, allow_nan=False)
            seq = self.sequence + 1
            self.file.seek(0, os.SEEK_END)
            csv.writer(self.file).writerow([1, seq, operation, content, self.digest(seq, operation, content)])
            self.sync()
            self.sequence = seq
        except (OSError, ValueError) as exc:
            self.failed = True
            raise PersistenceError(f'No se pudo confirmar el historial: {exc}') from exc
        finally:
            self.write_seconds += time.perf_counter() - started

    def close(self):
        if self.file is not None:
            self.file.close()
            self.file = None
