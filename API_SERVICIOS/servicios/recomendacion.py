"""Productos relacionados y recomendaciones.

- Atributos: un vector por producto (log del precio, hashing de categoría raíz
  y hoja, marca, popularidad y conversión). Los similares exactos salen del
  KD-Tree y los aproximados de HNSW, en el mismo espacio y con la misma
  métrica, así que se puede medir el recall@k de HNSW frente al exacto.
- Comportamiento: SparseMatrix usuario x producto con pesos por tipo de
  evento. Cada producto es el conjunto de usuarios con interacción positiva;
  MinHash + LSH devuelve candidatos por Jaccard.
- Complementarios: vecinos del grafo de co-compra.
Los índices se reconstruyen en diferido: si hubo cambios y pasó
``reconstruir_cada_seg``, o cuando se fuerza la reconstrucción.
"""
import hashlib
import math
import time

from src.structures.hash_table import HashTable
from src.structures.hnsw import HNSW
from src.structures.kd_tree import KDTree
from src.structures.minhash_lsh import LSHIndex, MinHash, jaccard
from src.structures.sparse_matrix import SparseMatrix
from src.structures.topk import top_k

from .base import Servicio

DIM_RAIZ, DIM_HOJA, DIM_MARCA = 8, 4, 4


def _cubeta(texto, dimension):
    return int.from_bytes(hashlib.blake2b(texto.encode(), digest_size=4).digest(), 'little') % dimension


