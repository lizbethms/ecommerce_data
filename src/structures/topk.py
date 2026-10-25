"""Top-K con heap acotado: O(n log k) tiempo, O(k) espacio."""
from .heap import MinHeap


def top_k(items, k, key=None):
    """Los k elementos de mayor key, ordenados de mayor a menor (estable entre iguales)."""
    if k <= 0:
        return []
    key = key or (lambda x: x)
    heap = MinHeap()
    for index, item in enumerate(items):
        # (score, -index): ante empate se conserva el primero que llegó.
        entry = (key(item), -index)
        if len(heap) < k:
            heap.push(entry, item)
        elif entry > heap.peek()[0]:
            heap.pushpop(entry, item)
    result = []
    while heap:
        result.append(heap.pop()[1])
    return result[::-1]
