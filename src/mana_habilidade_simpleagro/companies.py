"""Filiais/Empresas — Simple Agro.

Endpoint:
    GET /api/companies  — lista empresas, cada uma com filiais[].

Cada empresa tem várias filiais; procura-se a com filial_faturamento=True.
"""

from __future__ import annotations

import logging
from typing import Any

from .client import SimpleAgroClient
from .exceptions import NotFoundError

log = logging.getLogger("mana-habilidade-simpleagro.companies")


class CompaniesAPI:
    """API de filiais.

    Args:
        client: SimpleAgroClient.
    """

    def __init__(self, client: SimpleAgroClient) -> None:
        self.client = client
        self._filial_faturamento_cache: dict[str, Any] | None = None

    def filial_faturamento(self) -> dict[str, Any]:
        """Filial default de faturamento (a que aparece marcada como filial_faturamento).

        Cache 1× por instância.

        Returns:
            {"id", "nome", "cpf_cnpj", "codref"}

        Raises:
            NotFoundError: nenhuma filial marcada como filial_faturamento.
        """
        if self._filial_faturamento_cache:
            return self._filial_faturamento_cache

        data = self.client.get("/api/companies", params={"limit": 1})
        docs = data.get("docs") if isinstance(data, dict) else (
            data if isinstance(data, list) else []
        )
        for emp in docs:
            for f in emp.get("filiais", []):
                if f.get("filial_faturamento") and not f.get("deleted"):
                    fil = {
                        "id": f["_id"],
                        "nome": f.get("nome_fantasia", ""),
                        "cpf_cnpj": f.get("cpf_cnpj", ""),
                        "codref": f.get("codref", ""),
                    }
                    self._filial_faturamento_cache = fil
                    return fil
        raise NotFoundError("filial_faturamento não encontrada em /api/companies")

    def listar(self) -> list[dict[str, Any]]:
        """Lista todas as empresas com todas as filiais."""
        data = self.client.get("/api/companies", params={"limit": -1})
        if isinstance(data, dict):
            return data.get("docs") or []
        return data if isinstance(data, list) else []
