"""Cliente de la API REST de Wazuh (puerto 55000).

Flujo de autenticacion (probado en Wazuh 4.14):
  1. POST /security/user/authenticate?raw=true  con Basic Auth (user/pass)
     -> devuelve un token JWT en texto plano (valido ~15 min).
  2. Las siguientes llamadas usan  Authorization: Bearer <token>.

Se usa para: lista de agentes (/agents) e info del manager (/manager/info).

IMPORTANTE: en Wazuh 4.8+ las vulnerabilidades YA NO estan en la API REST
(el endpoint /vulnerability/{agent} fue eliminado). Para vulnerabilidades se
usa el Indexer (ver indexer.py).
"""
from __future__ import annotations

import logging
import time

import requests
import urllib3

from ..config import settings

# Certificados autofirmados en lab -> silenciar el aviso de verificacion.
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)


class WazuhAPIError(Exception):
    """Error claro y controlado al hablar con la API REST de Wazuh."""


class WazuhClient:
    """Wrapper minimo de la API REST de Wazuh con manejo de token JWT."""

    # El JWT vive ~15 min; renovamos un poco antes por seguridad.
    _TOKEN_TTL_SECONDS = 12 * 60

    def __init__(
        self,
        base_url: str | None = None,
        user: str | None = None,
        password: str | None = None,
        verify_ssl: bool | None = None,
        timeout: int | None = None,
    ) -> None:
        self.base_url = (base_url or settings.api_base_url).rstrip("/")
        self.user = user if user is not None else settings.wazuh_api_user
        self.password = password if password is not None else settings.wazuh_api_pass
        self.verify_ssl = (
            verify_ssl if verify_ssl is not None else settings.wazuh_verify_ssl
        )
        self.timeout = timeout or settings.wazuh_timeout
        self._token: str | None = None
        self._token_ts: float = 0.0

    # ----------------------------------------------------------------- token
    def get_token(self, force: bool = False) -> str:
        """Obtiene (y cachea) el token JWT. Renueva si expiro o si force=True."""
        if (
            self._token
            and not force
            and (time.time() - self._token_ts) < self._TOKEN_TTL_SECONDS
        ):
            return self._token

        url = f"{self.base_url}/security/user/authenticate?raw=true"
        try:
            resp = requests.post(
                url,
                auth=(self.user, self.password),
                verify=self.verify_ssl,
                timeout=self.timeout,
            )
        except requests.exceptions.RequestException as exc:
            raise WazuhAPIError(
                f"No se pudo conectar a la API de Wazuh ({self.base_url}): {exc}"
            ) from exc

        if resp.status_code == 401:
            raise WazuhAPIError(
                "Credenciales invalidas para la API de Wazuh (revisa "
                "WAZUH_API_USER / WAZUH_API_PASS)."
            )
        if resp.status_code != 200:
            raise WazuhAPIError(
                f"Fallo de autenticacion en Wazuh (HTTP {resp.status_code})."
            )

        token = resp.text.strip()
        if not token:
            raise WazuhAPIError("La API de Wazuh no devolvio un token.")

        self._token = token
        self._token_ts = time.time()
        return token

    # ----------------------------------------------------------------- HTTP
    def _get(self, path: str, params: dict | None = None) -> dict:
        """GET autenticado con reintento si el token expiro (401)."""
        url = f"{self.base_url}{path}"
        for attempt in (1, 2):
            token = self.get_token(force=(attempt == 2))
            headers = {"Authorization": f"Bearer {token}"}
            try:
                resp = requests.get(
                    url,
                    headers=headers,
                    params=params,
                    verify=self.verify_ssl,
                    timeout=self.timeout,
                )
            except requests.exceptions.RequestException as exc:
                raise WazuhAPIError(
                    f"Error de red llamando a {path}: {exc}"
                ) from exc

            if resp.status_code == 401 and attempt == 1:
                continue  # token expirado -> renovar y reintentar una vez

            if resp.status_code != 200:
                raise WazuhAPIError(
                    f"Wazuh respondio HTTP {resp.status_code} en {path}."
                )
            try:
                return resp.json()
            except ValueError as exc:
                raise WazuhAPIError(
                    f"Respuesta no-JSON de Wazuh en {path}."
                ) from exc

        raise WazuhAPIError(f"No fue posible autenticar la llamada a {path}.")

    # -------------------------------------------------------------- recursos
    def get_agents(self) -> list[dict]:
        """Devuelve la lista de agentes normalizada (nombre, ip, estado...)."""
        data = self._get("/agents", params={"limit": 1000})
        items = data.get("data", {}).get("affected_items", [])
        agents: list[dict] = []
        for it in items:
            agents.append(
                {
                    "id": it.get("id"),
                    "name": it.get("name", "—"),
                    "ip": it.get("ip") or it.get("registerIP") or "—",
                    "status": (it.get("status") or "unknown").lower(),
                    "os": (it.get("os") or {}).get("name", ""),
                    "version": it.get("version", ""),
                }
            )
        return agents

    def get_manager_info(self) -> dict:
        """Info del manager. El campo de version puede venir en varias claves."""
        data = self._get("/manager/info")
        items = data.get("data", {}).get("affected_items", [])
        info = items[0] if items else data.get("data", {})

        version = None
        for key in ("version", "wazuh_version", "release", "v"):
            if isinstance(info, dict) and info.get(key):
                version = str(info[key])
                break

        return {
            "version": version or "desconocida",
            "name": info.get("name") if isinstance(info, dict) else None,
            "raw": info,
        }

    def ping(self) -> bool:
        """True si se puede autenticar y consultar el manager."""
        try:
            self.get_manager_info()
            return True
        except WazuhAPIError:
            return False


# ---------------------------------------------------------------------------
# Prueba rapida:  python -m app.wazuh.client
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    client = WazuhClient()
    try:
        print("Manager:", client.get_manager_info())
        agents = client.get_agents()
        print(f"Agentes: {len(agents)}")
        for a in agents[:5]:
            print(f"  - {a['name']} ({a['ip']}) [{a['status']}]")
    except WazuhAPIError as err:
        print("ERROR:", err)
