"""Safras — descoberta de safras disponíveis no SA.

SA tem endpoints diferentes por instalação. Tenta em ordem:
    /api/safras, /api/seasons, /api/safra, /api/harvests, /api/crop-seasons

Retorna primeira lista não-vazia. Se nenhum funcionar, retorna [].
"""

from __future__ import annotations

import logging
from typing import Any

from .client import SimpleAgroClient
from .exceptions import UnauthorizedError

log = logging.getLogger("mana-simpleagro.safras")


ENDPOINTS_POSSIVEIS = [
    "/api/safras",
    "/api/seasons",
    "/api/safra",
    "/api/harvests",
    "/api/crop-seasons",
    "/api/safra/list",
]


class SafrasAPI:
    """API de safras.

    Args:
        client: SimpleAgroClient.
    """

    def __init__(self, client: SimpleAgroClient) -> None:
        self.client = client
        self._cache: list[dict[str, Any]] | None = None

    def listar(self, force_refresh: bool = False) -> list[dict[str, Any]]:
        """Descobre e cacheia lista de safras. Retorna [] se nenhum endpoint funcionar."""
        if self._cache is not None and not force_refresh:
            return self._cache

        for path in ENDPOINTS_POSSIVEIS:
            try:
                data = self.client.get(path, timeout=15)
            except UnauthorizedError:
                raise   # não engolir 401 real
            except Exception as e:
                log.debug("safras endpoint %s falhou: %s", path, e)
                continue

            items = (
                data if isinstance(data, list)
                else (data.get("data") or data.get("docs") or data.get("safras")
                      or data.get("seasons") or []) if isinstance(data, dict)
                else []
            )
            if items and isinstance(items, list):
                log.info("safras via %s: %d", path, len(items))
                self._cache = items
                return items

        log.warning("Nenhum endpoint de safras funcionou")
        self._cache = []
        return []

    def get_ativa(self, safra_id: str | None = None) -> dict[str, Any] | None:
        """Retorna dados da safra ativa (por id). Default: safra_id do client."""
        sid = safra_id or self.client.safra_id
        if not sid:
            return None
        for s in self.listar():
            if str(s.get("_id") or s.get("id")) == sid:
                return s
        return None
