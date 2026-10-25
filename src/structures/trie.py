"""Trie de autocompletado con pesos.

Insertar o actualizar un término de longitud L cuesta O(L). Completar un
prefijo cuesta O(L + S + S log k), donde S es el tamaño del subárbol del
prefijo. Cada término guarda su peso y una carga útil (p. ej. ids de producto).
"""
from .topk import top_k


class _Node:
    __slots__ = ('children', 'terminal', 'weight', 'payload', 'kind')

    def __init__(self):
        self.children = {}
        self.terminal = False
        self.weight = 0.0
        self.payload = None
        self.kind = None


class Trie:
    def __init__(self):
        self.root = _Node()
        self.size = 0

    def _walk(self, text):
        node = self.root
        for char in text:
            node = node.children.get(char)
            if node is None:
                return None
        return node

    def insert(self, term, weight=0.0, payload=None, kind=None):
        node = self.root
        for char in term:
            node = node.children.setdefault(char, _Node())
        if not node.terminal:
            node.terminal = True
            node.payload = set()
            self.size += 1
        node.weight += weight
        node.kind = node.kind or kind
        if payload is not None:
            node.payload.add(payload)
        return node

    def add_weight(self, term, delta):
        node = self._walk(term)
        if node is not None and node.terminal:
            node.weight += delta

    def __contains__(self, term):
        node = self._walk(term)
        return node is not None and node.terminal

    def get(self, term):
        node = self._walk(term)
        return node if node is not None and node.terminal else None

    def terms(self, prefix):
        """(término, nodo) de todo el subárbol del prefijo."""
        start = self._walk(prefix)
        if start is None:
            return
        stack = [(prefix, start)]
        while stack:
            text, node = stack.pop()
            if node.terminal:
                yield text, node
            for char, child in node.children.items():
                stack.append((text + char, child))

    def complete(self, prefix, k=10):
        """Top-k [(término, peso, tipo, carga)] por peso dentro del prefijo."""
        best = top_k(self.terms(prefix), k, key=lambda item: (item[1].weight, -len(item[0])))
        return [(term, node.weight, node.kind, node.payload) for term, node in best]
