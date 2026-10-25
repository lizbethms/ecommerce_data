"""Grafo no dirigido ponderado, PageRank ponderado y Louvain.

PageRank: O(I·(V + E)) para I iteraciones (método de potencias); la masa de
los nodos sin aristas se reparte uniformemente.
Louvain (Blondel et al., 2008): movimientos locales que maximizan la ganancia
de modularidad, seguidos de agregación de comunidades. Cada pasada cuesta
O(E) y en la práctica se hacen pocas pasadas.
"""
import random


class WeightedGraph:
    def __init__(self):
        self.adj = {}

    def add_node(self, node):
        self.adj.setdefault(node, {})

    def add_edge(self, u, v, weight=1.0):
        if u == v:
            raise ValueError('No se admiten bucles')
        self.adj.setdefault(u, {})
        self.adj.setdefault(v, {})
        self.adj[u][v] = self.adj[u].get(v, 0) + weight
        self.adj[v][u] = self.adj[v].get(u, 0) + weight

    def weight(self, u, v):
        return self.adj.get(u, {}).get(v, 0)

    def neighbors(self, node):
        return self.adj.get(node, {})

    def degree(self, node):
        return sum(self.adj.get(node, {}).values())

    def nodes(self):
        return self.adj.keys()

    def edges(self):
        """Cada arista una vez: (u, v, peso)."""
        seen = set()
        for u, neighbors in self.adj.items():
            seen.add(u)
            for v, w in neighbors.items():
                if v not in seen:
                    yield u, v, w

    def number_of_edges(self):
        return sum(len(n) for n in self.adj.values()) // 2

    def total_weight(self):
        return sum(sum(n.values()) for n in self.adj.values()) / 2

    def connected_components(self):
        seen, components = set(), []
        for start in self.adj:
            if start in seen:
                continue
            stack, component = [start], []
            seen.add(start)
            while stack:
                node = stack.pop()
                component.append(node)
                for neighbor in self.adj[node]:
                    if neighbor not in seen:
                        seen.add(neighbor)
                        stack.append(neighbor)
            components.append(component)
        return components


def pagerank(graph, damping=0.85, tol=1e-10, max_iter=100):
    nodes = list(graph.nodes())
    n = len(nodes)
    if not n:
        return {}
    rank = {u: 1 / n for u in nodes}
    strength = {u: graph.degree(u) for u in nodes}
    for _ in range(max_iter):
        dangling = sum(rank[u] for u in nodes if strength[u] == 0)
        base = (1 - damping) / n + damping * dangling / n
        new = {u: base for u in nodes}
        for u in nodes:
            if strength[u]:
                share = damping * rank[u] / strength[u]
                for v, w in graph.adj[u].items():
                    new[v] += share * w
        delta = sum(abs(new[u] - rank[u]) for u in nodes)
        rank = new
        if delta < tol:
            break
    return rank


def modularity(graph, partition, resolution=1.0):
    m = graph.total_weight()
    if not m:
        return 0.0
    internal, totals = {}, {}
    for u, v, w in graph.edges():
        if partition[u] == partition[v]:
            internal[partition[u]] = internal.get(partition[u], 0) + w
    for u in graph.nodes():
        totals[partition[u]] = totals.get(partition[u], 0) + graph.degree(u)
    return sum(internal.get(c, 0) / m - resolution * (t / (2 * m)) ** 2 for c, t in totals.items())


def _one_level(adj, resolution, rng):
    """Movimientos locales. adj puede tener bucles (peso interno de comunidades agregadas)."""
    degree = {u: sum(w for v, w in nbrs.items() if v != u) + 2 * nbrs.get(u, 0) for u, nbrs in adj.items()}
    m2 = sum(degree.values())
    community = {u: u for u in adj}
    totals = dict(degree)
    if not m2:
        return community, False
    improved = False
    order = list(adj)
    rng.shuffle(order)
    moved = True
    while moved:
        moved = False
        for u in order:
            current = community[u]
            links = {}
            for v, w in adj[u].items():
                if v != u:
                    links[community[v]] = links.get(community[v], 0) + w
            totals[current] -= degree[u]
            best, best_gain = current, links.get(current, 0) - resolution * totals[current] * degree[u] / m2
            for c, k_in in links.items():
                gain = k_in - resolution * totals[c] * degree[u] / m2
                if gain > best_gain + 1e-12:
                    best, best_gain = c, gain
            totals[best] += degree[u]
            if best != current:
                community[u] = best
                moved = improved = True
    return community, improved


def _aggregate(adj, community):
    new = {}
    for u, nbrs in adj.items():
        cu = community[u]
        new.setdefault(cu, {})
        for v, w in nbrs.items():
            cv = community[v]
            if u == v:
                new[cu][cu] = new[cu].get(cu, 0) + w
            elif cu == cv:
                new[cu][cu] = new[cu].get(cu, 0) + w / 2  # cada arista interna aparece dos veces
            else:
                new[cu][cv] = new[cu].get(cv, 0) + w
    return new


def louvain(graph, resolution=1.0, seed=2026, max_levels=10):
    """Partición {nodo: comunidad} con etiquetas 0..C-1 (las más grandes primero)."""
    rng = random.Random(seed)
    adj = {u: dict(nbrs) for u, nbrs in graph.adj.items()}
    partition = {u: u for u in adj}
    for _ in range(max_levels):
        community, improved = _one_level(adj, resolution, rng)
        if not improved:
            break
        partition = {u: community[c] for u, c in partition.items()}
        adj = _aggregate(adj, community)
    sizes = {}
    for c in partition.values():
        sizes[c] = sizes.get(c, 0) + 1
    labels = {c: i for i, c in enumerate(sorted(sizes, key=lambda c: (-sizes[c], str(c))))}
    return {u: labels[c] for u, c in partition.items()}
