"""Co-compra: grafo de productos ponderado por órdenes compartidas.

El peso de la arista (a, b) es el número de órdenes distintas que contienen a
ambos productos. Cada par se cuenta una vez por orden (HashTable order_id ->
productos), así que un reenvío o una segunda unidad no lo duplican. PageRank
da los productos influyentes y Louvain las agrupaciones de consumo. Ambos se
recalculan en diferido, solo cuando el grafo cambió.
"""
from src.structures.graph import WeightedGraph, louvain, modularity, pagerank
from src.structures.hash_table import HashTable
from src.structures.topk import top_k

from .base import Servicio


class ServicioCoCompra(Servicio):
    nombre = 'cocompra'
    tipos = frozenset({'purchase'})

    def __init__(self, config):
        super().__init__(config)
        self.grafo = WeightedGraph()
        self.por_orden = HashTable(1024)
        self.version = 0
        self._calculado = None  # (versión, pagerank, partición, modularidad)

    def procesar(self, evento, contexto):
        pid, orden = evento['product_id'], evento['order_id']
        productos = self.por_orden.setdefault(orden, set())
        if pid in productos:
            return {'aristas_actualizadas': 0, 'motivo': 'producto ya contado en esta orden'}
        self.grafo.add_node(pid)
        for otro in productos:
            self.grafo.add_edge(pid, otro, 1)
        actualizadas = len(productos)
        productos.add(pid)
        if actualizadas:
            self.version += 1
        return {'aristas_actualizadas': actualizadas}

    def _analisis(self):
        if self._calculado is None or self._calculado[0] != self.version:
            # Solo los productos con al menos una co-compra forman el grafo de dominio.
            sub = WeightedGraph()
            for u, v, w in self.grafo.edges():
                sub.add_edge(u, v, w)
            rank = pagerank(sub)
            particion = louvain(sub, seed=self.config.semilla)
            self._calculado = (self.version, rank, particion, modularity(sub, particion) if particion else 0.0)
        return self._calculado[1:]

    def pares(self, k=10):
        return [{'producto_a': u, 'producto_b': v, 'ordenes_compartidas': w}
                for u, v, w in top_k(self.grafo.edges(), k, key=lambda e: e[2])]

    def influyentes(self, k=10):
        rank, _, _ = self._analisis()
        return [{'product_id': p, 'pagerank': round(r, 6), 'grado_ponderado': self.grafo.degree(p),
                 'vecinos': len(self.grafo.neighbors(p))}
                for p, r in top_k(rank.items(), k, key=lambda item: item[1])]

    def comunidades(self, min_tamano=2, limite=20, top=5):
        rank, particion, q = self._analisis()
        grupos = {}
        for producto, comunidad in particion.items():
            grupos.setdefault(comunidad, []).append(producto)
        salida = []
        for comunidad, miembros in sorted(grupos.items(), key=lambda item: -len(item[1])):
            if len(miembros) < min_tamano:
                continue
            principales = top_k(miembros, top, key=lambda p: rank.get(p, 0))
            salida.append({'comunidad': comunidad, 'tamano': len(miembros), 'principales': principales})
            if len(salida) >= limite:
                break
        return {'modularidad': round(q, 4), 'comunidades_totales': len(grupos), 'comunidades': salida}

    def comunidad_de(self, product_id):
        _, particion, _ = self._analisis()
        return particion.get(product_id)

    def cross_selling(self, product_id, k=10):
        """Vecinos directos por peso (desempate por PageRank); si faltan, se completa
        con productos influyentes de la misma comunidad."""
        rank, particion, _ = self._analisis()
        vecinos = self.grafo.neighbors(product_id)
        directos = top_k(vecinos.items(), k, key=lambda item: (item[1], rank.get(item[0], 0)))
        maximo = max((w for _, w in directos), default=1)
        salida = [{'product_id': p, 'puntaje': round(w / maximo, 4), 'ordenes_compartidas': w, 'motivo': 'co-compra'}
                  for p, w in directos]
        comunidad = particion.get(product_id)
        if len(salida) < k and comunidad is not None:
            vistos = {product_id, *vecinos}
            mismos = (p for p, c in particion.items() if c == comunidad and p not in vistos)
            for p in top_k(mismos, k - len(salida), key=lambda p: rank.get(p, 0)):
                salida.append({'product_id': p, 'puntaje': 0.25, 'ordenes_compartidas': 0, 'motivo': 'misma_comunidad'})
        return salida

    def estadisticas(self):
        componentes = self.grafo.connected_components()
        return dict(super().estadisticas(), nodos=len(self.grafo.adj), aristas=self.grafo.number_of_edges(),
                    peso_total=self.grafo.total_weight(), ordenes=len(self.por_orden),
                    componentes=len(componentes), componente_mayor=max(map(len, componentes), default=0))
