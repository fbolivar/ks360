"""Generacion de graficos con matplotlib para embeber en el PDF.

Cada funcion devuelve un *data URI* (base64 PNG) listo para insertar en el HTML
como  <img src="...">. Asi WeasyPrint no depende de rutas de archivo.
"""
from __future__ import annotations

import base64
import io

import matplotlib

matplotlib.use("Agg")  # backend sin display (servidor)
import matplotlib.pyplot as plt  # noqa: E402

# Paleta de marca Click Solutions
COLOR_PRIMARY = "#f07e22"
COLOR_DARK = "#2b2b2b"
SEVERITY_COLORS = {
    "critico": "#c0392b",
    "alto": "#e67e22",
    "medio": "#f1c40f",
    "info": "#7f8c8d",
}
COLOR_ACTIVE = "#27ae60"
COLOR_INACTIVE = "#c0392b"

plt.rcParams.update(
    {
        "font.size": 11,
        "font.family": "sans-serif",
        "axes.edgecolor": COLOR_DARK,
        "text.color": COLOR_DARK,
        "axes.labelcolor": COLOR_DARK,
        "xtick.color": COLOR_DARK,
        "ytick.color": COLOR_DARK,
    }
)


def _fig_to_data_uri(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=140, bbox_inches="tight", transparent=True)
    plt.close(fig)
    buf.seek(0)
    b64 = base64.b64encode(buf.read()).decode("ascii")
    return f"data:image/png;base64,{b64}"


def donut_agents(active: int, inactive: int) -> str | None:
    """Dona de agentes activos vs inactivos. None si no hay datos."""
    total = active + inactive
    if total == 0:
        return None
    fig, ax = plt.subplots(figsize=(4, 4))
    wedges, _ = ax.pie(
        [active, inactive],
        colors=[COLOR_ACTIVE, COLOR_INACTIVE],
        startangle=90,
        wedgeprops={"width": 0.42, "edgecolor": "white", "linewidth": 2},
    )
    ax.text(
        0, 0, f"{active}/{total}", ha="center", va="center",
        fontsize=18, fontweight="bold", color=COLOR_DARK,
    )
    ax.text(0, -0.22, "activos", ha="center", va="center", fontsize=10, color="#666")
    ax.legend(
        wedges,
        [f"Activos ({active})", f"Inactivos ({inactive})"],
        loc="lower center",
        bbox_to_anchor=(0.5, -0.18),
        ncol=2,
        frameon=False,
        fontsize=9,
    )
    ax.set_aspect("equal")
    return _fig_to_data_uri(fig)


def bars_alerts_by_severity(by_severity: dict[str, int]) -> str | None:
    """Barras de alertas por severidad. None si todo es cero."""
    order = ["critico", "alto", "medio", "info"]
    labels = {"critico": "Crítico", "alto": "Alto", "medio": "Medio", "info": "Info"}
    values = [by_severity.get(k, 0) for k in order]
    if sum(values) == 0:
        return None
    fig, ax = plt.subplots(figsize=(6, 3.2))
    bars = ax.bar(
        [labels[k] for k in order],
        values,
        color=[SEVERITY_COLORS[k] for k in order],
        width=0.6,
    )
    ax.set_ylabel("Alertas")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.bar_label(bars, padding=3, fontsize=10, fontweight="bold")
    ax.margins(y=0.18)
    return _fig_to_data_uri(fig)


def build_charts(data: dict) -> dict:
    """Devuelve un dict con los data URIs de los graficos del reporte."""
    agents = data["agents"]
    return {
        "agents_donut": donut_agents(agents["active"], agents["inactive"]),
        "alerts_bars": bars_alerts_by_severity(data["alerts"]["by_severity"]),
    }
