"""HNSW (Malkov & Yashunin, 2018) simplificado: grafo de proximidad multicapa.

Cada nodo recibe un nivel ⌊-ln U · mL⌋ con mL = 1/ln M. La búsqueda baja de
forma voraz por las capas superiores y en la capa 0 hace una búsqueda en haz
de ancho ef. Inserción y consulta cuestan cerca de O(log n) en la práctica;
el espacio es O(n·M). La vecindad se poda con la heurística simple: se
conservan los M más cercanos.
"""
import math
import random

from .heap import MinHeap
from .kd_tree import squared_distance


class HNSW:
    def __init__(self, M=8, ef_construction=48, ef_search=32, seed=2026):
        self.M, self.M0 = M, 2 * M
        self.ef_construction, self.ef_search = ef_construction, ef_search
        self.mL = 1 / math.log(M)
        self.rng = random.Random(seed)
        self.vectors = {}
        self.layers = []  # layers[l][nodo] = set(vecinos)
        self.entry = None
        self.distance_evaluations = 0

    def __len__(self):
        return len(self.vectors)

    def _distance(self, a, b):
        self.distance_evaluations += 1
        return squared_distance(a, b)

    def _search_layer(self, query, entries, ef, layer):
        visited = set(entries)
        candidates = MinHeap()  # más cercano primero
        results = MinHeap()     # peor primero (distancia negativa)
        for e in entries:
            d = self._distance(query, self.vectors[e])
            candidates.push(d, e)
            results.push(-d, e)
        while candidates:
            d, node = candidates.pop()
            if d > -results.peek()[0]:
                break
            for neighbor in self.layers[layer].get(node, ()):
                if neighbor in visited:
                    continue
                visited.add(neighbor)
                dn = self._distance(query, self.vectors[neighbor])
                if len(results) < ef or dn < -results.peek()[0]:
                    candidates.push(dn, neighbor)
                    results.push(-dn, neighbor)
                    if len(results) > ef:
                        results.pop()
        found = []
        while results:
            negative, node = results.pop()
            found.append((-negative, node))
        return found[::-1]  # de menor a mayor distancia

    def _prune(self, node, layer):
        limit = self.M0 if layer == 0 else self.M
        neighbors = self.layers[layer][node]
        if len(neighbors) > limit:
            vector = self.vectors[node]
            ranked = sorted(neighbors, key=lambda n: self._distance(vector, self.vectors[n]))
            self.layers[layer][node] = set(ranked[:limit])

    def insert(self, key, vector):
        if key in self.vectors:
            raise ValueError('Clave repetida')
        self.vectors[key] = vector
        level = int(-math.log(1 - self.rng.random()) * self.mL)
        while len(self.layers) <= level:
            self.layers.append({})
        for layer in range(level + 1):
            self.layers[layer][key] = set()
        if self.entry is None:
            self.entry = key
            return
        entry_level = self._level(self.entry)
        entries = [self.entry]
        for layer in range(entry_level, level, -1):
            entries = [self._search_layer(vector, entries, 1, layer)[0][1]]
        for layer in range(min(level, entry_level), -1, -1):
            found = self._search_layer(vector, entries, self.ef_construction, layer)
            for _, neighbor in found[:self.M]:
                self.layers[layer][key].add(neighbor)
                self.layers[layer][neighbor].add(key)
                self._prune(neighbor, layer)
            entries = [node for _, node in found]
        if level > entry_level:
            self.entry = key

    def _level(self, key):
        level = 0
        while level + 1 < len(self.layers) and key in self.layers[level + 1]:
            level += 1
        return level

    def search(self, query, k, exclude=None):
        """[(clave, distancia)] aproximados, de menor a mayor distancia."""
        if self.entry is None:
            return []
        entries = [self.entry]
        for layer in range(self._level(self.entry), 0, -1):
            entries = [self._search_layer(query, entries, 1, layer)[0][1]]
        found = self._search_layer(query, entries, max(self.ef_search, k + 1), 0)
        return [(node, math.sqrt(d)) for d, node in found if node != exclude][:k]
