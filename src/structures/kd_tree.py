"""KD-Tree con KNN exacto (distancia euclidiana).

La construcción por mediana cuesta O(n log² n). Una consulta KNN es O(log n)
en promedio para dimensiones bajas y se degrada hacia O(n) cuando la
dimensión crece: la poda pierde eficacia, pero el resultado sigue siendo exacto.
"""
from .heap import MinHeap


def squared_distance(a, b):
    return sum((x - y) ** 2 for x, y in zip(a, b))


class _Node:
    __slots__ = ('key', 'point', 'axis', 'left', 'right')

    def __init__(self, key, point, axis, left, right):
        self.key, self.point, self.axis, self.left, self.right = key, point, axis, left, right


class KDTree:
    def __init__(self, items):
        """items: iterable de (id, vector)."""
        items = list(items)
        self.size = len(items)
        self.dim = len(items[0][1]) if items else 0
        self.root = self._build(items, 0)

    def _build(self, items, depth):
        if not items:
            return None
        axis = depth % self.dim
        items = sorted(items, key=lambda item: item[1][axis])
        mid = len(items) // 2
        key, point = items[mid]
        return _Node(key, point, axis, self._build(items[:mid], depth + 1), self._build(items[mid + 1:], depth + 1))

    def knn(self, query, k, exclude=None):
        """Lista [(id, distancia)] de los k más cercanos, de menor a mayor distancia."""
        if k <= 0 or self.root is None:
            return []
        best = MinHeap()  # max-heap por distancia negativa: la raíz es el peor candidato

        def visit(node):
            if node is None:
                return
            if node.key != exclude:
                d = squared_distance(query, node.point)
                if len(best) < k:
                    best.push(-d, node.key)
                elif d < -best.peek()[0]:
                    best.pushpop(-d, node.key)
            diff = query[node.axis] - node.point[node.axis]
            near, far = (node.left, node.right) if diff < 0 else (node.right, node.left)
            visit(near)
            # Solo se explora el otro lado si la esfera actual cruza el hiperplano.
            if len(best) < k or diff * diff < -best.peek()[0]:
                visit(far)

        visit(self.root)
        result = []
        while best:
            negative, key = best.pop()
            result.append((key, (-negative) ** 0.5))
        return result[::-1]
