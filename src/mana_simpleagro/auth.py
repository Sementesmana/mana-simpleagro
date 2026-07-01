"""Login OAuth Simple Agro (AdonisJS) + XSRF + cache de token 50min.

Padrão descoberto e validado 2026-06-04 (via sniffing do painel):
    1. GET /sales/login no painel  → cookie XSRF-TOKEN
    2. POST /api/auth/login com header X-XSRF-TOKEN + Origin/Referer do painel
    3. Response tem token JWT (pode vir já com "Bearer " ou em várias chaves)
    4. Envia Authorization: Bearer <token> em todo request seguinte
    5. Cache token 50min (JWT tem TTL 60min, com margem de 10min)

Reprodução do padrão em ~10 agentes Maná (agente-pedidos, financeiro-sa,
lancamento-pedido, tms, premiacao, mapa-pedidos, bot-multiplicacao, etc).
"""

from __future__ import annotations

import base64
import json
import logging
import time
from urllib.parse import unquote

import requests

from .exceptions import ConfigError, LoginError

log = logging.getLogger("mana-simpleagro.auth")

TOKEN_TTL_SEG = 50 * 60   # 50min (JWT expira em ~60min)

# URL do painel derivada da URL da API (é obrigatório pro cookie XSRF)
_API_HOSTNAME_TROCA = ("sementesmana.api.simpleagro.com.br:3333",
                       "sementesmana.painel.simpleagro.com.br:3333")


def _url_painel_login(base_api: str) -> str:
    """Deriva URL do painel /sales/login a partir da URL da API."""
    return base_api.replace(*_API_HOSTNAME_TROCA) + "/sales/login"


def _decode_jwt_claims(token: str) -> list[str]:
    """Decodifica claims do JWT (diagnóstico). Sem valores, só nomes das chaves."""
    try:
        raw = token.replace("Bearer ", "")
        p = raw.split(".")[1]
        p += "=" * (-len(p) % 4)
        return list(json.loads(base64.urlsafe_b64decode(p)).keys())
    except Exception:
        return []


class SimpleAgroAuth:
    """Gerencia login SA + cache de token.

    Args:
        base_url: URL raiz da API SA (ex: https://sementesmana.api.simpleagro.com.br:3333)
        username: SA_USERNAME (login do usuário SA).
        password: SA_PASSWORD.
        session: opcional — requests.Session compartilhado com o resto do cliente.
                 Se None, cria uma nova (não recomendado — token vai pra Session).
        token_ttl: segundos que o token é considerado válido (default 3000 = 50min).

    Uso típico:
        auth = SimpleAgroAuth(base_url, user, senha)
        token = auth.get_token()  # login on-demand + cache
    """

    def __init__(
        self,
        base_url: str,
        username: str,
        password: str,
        session: requests.Session | None = None,
        token_ttl: int = TOKEN_TTL_SEG,
    ) -> None:
        if not base_url:
            raise ConfigError("SA base_url não pode ser vazio")
        if not username or not password:
            raise ConfigError("SA_USERNAME / SA_PASSWORD obrigatórios")

        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.session = session or requests.Session()
        self.token_ttl = token_ttl
        self._token: str | None = None
        self._expira_em: float = 0.0

    # ── Público ─────────────────────────────────────────────────────

    def get_token(self, force_relogin: bool = False) -> str:
        """Retorna token válido. Faz login on-demand se cache expirou."""
        if not force_relogin and self._token and time.time() < self._expira_em:
            return self._token
        self._login()
        return self._token or ""

    def invalidate(self) -> None:
        """Força novo login na próxima chamada (útil após 401)."""
        self._token = None
        self._expira_em = 0.0

    def is_authenticated(self) -> bool:
        """True se tem token cacheado (não valida com SA)."""
        return bool(self._token) and time.time() < self._expira_em

    # ── Interno ─────────────────────────────────────────────────────

    def _get_xsrf(self) -> str:
        """Puxa cookie XSRF-TOKEN visitando o painel — necessário pro login AdonisJS."""
        try:
            self.session.get(_url_painel_login(self.base_url), timeout=15)
            token = self.session.cookies.get("XSRF-TOKEN", "")
            return unquote(token) if token else ""
        except Exception as e:
            log.warning("XSRF indisponível: %s (seguindo sem)", e)
            return ""

    def _login(self) -> None:
        """Faz login no SA e armazena token no self + no header Authorization da session.

        Raises:
            LoginError: HTTP != 2xx, sem token na resposta, network error.
        """
        xsrf = self._get_xsrf()
        if xsrf:
            self.session.headers["X-XSRF-TOKEN"] = xsrf

        # Headers que espelham o browser — SA às vezes devolve resposta magra
        # (sem produtos na price-table) pra clientes que não parecem navegador
        painel = _url_painel_login(self.base_url).rsplit("/sales/login", 1)[0]
        self.session.headers.update({
            "Origin": painel,
            "Referer": painel + "/sales/login",
            "Accept": "application/json, text/plain, */*",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
            ),
        })

        url = f"{self.base_url}/api/auth/login"
        body = {"login": self.username, "senha": self.password}

        log.info("SA login como '%s'...", self.username)
        try:
            r = self.session.post(url, json=body, timeout=30)
        except requests.RequestException as e:
            raise LoginError(f"SA login network error: {e}") from e

        if r.status_code != 200:
            raise LoginError(
                f"SA login HTTP {r.status_code}: {r.text[:200]}"
            )

        try:
            data = r.json()
        except ValueError as e:
            raise LoginError(f"SA login response inválida (não é JSON): {e}") from e

        raw_token = (
            data.get("token")
            or data.get("accessToken")
            or data.get("access_token")
            or (data.get("data") or {}).get("token")
        )
        if not raw_token:
            raise LoginError(
                f"SA login sem token na resposta (chaves: {list(data.keys())})"
            )

        self._token = (
            raw_token if str(raw_token).startswith("Bearer ")
            else f"Bearer {raw_token}"
        )
        self._expira_em = time.time() + self.token_ttl

        # Aplica Authorization na session pro resto dos requests
        self.session.headers["Authorization"] = self._token

        # XSRF só é usado no login — remove pra não contaminar GETs
        self.session.headers.pop("X-XSRF-TOKEN", None)
        self.session.cookies.clear()

        claims = _decode_jwt_claims(self._token)
        log.info("SA login OK (claims JWT: %s)", claims)
