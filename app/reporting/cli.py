"""CLI de prueba: genera un PDF de ejemplo desde la terminal.

Uso:
    python -m app.reporting.cli
    python -m app.reporting.cli --days 7 --client "ACME Corp"

Funciona aunque Wazuh no este disponible: el reporte se genera igualmente,
indicando el estado de conexion.
"""
from __future__ import annotations

import argparse
import logging
import sys

from ..config import settings
from .pdf import generate_report_pdf


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Genera un reporte PDF de CK360.")
    parser.add_argument(
        "--days", type=int, default=settings.report_days,
        help="Dias del periodo a reportar.",
    )
    parser.add_argument(
        "--client", type=str, default=settings.client_name,
        help="Nombre del cliente.",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )

    print(f"==> Generando reporte para '{args.client}' (ultimos {args.days} dias)...")
    result = generate_report_pdf(days=args.days, client_name=args.client)

    print(f"    Estado:  {result['status']}")
    print(f"    Archivo: {result['filepath']}")
    if result["status"] != "ok":
        print("    NOTA: no se pudo conectar a Wazuh; el PDF se generó con el")
        print("          formato pero sin datos. Revisa el .env y la red.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
