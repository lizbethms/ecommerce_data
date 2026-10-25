"""Tabla hash con direccionamiento abierto y sondeo lineal.

Inserción, búsqueda y borrado O(1) esperado con factor de carga <= 0.65;
el redimensionado duplica la capacidad (O(n) amortizado a O(1)). Los borrados
dejan una lápida para no cortar las cadenas de sondeo.
"""

_EMPTY = object()
_DELETED = object()


class HashTable:
    def __init__(self, capacity=8, max_load=0.65):
        size = 8
        while size < capacity:
            size *= 2
        self._keys = [_EMPTY] * size
        self._values = [None] * size
        self._size = 0
        self._used = 0  # ocupadas + lápidas
        self._max_load = max_load

    def __len__(self):
        return self._size

    def _slot(self, key):
        """Índice de la clave si existe; si no, el primer hueco reutilizable."""
        mask = len(self._keys) - 1
        i = hash(key) & mask
        tombstone = None
        while True:
            current = self._keys[i]
            if current is _EMPTY:
                return (tombstone if tombstone is not None else i), False
            if current is _DELETED:
                if tombstone is None:
                    tombstone = i
            elif current == key:
                return i, True
            i = (i + 1) & mask

    def _resize(self, capacity):
        old = [(k, v) for k, v in zip(self._keys, self._values) if k is not _EMPTY and k is not _DELETED]
        self._keys = [_EMPTY] * capacity
        self._values = [None] * capacity
        self._size = self._used = 0
        for k, v in old:
            self[k] = v

    def __setitem__(self, key, value):
        i, found = self._slot(key)
        if found:
            self._values[i] = value
            return
        if self._keys[i] is _EMPTY:
            self._used += 1
        self._keys[i], self._values[i] = key, value
        self._size += 1
        if self._used > self._max_load * len(self._keys):
            self._resize(len(self._keys) * 2 if self._size > self._max_load * len(self._keys) / 2 else len(self._keys))

    def __getitem__(self, key):
        i, found = self._slot(key)
        if not found:
            raise KeyError(key)
        return self._values[i]

    def get(self, key, default=None):
        i, found = self._slot(key)
        return self._values[i] if found else default

    def __contains__(self, key):
        return self._slot(key)[1]

    def __delitem__(self, key):
        i, found = self._slot(key)
        if not found:
            raise KeyError(key)
        self._keys[i], self._values[i] = _DELETED, None
        self._size -= 1

    def pop(self, key, default=None):
        i, found = self._slot(key)
        if not found:
            return default
        value = self._values[i]
        self._keys[i], self._values[i] = _DELETED, None
        self._size -= 1
        return value

    def setdefault(self, key, default):
        i, found = self._slot(key)
        if found:
            return self._values[i]
        self[key] = default
        return default

    def items(self):
        for k, v in zip(self._keys, self._values):
            if k is not _EMPTY and k is not _DELETED:
                yield k, v

    def keys(self):
        return (k for k, _ in self.items())

    def values(self):
        return (v for _, v in self.items())

    __iter__ = keys
