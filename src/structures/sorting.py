"""Ordenación estable y búsqueda binaria (etapa 1: lotes ordenados)."""


def merge_sort(items, key=None):
    """Merge sort estable. Tiempo O(n log n), espacio O(n)."""
    key = key or (lambda x: x)
    items = list(items)
    if len(items) <= 1:
        return items
    keyed = [(key(x), x) for x in items]
    width = 1
    buffer = keyed[:]
    while width < len(keyed):
        for lo in range(0, len(keyed), 2 * width):
            mid, hi = min(lo + width, len(keyed)), min(lo + 2 * width, len(keyed))
            i, j, k = lo, mid, lo
            while i < mid and j < hi:
                # <= mantiene la estabilidad: a igualdad gana el de la izquierda.
                if keyed[i][0] <= keyed[j][0]:
                    buffer[k] = keyed[i]
                    i += 1
                else:
                    buffer[k] = keyed[j]
                    j += 1
                k += 1
            buffer[k:hi] = keyed[i:mid] if i < mid else keyed[j:hi]
        keyed, buffer = buffer, keyed
        width *= 2
    return [x for _, x in keyed]


def bisect_left(items, value, key=None):
    """Primer índice i con key(items[i]) >= value. O(log n)."""
    lo, hi = 0, len(items)
    while lo < hi:
        mid = (lo + hi) // 2
        current = key(items[mid]) if key else items[mid]
        if current < value:
            lo = mid + 1
        else:
            hi = mid
    return lo


def bisect_right(items, value, key=None):
    """Primer índice i con key(items[i]) > value. O(log n)."""
    lo, hi = 0, len(items)
    while lo < hi:
        mid = (lo + hi) // 2
        current = key(items[mid]) if key else items[mid]
        if value < current:
            hi = mid
        else:
            lo = mid + 1
    return lo


def binary_search(items, value, key=None):
    """Índice de value en una secuencia ordenada, o -1. O(log n)."""
    i = bisect_left(items, value, key)
    if i < len(items) and (key(items[i]) if key else items[i]) == value:
        return i
    return -1
