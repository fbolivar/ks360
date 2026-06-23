# KS360 — Plataforma de Reportes MSSP (Click Solutions)

Aplicación web que consume datos de un servidor **Wazuh 4.14** (API REST +
Indexer/OpenSearch) y genera **reportes ejecutivos de ciberseguridad en PDF** con
la marca **Click Solutions**, además de un **panel web** para visualizarlos,
configurarlos, descargarlos y programarlos.

> Pensada para un micro-MSSP (proveedor gestionado de seguridad). El modelo de
> datos ya soporta **multi-cliente** (`tenant_id`), aunque hoy opera con un solo
> cliente leído de `.env`.

---

## 1. Requisitos

- **Python 3.11+** (probado en 3.14).
- Un servidor **Wazuh 4.14** alcanzable desde esta máquina:
  - API REST en `https://<WAZUH_HOST>:55000`
  - Indexer/OpenSearch en `https://<WAZUH_HOST>:9200`
- **Dependencias de sistema para WeasyPrint** (Ubuntu/Debian):

```bash
sudo apt update
sudo apt install -y \
  libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf-2.0-0 \
  libffi-dev libcairo2 fonts-dejavu-core
```

> En Ubuntu 24.04+ el paquete puede llamarse `libgdk-pixbuf-2.0-0`. Si no existe,
> prueba `libgdk-pixbuf2.0-0`.

---

## 2. Instalación

```bash
# 1) Clonar y entrar
git clone https://github.com/fbolivar/ks360.git
cd ks360

# 2) Entorno virtual
python3 -m venv venv
source venv/bin/activate

# 3) Dependencias de Python
pip install --upgrade pip
pip install -r requirements.txt

# 4) Configuración
cp .env.example .env
nano .env        # completa WAZUH_HOST, credenciales, ADMIN_PASS, SESSION_SECRET...
```

---

## 3. Configuración (`.env`)

| Variable | Descripción |
|----------|-------------|
| `WAZUH_HOST` | IP/host del servidor Wazuh (sin esquema ni puerto). |
| `WAZUH_API_PORT` | Puerto de la API REST (default `55000`). |
| `WAZUH_API_USER` / `WAZUH_API_PASS` | Credenciales de la API REST de Wazuh. |
| `INDEXER_PORT` | Puerto del Indexer/OpenSearch (default `9200`). |
| `INDEXER_USER` / `INDEXER_PASS` | Credenciales del Indexer. |
| `WAZUH_VERIFY_SSL` | `false` en lab (certs autofirmados); `true` en prod con certs propios. |
| `CLIENT_NAME` | Nombre del cliente que aparece en el reporte. |
| `REPORT_DAYS` | Días del periodo a reportar (default `30`). |
| `ADMIN_USER` / `ADMIN_PASS` | Credenciales del panel web. |
| `SESSION_SECRET` | Clave para firmar las cookies de sesión (cámbiala). |
| `REPORT_SCHEDULE` | `monthly` o `weekly`. |
| `SMTP_*` | Configuración de correo (opcional). |
| `DATABASE_URL` | Conexión SQLAlchemy (default SQLite local). |

> ⚠️ **Certificados autofirmados:** en laboratorio las llamadas HTTPS usan
> `verify=False` (avisos silenciados). Para producción, pon certificados propios
> y `WAZUH_VERIFY_SSL=true`.

---

## 4. Uso

### 4.1 Generar un PDF de prueba (sin levantar el panel)

```bash
python -m app.reporting.cli
```

Genera un PDF en `output/` usando la configuración de `.env`. Si Wazuh no
responde, **no falla**: el reporte se genera igual indicando claramente el fallo
de conexión (útil para validar la maquetación).

### 4.2 Levantar el panel web

```bash
./run.sh                      # http://0.0.0.0:8000
# o directamente:
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Abre `http://<servidor>:8000`, inicia sesión con `ADMIN_USER` / `ADMIN_PASS` y:

- **Dashboard** — estado de conexión a Wazuh + lista de reportes + botón *Generar*.
- **Configuración** — nombre del cliente, periodicidad, días, destinatarios.
- **Descargar** — cada reporte generado.
- **`/health`** — chequeo JSON de API e Indexer.

### 4.3 Reportes programados

