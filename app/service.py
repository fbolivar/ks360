"""Servicio de generacion y persistencia de reportes.

Lo usan tanto el panel web como el scheduler, para no duplicar logica.
"""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from .config import settings
from .mailer import send_report_email
from .models import GeneratedReport, ReportConfig, Tenant
from .reporting.pdf import generate_report_pdf

logger = logging.getLogger(__name__)


def generate_and_store(
    db: Session,
    tenant_id: int = 1,
    days: int | None = None,
    client_name: str | None = None,
    send_email: bool = False,
) -> GeneratedReport:
    """Genera el PDF, lo registra en la BD y (opcional) lo envia por correo."""
    tenant = db.get(Tenant, tenant_id)
    config = (
        db.query(ReportConfig).filter(ReportConfig.tenant_id == tenant_id).first()
    )

    days = days or (config.period_days if config else settings.report_days)
    client_name = (
        client_name
        or (config.client_name if config else None)
        or (tenant.name if tenant else None)
        or settings.client_name
    )

    result = generate_report_pdf(tenant=tenant, days=days, client_name=client_name)

    report = GeneratedReport(
        tenant_id=tenant_id,
        client_name=result["client_name"],
        filename=result["filename"],
        filepath=result["filepath"],
        period_label=result["period_label"],
        period_days=result["period_days"],
        status=result["status"],
        summary=result["summary"],
    )
    db.add(report)
    db.commit()
    db.refresh(report)

    if send_email and config and config.recipients:
        recipients = [r.strip() for r in config.recipients.split(",")]
        send_report_email(result["filepath"], recipients)

    return report
