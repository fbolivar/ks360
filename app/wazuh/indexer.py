"""Cliente del Indexer / OpenSearch de Wazuh (puerto 9200).

Autenticacion: Basic Auth (usuario/clave del indexer).
Se usa para:
  - Alertas:            indice  wazuh-alerts-*
  - Vulnerabilidades:   indice  wazuh-states-vulnerabilities-*

Tolera indices vacios o inexistentes devolviendo estructuras vacias en vez de
romper el reporte.
"""
from __future__ import annotations

import logging

import requests
import urllib3

from ..config import settings

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)

ALERTS_INDEX = "wazuh-alerts-*"
VULN_INDEX = "wazuh-states-vulnerabilities-*"


class IndexerError(Exception):
    """Error controlado al hablar con el Indexer/OpenSearch."""


class IndexerClient:
    """Wrapper minimo de consultas DSL contra el Indexer de Wazuh."""

    def __init__(
        self,
        base_url: str | None = None,
        user: str | None = None,
        password: str | None = None,
        verify_ssl: bool | None = None,
        timeout: int | None = None,
    ) -> None:
        self.base_url = (base_url or settings.indexer_base_url).rstrip("/")
        self.user = user if user is not None else settings.indexer_user
        self.password = password if password is not None else settings.indexer_pass
        self.verify_ssl = (
            verify_ssl if verify_ssl is not None else settings.wazuh_verify_ssl
        )
        self.timeout = timeout or settings.wazuh_timeout

    # ------------------------------------------------------------------ HTTP
    def _search(self, index: str, body: dict) -> dict:
        """Ejecuta un _search. Devuelve {} si el indice no existe (404)."""
        url = f"{self.base_url}/{index}/_search"
        try:
            resp = requests.post(
                url,
                json=body,
                auth=(self.user, self.password),
                verify=self.verify_ssl,
                timeout=self.timeout,
            )
        except requests.exceptions.RequestException as exc:
            raise IndexerError(
                f"No se pudo conectar al Indexer ({self.base_url}): {exc}"
            ) from exc

        if resp.status_code == 404:
            logger.warning("Indice no encontrado: %s", index)
            return {}
        if resp.status_code == 401:
            raise IndexerError(
                "Credenciales invalidas para el Indexer (revisa "
                "INDEXER_USER / INDEXER_PASS)."
            )
        if resp.status_code != 200:
            raise IndexerError(
                f"El Indexer respondio HTTP {resp.status_code} en {index}."
            )
        try:
            return resp.json()
        except ValueError as exc:
            raise IndexerError("Respuesta no-JSON del Indexer.") from exc

    # -------------------------------------------------------------- consultas
    def alerts_by_level(self, days: int) -> dict[int, int]:
        """Cuenta de alertas agrupadas por rule.level en los ultimos `days`."""
        body = {
            "size": 0,
            "query": {"range": {"timestamp": {"gte": f"now-{days}d"}}},
            "aggs": {
                "by_level": {
                    "terms": {
                        "field": "rule.level",
                        "size": 30,
                        "order": {"_key": "asc"},
                    }
                }
            },
        }
        res = self._search(ALERTS_INDEX, body)
        buckets = (
            res.get("aggregations", {}).get("by_level", {}).get("buckets", [])
        )
        return {int(b["key"]): int(b["doc_count"]) for b in buckets}

    def total_alerts(self, days: int) -> int:
        """Total de alertas del periodo."""
        body = {
            "size": 0,
            "track_total_hits": True,
            "query": {"range": {"timestamp": {"gte": f"now-{days}d"}}},
        }
        res = self._search(ALERTS_INDEX, body)
        total = res.get("hits", {}).get("total", {})
        if isinstance(total, dict):
            return int(total.get("value", 0))
        return int(total or 0)

    def top_alerts(
        self, days: int, min_level: int = 10, size: int = 20
    ) -> list[dict]:
        """Alertas con rule.level >= min_level, mas recientes primero."""
        body = {
            "size": size,
            "query": {
                "bool": {
                    "filter": [
                        {"range": {"timestamp": {"gte": f"now-{days}d"}}},
                        {"range": {"rule.level": {"gte": min_level}}},
                    ]
                }
            },
            "sort": [{"timestamp": {"order": "desc"}}],
        }
        res = self._search(ALERTS_INDEX, body)
        hits = res.get("hits", {}).get("hits", [])
        return [h.get("_source", {}) for h in hits]

    def vulnerabilities(self, size: int = 200) -> list[dict]:
        """CVEs del indice de vulnerabilidades. Lista vacia si no hay indice."""
        body = {
            "size": size,
            "query": {"match_all": {}},
        }
        res = self._search(VULN_INDEX, body)
        if not res:
            return []
        hits = res.get("hits", {}).get("hits", [])
        return [h.get("_source", {}) for h in hits]

    def ping(self) -> bool:
        """True si el Indexer responde (aunque no haya datos)."""
        try:
            self.total_alerts(1)
            return True
        except IndexerError:
            return False


# ---------------------------------------------------------------------------
# Prueba rapida:  python -m app.wazuh.indexer
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    idx = IndexerClient()
    try:
        days = settings.report_days
        print("Total alertas:", idx.total_alerts(days))
        print("Por nivel:", idx.alerts_by_level(days))
        print("Top criticas:", len(idx.top_alerts(days)))
        print("Vulnerabilidades:", len(idx.vulnerabilities()))
    except IndexerError as err:
        print("ERROR:", err)
