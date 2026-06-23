"""Modelos de datos (SQLAlchemy).

Todos los modelos llevan `tenant_id` desde el dia 1 para soportar MULTI-CLIENTE
en el futuro, aunque ahora se opere con un unico tenant leido de .env.
"""
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .config import settings
from .database import Base, SessionLocal


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Tenant(Base):
    """Cliente del MSSP. Puede tener su propio Wazuh y credenciales."""

    __tablename__ = "tenants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    wazuh_host: Mapped[str | None] = mapped_column(String(255), nullable=True)
    wazuh_api_user: Mapped[str | None] = mapped_column(String(120), nullable=True)
    wazuh_api_pass: Mapped[str | None] = mapped_column(String(255), nullable=True)
    indexer_user: Mapped[str | None] = mapped_column(String(120), nullable=True)
    indexer_pass: Mapped[str | None] = mapped_column(String(255), nullable=True)
    logo_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    configs: Mapped[list["ReportConfig"]] = relationship(
        back_populates="tenant", cascade="all, delete-orphan"
    )
    reports: Mapped[list["GeneratedReport"]] = relationship(
        back_populates="tenant", cascade="all, delete-orphan"
    )


class ReportConfig(Base):
    """Configuracion de reporte por tenant: periodicidad y destinatarios."""

    __tablename__ = "report_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    client_name: Mapped[str] = mapped_column(String(200), nullable=False)
    periodicity: Mapped[str] = mapped_column(String(20), default="monthly")  # monthly|weekly
    period_days: Mapped[int] = mapped_column(Integer, default=30)
    recipients: Mapped[str | None] = mapped_column(Text, nullable=True)  # CSV de correos
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, onupdate=_utcnow
    )

    tenant: Mapped["Tenant"] = relationship(back_populates="configs")


class GeneratedReport(Base):
    """Registro de cada PDF generado."""

    __tablename__ = "generated_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    client_name: Mapped[str] = mapped_column(String(200), nullable=False)
    filename: Mapped[str] = mapped_column(String(300), nullable=False)
    filepath: Mapped[str] = mapped_column(String(600), nullable=False)
    period_label: Mapped[str] = mapped_column(String(120), nullable=False)
    period_days: Mapped[int] = mapped_column(Integer, default=30)
    status: Mapped[str] = mapped_column(String(20), default="ok")  # ok|error
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    tenant: Mapped["Tenant"] = relationship(back_populates="reports")


def ensure_default_tenant() -> "Tenant":
    """Crea (si no existe) el tenant por defecto a partir de .env.

    Devuelve el tenant con id=1 que se usa mientras la app es mono-cliente.
    """
    db = SessionLocal()
    try:
        tenant = db.get(Tenant, 1)
        if tenant is None:
            tenant = Tenant(id=1, name=settings.client_name)
            db.add(tenant)
            db.flush()
            db.add(
                ReportConfig(
                    tenant_id=tenant.id,
                    client_name=settings.client_name,
                    periodicity=settings.report_schedule,
                    period_days=settings.report_days,
                )
            )
        # Mantener el tenant por defecto sincronizado con el .env (fuente de
        # verdad en modo mono-cliente). Evita hosts/credenciales obsoletos.
        tenant.wazuh_host = settings.clean_host
        tenant.wazuh_api_user = settings.wazuh_api_user
        tenant.indexer_user = settings.indexer_user
        db.commit()
        db.refresh(tenant)
        return tenant
    finally:
        db.close()
