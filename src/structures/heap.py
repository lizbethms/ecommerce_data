
"""
Implementación de Heap Binario Mínimo con desempate estable.

Estructura de datos:
    - Heap binario mínimo implementado mediante una lista.
    - Cada entrada contiene (clave, secuencia, valor).

Características:
    - Prioriza los elementos con menor clave.
    - Mantiene el orden de llegada para claves iguales (FIFO).
    - Evita comparar directamente los valores almacenados.

Complejidad temporal:
    - push():     O(log n)
    - pop():      O(log n)
    - peek():     O(1)
    - pushpop():  O(log n)
    - smallest(): O(n log n)

Complejidad espacial:
    - O(n)
"""

from itertools import count


# ============================================================
# CLASE: MinHeap
# Implementa un Heap Binario Mínimo con desempate estable.
# ============================================================

class MinHeap:

    # --------------------------------------------------------
    # 1. INICIALIZACIÓN DEL HEAP
    # --------------------------------------------------------

    def __init__(self):

        # Lista que almacena los elementos del heap.
        self._items = []

        # Contador para mantener el orden de llegada.
        self._sequence = count()

    # --------------------------------------------------------
    # 2. OBTENER LA CANTIDAD DE ELEMENTOS
    # --------------------------------------------------------

    def __len__(self):

        return len(self._items)

    # --------------------------------------------------------
    # 3. VERIFICAR SI EL HEAP CONTIENE ELEMENTOS
    # --------------------------------------------------------

    def __bool__(self):

        return bool(self._items)

    # --------------------------------------------------------
    # 4. INSERTAR UN ELEMENTO EN EL HEAP
    # --------------------------------------------------------

    def push(self, key, value=None):

        # Insertar el elemento con su secuencia de llegada.
        self._items.append(
            (key, next(self._sequence), value)
        )

        # Restaurar la propiedad del heap hacia arriba.
        self._sift_up(len(self._items) - 1)

    # --------------------------------------------------------
    # 5. CONSULTAR EL ELEMENTO MÍNIMO
    # --------------------------------------------------------

    def peek(self):

        # Validar que el heap no esté vacío.
        if not self._items:
            raise IndexError('Heap vacío')

        # Obtener el elemento ubicado en la raíz.
        key, _, value = self._items[0]

        return key, value

    # --------------------------------------------------------
    # 6. EXTRAER EL ELEMENTO MÍNIMO
    # --------------------------------------------------------

    def pop(self):

        # Validar que el heap contenga elementos.
        if not self._items:
            raise IndexError('Heap vacío')

        # Extraer el último elemento.
        last = self._items.pop()

        # Caso 1: el heap tenía un único elemento.
        if not self._items:
            return last[0], last[2]

        # Caso 2: el heap contiene más elementos.
        top = self._items[0]

        # Reemplazar la raíz con el último elemento.
        self._items[0] = last

        # Restaurar la propiedad del heap hacia abajo.
        self._sift_down(0)

        return top[0], top[2]

    # --------------------------------------------------------
    # 7. INSERTAR Y EXTRAER EL ELEMENTO MÍNIMO
    # --------------------------------------------------------

    def pushpop(self, key, value=None):

        """
        Inserta y extrae el mínimo en un solo O(log n).
        """

        # Crear la nueva entrada.
        entry = (key, next(self._sequence), value)

        # Comparar la nueva entrada con la raíz.
        if self._items and self._items[0] < entry:

            # Intercambiar la entrada con el mínimo actual.
            entry, self._items[0] = (
                self._items[0], entry
            )

            # Restaurar la propiedad del heap.
            self._sift_down(0)

        return entry[0], entry[2]

    # --------------------------------------------------------
    # 8. OBTENER LOS N ELEMENTOS MÁS PEQUEÑOS
    # --------------------------------------------------------

    def smallest(self, n):

        """
        Los n menores sin modificar el heap:
        O(n log n) sobre una copia.
        """

        # Crear una copia independiente del heap.
        copy = MinHeap()

        # Copiar los elementos originales.
        copy._items = list(self._items)

        # Extraer los n elementos más pequeños.
        return [
            copy.pop()
            for _ in range(min(n, len(copy)))
        ]

    # --------------------------------------------------------
    # 9. RESTAURAR LA PROPIEDAD DEL HEAP HACIA ARRIBA
    # --------------------------------------------------------

    def _sift_up(self, i):

        items = self._items

        # Continuar mientras el nodo no sea la raíz.
        while i > 0:

            # Calcular el índice del nodo padre.
            parent = (i - 1) // 2

            # Comparar el nodo actual con su padre.
            if items[i] < items[parent]:

                # Intercambiar los elementos.
                items[i], items[parent] = (
                    items[parent], items[i]
                )

                # Actualizar la posición actual.
                i = parent

            else:
                break

    # --------------------------------------------------------
    # 10. RESTAURAR LA PROPIEDAD DEL HEAP HACIA ABAJO
    # --------------------------------------------------------

    def _sift_down(self, i):

        items, n = self._items, len(self._items)

        while True:

            # Calcular el índice del hijo izquierdo.
            left, smallest = 2 * i + 1, i

            # Comparar con el hijo izquierdo.
            if left < n and items[left] < items[smallest]:
                smallest = left

            # Comparar con el hijo derecho.
            if left + 1 < n and items[left + 1] < items[smallest]:
                smallest = left + 1

            # Finalizar si se cumple la propiedad del heap.
            if smallest == i:
                return

            # Intercambiar con el hijo de menor prioridad numérica.
            items[i], items[smallest] = (
                items[smallest], items[i]
            )

            # Continuar desde la nueva posición.
            i = smallest