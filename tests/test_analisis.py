import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.analysis.informe_tiempos import pendiente
from src.analysis.plataforma import plataforma
from src.analysis.tiempos import CASOS, PARES, _errores, calidad
from src.structures.count_min import CountMinSketch


class TestAnalisis(unittest.TestCase):
    def test_pendiente_log_log(self):
        b, r2 = pendiente([10, 100, 1000], [2, 20, 200])  # lineal
        self.assertAlmostEqual(b, 1.0)
        self.assertAlmostEqual(r2, 1.0)
        b, _ = pendiente([10, 100, 1000], [5, 5, 5])  # constante
        self.assertAlmostEqual(b, 0.0)
        self.assertEqual(pendiente([10], [1]), (None, None))  # una escala no define pendiente

    def test_errores_de_frecuencia(self):
        resumen = _errores([3, 5, 2], [3, 4, 2])
        self.assertEqual(resumen['error_maximo'], 1)
        self.assertAlmostEqual(resumen['mae'], 1 / 3)
        self.assertAlmostEqual(resumen['sobreestimadas'], 1 / 3)

    def test_calidad_cms_nunca_subestima_y_respeta_la_cota(self):
        entries = [(f'k{i % 50}', float(i)) for i in range(5000)]
        cms = CountMinSketch(1024, 4)
        for key, _ in entries:
            cms.add(key)
        resultado = calidad('cms', cms, dict(entries=entries, unique=sorted({k for k, _ in entries})))
        self.assertGreaterEqual(resultado['error_minimo'], 0)
        self.assertEqual(resultado['dentro_de_cota'], 1.0)

    def test_casos_y_pares_consistentes(self):
        for aproximada, exacta in PARES:
            self.assertEqual(CASOS[aproximada]['carga'], CASOS[exacta]['carga'])
        self.assertTrue(all(spec['construccion'] or spec['operacion'] for spec in CASOS.values()))

    def test_plataforma(self):
        info = plataforma()
        self.assertTrue(info['python'])
        self.assertGreaterEqual(info['nucleos_logicos'] or 1, 1)


if __name__ == '__main__':
    unittest.main()
