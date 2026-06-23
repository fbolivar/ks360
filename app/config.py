"""Carga de configuracion desde variables de entorno / archivo .env.

Toda la configuracion (credenciales, hosts, parametros) vive aqui y se lee de
.env mediante pydantic-settings. NUNCA hardcodear secretos en el codigo.
"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Servidor Wazuh -----------------------------------------------------
    wazuh_host: str = "127.0.0.1"          # IP o hostname (sin esquema ni puerto)
    wazuh_api_port: int = 55000
    wazuh_api_user: str = ""
    wazuh_api_pass: str = ""
    indexer_port: int = 9200
    indexer_user: str = ""
    indexer_pass: str = ""
    wazuh_verify_ssl: bool = False         # certs autofirmados en lab => False
    wazuh_timeout: int = 30

    # --- Cliente / Tenant por defecto --------------------------------------
    client_name: str = "Cliente Demo"
    report_days: int = 30

    # --- Panel web (auth admin) --------------------------------------------
    admin_user: str = "admin"
    admin_pass: str = "changeme"
    session_secret: str = "cambia-esta-clave-secreta"

    # --- SMTP (opcional) ----------------------------------------------------
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_pass: str | None = None
    smtp_from: str | None = None
    smtp_use_tls: bool = True

    # --- Base de datos ------------------------------------------------------
    database_url: str = "sqlite:///./ks360.db"

    # --- Scheduler ----------------------------------------------------------
    report_schedule: str = "monthly"       # monthly | weekly
    report_hour: int = 7
    report_day_of_month: int = 1
    report_day_of_week: str = "mon"

    # ------------------------------------------------------------------ utils
    @property
    def clean_host(self) -> str:
        """Devuelve solo el host, quitando esquema y puerto si vinieran."""
        host = self.wazuh_host.strip()
        for prefix in ("https://", "http://"):
            if host.startswith(prefix):
                host = host[len(prefix):]
        return host.rstrip("/").split(":")[0].split("/")[0]

    @property
    def api_base_url(self) -> str:
        return f"https://{self.clean_host}:{self.wazuh_api_port}"

    @property
    def indexer_base_url(self) -> str:
        return f"https://{self.clean_host}:{self.indexer_port}"

    @property
    def smtp_configured(self) -> bool:
        return bool(self.smtp_host and self.smtp_from)


@lru_cache
def get_settings() -> Settings:
    """Settings cacheadas (se leen una sola vez por proceso)."""
    return Settings()


# Instancia global de conveniencia.
settings = get_settings()
