"""B+Tree en memoria con hojas enlazadas.

Cada clave guarda una lista de valores (claves repetidas, p. ej. el mismo precio
para varios productos). Búsqueda e inserción O(log_m n); un rango cuesta
O(log_m n + r), porque se recorren las hojas enlazadas. Los borrados quitan el
valor de su lista sin rebalancear: las claves vacías se omiten en los recorridos.
Esta versión vive en memoria; la variante en disco queda para los benchmarks.
"""
from .sorting import bisect_left, bisect_right


class _Node:
    __slots__ = ('leaf', 'keys', 'children', 'values', 'next')

    def __init__(self, leaf):
        self.leaf = leaf
        self.keys = []
        self.children = []  # nodos internos
        self.values = []    # hojas: lista de valores por clave
        self.next = None    # hojas: siguiente hoja


class BPlusTree:
    def __init__(self, order=32):
        if order < 3:
            raise ValueError('El orden debe ser >= 3')
        self.order = order
        self.root = _Node(leaf=True)
        self._entries = 0

    def __len__(self):
        return self._entries

    def _leaf(self, key):
        node = self.root
        while not node.leaf:
            node = node.children[bisect_right(node.keys, key)]
        return node

    def search(self, key):
        leaf = self._leaf(key)
        i = bisect_left(leaf.keys, key)
        if i < len(leaf.keys) and leaf.keys[i] == key:
            return list(leaf.values[i])
        return []

    def insert(self, key, value):
        split = self._insert(self.root, key, value)
        if split:
            separator, right = split
            root = _Node(leaf=False)
            root.keys, root.children = [separator], [self.root, right]
            self.root = root
        self._entries += 1

    def _insert(self, node, key, value):
        if node.leaf:
            i = bisect_left(node.keys, key)
            if i < len(node.keys) and node.keys[i] == key:
                node.values[i].append(value)
                return None
            node.keys.insert(i, key)
            node.values.insert(i, [value])
            if len(node.keys) < self.order:
                return None
            mid = len(node.keys) // 2
            right = _Node(leaf=True)
            right.keys, right.values = node.keys[mid:], node.values[mid:]
            node.keys, node.values = node.keys[:mid], node.values[:mid]
            right.next, node.next = node.next, right
            return right.keys[0], right
        i = bisect_right(node.keys, key)
        split = self._insert(node.children[i], key, value)
        if not split:
            return None
        separator, child = split
        node.keys.insert(i, separator)
        node.children.insert(i + 1, child)
        if len(node.keys) < self.order:
            return None
        mid = len(node.keys) // 2
        right = _Node(leaf=False)
        promoted = node.keys[mid]
        right.keys, right.children = node.keys[mid + 1:], node.children[mid + 1:]
        node.keys, node.children = node.keys[:mid], node.children[:mid + 1]
        return promoted, right

    def remove(self, key, value):
        leaf = self._leaf(key)
        i = bisect_left(leaf.keys, key)
        if i < len(leaf.keys) and leaf.keys[i] == key and value in leaf.values[i]:
            leaf.values[i].remove(value)
            self._entries -= 1
            return True
        return False

    def range(self, low=None, high=None, include_high=True):
        """(clave, valor) con low <= clave <= high (o < high), en orden de clave."""
        if low is None:
            leaf = self.root
            while not leaf.leaf:
                leaf = leaf.children[0]
            i = 0
        else:
            leaf = self._leaf(low)
            i = bisect_left(leaf.keys, low)
        while leaf is not None:
            while i < len(leaf.keys):
                key = leaf.keys[i]
                if high is not None and (key > high or (not include_high and key == high)):
                    return
                for value in leaf.values[i]:
                    yield key, value
                i += 1
            leaf, i = leaf.next, 0

    def height(self):
        node, h = self.root, 1
        while not node.leaf:
            node, h = node.children[0], h + 1
        return h
