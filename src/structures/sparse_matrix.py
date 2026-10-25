"""Matriz dispersa por diccionarios (filas y columnas indexadas).

add/get O(1) esperado; recorrer una fila o una columna cuesta O(nnz de esa fila
o columna). Espacio O(nnz).
"""


class SparseMatrix:
    def __init__(self):
        self._rows = {}
        self._cols = {}
        self.nnz = 0

    def add(self, row, col, value):
        cells = self._rows.setdefault(row, {})
        if col not in cells:
            self.nnz += 1
            self._cols.setdefault(col, {})
            cells[col] = 0.0
        cells[col] += value
        self._cols[col][row] = cells[col]

    def get(self, row, col, default=0.0):
        return self._rows.get(row, {}).get(col, default)

    def row(self, row):
        return dict(self._rows.get(row, {}))

    def col(self, col):
        return dict(self._cols.get(col, {}))

    def rows(self):
        return self._rows.keys()

    def cols(self):
        return self._cols.keys()

    @property
    def shape(self):
        return len(self._rows), len(self._cols)
