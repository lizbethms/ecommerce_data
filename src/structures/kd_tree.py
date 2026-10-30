"""KD-Tree con KNN exacto (distancia euclidiana).

La construcción por mediana cuesta O(n log² n). Una consulta KNN es O(log n)
en promedio para dimensiones bajas y se degrada hacia O(n) cuando la
dimensión crece: la poda pierde eficacia, pero el resultado sigue siendo exacto.
"""
import math
from numbers import Real

from .heap import MinHeap


def squared_distance(a, b):
    """Distancia euclidiana al cuadrado entre vectores de igual dimensión."""
    if len(a) != len(b):
        raise ValueError(f'Dimensiones incompatibles: {len(a)} y {len(b)}')
    return sum((x - y) ** 2 for x, y in zip(a, b))


def _point(point, expected_dim=None):
    """Valida y congela un vector para que el índice no pueda quedar obsoleto."""
    try:
        point = tuple(point)
    except TypeError:
        raise ValueError('El vector debe ser iterable') from None
    if not point:
        raise ValueError('Los vectores no pueden estar vacíos')
    if expected_dim is not None and len(point) != expected_dim:
        raise ValueError(f'Dimensión inválida: {len(point)}; esperada: {expected_dim}')
    if any(not isinstance(value, Real) or not math.isfinite(value) for value in point):
        raise ValueError('Los vectores requieren números reales finitos')
    return point


class _Node:
    __slots__ = ('key', 'point', 'axis', 'left', 'right')

    def __init__(self, key, point, axis, left, right):
        self.key, self.point, self.axis, self.left, self.right = key, point, axis, left, right


class KDTree:
    def __init__(self, items):
        """items: iterable de (id, vector)."""
        items = list(items)
        self.size = len(items)
        if not items:
            self.dim, self.root, self._rank = 0, None, {}
            return
        first = _point(items[0][1])
        self.dim = len(first)
        normalized = []
        seen = set()
        for index, (key, point) in enumerate(items):
            try:
                if key in seen:
                    raise ValueError(f'ID duplicado: {key!r}')
                seen.add(key)
            except TypeError:
                raise ValueError(f'ID no hashable en posición {index}: {key!r}') from None
            normalized.append((key, first if index == 0 else _point(point, self.dim)))
        # El rango permite desempatar distancias sin comparar IDs heterogéneos.
        ordered_keys = sorted(seen, key=lambda key: (type(key).__name__, repr(key)))
        self._rank = {key: rank for rank, key in enumerate(ordered_keys)}
        self.root = self._build(normalized, 0)

    def _build(self, items, depth):
        if not items:
            return None
        axis = depth % self.dim
        items = sorted(items, key=lambda item: (item[1][axis], self._rank[item[0]]))
        mid = len(items) // 2
        key, point = items[mid]
        return _Node(key, point, axis, self._build(items[:mid], depth + 1), self._build(items[mid + 1:], depth + 1))

    def knn(self, query, k, exclude=None, with_stats=False):
        """Devuelve hasta k vecinos, ordenados por distancia e ID estable.

        Con ``with_stats=True`` devuelve ``(vecinos, métricas)`` para observar
        el trabajo de la poda sin modificar el contrato habitual.
        """
        if k <= 0 or self.root is None:
            empty = []
            stats = dict(total_nodes=self.size, nodes_visited=0, distance_evaluations=0,
                         branches_pruned=0, visited_fraction=0.0)
            return (empty, stats) if with_stats else empty
        query = _point(query, self.dim)
        # La menor clave representa el peor candidato: mayor distancia y, en
        # empate, mayor rango. Así MinHeap funciona como un max-heap acotado.
        best = MinHeap()
        stats = dict(total_nodes=self.size, nodes_visited=0, distance_evaluations=0,
                     branches_pruned=0)

        def visit(node):
            if node is None:
                return
            stats['nodes_visited'] += 1
            if node.key != exclude:
                d = squared_distance(query, node.point)
                stats['distance_evaluations'] += 1
                candidate = (-d, -self._rank[node.key])
                if len(best) < k:
                    best.push(candidate, node.key)
                elif candidate > best.peek()[0]:
                    best.pushpop(candidate, node.key)
            diff = query[node.axis] - node.point[node.axis]
            near, far = (node.left, node.right) if diff < 0 else (node.right, node.left)
            visit(near)
            # Solo se explora el otro lado si la esfera actual cruza el hiperplano.
            worst_distance = -best.peek()[0][0] if best else math.inf
            if len(best) < k or diff * diff <= worst_distance:
                visit(far)
            elif far is not None:
                stats['branches_pruned'] += 1

        visit(self.root)
        result = []
        while best:
            (negative, _), key = best.pop()
            result.append((key, math.sqrt(-negative)))
        result.reverse()
        stats['visited_fraction'] = stats['nodes_visited'] / self.size
        return (result, stats) if with_stats else result
