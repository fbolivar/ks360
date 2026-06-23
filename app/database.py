"""Configuracion de SQLAlchemy: engine, sesion y base declarativa."""
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from .config import settings

# Para SQLite es necesario desactivar el check de hilo (FastAPI usa varios).
_connect_args = (
    {"check_same_thread": False}
    if settings.database_url.startswith("sqlite")
    else {}
)

engine = create_engine(
    settings.database_url,
    connect_args=_connect_args,
    future=True,
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    future=True,
)

Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """Dependencia de FastAPI: entrega una sesion y la cierra al final."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Crea las tablas si no existen y siembra el tenant por defecto."""
    from . import models  # noqa: F401  (registra los modelos en Base)

    Base.metadata.create_all(bind=engine)
    models.ensure_default_tenant()
