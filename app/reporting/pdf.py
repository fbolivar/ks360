"""Renderizado del reporte: Jinja2 (HTML) -> WeasyPrint (PDF)."""
from __future__ import annotations

import base64
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .charts import build_charts
from .collector import collect_report_data

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent  # .../app
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"
OUTPUT_DIR = BASE_DIR.parent / "output"  # .../ks360/output

FOOTER_TEXT = (
    "CK SOLUTIONS SAS — Click Solutions · info@clicksolutions.com.co · "
    "+601 2225078 · clicksolutions.com.co · Documento confidencial"
)

_env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=select_autoescape(["html", "xml"]),
)


def _image_data_uri(path: Path) -> str | None:
    """Convierte una imagen local a data URI (o None si no existe)."""
    if not path.exists():
        return None
    mime = "image/png"
    if path.suffix.lower() in (".jpg", ".jpeg"):
        mime = "image/jpeg"
    b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{b64}"


def _slugify(text: str) -> str:
    text = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE).strip().lower()
    return re.sub(r"[\s_-]+", "-", text) or "cliente"


def render_report_html(data: dict) -> str:
    """Renderiza el HTML del reporte a partir del dict de datos."""
    charts = build_charts(data)
    logo = _image_data_uri(STATIC_DIR / "img" / "logo.png")
    css_path = STATIC_DIR / "css" / "report.css"
    css_inline = css_path.read_text(encoding="utf-8") if css_path.exists() else ""

    template = _env.get_template("report.html")
    return template.render(
        data=data,
        charts=charts,
        logo=logo,
        footer_text=FOOTER_TEXT,
        css_inline=css_inline,
    )


def generate_report_pdf(
    data: dict | None = None,
    tenant=None,
    days: int | None = None,
    client_name: str | None = None,
    output_dir: Path | None = None,
) -> dict:
    """Genera el PDF del reporte y lo guarda en disco.

    Devuelve un dict con metadatos: filepath, filename, period_label, status,
    summary. No requiere que Wazuh este disponible (el reporte se genera igual).
    """
    # Importacion diferida: WeasyPrint solo se necesita aqui y carga libs nativas.
    from weasyprint import HTML

    if data is None:
        data = collect_report_data(tenant=tenant, days=days, client_name=client_name)

    output_dir = output_dir or OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    html = render_report_html(data)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    filename = f"reporte-{_slugify(data['client_name'])}-{stamp}.pdf"
    filepath = output_dir / filename

    HTML(string=html, base_url=str(STATIC_DIR)).write_pdf(str(filepath))
    logger.info("Reporte generado: %s", filepath)

    status = "ok" if (
        data["connection"]["api_ok"] or data["connection"]["indexer_ok"]
    ) else "error"

    return {
        "filepath": str(filepath),
        "filename": filename,
        "period_label": data["period_label"],
        "period_days": data["period_days"],
        "client_name": data["client_name"],
        "status": status,
        "summary": data["summary_text"],
    }