class ServicioRecomendacion(Servicio):
    nombre = 'recomendacion'

    def __init__(self, config, catalogo, cocompra):
        super().__init__(config)
        self.catalogo, self.cocompra = catalogo, cocompra
        self.matriz = SparseMatrix()
        self.comprados = HashTable(1024)  # user_id -> productos comprados
        self.minhash = MinHash(config.minhash_permutaciones, config.semilla)
        self.sucio = True
        self.construido = None
        self.kd = self.hnsw = self.lsh = None
        self.vectores = {}
        self.usuarios_por_producto = {}
        self.tiempos = {}

    def procesar(self, evento, contexto):
        pid, uid = evento['product_id'], evento['user_id']
        if pid is None:
            return None
        peso = self.config.pesos_interaccion.get(evento['event_type'], 0.0)
        if evento['event_type'] == 'review':
            peso *= evento['rating'] - 3
        if peso:
            self.matriz.add(uid, pid, peso)
        if evento['event_type'] == 'purchase':
            self.comprados.setdefault(uid, set()).add(pid)
        self.sucio = True
        return None

    # ---------- representaciones ----------
    def vector(self, producto, log_precio_max, log_pop_max):
        v = [0.0] * (1 + DIM_RAIZ + DIM_HOJA + DIM_MARCA + 2)
        precio = float(producto['price'] or 0)
        v[0] = math.log1p(precio) / log_precio_max if log_precio_max else 0.0
        if producto['category_code']:
            partes = producto['category_code'].split('.')
            v[1 + _cubeta(partes[0], DIM_RAIZ)] = 1.0
            v[1 + DIM_RAIZ + _cubeta(producto['category_code'], DIM_HOJA)] = 0.7
        else:
            v[1 + DIM_RAIZ + _cubeta(str(producto['category_id']), DIM_HOJA)] = 0.7
        if producto['brand']:
            v[1 + DIM_RAIZ + DIM_HOJA + _cubeta(producto['brand'], DIM_MARCA)] = 0.5
        popularidad = max(0.0, producto['popularidad'])
        v[-2] = 0.5 * math.log1p(popularidad) / log_pop_max if log_pop_max else 0.0
        v[-1] = 0.3 * min(1.0, producto['vendidos'] / (producto['vistas'] + 1))
        return v

    def reconstruir(self, forzar=False):
        ahora = time.monotonic()
        vencido = self.construido is None or ahora - self.construido >= self.config.reconstruir_cada_seg
        if not forzar and not (self.sucio and vencido):
            return False
        productos = [self.catalogo.registro(p) for p in self.catalogo.ids()]
        if not productos:
            return False
        inicio = time.perf_counter()
        log_precio = math.log1p(max(float(p['price'] or 0) for p in productos))
        log_pop = math.log1p(max(max(0.0, p['popularidad']) for p in productos))
        self.vectores = {p['product_id']: self.vector(p, log_precio, log_pop) for p in productos}
        t0 = time.perf_counter()
        self.kd = KDTree(self.vectores.items())
        t1 = time.perf_counter()
        self.hnsw = HNSW(self.config.hnsw_m, self.config.hnsw_ef, self.config.hnsw_ef, self.config.semilla)
        for pid, vector in self.vectores.items():
            self.hnsw.insert(pid, vector)
        t2 = time.perf_counter()
        filas = self.config.minhash_permutaciones // self.config.lsh_bandas
        self.lsh = LSHIndex(self.config.lsh_bandas, filas)
        self.usuarios_por_producto = {}
        for pid in self.matriz.cols():
            usuarios = {u for u, w in self.matriz.col(pid).items() if w > 0}
            if usuarios:
                self.usuarios_por_producto[pid] = usuarios
                self.lsh.insert(pid, self.minhash.signature(usuarios))
        t3 = time.perf_counter()
        self.tiempos = dict(vectores_s=round(t0 - inicio, 4), kd_tree_s=round(t1 - t0, 4),
                            hnsw_s=round(t2 - t1, 4), minhash_lsh_s=round(t3 - t2, 4))
        self.construido, self.sucio = time.monotonic(), False
        return True

    # ---------- consultas ----------
    def similares(self, product_id, k=10, metodo='hnsw'):
        self.reconstruir()
        if product_id not in self.vectores and metodo != 'minhash':
            return None
        if metodo == 'knn':
            vecinos = [(p, round(d, 4)) for p, d in self.kd.knn(self.vectores[product_id], k, exclude=product_id)]
            return {'metodo': 'kd_tree_exacto', 'resultados': self._detallar(vecinos, 'distancia')}
        if metodo == 'hnsw':
            consulta = self.vectores[product_id]
            aproximados = self.hnsw.search(consulta, k, exclude=product_id)
            exactos = {p for p, _ in self.kd.knn(consulta, k, exclude=product_id)}
            recall = len(exactos & {p for p, _ in aproximados}) / len(exactos) if exactos else None
            return {'metodo': 'hnsw', 'recall_vs_exacto': recall,
                    'resultados': self._detallar([(p, round(d, 4)) for p, d in aproximados], 'distancia')}
        if metodo == 'minhash':
            if self.lsh is None or product_id not in self.lsh.signatures:
                return {'metodo': 'minhash_lsh', 'resultados': [], 'nota': 'producto sin interacciones de usuarios'}
            base = self.usuarios_por_producto[product_id]
            resultados = []
            for p, estimado in self.lsh.query(product_id, k):
                fila = self.catalogo.obtener(p) or {'product_id': p}
                resultados.append(dict(fila, jaccard_estimado=round(estimado, 4),
                                       jaccard_exacto=round(jaccard(base, self.usuarios_por_producto[p]), 4)))
            return {'metodo': 'minhash_lsh', 'resultados': resultados}
        raise ValueError('Método: knn, hnsw o minhash')

    def _detallar(self, pares, campo):
        return [dict(self.catalogo.obtener(p) or {'product_id': p}, **{campo: valor}) for p, valor in pares]

    def complementarios(self, product_id, k=10):
        return [dict(self.catalogo.obtener(c['product_id']) or {}, **c)
                for c in self.cocompra.cross_selling(product_id, k)]

    def para_usuario(self, user_id, k=10):
        """Combina co-compra, similitud de atributos y de comportamiento desde las
        interacciones más fuertes del usuario. Si no hay historial, usa popularidad."""
        self.reconstruir()
        fila = self.matriz.row(user_id)
        excluir = self.comprados.get(user_id, set())
        semillas = [(p, w) for p, w in top_k(fila.items(), 5, key=lambda item: item[1]) if w > 0]
        if not semillas:
            populares = self.catalogo.populares(k, excluir)
            return {'estrategia': 'popularidad', 'resultados': [
                dict(self.catalogo.vista(p), puntaje=round(p['popularidad'], 3), motivos=['popular']) for p in populares]}
        puntajes, motivos = {}, {}

        def sumar(candidato, valor, motivo):
            if candidato in excluir:
                return
            puntajes[candidato] = puntajes.get(candidato, 0.0) + valor
            motivos.setdefault(candidato, set()).add(motivo)

        maximo = max(w for _, w in semillas)
        for pid, peso in semillas:
            w = peso / maximo
            for c in self.cocompra.cross_selling(pid, 10):
                sumar(c['product_id'], 1.0 * w * c['puntaje'], 'co-compra')
            if pid in self.vectores:
                for c, d in self.hnsw.search(self.vectores[pid], 10, exclude=pid):
                    sumar(c, 0.6 * w / (1 + d), 'atributos_similares')
            if self.lsh is not None and pid in self.lsh.signatures:
                for c, j in self.lsh.query(pid, 10):
                    sumar(c, 0.8 * w * j, 'comportamiento_similar')
        for pid, _ in semillas:
            puntajes.pop(pid, None)
        mejores = top_k(puntajes.items(), k, key=lambda item: item[1])
        return {'estrategia': 'hibrida', 'semillas': [p for p, _ in semillas], 'resultados': [
            dict(self.catalogo.obtener(p) or {'product_id': p}, puntaje=round(s, 4), motivos=sorted(motivos[p]))
            for p, s in mejores]}

    def estadisticas(self):
        filas, columnas = self.matriz.shape
        return dict(super().estadisticas(), matriz={'usuarios': filas, 'productos': columnas, 'nnz': self.matriz.nnz},
                    indices_construidos=self.construido is not None, pendiente_reconstruir=self.sucio,
                    vectores=len(self.vectores), conjuntos_minhash=len(self.lsh.signatures) if self.lsh else 0,
                    hnsw_capas=len(self.hnsw.layers) if self.hnsw else 0, tiempos_construccion=self.tiempos)
