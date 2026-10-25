"""MinHash + LSH por bandas para similitud de Jaccard entre conjuntos.

Una firma cuesta O(n·|S|) con n permutaciones. P[min h(A) = min h(B)] = J(A, B),
así que la fracción de posiciones iguales estima J. LSH divide la firma en b
bandas de r filas: dos conjuntos son candidatos con probabilidad 1 - (1 - J^r)^b.
"""
import hashlib
import random

_PRIME = (1 << 61) - 1
_MAX = (1 << 32) - 1


def _base_hash(element):
    return int.from_bytes(hashlib.blake2b(str(element).encode(), digest_size=8).digest(), 'little')


def jaccard(a, b):
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b)


class MinHash:
    def __init__(self, num_perm=64, seed=2026):
        rng = random.Random(seed)
        self.num_perm = num_perm
        self._params = [(rng.randrange(1, _PRIME), rng.randrange(0, _PRIME)) for _ in range(num_perm)]

    def signature(self, elements):
        hashes = [_base_hash(e) for e in elements]
        if not hashes:
            return (_MAX,) * self.num_perm
        return tuple(min(((a * h + b) % _PRIME) & _MAX for h in hashes) for a, b in self._params)

    @staticmethod
    def estimate(sig_a, sig_b):
        return sum(x == y for x, y in zip(sig_a, sig_b)) / len(sig_a)


class LSHIndex:
    def __init__(self, bands=16, rows=4):
        self.bands, self.rows = bands, rows
        self._buckets = [{} for _ in range(bands)]
        self.signatures = {}

    def insert(self, key, signature):
        if len(signature) != self.bands * self.rows:
            raise ValueError('La firma debe tener bands * rows posiciones')
        self.signatures[key] = signature
        for band in range(self.bands):
            chunk = signature[band * self.rows:(band + 1) * self.rows]
            self._buckets[band].setdefault(chunk, set()).add(key)

    def candidates(self, signature, exclude=None):
        found = set()
        for band in range(self.bands):
            chunk = signature[band * self.rows:(band + 1) * self.rows]
            found |= self._buckets[band].get(chunk, set())
        found.discard(exclude)
        return found

    def query(self, key, k=10):
        """Candidatos de LSH ordenados por Jaccard estimado: [(clave, estimación)]."""
        signature = self.signatures[key]
        scored = [(other, MinHash.estimate(signature, self.signatures[other]))
                  for other in self.candidates(signature, exclude=key)]
        scored.sort(key=lambda item: -item[1])
        return scored[:k]
