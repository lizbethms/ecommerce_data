"""
Implementación de caché LRU (Least Recently Used).

Estructuras de datos utilizadas:
    - Tabla hash: permite acceder rápidamente a los elementos.
    - Lista doblemente enlazada: mantiene el orden de uso.

Complejidad temporal esperada:
    - get():    O(1)
    - put():    O(1)
    - delete(): O(1)
"""

from .hash_table import HashTable


# ============================================================
# CLASE: _Node
# Representa un nodo de la lista doblemente enlazada.
# ============================================================

class _Node:

    __slots__ = ('key', 'value', 'prev', 'next')

    def __init__(self, key=None, value=None):
        self.key, self.value, self.prev, self.next = (
            key, value, None, None
        )


# ============================================================
# CLASE: LRUCache
# Implementa la política de reemplazo Least Recently Used.
# ============================================================

class LRUCache:

    # --------------------------------------------------------
    # 1. INICIALIZACIÓN DE LA CACHÉ
    # --------------------------------------------------------

    def __init__(self, capacity):

        if capacity <= 0:
            raise ValueError('La capacidad debe ser positiva')

        self.capacity = capacity
        self._index = HashTable()

        # Nodos centinela:
        # head.next representa el elemento más reciente.
        # tail.prev representa el elemento menos reciente.

        self._head, self._tail = _Node(), _Node()

        self._head.next, self._tail.prev = (
            self._tail, self._head
        )

        # Contadores de rendimiento.
        self.hits = self.misses = self.evictions = 0

    # --------------------------------------------------------
    # 2. OBTENER LA CANTIDAD DE ELEMENTOS
    # --------------------------------------------------------

    def __len__(self):
        return len(self._index)

    # --------------------------------------------------------
    # 3. DESVINCULAR UN NODO DE LA LISTA
    # --------------------------------------------------------

    def _unlink(self, node):

        node.prev.next, node.next.prev = (
            node.next, node.prev
        )

    # --------------------------------------------------------
    # 4. INSERTAR UN NODO AL INICIO DE LA LISTA
    # --------------------------------------------------------

    def _push_front(self, node):

        node.prev, node.next = (
            self._head, self._head.next
        )

        self._head.next.prev = node
        self._head.next = node

    # --------------------------------------------------------
    # 5. CONSULTAR UN ELEMENTO DE LA CACHÉ
    # --------------------------------------------------------

    def get(self, key, default=None):

        node = self._index.get(key)

        # Elemento no encontrado.
        if node is None:
            self.misses += 1
            return default

        # Elemento encontrado.
        self.hits += 1

        # Actualizar el orden de uso.
        self._unlink(node)
        self._push_front(node)

        return node.value

    # --------------------------------------------------------
    # 6. INSERTAR O ACTUALIZAR UN ELEMENTO
    # --------------------------------------------------------

    def put(self, key, value):

        node = self._index.get(key)

        # Caso 1: la clave ya existe.
        if node is not None:

            node.value = value

            self._unlink(node)
            self._push_front(node)

            return

        # Caso 2: la caché alcanzó su capacidad máxima.
        if len(self._index) >= self.capacity:

            oldest = self._tail.prev

            self._unlink(oldest)
            del self._index[oldest.key]

            self.evictions += 1

        # Caso 3: insertar un nuevo elemento.
        node = _Node(key, value)

        self._index[key] = node
        self._push_front(node)

    # --------------------------------------------------------
    # 7. ELIMINAR UN ELEMENTO DE LA CACHÉ
    # --------------------------------------------------------

    def delete(self, key):

        node = self._index.pop(key)

        if node is not None:
            self._unlink(node)

    # --------------------------------------------------------
    # 8. OBTENER ESTADÍSTICAS DE RENDIMIENTO
    # --------------------------------------------------------

    def stats(self):

        total = self.hits + self.misses

        return dict(
            capacity=self.capacity,
            size=len(self),
            hits=self.hits,
            misses=self.misses,
            evictions=self.evictions,
            hit_rate=self.hits / total if total else None
        )