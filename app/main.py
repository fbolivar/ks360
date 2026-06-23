"""KS360 — Panel web FastAPI.

Rutas:
  GET  /login | POST /login | GET /logout
  GET  /                      -> dashboard (estado + reportes + generar)
  POST /reports/generate      -> genera un reporte ahora
  GET  /reports/{id}/download -> descarga el PDF
  GET  /config | POST /config -> configuracion del cliente
  GET  /health                -> chequeo de conexion (JSON)
"""
from __future__ import annotations

import logging
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from .config import settings
from .database import get_db, init_db
from .models import GeneratedReport, ReportConfig
from .scheduler import shutdown_scheduler, start_scheduler
from .service import generate_and_store
from .wazuh.client import WazuhClient
from .wazuh.indexer import IndexerClient

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("ks360")

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    start_scheduler()
    logger.info("KS360 iniciado.")
    yield
    shutdown_scheduler()


app = FastAPI(title="KS360 — Reportes MSSP", lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=settings.session_secret)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


# --------------------------------------------------------------------- auth
def is_authenticated(request: Request) -> bool:
    return bool(request.session.get("user"))


def require_login(request: Request):
    """Dependencia: si no hay sesion, corta con una redireccion a /login."""
    if not is_authenticated(request):
        return RedirectResponse(url="/login", status_code=303)
    return None


@app.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    if is_authenticated(request):
        return RedirectResponse(url="/", status_code=303)
    return templates.TemplateResponse(request, "login.html", {"error": None})


@app.post("/login")
def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):
    ok_user = secrets.compare_digest(username, settings.admin_user)
    ok_pass = secrets.compare_digest(password, settings.admin_pass)
    if ok_user and ok_pass:
        request.session["user"] = username
        return RedirectResponse(url="/", status_code=303)
    return templates.TemplateResponse(
        request, "login.html", {"error": "Credenciales inválidas."}, status_code=401
    )


@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)


# ---------------------------------------------------------------- dashboard
@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    if not is_authenticated(request):
        return RedirectResponse(url="/login", status_code=303)

    reports = (
        db.query(GeneratedReport)
        .order_by(GeneratedReport.created_at.desc())
        .limit(50)
        .all()
    )
    config = db.query(ReportConfig).filter(ReportConfig.tenant_id == 1).first()
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "reports": reports,
            "config": config,
            "client_name": settings.client_name,
            "wazuh_host": settings.clean_host,
        },
    )


@app.post("/reports/generate")
def reports_generate(request: Request, db: Session = Depends(get_db)):
    if not is_authenticated(request):
        return RedirectResponse(url="/login", status_code=303)
    try:
        generate_and_store(db, tenant_id=1, send_email=True)
    except Exception as exc:  # noqa: BLE001
        logger.error("Error generando reporte manual: %s", exc)
    return RedirectResponse(url="/", status_code=303)


@app.get("/reports/{report_id}/download")
def reports_download(report_id: int, request: Request, db: Session = Depends(get_db)):
    if not is_authenticated(request):
        return RedirectResponse(url="/login", status_code=303)
    report = db.get(GeneratedReport, report_id)
    if not report or not Path(report.filepath).exists():
        return JSONResponse({"error": "Reporte no encontrado."}, status_code=404)
    return FileResponse(
        report.filepath, media_type="application/pdf", filename=report.filename
    )


# ------------------------------------------------------------------- config
@app.get("/config", response_class=HTMLResponse)
def config_form(request: Request, db: Session = Depends(get_db)):
    if not is_authenticated(request):
        return RedirectResponse(url="/login", status_code=303)
    config = db.query(ReportConfig).filter(ReportConfig.tenant_id == 1).first()
    return templates.TemplateResponse(
        request, "config.html", {"config": config, "saved": False}
    )


@app.post("/config", response_class=HTMLResponse)
def config_save(
    request: Request,
    client_name: str = Form(...),
    periodicity: str = Form("monthly"),
    period_days: int = Form(30),
    recipients: str = Form(""),
    db: Session = Depends(get_db),
):
    if not is_authenticated(request):
        return RedirectResponse(url="/login", status_code=303)

    config = db.query(ReportConfig).filter(ReportConfig.tenant_id == 1).first()
    if not config:
        config = ReportConfig(tenant_id=1, client_name=client_name)
        db.add(config)

    # Validacion/saneo basico.
    config.client_name = client_name.strip()[:200] or settings.client_name
    config.periodicity = "weekly" if periodicity == "weekly" else "monthly"
    config.period_days = max(1, min(int(period_days or 30), 365))
    config.recipients = ",".join(
        e.strip() for e in recipients.split(",") if e.strip() and "@" in e
    )
    db.commit()
    db.refresh(config)
    return templates.TemplateResponse(
        request, "config.html", {"config": config, "saved": True}
    )


# ------------------------------------------------------------------- health
@app.get("/health")
def health():
    """Chequeo de conexion a API e Indexer (JSON).

    Usa un timeout corto para no bloquear el panel si Wazuh no responde.
    """
    api_ok = WazuhClient(timeout=4).ping()
    indexer_ok = IndexerClient(timeout=4).ping()
    status = "ok" if (api_ok and indexer_ok) else "degraded"
    return JSONResponse(
        {
            "status": status,
            "wazuh_api": "ok" if api_ok else "fallo",
            "indexer": "ok" if indexer_ok else "fallo",
            "host": settings.clean_host,
        }
    )
