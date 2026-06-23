"""Envio de reportes por correo (SMTP). Stub seguro.

Si no hay SMTP configurado en .env, NO falla: registra en el log que el envio
se omitio y retorna False.
"""
from __future__ import annotations

import logging
import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path

from .config import settings

logger = logging.getLogger(__name__)


def send_report_email(pdf_path: str | Path, recipients: list[str]) -> bool:
    """Envia el PDF a los destinatarios. Devuelve True si se envio."""
    recipients = [r.strip() for r in recipients if r and r.strip()]
    if not recipients:
        logger.info("Envío omitido (sin destinatarios).")
        return False

    if not settings.smtp_configured:
        logger.info("Envío omitido (SMTP no configurado).")
        return False

    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        logger.warning("Envío omitido (PDF no encontrado: %s).", pdf_path)
        return False

    msg = EmailMessage()
    msg["Subject"] = "Informe Ejecutivo de Seguridad — Click Solutions"
    msg["From"] = settings.smtp_from
    msg["To"] = ", ".join(recipients)
    msg.set_content(
        "Adjunto encontrará el Informe Ejecutivo de Seguridad Gestionada (MDR) "
        "generado por Click Solutions.\n\n"
        "Este mensaje y su adjunto son confidenciales.\n\n"
        "CK SOLUTIONS SAS — Click Solutions"
    )
    msg.add_attachment(
        pdf_path.read_bytes(),
        maintype="application",
        subtype="pdf",
        filename=pdf_path.name,
    )

    try:
        if settings.smtp_use_tls:
            context = ssl.create_default_context()
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as s:
                s.starttls(context=context)
                if settings.smtp_user:
                    s.login(settings.smtp_user, settings.smtp_pass or "")
                s.send_message(msg)
        else:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as s:
                if settings.smtp_user:
                    s.login(settings.smtp_user, settings.smtp_pass or "")
                s.send_message(msg)
        logger.info("Reporte enviado a %s", recipients)
        return True
    except Exception as exc:  # noqa: BLE001 - no romper la generacion por correo
        logger.error("Fallo el envío de correo: %s", exc)
        return False
