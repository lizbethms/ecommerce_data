"""Caché LRU: tabla hash + lista doblemente enlazada. get/put/delete O(1)."""
from .hash_table import HashTable


class _Node:
    __slots__ = ('key', 'value', 'prev', 'next')

    def __init__(self, key=None, value=None):
        self.key, self.value, self.prev, self.next = key, value, None, None


class LRUCache:
    def __init__(self, capacity):
        if capacity <= 0:
            raise ValueError('La capacidad debe ser positiva')
        self.capacity = capacity
        self._index = HashTable()
        self._head, self._tail = _Node(), _Node()  # centinelas: head.next es el más reciente
        self._head.next, self._tail.prev = self._tail, self._head
        self.hits = self.misses = self.evictions = 0

    def __len__(self):
        return len(self._index)

    def _unlink(self, node):
        node.prev.next, node.next.prev = node.next, node.prev

    def _push_front(self, node):
        node.prev, node.next = self._head, self._head.next
        self._head.next.prev = node
        self._head.next = node

    def get(self, key, default=None):
        node = self._index.get(key)
        if node is None:
            self.misses += 1
            return default
        self.hits += 1
        self._unlink(node)
        self._push_front(node)
        return node.value

    def put(self, key, value):
        node = self._index.get(key)
        if node is not None:
            node.value = value
            self._unlink(node)
            self._push_front(node)
            return
        if len(self._index) >= self.capacity:
            oldest = self._tail.prev
            self._unlink(oldest)
            del self._index[oldest.key]
            self.evictions += 1
        node = _Node(key, value)
        self._index[key] = node
        self._push_front(node)

    def delete(self, key):
        node = self._index.pop(key)
        if node is not None:
            self._unlink(node)

    def stats(self):
        total = self.hits + self.misses
        return dict(capacity=self.capacity, size=len(self), hits=self.hits, misses=self.misses,
                    evictions=self.evictions, hit_rate=self.hits / total if total else None)
