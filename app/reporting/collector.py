"""Orquestador del reporte: junta agentes + alertas + vulnerabilidades en un
unico diccionario listo para la plantilla.

Diseno robusto: NUNCA lanza excepcion hacia arriba. Si una fuente (API o
Indexer) falla, se registra el error en `connection.errors` y se continua con
datos vacios, de modo que el PDF siempre se pueda generar (indicando el fallo).

Recibe `tenant` como parametro para soportar multi-cliente en el futuro; si es
None usa la configuracion global de .env.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from ..config import settings
from ..wazuh.client import WazuhAPIError, WazuhClient
from ..wazuh.indexer import IndexerClient, IndexerError

logger = logging.getLogger(__name__)


# --- Escala de severidad por nivel de regla Wazuh --------------------------
#   >=12 critico | 10-11 alto | 7-9 medio | <7 informativo
def severity_from_level(level: int) -> str:
    if level >= 12:
        return "critico"
    if level >= 10:
        return "alto"
    if level >= 7:
        return "medio"
    return "info"


SEVERITY_LABELS = {
    "critico": "Crítico",
    "alto": "Alto",
    "medio": "Medio",
    "bajo": "Bajo",
    "info": "Informativo",
}

# Orden para priorizar vulnerabilidades (mayor primero).
VULN_SEVERITY_RANK = {
    "critical": 4,
    "high": 3,
    "medium": 2,
    "moderate": 2,
    "low": 1,
    "untriaged": 0,
    "": 0,
}

# --- Mapa simple regla -> recomendacion ------------------------------------
# Se evalua por palabras clave en rule.groups o en la descripcion.
RECOMMENDATION_RULES: list[tuple[tuple[str, ...], str]] = [
    (("authentication_failed", "invalid_login", "win_authentication_failed",
      "ssh", "sshd", "brute"),
     "Revisar intentos de acceso fallidos; aplicar bloqueo por fuerza bruta "
     "(fail2ban / políticas de bloqueo) y validar cuentas comprometidas."),
    (("web", "attack", "sql_injection", "web_scan", "nginx", "apache"),
     "Revisar logs del servicio web; validar WAF y reglas de entrada; parchear "
     "la aplicación expuesta."),
    (("malware", "virustotal", "rootcheck", "trojan", "yara"),
     "Aislar el host afectado, ejecutar análisis antimalware completo y validar "
     "persistencia/IOC."),
    (("vulnerability", "cve"),
     "Priorizar la aplicación de parches del paquete afectado."),
    (("firewall", "ids", "suricata", "netflow"),
     "Revisar tráfico de red asociado y reglas de firewall/IDS."),
    (("syscheck", "fim", "integrity"),
     "Verificar cambios de integridad en archivos críticos (FIM) y confirmar si "
     "fueron autorizados."),
    (("privilege", "sudo", "escalation", "policy"),
     "Auditar escalamiento de privilegios y revisar permisos de la cuenta."),
]

GENERIC_RECOMMENDATION = "Revisar y validar el evento; correlacionar con otros indicadores."


def recommend_for_alert(source: dict) -> str:
    """Deriva una recomendacion a partir de los grupos/descripcion de la regla."""
    rule = source.get("rule", {}) or {}
    haystack = " ".join(
        [
            " ".join(rule.get("groups", []) or []),
            str(rule.get("description", "")),
        ]
    ).lower()
    for keywords, advice in RECOMMENDATION_RULES:
        if any(k in haystack for k in keywords):
            return advice
    return GENERIC_RECOMMENDATION


def _extract_mitre(source: dict) -> str:
    rule = source.get("rule", {}) or {}
    mitre = rule.get("mitre", {}) or {}
    ids = mitre.get("id", []) or []
    if isinstance(ids, str):
        ids = [ids]
    return ", ".join(ids) if ids else "—"


def _vuln_severity(source: dict) -> str:
    vuln = source.get("vulnerability", {}) or {}
    sev = (vuln.get("severity") or source.get("severity") or "").strip().lower()
    return sev


def _build_executive_summary(data: dict) -> str:
    """Genera un parrafo ejecutivo en lenguaje de negocio a partir de los datos."""
    agents = data["agents"]
    alerts = data["alerts"]
    vulns = data["vulnerabilities"]
    conn = data["connection"]

    if not conn["api_ok"] and not conn["indexer_ok"]:
        return (
            "Durante este periodo no fue posible establecer conexión con la "
            "plataforma de monitoreo (Wazuh). El presente informe se emite con "
            "fines de formato; los datos de seguridad deberán consolidarse una "
            "vez restablecida la conexión. Se recomienda verificar la "
            "disponibilidad del servidor y las credenciales de acceso."
        )

    criticos = alerts["by_severity"].get("critico", 0)
    altos = alerts["by_severity"].get("alto", 0)
    vuln_crit = sum(
        1 for v in vulns if v["severity_key"] in ("critical", "high")
    )

    partes = [
        f"Durante el periodo evaluado ({data['period_label']}) se mantuvieron "
        f"bajo monitoreo {agents['total']} activos "
        f"({agents['active']} activos en línea, {agents['inactive']} inactivos)."
    ]
    partes.append(
        f"Se procesaron {alerts['total']} alertas de seguridad, de las cuales "
        f"{criticos} fueron de severidad crítica y {altos} de severidad alta."
    )
    if vulns:
        partes.append(
            f"Se identificaron {len(vulns)} vulnerabilidades indexadas "
            f"({vuln_crit} de severidad alta o crítica) que requieren atención "
            f"priorizada."
        )
    else:
        partes.append(
            "No se registraron vulnerabilidades indexadas en el periodo."
        )

    if criticos == 0 and altos == 0:
        partes.append(
            "La postura general del periodo es estable: no se detectaron "
            "incidentes críticos o altos que requieran respuesta inmediata."
        )
    else:
        partes.append(
            "Se recomienda atender de forma prioritaria los incidentes "
            "críticos y altos listados, así como el plan de remediación de "
            "vulnerabilidades."
        )
    return " ".join(partes)


def _build_recommendations(data: dict) -> list[str]:
    recs: list[str] = []
    alerts = data["alerts"]
    vulns = data["vulnerabilities"]
    agents = data["agents"]

    if alerts["by_severity"].get("critico", 0) > 0:
        recs.append(
            "Atender de inmediato los incidentes de severidad crítica y aplicar "
            "contención sobre los activos afectados."
        )
    if any(v["severity_key"] in ("critical", "high") for v in vulns):
        recs.append(
            "Ejecutar el ciclo de parcheo de las vulnerabilidades altas y "
            "críticas, comenzando por los activos expuestos."
        )
    if agents["inactive"] > 0:
        recs.append(
            f"Restablecer la conectividad de los {agents['inactive']} agentes "
            "inactivos para recuperar cobertura total del monitoreo."
        )
    if not recs:
        recs.append(
            "Mantener el monitoreo continuo y la revisión periódica de reglas y "
            "umbrales de alerta."
        )
    recs.append(
        "Revisar credenciales y políticas de acceso; mantener respaldo y "
        "rotación de claves de los servicios críticos."
    )
    return recs


def collect_report_data(
    tenant=None,
    days: int | None = None,
    client_name: str | None = None,
) -> dict:
    """Construye el diccionario de datos del reporte.

    `tenant` puede ser un objeto/dict con overrides (host, credenciales). Si es
    None se usa la config global de .env.
    """
    days = days or settings.report_days
    client_name = client_name or (
        getattr(tenant, "name", None) if tenant else None
    ) or settings.client_name

    # Permite overrides por tenant (multi-cliente futuro).
    host = getattr(tenant, "wazuh_host", None) if tenant else None
    api_base = f"https://{host}:{settings.wazuh_api_port}" if host else None
    idx_base = f"https://{host}:{settings.indexer_port}" if host else None

    now = datetime.now(timezone.utc)
    data: dict = {
        "client_name": client_name,
        "period_days": days,
        "period_label": f"Últimos {days} días",
        "generated_at": now,
        "generated_at_str": now.strftime("%Y-%m-%d %H:%M UTC"),
        "manager": {"version": "desconocida", "connected": False},
        "connection": {"api_ok": False, "indexer_ok": False, "errors": []},
        "agents": {"items": [], "total": 0, "active": 0, "inactive": 0},
        "alerts": {
            "by_level": {},
            "total": 0,
            "by_severity": {"critico": 0, "alto": 0, "medio": 0, "info": 0},
        },
        "incidents": [],
        "vulnerabilities": [],
    }

    # --- API REST: agentes + manager ---------------------------------------
    try:
        client = WazuhClient(
            base_url=api_base,
            user=getattr(tenant, "wazuh_api_user", None) if tenant else None,
            password=getattr(tenant, "wazuh_api_pass", None) if tenant else None,
        )
        manager = client.get_manager_info()
        data["manager"] = {"version": manager["version"], "connected": True}

        agents = client.get_agents()
        active = sum(1 for a in agents if a["status"] == "active")
        data["agents"] = {
            "items": agents,
            "total": len(agents),
            "active": active,
            "inactive": len(agents) - active,
        }
        data["connection"]["api_ok"] = True
    except WazuhAPIError as exc:
        logger.error("Fallo API Wazuh: %s", exc)
        data["connection"]["errors"].append(f"API Wazuh: {exc}")

    # --- Indexer: alertas + vulnerabilidades -------------------------------
    try:
        idx = IndexerClient(
            base_url=idx_base,
            user=getattr(tenant, "indexer_user", None) if tenant else None,
            password=getattr(tenant, "indexer_pass", None) if tenant else None,
        )

        by_level = idx.alerts_by_level(days)
        total = idx.total_alerts(days)
        by_sev = {"critico": 0, "alto": 0, "medio": 0, "info": 0}
        for level, count in by_level.items():
            by_sev[severity_from_level(level)] += count
        data["alerts"] = {
            "by_level": by_level,
            "total": total or sum(by_level.values()),
            "by_severity": by_sev,
        }

        # Incidentes priorizados (nivel >= 10).
        incidents = []
        for src in idx.top_alerts(days, min_level=10, size=25):
            rule = src.get("rule", {}) or {}
            agent = src.get("agent", {}) or {}
            ts = src.get("timestamp", "")
            incidents.append(
                {
                    "date": str(ts)[:19].replace("T", " "),
                    "agent": agent.get("name", "—"),
                    "description": rule.get("description", "—"),
                    "level": int(rule.get("level", 0) or 0),
                    "mitre": _extract_mitre(src),
                    "recommendation": recommend_for_alert(src),
                }
            )
        incidents.sort(key=lambda x: x["level"], reverse=True)
        data["incidents"] = incidents

        # Vulnerabilidades, ordenadas por severidad.
        vulns = []
        for src in idx.vulnerabilities(size=300):
            vuln = src.get("vulnerability", {}) or {}
            pkg = src.get("package", {}) or {}
            sev_key = _vuln_severity(src)
            vulns.append(
                {
                    "severity_key": sev_key,
                    "severity": sev_key.capitalize() if sev_key else "—",
                    "cve": vuln.get("id") or vuln.get("cve") or "—",
                    "package": pkg.get("name", "—"),
                    "package_version": pkg.get("version", ""),
                    "description": (vuln.get("description") or "—")[:300],
                }
            )
        vulns.sort(
            key=lambda v: VULN_SEVERITY_RANK.get(v["severity_key"], 0),
            reverse=True,
        )
        data["vulnerabilities"] = vulns
        data["connection"]["indexer_ok"] = True
    except IndexerError as exc:
        logger.error("Fallo Indexer: %s", exc)
        data["connection"]["errors"].append(f"Indexer: {exc}")

    # --- Texto derivado ----------------------------------------------------
    data["summary_text"] = _build_executive_summary(data)
    data["recommendations"] = _build_recommendations(data)
    data["severity_labels"] = SEVERITY_LABELS
    return data
