"""Estructuras probabilísticas con hashes estables entre procesos."""
import hashlib
import math
from collections import Counter


def indices(key, width, depth):
    # Separar las filas del CMS evita reutilizar una misma función hash.
    for row in range(depth):
        digest = hashlib.sha256(f'{row}:{key}'.encode()).digest()
        yield int.from_bytes(digest[:8], 'big') % width


class BloomFilter:
    def __init__(self, capacity=1000, false_positive_rate=0.01):
        if capacity <= 0 or not 0 < false_positive_rate < 1:
            raise ValueError('Capacidad o probabilidad Bloom inválida')
        self.capacity = capacity
        self.width = math.ceil(-capacity * math.log(false_positive_rate) / math.log(2)**2)
        self.depth = max(1, round(self.width / capacity * math.log(2)))
        self.bits = bytearray((self.width + 7) // 8)

    def add(self, key):
        for index in indices(key, self.width, self.depth):
            self.bits[index // 8] |= 1 << (index % 8)

    def contains(self, key):
        return all(self.bits[i // 8] & (1 << (i % 8)) for i in indices(key, self.width, self.depth))

    def occupancy(self):
        return sum(byte.bit_count() for byte in self.bits) / self.width


class CountMinSketch:
    def __init__(self, epsilon=0.01, delta=0.001):
        if not 0 < epsilon < 1 or not 0 < delta < 1:
            raise ValueError('Parámetros CMS inválidos')
        self.width = math.ceil(math.e / epsilon)
        self.depth = math.ceil(math.log(1 / delta))
        # Enteros Python: las sumas positivas no desbordan.
        self.rows = [[0] * self.width for _ in range(self.depth)]

    def add(self, key):
        for row, index in enumerate(indices(key, self.width, self.depth)):
            self.rows[row][index] += 1

    def estimate(self, key):
        return min(self.rows[row][index] for row, index in enumerate(indices(key, self.width, self.depth)))


class WindowCounts:
    def __init__(self, epsilon=0.01, delta=0.001):
        self.epsilon, self.delta = epsilon, delta
        self.minute = None
        self.blocks = [None] * 5

    def advance(self, minute):
        self.minute = minute if self.minute is None else max(self.minute, minute)
        for index, block in enumerate(self.blocks):
            if block is not None and block[0] < self.minute - 4:
                self.blocks[index] = None

    def add(self, minute, key):
        self.advance(minute)
        if minute < self.minute - 4:
            return False
        index = minute % 5
        # Cada posición conserva el minuto absoluto, incluso ante saltos o tardíos.
        if self.blocks[index] is None or self.blocks[index][0] != minute:
            self.blocks[index] = (minute, CountMinSketch(self.epsilon, self.delta), Counter())
        _, sketch, exact = self.blocks[index]
        sketch.add(key)
        exact[key] += 1
        return True

    def counts(self, key):
        active = [block for block in self.blocks if block is not None]
        return sum(b[1].estimate(key) for b in active), sum(b[2][key] for b in active)
