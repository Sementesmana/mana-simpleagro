"""Cliente HTTP base do Simple Agro — session + retry + auto-relogin em 401.

Toda operação (orders, clients, wallets, catalog) usa este cliente por baixo.
Ele é a peça central que garante:
- 1 login por cliente (cache de token via SimpleAgroAuth)
- Relogin transparente em 401
- Timeout configurável por request
- Requisições autenticadas ao SA
"""

from __future__ import annotations

import logging
from typing import Any

import requests

from .auth import SimpleAgroAuth
from .exceptions import (
    NetworkError,
    NotFoundError,
    ServerError,
    UnauthorizedError,
    ValidationError,
)

log = logging.getLogger("mana-simpleagro.client")

TIMEOUT_DEFAULT = 30


class SimpleAgroClient:
    """Cliente HTTP autenticado pra API do Simple Agro.

    Args:
        base_url: URL raiz da API SA. Default lê SA_BASE_URL do env.
        username: SA_USERNAME. Default lê env.
        password: SA_PASSWORD. Default lê env.
        timeout: timeout padrão em segundos (default 30).
        session: opcional — requests.Session pré-configurado.
        safra_id: ID da safra ativa (usado por defaults em orders/catalog).
        grupo_id: ID do grupo de produto (usado por defaults em catalog).

    Uso típico:
        client = SimpleAgroClient()  # lê env vars
        client.login()
        pedidos = client.get("/api/orders", params={...})
    """

    def __init__(
        self,
        base_url: str | None = None,
        username: str | None = None,
        password: str | None = None,
        timeout: int = TIMEOUT_DEFAULT,
        session: requests.Session | None = None,
        safra_id: str | None = None,
        grupo_id: str | None = None,
    ) -> None:
        import os
        self.base_url = (base_url or os.getenv("SA_BASE_URL", "")).rstrip("/")
        self.timeout = timeout
        self.session = session or requests.Session()
        self.session.headers.setdefault("Content-Type", "application/json")
        self.safra_id = safra_id or os.getenv("SA_SAFRA_ID", "")
        self.grupo_id = grupo_id or os.getenv("SA_GRUPO_ID", "")

        self.auth = SimpleAgroAuth(
            base_url=self.base_url,
            username=username or os.getenv("SA_USERNAME", ""),
            password=password or os.getenv("SA_PASSWORD", ""),
            session=self.session,
        )

    # ── Ciclo de autenticação ─────────────────────────────────────

    def login(self) -> str:
        """Login explícito (útil pra validar credenciais no boot). Retorna token."""
        return self.auth.get_token()

    def is_authenticated(self) -> bool:
        return self.auth.is_authenticated()

    # ── HTTP genérico com auto-relogin ────────────────────────────

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict | None = None,
        json: Any = None,
        files: dict | None = None,
        data: Any = None,
        timeout: int | None = None,
        expect_json: bool = True,
        allow_relogin: bool = True,
    ) -> Any:
        """Faz request autenticado ao SA.

        Args:
            method: GET, POST, PUT, PATCH, DELETE.
            path: começa com /api/... .
            params: query string.
            json: body JSON.
            files: multipart (POST /api/clients usa multipart).
            data: body form-urlencoded (raro).
            timeout: sobrescreve self.timeout.
            expect_json: se True, retorna parsed JSON; se False retorna response.
            allow_relogin: interno — evita loop de relogin.

        Returns:
            dict/list (JSON parseado) ou requests.Response se expect_json=False.

        Raises:
            UnauthorizedError: 401 mesmo após relogin.
            NotFoundError: 404.
            ValidationError: 400 (dados inválidos).
            ServerError: 5xx.
            NetworkError: timeout, DNS, etc.
        """
        self.auth.get_token()  # garante que há token válido antes
        url = f"{self.base_url}{path}"
        try:
            r = self.session.request(
                method=method,
                url=url,
                params=params,
                json=json,
                files=files,
                data=data,
                timeout=timeout or self.timeout,
            )
        except requests.RequestException as e:
            raise NetworkError(f"{method} {path}: {e}") from e

        # 401 → tenta relogin uma vez
        if r.status_code == 401 and allow_relogin:
            log.warning("SA 401 em %s — relogin transparente", path)
            self.auth.invalidate()
            self.auth.get_token(force_relogin=True)
            return self.request(
                method=method,
                path=path,
                params=params,
                json=json,
                files=files,
                data=data,
                timeout=timeout,
                expect_json=expect_json,
                allow_relogin=False,   # não recursivo
            )

        if r.status_code == 401:
            raise UnauthorizedError(f"401 em {path} após relogin: {r.text[:200]}")
        if r.status_code == 404:
            raise NotFoundError(f"404 em {path}")
        if r.status_code == 400:
            raise ValidationError(f"400 em {path}: {r.text[:400]}")
        if 500 <= r.status_code < 600:
            raise ServerError(f"HTTP {r.status_code} em {path}: {r.text[:200]}")
        if r.status_code >= 400:
            raise ValidationError(f"HTTP {r.status_code} em {path}: {r.text[:200]}")

        if not expect_json:
            return r
        try:
            return r.json()
        except ValueError as e:
            raise NetworkError(f"resposta não-JSON em {path}: {e}") from e

    # ── Helpers HTTP ───────────────────────────────────────────────

    def get(self, path: str, params: dict | None = None, **kw: Any) -> Any:
        return self.request("GET", path, params=params, **kw)

    def post(self, path: str, json: Any = None, files: dict | None = None, **kw: Any) -> Any:
        return self.request("POST", path, json=json, files=files, **kw)

    def put(self, path: str, json: Any = None, **kw: Any) -> Any:
        return self.request("PUT", path, json=json, **kw)

    def patch(self, path: str, json: Any = None, **kw: Any) -> Any:
        return self.request("PATCH", path, json=json, **kw)

    def delete(self, path: str, **kw: Any) -> Any:
        return self.request("DELETE", path, **kw)

    # ── Healthcheck ────────────────────────────────────────────────

    def health(self) -> bool:
        """Ping leve: tenta GET /api/clients?limit=1. True se HTTP 200."""
        try:
            self.get("/api/clients", params={"limit": 1, "page": 1}, expect_json=False)
            return True
        except Exception as e:
            log.warning("SA health falhou: %s", e)
            return False
