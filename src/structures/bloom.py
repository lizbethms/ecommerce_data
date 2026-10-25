"""Bloom Filter con doble hashing.

Dimensiona m = -n ln p / (ln 2)² bits y k = (m/n) ln 2 funciones para n claves
y una tasa objetivo p de falsos positivos. add y consulta cuestan O(k); el
espacio es O(m) bits. No tiene falsos negativos. Un positivo solo indica que la
clave quizá está, por eso siempre se verifica contra un registro exacto.
"""
import hashlib
import math


class BloomFilter:
    def __init__(self, capacity, fp_rate=0.01):
        if capacity <= 0 or not 0 < fp_rate < 1:
            raise ValueError('Capacidad positiva y 0 < fp_rate < 1')
        self.capacity, self.fp_rate = capacity, fp_rate
        self.m = max(8, math.ceil(-capacity * math.log(fp_rate) / math.log(2) ** 2))
        self.k = max(1, round(self.m / capacity * math.log(2)))
        self.bits = bytearray((self.m + 7) // 8)
        self.count = 0

    def _positions(self, key):
        digest = hashlib.sha256(str(key).encode()).digest()
        h1 = int.from_bytes(digest[:8], 'little')
        h2 = int.from_bytes(digest[8:16], 'little') | 1
        return ((h1 + i * h2) % self.m for i in range(self.k))

    def add(self, key):
        for p in self._positions(key):
            self.bits[p >> 3] |= 1 << (p & 7)
        self.count += 1

    def __contains__(self, key):
        return all(self.bits[p >> 3] & (1 << (p & 7)) for p in self._positions(key))

    def expected_fp_rate(self):
        """(1 - e^{-kn/m})^k con las n claves insertadas."""
        return (1 - math.exp(-self.k * self.count / self.m)) ** self.k

    def stats(self):
        return dict(bits=self.m, hashes=self.k, inserted=self.count, bytes=len(self.bits),
                    target_fp_rate=self.fp_rate, expected_fp_rate=self.expected_fp_rate())
