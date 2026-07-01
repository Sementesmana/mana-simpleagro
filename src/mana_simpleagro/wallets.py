"""Carteiras (customers-wallets) — vínculo vendedor↔clientes no Simple Agro.

Endpoints:
    GET  /api/customers-wallets              — listar todas (limit=-1 pega tudo)
    GET  /api/customers-wallets/{id}         — 1 carteira completa
    PUT  /api/customers-wallets/{id}         — documento inteiro (GET → append → PUT)
    GET  /api/customers-wallets/get-consultant/{cliente_id}?propID={prop_id}
                                             — vendedor do cliente (endpoint do painel)

Toda vez que o pedido precisa saber "quem é o vendedor deste cliente?", a
resposta vem daqui. Cliente pode estar em múltiplas carteiras.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from .client import SimpleAgroClient

log = logging.getLogger("mana-simpleagro.wallets")


class WalletsAPI:
    """API de carteiras (vendedor↔clientes).

    Args:
        client: SimpleAgroClient.
    """

    def __init__(self, client: SimpleAgroClient) -> None:
        self.client = client

    # ── Leitura ─────────────────────────────────────────────────────

    def listar(self, limit: int = -1) -> list[dict[str, Any]]:
        """Lista todas as carteiras (default: tudo)."""
        data = self.client.get("/api/customers-wallets", params={"limit": str(limit)})
        if isinstance(data, dict):
            return data.get("docs") or (data if isinstance(data, list) else [])
        return data if isinstance(data, list) else []

    def get(self, wallet_id: str) -> dict[str, Any]:
        """GET carteira por id (documento completo)."""
        return self.client.get(f"/api/customers-wallets/{wallet_id}")

    def get_consultant(
        self, cliente_id: str, propriedade_id: str | None = None
    ) -> list[dict[str, Any]]:
        """Endpoint especial do painel — vendedor(es) do cliente/propriedade.

        Retorna: [{vendedor_id, vendedor_nome, vendedor_codref, carteira_id}]
        Vazio se cliente não está em carteira.
        """
        params: dict[str, Any] = {"fields": "nome,codref,carteira,cargo"}
        if propriedade_id:
            params["propID"] = propriedade_id
        try:
            data = self.client.get(
                f"/api/customers-wallets/get-consultant/{cliente_id}",
                params=params,
            )
        except Exception as e:
            log.warning("get-consultant %s: %s", cliente_id, e)
            return []

        lst = data if isinstance(data, list) else (
            data.get("docs") if isinstance(data, dict) else [data]
        )
        if not isinstance(lst, list):
            return []
        out = []
        for c in lst:
            if not isinstance(c, dict):
                continue
            out.append({
                "vendedor_id": c.get("_id"),
                "vendedor_nome": c.get("nome", ""),
                "vendedor_codref": c.get("codref", ""),
                "carteira_id": (c.get("carteira") or {}).get("id"),
            })
        return out

    # ── Consultas derivadas (sobre a lista completa) ────────────────

    def do_vendedor(self, vendedor_sa_id: str) -> dict[str, Any] | None:
        """Encontra a carteira de um vendedor específico (varre todas)."""
        for w in self.listar():
            vid, _, _ = _consultor_info(w)
            if vid == vendedor_sa_id:
                return w
        return None

    def do_cliente(self, cliente_id: str) -> list[dict[str, Any]]:
        """Vendedores possíveis do cliente = carteiras que o contêm.

        Returns:
            [{vendedor_id, vendedor_nome, vendedor_codref, carteira_id}]
        """
        out = []
        for w in self.listar():
            clientes = w.get("clientes", [])
            if any(c.get("cliente_id") == cliente_id for c in clientes if isinstance(c, dict)):
                vid, vnome, vcodref = _consultor_info(w)
                out.append({
                    "vendedor_id": vid,
                    "vendedor_nome": vnome,
                    "vendedor_codref": vcodref,
                    "carteira_id": w.get("_id"),
                })
        return out

    # ── Escrita ─────────────────────────────────────────────────────

    def adicionar_cliente(
        self,
        wallet_id: str,
        cliente: dict[str, Any],
        propriedades_ids: list[str],
    ) -> dict[str, Any]:
        """Adiciona cliente à carteira (idempotente).

        Padrão AdonisJS: SA exige PUT do DOCUMENTO INTEIRO.
        Re-lê antes do PUT pra minimizar janela de concorrência.

        Args:
            wallet_id: _id da carteira.
            cliente: dict com _id, nome, cpf_cnpj.
            propriedades_ids: lista de _ids de propriedades do cliente.

        Returns:
            Carteira atualizada.
        """
        # Re-lê pra pegar versão mais fresca
        w = self.get(wallet_id)
        clientes = w.get("clientes", [])
        # Idempotência: se já tá lá, não faz nada
        if any(c.get("cliente_id") == cliente["_id"] for c in clientes):
            return w

        clientes.append({
            "cliente_id": cliente["_id"],
            "propriedades": propriedades_ids,
            "nome": cliente.get("nome", ""),
            "cpf_cnpj": cliente.get("cpf_cnpj", ""),
            "gerenciarCarteiraPorPropriedade": True,
            "deleted": False,
            "status": True,
        })
        w["clientes"] = clientes
        return self.client.put(f"/api/customers-wallets/{wallet_id}", json=w)


# ── Helpers internos ─────────────────────────────────────────────


def _nome_da_carteira(w: dict) -> str:
    """Carteiras seguem padrão 'Cart [NOME]' — extrai o nome."""
    m = re.search(r"\[(.+?)\]", w.get("nome", ""))
    return m.group(1).strip() if m else w.get("nome", "").strip()


def _consultor_info(w: dict) -> tuple[str | None, str, str]:
    """consultor_id pode vir como string OU como doc expandido — normaliza.

    Returns:
        (vendedor_id, vendedor_nome, vendedor_codref)
    """
    cid = w.get("consultor_id")
    if isinstance(cid, dict):
        return (
            cid.get("_id"),
            cid.get("nome") or _nome_da_carteira(w),
            cid.get("codref", ""),
        )
    return cid, _nome_da_carteira(w), ""