`APScheduler` arranca con la app y genera el reporte automáticamente según la
config (por defecto **mensual, día 1 a las 07:00**, periodo anterior).

Para cambiar la periodicidad, ajusta en `.env`:

```ini
REPORT_SCHEDULE=weekly         # o monthly
REPORT_HOUR=7
REPORT_DAY_OF_MONTH=1          # solo monthly
REPORT_DAY_OF_WEEK=mon         # solo weekly
```

### 4.4 Envío por correo

Si configuras `SMTP_HOST` y `SMTP_FROM`, los reportes pueden enviarse a los
destinatarios definidos en *Configuración*. Si no hay SMTP configurado, el envío
se **omite** y queda registrado en el log (no falla).

---

## 5. Arquitectura

```
app/
├── main.py            # FastAPI: panel web + API + login
├── config.py          # settings desde .env (pydantic-settings)
├── database.py        # SQLAlchemy engine + sesión
├── models.py          # Tenant, ReportConfig, GeneratedReport (con tenant_id)
├── mailer.py          # envío SMTP (stub seguro)
├── scheduler.py       # APScheduler: reportes periódicos
├── wazuh/
│   ├── client.py      # API REST: token JWT, agentes, manager/info
│   └── indexer.py     # OpenSearch: alertas y vulnerabilidades
├── reporting/
│   ├── collector.py   # orquesta y arma el dict de datos del reporte
│   ├── charts.py      # gráficos PNG con matplotlib (base64)
│   ├── pdf.py         # Jinja2 + WeasyPrint -> PDF
│   └── cli.py         # genera un PDF de prueba desde terminal
├── templates/         # report.html (PDF) + panel web
└── static/            # CSS de marca + logo/favicon
```

### Vías de datos a Wazuh (ya validadas)

- **API REST** (`:55000`): autenticación Basic → token JWT (`~15 min`) usado como
  `Bearer`. Se usa para **agentes** y **manager/info**.
- **Indexer/OpenSearch** (`:9200`): Basic Auth. Se usa para **alertas**
  (`wazuh-alerts-*`) y **vulnerabilidades** (`wazuh-states-vulnerabilities-*`).

> En Wazuh 4.8+ el endpoint `/vulnerability/{agent}` de la API REST fue eliminado:
> las vulnerabilidades se leen **solo** desde el Indexer.

---

## 6. Seguridad

- **Cero credenciales hardcodeadas:** todo vive en `.env` (gitignored).
- El panel web exige **login** (usuario/clave admin desde `.env`).
- Ejecuta el servidor **detrás de un firewall**.
- Restringe el acceso al **Indexer (9200)** únicamente a este host.
- **Rota credenciales** periódicamente y usa **SSL propio** en producción
  (`WAZUH_VERIFY_SSL=true`).

---

## 7. Cómo verificar que funciona (checklist)

- [ ] `pip install -r requirements.txt` sin errores.
- [ ] `python -m app.reporting.cli` genera un PDF en `output/`.
- [ ] El PDF muestra portada con logo, secciones y gráficos.
- [ ] `./run.sh` levanta el panel y `/health` responde el estado de API e Indexer.
- [ ] Login con `ADMIN_USER`/`ADMIN_PASS` funciona.
- [ ] El botón *Generar reporte ahora* crea un registro y un PDF descargable.
- [ ] Con credenciales reales de Wazuh, las tablas se llenan con datos.

---

## 8. Estado y mejoras futuras

**Listo:**
- Capa Wazuh (API REST + Indexer) con manejo de token, errores y timeouts.
- Reporte PDF ejecutivo con marca Click Solutions (portada, resumen, cobertura,
  alertas, incidentes priorizados, vulnerabilidades, conclusiones).
- Panel web con login, dashboard, configuración, descarga y health.
- Scheduler de reportes periódicos.
- Envío por correo (stub seguro).
- Modelo de datos multi-cliente (`tenant_id`).

**Mejoras futuras:**
- Panel multi-tenant completo (gestión de varios clientes desde la UI).
- Dashboards en vivo (no solo PDF).
- Notificaciones por WhatsApp/Telegram.
- Mapa regla→recomendación más extenso y editable desde la UI.

---

*CK SOLUTIONS SAS — Click Solutions · info@clicksolutions.com.co · +601 2225078 ·
clicksolutions.com.co · Documento confidencial.*
