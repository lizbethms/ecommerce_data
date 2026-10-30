"""Figuras del informe final derivadas de CSV persistidos; no ejecuta benchmarks."""
from pathlib import Path
import csv
import os

os.environ.setdefault("MPLCONFIGDIR", "/private/tmp/eda-mpl")
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "informe_figuras"
OUT.mkdir(parents=True, exist_ok=True)
SCALES = ("1K", "10K", "100K", "1M")


def rows(path):
    with path.open(newline="", encoding="utf-8") as file:
        return list(csv.DictReader(file))


def table(scale, name):
    return rows(ROOT / "results" / f"flujo_{scale}" / "informe" / "tablas" / f"{name}.csv")


plt.rcParams.update({"font.size": 8, "axes.spines.top": False, "axes.spines.right": False})
colors = {"jaccard_exhaustivo": "#355c7d", "minhash_lsh": "#c06c3e",
          "fuerza_bruta": "#355c7d", "hnsw": "#c06c3e", "kd_tree": "#669999"}
fig, axes = plt.subplots(1, 2, figsize=(10, 3.4))
for family, ax in zip(("conjuntos", "vectorial"), axes):
    names = [r["algoritmo"] for r in table("1K", "similitud_resumen") if r["familia"] == family]
    for name in names:
        xs, ys = [], []
        for scale in SCALES:
            r = next(r for r in table(scale, "similitud_resumen") if r["algoritmo"] == name)
            xs.append(int(table(scale, "fuente")[0]["conjuntos" if family == "conjuntos" else "vectores"]))
            ys.append(float(r["media_ms"]))
        ax.loglog(xs, ys, marker="o", label=name.replace("_", " "), color=colors[name])
    ax.set(title="Jaccard y MinHash/LSH" if family == "conjuntos" else "KNN vectorial", xlabel="Elementos en el índice", ylabel="Consulta media (ms)")
    ax.grid(alpha=.25, which="both")
    ax.legend(fontsize=7)
fig.tight_layout()
fig.savefig(OUT / "escalabilidad_consulta.pdf")
plt.close(fig)

memory = rows(ROOT / "results" / "experimentos" / "memoria_completa_01" / "resumen_memoria.csv")
fig, axes = plt.subplots(1, 3, figsize=(10, 3.1))
groups = (("bloom", "set_exacto"), ("cms", "counter_exacto"),
          ("hnsw", "kd_tree", "fuerza_bruta_vectores"))
for ax, names in zip(axes, groups):
    for name in names:
        rr = [r for r in memory if r["caso"] == name]
        ax.loglog([int(r["n_indice"]) for r in rr],
                  [float(r["actual_indice_bytes_media"]) / 2**20 for r in rr],
                  marker="o", label=name.replace("_", " "))
    ax.set(xlabel="Carga real del índice", ylabel="Memoria actual (MiB)")
    ax.grid(alpha=.25, which="both")
    ax.legend(fontsize=7)
fig.tight_layout()
fig.savefig(OUT / "escalabilidad_memoria.pdf")
plt.close(fig)
