"""Búsqueda: autocompletado con Trie y resultados por relevancia o popularidad.

El Trie indexa nombres de producto, marcas, tokens de categoría y las
consultas observadas. El peso de un término es la suma de la popularidad de
sus productos (o el número de veces que se buscó, si es una consulta). Una
búsqueda une los productos de los términos que empiezan con cada token y
ordena con Top-K.
"""
from src.structures.hash_table import HashTable
from src.structures.topk import top_k
from src.structures.trie import Trie

from .base import Servicio


def terminos(producto):
    """(término, tipo) con los que se encuentra un producto."""
    salida = {(producto['nombre'], 'producto')}
    if producto['brand']:
        salida.add((producto['brand'], 'marca'))
    if producto['category_code']:
        for parte in producto['category_code'].split('.'):
            salida.add((parte.replace('_', ' '), 'categoria'))
    for token in producto['nombre'].split():
        salida.add((token, 'token'))
    return salida


class ServicioBusqueda(Servicio):
    nombre = 'busqueda'

    def __init__(self, config, catalogo):
        super().__init__(config)
        self.catalogo = catalogo
        self.trie = Trie()
        self.indexados = HashTable(4096)  # product_id -> términos con los que se indexó
        self.consultas = 0

    def indexar(self, producto):
        anteriores = self.indexados.get(producto['product_id'], set())
        actuales = terminos(producto)
        for termino, tipo in actuales - anteriores:
            self.trie.insert(termino.lower(), max(0.0, producto['popularidad']), producto['product_id'], tipo)
        self.indexados[producto['product_id']] = actuales | anteriores

    def indexar_catalogo(self):
        for pid in self.catalogo.ids():
            self.indexar(self.catalogo.registro(pid))

    def procesar(self, evento, contexto):
        if evento['event_type'] == 'search':
            self.trie.insert(evento['query'].lower(), 1.0, None, 'consulta')
            return None
        pid = evento['product_id']
        producto = self.catalogo.registro(pid) if pid else None
        if producto is None:
            return None
        self.indexar(producto)
        delta = (contexto.get('catalogo') or {}).get('delta_popularidad', 0.0)
        if delta:
            for termino, _ in self.indexados[pid]:
                self.trie.add_weight(termino.lower(), delta)
        return None

    def autocompletar(self, prefijo, k=10):
        self.consultas += 1
        return [{'texto': texto, 'peso': round(peso, 2), 'tipo': tipo, 'productos': len(carga or ())}
                for texto, peso, tipo, carga in self.trie.complete(prefijo.strip().lower(), k)]

    def buscar(self, consulta, orden='relevancia', k=20):
        self.consultas += 1
        tokens = [t for t in consulta.lower().split() if t]
        cobertura, exactas = {}, {}
        for i, token in enumerate(tokens):
            for termino, nodo in self.trie.terms(token):
                for pid in nodo.payload or ():
                    cobertura.setdefault(pid, set()).add(i)
                    if termino == token:
                        exactas[pid] = exactas.get(pid, 0) + 1
        if orden == 'popularidad':
            clave = lambda pid: (len(cobertura[pid]), self.catalogo.popularidad(pid))
        elif orden == 'relevancia':
            clave = lambda pid: (len(cobertura[pid]), exactas.get(pid, 0), self.catalogo.popularidad(pid))
        else:
            raise ValueError('Orden: relevancia o popularidad')
        mejores = top_k(cobertura, k, key=clave)
        return {'consulta': consulta, 'orden': orden, 'coincidencias': len(cobertura), 'resultados': [
            dict(self.catalogo.obtener(pid), tokens_coincidentes=len(cobertura[pid]),
                 relevancia=round(len(cobertura[pid]) / len(tokens), 3)) for pid in mejores]}

    def estadisticas(self):
        return dict(super().estadisticas(), terminos=self.trie.size, productos_indexados=len(self.indexados),
                    consultas_servidas=self.consultas)
