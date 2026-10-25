"""Consulta de productos: lookup puntual, rangos por precio/categoría y disponibilidad.

- Consulta puntual: HashTable por product_id, con un LRUCache delante.
- Rango de precio: B+Tree con clave Decimal(price).
- Rango de categoría: B+Tree con clave category_code. Un prefijo como
  "electronics" equivale al rango [prefijo, prefijo + U+FFFF].
- Por category_id: HashTable category_id -> conjunto de productos.
"""
from decimal import Decimal

from src.structures.bplus_tree import BPlusTree
from src.structures.hash_table import HashTable
from src.structures.lru import LRUCache
from src.structures.topk import top_k

from .base import Servicio


def nombre_producto(category_code, brand, category_id):
    hoja = category_code.split('.')[-1].replace('_', ' ') if category_code else None
    partes = [p for p in (brand, hoja) if p]
    return ' '.join(partes) if partes else f'producto categoria {str(category_id)[-6:]}'


class ServicioCatalogo(Servicio):
    nombre = 'catalogo'

    def __init__(self, config):
        super().__init__(config)
        self.productos = HashTable(4096)
        self.cache = LRUCache(config.lru_capacidad)
        self.por_precio = BPlusTree(config.orden_bplus)
        self.por_codigo = BPlusTree(config.orden_bplus)
        self.por_category_id = HashTable()

    # ---------- carga y actualización ----------
    def _registrar(self, product_id, category_id=None, category_code=None, brand=None, price=None, stock=None):
        producto = self.productos.get(product_id)
        if producto is None:
            producto = dict(product_id=product_id, category_id=None, category_code=None, brand=None, price=None,
                            stock=self.config.stock_base if stock is None else stock,
                            vendidos=0, devueltos=0, vistas=0, carritos=0, resenas=0, suma_rating=0,
                            popularidad=0.0, nombre=None)
            self.productos[product_id] = producto
        if price is not None and price != producto['price']:
            if producto['price'] is not None:
                self.por_precio.remove(Decimal(producto['price']), product_id)
            producto['price'] = price
            self.por_precio.insert(Decimal(price), product_id)
        if category_code and category_code != producto['category_code']:
            if producto['category_code']:
                self.por_codigo.remove(producto['category_code'], product_id)
            producto['category_code'] = category_code
            self.por_codigo.insert(category_code, product_id)
        if category_id and category_id != producto['category_id']:
            if producto['category_id']:
                self.por_category_id.get(producto['category_id'], set()).discard(product_id)
            producto['category_id'] = category_id
            self.por_category_id.setdefault(category_id, set()).add(product_id)
        if brand:
            producto['brand'] = brand
        producto['nombre'] = nombre_producto(producto['category_code'], producto['brand'], producto['category_id'])
        self.cache.delete(product_id)
        return producto

    def cargar_catalogo(self, filas):
        for fila in filas:
            self._registrar(fila['product_id'], fila['category_id'], fila['category_code'], fila['brand'],
                            fila['last_observed_price'])

    def cargar_inventario(self, filas):
        """Stock inicial = reposición sintética total + stock_base; el tráfico descuenta compras."""
        for fila in filas:
            producto = self._registrar(fila['product_id'])
            producto['stock'] = fila['supplied'] + self.config.stock_base

    def procesar(self, evento, contexto):
        pid = evento['product_id']
        if pid is None:
            return None
        nuevo = pid not in self.productos
        producto = self._registrar(pid, evento['category_id'], evento['category_code'], evento['brand'], evento['price'])
        tipo = evento['event_type']
        pesos = self.config.pesos_interaccion
        delta = pesos.get(tipo, 0.0)
        if tipo == 'view':
            producto['vistas'] += 1
        elif tipo == 'cart':
            producto['carritos'] += 1
        elif tipo == 'purchase':
            producto['vendidos'] += evento['quantity']
            producto['stock'] -= evento['quantity']
        elif tipo == 'return':
            producto['devueltos'] += evento['quantity']
            producto['stock'] += evento['quantity']
        elif tipo == 'review':
            producto['resenas'] += 1
            producto['suma_rating'] += evento['rating']
            delta = pesos['review'] * (evento['rating'] - 3)
        producto['popularidad'] += delta
        return {'nuevo_producto': nuevo, 'stock': producto['stock'], 'sin_stock': producto['stock'] < 0,
                'delta_popularidad': delta}

    # ---------- consultas ----------
    def vista(self, producto):
        resenas = producto['resenas']
        return dict(product_id=producto['product_id'], nombre=producto['nombre'], category_id=producto['category_id'],
                    category_code=producto['category_code'], brand=producto['brand'], price=producto['price'],
                    stock=producto['stock'], disponible=producto['stock'] > 0, vendidos=producto['vendidos'],
                    devueltos=producto['devueltos'], vistas=producto['vistas'], carritos=producto['carritos'],
                    rating_promedio=round(producto['suma_rating'] / resenas, 2) if resenas else None,
                    resenas=resenas, popularidad=round(producto['popularidad'], 2))

    def obtener(self, product_id):
        en_cache = self.cache.get(product_id)
        if en_cache is not None:
            return dict(en_cache, cache='hit')
        producto = self.productos.get(product_id)
        if producto is None:
            return None
        resultado = self.vista(producto)
        self.cache.put(product_id, resultado)
        return dict(resultado, cache='miss')

    def popularidad(self, product_id):
        producto = self.productos.get(product_id)
        return producto['popularidad'] if producto else 0.0

    def rango(self, precio_min=None, precio_max=None, categoria=None, category_id=None,
              solo_disponibles=False, limite=50):
        """Consulta por rango de precio, opcionalmente filtrada por prefijo de categoría."""
        bajo = Decimal(str(precio_min)) if precio_min is not None else None
        alto = Decimal(str(precio_max)) if precio_max is not None else None
        if categoria and bajo is None and alto is None:
            fuente = ((None, pid) for _, pid in self.por_codigo.range(categoria, categoria + '￿'))
        else:
            fuente = self.por_precio.range(bajo, alto)
        resultados = []
        for _, pid in fuente:
            producto = self.productos[pid]
            if categoria and not (producto['category_code'] or '').startswith(categoria):
                continue
            if category_id and producto['category_id'] != category_id:
                continue
            if solo_disponibles and producto['stock'] <= 0:
                continue
            resultados.append(self.vista(producto))
            if len(resultados) >= limite:
                break
        return resultados

    def por_categoria(self, category_id, limite=50):
        pids = self.por_category_id.get(category_id, set())
        return [self.vista(self.productos[p]) for p in sorted(pids)[:limite]]

    def categorias(self, nivel=None):
        conteo = {}
        for codigo, _ in self.por_codigo.range():
            clave = '.'.join(codigo.split('.')[:nivel]) if nivel else codigo
            conteo[clave] = conteo.get(clave, 0) + 1
        return [{'category_code': c, 'productos': n} for c, n in sorted(conteo.items())]

    def populares(self, k=10, excluir=()):
        excluir = set(excluir)
        candidatos = (p for _, p in self.productos.items() if p['product_id'] not in excluir)
        return top_k(candidatos, k, key=lambda p: p['popularidad'])

    def ids(self):
        return list(self.productos.keys())

    def registro(self, product_id):
        return self.productos.get(product_id)

    def precio_maximo(self):
        ultimo = None
        for clave, _ in self.por_precio.range():
            ultimo = clave
        return float(ultimo) if ultimo is not None else 0.0

    def estadisticas(self):
        return dict(super().estadisticas(), productos=len(self.productos), cache=self.cache.stats(),
                    bplus_precio={'entradas': len(self.por_precio), 'altura': self.por_precio.height()},
                    bplus_categoria={'entradas': len(self.por_codigo), 'altura': self.por_codigo.height()},
                    categorias_id=len(self.por_category_id))
