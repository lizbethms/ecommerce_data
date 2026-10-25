"""Count-Min Sketch y su variante por ventana temporal.

CMS: d filas de w contadores. Una actualización o consulta cuesta O(d). La
estimación nunca subestima: con w = ⌈e/ε⌉ y d = ⌈ln 1/δ⌉, el error es <= ε·N
con probabilidad 1 - δ. Un CMS simple no olvida eventos vencidos, por eso
WindowedCMS reparte la ventana en sub-ventanas rotativas (una por sketch) y
descarta las que ya expiraron.
"""
import hashlib


class CountMinSketch:
    def __init__(self, width=2048, depth=4):
        if width <= 0 or depth <= 0:
            raise ValueError('Ancho y profundidad positivos')
        self.width, self.depth = width, depth
        self.table = [[0] * width for _ in range(depth)]
        self.total = 0

    def _columns(self, key):
        digest = hashlib.blake2b(str(key).encode(), digest_size=16).digest()
        h1 = int.from_bytes(digest[:8], 'little')
        h2 = int.from_bytes(digest[8:], 'little') | 1
        return [(h1 + i * h2) % self.width for i in range(self.depth)]

    def add(self, key, count=1):
        for row, col in enumerate(self._columns(key)):
            self.table[row][col] += count
        self.total += count

    def estimate(self, key):
        return min(self.table[row][col] for row, col in enumerate(self._columns(key)))


class WindowedCMS:
    """Estimación de frecuencia en (t - window, t], con resolución de window/slots."""

    def __init__(self, window_seconds, slots=6, width=1024, depth=4):
        if window_seconds <= 0 or slots <= 0:
            raise ValueError('Ventana y sub-ventanas positivas')
        self.window, self.slots = window_seconds, slots
        self.slot_seconds = window_seconds / slots
        self.width, self.depth = width, depth
        self._sketches = {}  # índice de sub-ventana -> CountMinSketch

    def _slot(self, timestamp):
        return int(timestamp // self.slot_seconds)

    def _expire(self, current):
        for slot in [s for s in self._sketches if s <= current - self.slots]:
            del self._sketches[slot]

    def add(self, key, timestamp, count=1):
        slot = self._slot(timestamp)
        self._expire(max(slot, max(self._sketches, default=slot)))
        if slot <= max(self._sketches, default=slot) - self.slots:
            return  # evento más viejo que la ventana vigente
        sketch = self._sketches.get(slot)
        if sketch is None:
            sketch = self._sketches[slot] = CountMinSketch(self.width, self.depth)
        sketch.add(key, count)

    def estimate(self, key, timestamp):
        slot = self._slot(timestamp)
        return sum(sketch.estimate(key) for s, sketch in self._sketches.items() if slot - self.slots < s <= slot)

    def stats(self):
        return dict(window_seconds=self.window, slots=self.slots, active_slots=len(self._sketches),
                    width=self.width, depth=self.depth,
                    counters=len(self._sketches) * self.width * self.depth)
