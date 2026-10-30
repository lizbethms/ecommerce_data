"""Bloom Filter con doble hashing.

Dimensiona m = -n ln p / (ln 2)² bits y k = (m/n) ln 2 funciones para n claves
y una tasa objetivo p de falsos positivos. add y consulta cuestan O(k); el
espacio es O(m) bits. No tiene falsos negativos. Un positivo solo indica que la
clave quizá está, por eso siempre se verifica contra un registro exacto.
"""
import hashlib
import math


def _next_prime(value):
    """Menor primo >= value; garantiza que el paso del doble hash sea coprimo."""
    if value <= 2:
        return 2
    candidate = value if value % 2 else value + 1
    while True:
        limit = math.isqrt(candidate)
        if all(candidate % divisor for divisor in range(3, limit + 1, 2)):
            return candidate
        candidate += 2


def _encode_key(key):
    """Representación estable con etiqueta de tipo para evitar 1 == '1' al hashear."""
    if isinstance(key, bytes):
        return b'bytes\0' + key
    if isinstance(key, str):
        return b'str\0' + key.encode('utf-8')
    kind = f'{type(key).__module__}.{type(key).__qualname__}'.encode('utf-8')
    return kind + b'\0' + repr(key).encode('utf-8')


class BloomFilter:
    def __init__(self, capacity, fp_rate=0.01):
        if isinstance(capacity, bool) or not isinstance(capacity, int) or capacity <= 0:
            raise ValueError('La capacidad debe ser un entero positivo')
        if isinstance(fp_rate, bool) or not isinstance(fp_rate, (int, float)) or not math.isfinite(fp_rate) or not 0 < fp_rate < 1:
            raise ValueError('Capacidad positiva y 0 < fp_rate < 1')
        self.capacity, self.fp_rate = capacity, fp_rate
        requested_bits = max(8, math.ceil(-capacity * math.log(fp_rate) / math.log(2) ** 2))
        self.m = _next_prime(requested_bits)
        self.k = max(1, round(self.m / capacity * math.log(2)))
        self.bits = bytearray((self.m + 7) // 8)
        self.count = 0

    def _positions(self, key):
        digest = hashlib.sha256(_encode_key(key)).digest()
        h1 = int.from_bytes(digest[:8], 'little')
        # m es primo: cualquier paso en [1, m-1] recorre posiciones distintas
        # hasta completar el ciclo y no degrada silenciosamente el número de hashes.
        h2 = int.from_bytes(digest[8:16], 'little') % (self.m - 1) + 1
        return ((h1 + i * h2) % self.m for i in range(self.k))

    def add(self, key):
        changed = False
        for p in self._positions(key):
            byte, mask = p >> 3, 1 << (p & 7)
            if not self.bits[byte] & mask:
                changed = True
                self.bits[byte] |= mask
        self.count += 1
        return changed

    def update(self, keys):
        """Inserta un iterable y devuelve el número de llamadas realizadas."""
        inserted = 0
        for key in keys:
            self.add(key)
            inserted += 1
        return inserted

    def clear(self):
        """Vacía el filtro conservando su dimensionamiento."""
        self.bits[:] = b'\0' * len(self.bits)
        self.count = 0

    def __contains__(self, key):
        for p in self._positions(key):
            if not self.bits[p >> 3] & (1 << (p & 7)):
                return False
        return True

    def __len__(self):
        """Número de inserciones; puede incluir claves repetidas."""
        return self.count

    def set_bits(self):
        return sum(byte.bit_count() for byte in self.bits)

    def fill_ratio(self):
        return self.set_bits() / self.m

    def estimated_items(self):
        """Estima claves distintas a partir de la ocupación observada."""
        fill = self.fill_ratio()
        if fill >= 1:
            return math.inf
        return -self.m / self.k * math.log1p(-fill)

    def expected_fp_rate(self):
        """Estimación teórica usando el total de inserciones (incluye repetidas)."""
        return (1 - math.exp(-self.k * self.count / self.m)) ** self.k

    def observed_fp_estimate(self):
        """Probabilidad estimada desde la proporción real de bits activos."""
        return self.fill_ratio() ** self.k

    def stats(self):
        active = self.set_bits()
        estimated = self.estimated_items()
        return dict(bits=self.m, hashes=self.k, inserted=self.count, bytes=len(self.bits),
                    capacity=self.capacity, capacity_exceeded=estimated > self.capacity,
                    insertion_calls_exceeded=self.count > self.capacity,
                    set_bits=active, fill_ratio=active / self.m,
                    estimated_distinct_items=estimated,
                    target_fp_rate=self.fp_rate, expected_fp_rate=self.expected_fp_rate(),
                    observed_fp_estimate=(active / self.m) ** self.k,
                    hash_algorithm='sha256-double-hashing')
