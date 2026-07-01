"""Orders — pedidos do Simple Agro (leitura, criação, atualização, cancelamento).

Endpoints cobertos:
    GET    /api/orders              — list (com filtros safra_id, grupo_id, etc)
    GET    /api/orders/{id}         — get by id
    POST   /api/orders              — criar cabeçalho (nasce "Em cotação")
    POST   /api/orders/{id}/items   — criar item
    PUT    /api/orders/{id}/items/{item_id}   — atualizar item (força recálculo)
    PUT    /api/orders/{id}/payment           — parcelas + itens consolidados
    PATCH  /api/orders/{id}/status            — mudar status (Aguardando/Cancelado/Reaberto)

Padrão descoberto e validado em produção (agente-pedidos, agente-lancamento-pedido,
agente-financeiro-sa, agente-tms).
"""

from __future__ import annotations

import logging
from typing import Any

from .client import SimpleAgroClient
from .exceptions import ValidationError

log = logging.getLogger("mana-habilidade-simpleagro.orders")


class OrdersAPI:
    """API de pedidos. Instanciar via `SimpleAgro.orders` (do __init__).

    Args:
        client: SimpleAgroClient (base HTTP autenticado).
    """

    def __init__(self, client: SimpleAgroClient) -> None:
        self.client = client

    # ── Leitura ─────────────────────────────────────────────────────

    def list(
        self,
        safra_id: str | None = None,
        grupo_produto_id: str | None = None,
        status_erp: str | None = None,
        limit: int = -1,
        deleted: bool = False,
        extras: dict | None = None,
    ) -> list[dict[str, Any]]:
        """Lista pedidos com filtros.

        Args:
            safra_id: ID da safra (default: client.safra_id).
            grupo_produto_id: filtra itens.grupo_produto.id (default: client.grupo_id).
            status_erp: opcional — 'Aprovado', 'Erro Integração', etc.
            limit: -1 pra todos (default), N pra paginar.
            deleted: incluir pedidos deletados (default False).
            extras: dict de params HTTP extras (ex: {"vendedor.id": "..."}).

        Returns:
            Lista de dicts (raw do SA — cada pedido tem cliente, vendedor, itens,
            pagamento, geolocalizacao_entrega, etc).
        """
        sid = safra_id or self.client.safra_id
        gid = grupo_produto_id or self.client.grupo_id
        params: dict[str, Any] = {
            "safra.id": sid,
            "limit": limit,
            "deleted": "false" if not deleted else "true",
        }
        if gid:
            params["itens.grupo_produto.id"] = gid
        if status_erp:
            params["status_erp"] = status_erp
        if extras:
            params.update(extras)

        data = self.client.get("/api/orders", params=params, timeout=120)
        return _extract_docs(data)

    def get(self, order_id: str) -> dict[str, Any]:
        """Busca 1 pedido por _id."""
        return self.client.get(f"/api/orders/{order_id}")

    def list_com_erro_integracao(
        self,
        safra_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Atalho: pedidos com status_erp='Erro Integração' na safra ativa."""
        return self.list(safra_id=safra_id, status_erp="Erro Integração")

    def list_por_cnpj(
        self,
        cnpj: str,
        safra_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Atalho: pedidos de um cliente específico (por CPF/CNPJ)."""
        from .helpers import so_digitos
        sid = safra_id or self.client.safra_id
        params = {
            "safra.id": sid,
            "limit": -1,
            "deleted": "false",
            "cliente.cpf_cnpj": so_digitos(cnpj),
        }
        data = self.client.get("/api/orders", params=params, timeout=60)
        return _extract_docs(data)

    # ── Escrita: criar pedido completo ──────────────────────────────

    def criar_pedido(
        self,
        cabecalho: dict[str, Any],
        itens: list[dict[str, Any]],
        parcelas: list[dict[str, Any]],
        observacao: str = "",
        finalizar: bool = True,
    ) -> tuple[str, str]:
        """Cria pedido completo (cabeçalho + itens + pagamento + status).

        Args:
            cabecalho: shape do POST /api/orders (filial, safra, tabela_preco_base,
                       cliente, vendedor, propriedade, tipo_frete, tipo_pagamento, ...).
            itens: lista de itens (cada um shape do POST /api/orders/{id}/items).
            parcelas: lista de parcelas (shape do PUT /api/orders/{id}/payment).
            observacao: string de rastreamento (ex: "Lançado via WhatsApp por X").
            finalizar: se True, PATCH status pra "Aguardando Aprovação".
                       Se False, deixa em "Em cotação" (default do criar).

        Returns:
            (order_id, numero_do_pedido)

        Raises:
            ValidationError: SA rejeitou cabeçalho/item/parcelas.
        """
        if observacao:
            cabecalho["observacao"] = observacao

        # 1. POST cabeçalho — nasce "Em cotação"
        pedido = self.client.post("/api/orders", json=cabecalho)
        pid = pedido.get("_id")
        if not pid:
            raise ValidationError(f"criar_pedido: SA não retornou _id: {pedido}")

        # 2. POST cada item + PUT recálculo (workaround: SA lazy-calc)
        itens_criados = []
        for item in itens:
            item_criado = self.client.post(f"/api/orders/{pid}/items", json=item)
            itens_criados.append(item_criado)
            iid = item_criado.get("_id")
            if iid:
                # Workaround: SA só calcula preço ao EDITAR item
                try:
                    self.client.put(
                        f"/api/orders/{pid}/items/{iid}", json=item, expect_json=False
                    )
                except Exception as e:
                    log.warning("PUT recalc item %s falhou: %s", iid, e)

        # 3. PUT payment (parcelas + itens consolidados)
        body_pay = {
            "geolocalizacao_entrega": cabecalho.get("geolocalizacao_entrega"),
            "itens": itens_criados,
            "pagamento": {"parcelas": parcelas},
        }
        self.client.put(f"/api/orders/{pid}/payment", json=body_pay, expect_json=False)

        # 4. PATCH status pra "Aguardando Aprovação" (opcional)
        if finalizar:
            self.client.patch(
                f"/api/orders/{pid}/status",
                json={"status_pedido": "Aguardando Aprovação"},
                expect_json=False,
            )

        numero = pedido.get("numero", "")
        log.info("Pedido %s (%s) criado", numero, pid)
        return pid, numero

    # ── Escrita: operações individuais ─────────────────────────────

    def criar_cabecalho(self, cabecalho: dict[str, Any]) -> dict[str, Any]:
        """POST /api/orders — só o cabeçalho, sem itens/parcelas. Retorna pedido criado."""
        return self.client.post("/api/orders", json=cabecalho)

    def adicionar_item(self, order_id: str, item: dict[str, Any]) -> dict[str, Any]:
        """POST /api/orders/{id}/items — adiciona item ao pedido."""
        return self.client.post(f"/api/orders/{order_id}/items", json=item)

    def atualizar_item(
        self, order_id: str, item_id: str, item: dict[str, Any]
    ) -> None:
        """PUT /api/orders/{id}/items/{item_id} — força recálculo de preço."""
        self.client.put(
            f"/api/orders/{order_id}/items/{item_id}", json=item, expect_json=False
        )

    def atualizar_payment(
        self, order_id: str, parcelas: list[dict[str, Any]], itens: list[dict[str, Any]],
        geolocalizacao: dict | None = None,
    ) -> None:
        """PUT /api/orders/{id}/payment — parcelas + itens consolidados."""
        body = {
            "geolocalizacao_entrega": geolocalizacao,
            "itens": itens,
            "pagamento": {"parcelas": parcelas},
        }
        self.client.put(f"/api/orders/{order_id}/payment", json=body, expect_json=False)

    def mudar_status(
        self, order_id: str, status: str, observacao: str = ""
    ) -> None:
        """PATCH /api/orders/{id}/status — muda status (Cancelado, Aguardando, Reaberto)."""
        body: dict[str, Any] = {"status_pedido": status}
        if observacao:
            body["observacao"] = observacao
        self.client.patch(f"/api/orders/{order_id}/status", json=body, expect_json=False)

    # ── Atalhos de status ──────────────────────────────────────────

    def finalizar(self, order_id: str) -> None:
        """PATCH status → 'Aguardando Aprovação' (submeter pedido)."""
        self.mudar_status(order_id, "Aguardando Aprovação")

    def cancelar(self, order_id: str, motivo: str = "", operador: str = "") -> None:
        """PATCH status → 'Cancelado' com observação."""
        obs = ""
        if operador:
            obs = f"Cancelado por {operador}"
            if motivo:
                obs += f" — {motivo}"
        elif motivo:
            obs = f"Cancelado: {motivo}"
        self.mudar_status(order_id, "Cancelado", observacao=obs)

    def reabrir(self, order_id: str) -> None:
        """PATCH status → 'Reaberto' + GET pra regenerar PDF."""
        self.mudar_status(order_id, "Reaberto")
        try:
            self.client.get(f"/api/orders/{order_id}")
        except Exception as e:
            log.warning("reabrir: GET pós-status falhou: %s", e)


# ─────────────────────────────────────────────────────────────────
# Helpers internos
# ─────────────────────────────────────────────────────────────────


def _extract_docs(data: Any) -> list[dict[str, Any]]:
    """SA pode devolver array direto OU {docs: [...]} OU {data: [...]}. Normaliza."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return (
            data.get("docs")
            or data.get("data")
            or data.get("orders")
            or []
        )
    return []
