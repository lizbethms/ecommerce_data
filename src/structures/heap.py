"""Heap binario mínimo con desempate estable.

push/pop O(log n), peek O(1), espacio O(n). Cada entrada es (clave, secuencia,
valor): la secuencia de llegada desempata claves iguales (FIFO entre iguales) y
evita comparar los valores.
"""
from itertools import count


class MinHeap:
    def __init__(self):
        self._items = []
        self._sequence = count()

    def __len__(self):
        return len(self._items)

    def __bool__(self):
        return bool(self._items)

    def push(self, key, value=None):
        self._items.append((key, next(self._sequence), value))
        self._sift_up(len(self._items) - 1)

    def peek(self):
        if not self._items:
            raise IndexError('Heap vacío')
        key, _, value = self._items[0]
        return key, value

    def pop(self):
        if not self._items:
            raise IndexError('Heap vacío')
        last = self._items.pop()
        if not self._items:
            return last[0], last[2]
        top = self._items[0]
        self._items[0] = last
        self._sift_down(0)
        return top[0], top[2]

    def pushpop(self, key, value=None):
        """Inserta y extrae el mínimo en un solo O(log n)."""
        entry = (key, next(self._sequence), value)
        if self._items and self._items[0] < entry:
            entry, self._items[0] = self._items[0], entry
            self._sift_down(0)
        return entry[0], entry[2]

    def smallest(self, n):
        """Los n menores sin modificar el heap: O(n log n) sobre una copia."""
        copy = MinHeap()
        copy._items = list(self._items)
        return [copy.pop() for _ in range(min(n, len(copy)))]

    def _sift_up(self, i):
        items = self._items
        while i > 0:
            parent = (i - 1) // 2
            if items[i] < items[parent]:
                items[i], items[parent] = items[parent], items[i]
                i = parent
            else:
                break

    def _sift_down(self, i):
        items, n = self._items, len(self._items)
        while True:
            left, smallest = 2 * i + 1, i
            if left < n and items[left] < items[smallest]:
                smallest = left
            if left + 1 < n and items[left + 1] < items[smallest]:
                smallest = left + 1
            if smallest == i:
                return
            items[i], items[smallest] = items[smallest], items[i]
            i = smallest
