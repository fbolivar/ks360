"""Capa de reporting: recoleccion de datos, graficos y generacion de PDF."""

from .collector import collect_report_data
from .pdf import generate_report_pdf

__all__ = ["collect_report_data", "generate_report_pdf"]
