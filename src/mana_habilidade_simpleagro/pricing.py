"""Engine de preço — fórmula validada 2026-06-04.

Fórmula:
    preço_tabela(venc) = preço_base × (1 + taxa_adicao/100) ^ (dias(data_base→venc)/30)

Aplica ao vencimento do pedido pra calcular royalties + germoplasma + custo.
Validado bit-a-bit contra painel SA (O790IPRO GOIAS 4906,12 → 85 dias → 5174,857016).
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

from .client import SimpleAgroClient
from .catalog import CatalogAPI
from .exceptions import NotFoundError
from .helpers import normalizar_produto, parse_ptbr

log = logging.getLogger("mana-habilidade-simpleagro.pricing")


class PricingAPI:
    """Cálculo de preço no vencimento — usa Catalog pra pegar tabelas.

    Args:
        client: SimpleAgroClient.
        catalog: CatalogAPI (opcional — se None cria um).
    """

    def __init__(
        self,
        client: SimpleAgroClient,
        catalog: CatalogAPI | None = None,
    ) -> None:
        self.client = client
        self.catalog = catalog or CatalogAPI(client)

    def fator_juros(self, tabela_doc: dict[str, Any], venc_iso: str) -> float:
        """Calcula fator de juros da fórmula pt-BR (pra 1 tabela + 1 vencimento)."""
        base = str(tabela_doc.get("data_base", ""))[:10]
        taxa = parse_ptbr(tabela_doc.get("taxa_adicao") or "0")
        if not base or not venc_iso:
            return 1.0
        try:
            d0 = date.fromisoformat(base)
            d1 = date.fromisoformat(str(venc_iso)[:10])
        except ValueError:
            return 1.0
        dias = (d1 - d0).days
        if dias <= 0 or taxa <= 0:
            return 1.0
        return (1 + taxa / 100.0) ** (dias / 30.0)

    def dados_produto(
        self,
        nome_produto: str,
        tabela_id: str,
        vencimento_iso: str,
        safra_id: str | None = None,
    ) -> dict[str, Any]:
        """Dados do produto com preço ajustado ao vencimento.

        Args:
            nome_produto: nome (aceita match parcial, case-insensitive).
            tabela_id: _id da tabela de preço.
            vencimento_iso: 'YYYY-MM-DD' — data de vencimento da parcela.

        Returns:
            {
                "produto": {"id", "nome"},
                "peso_embalagem": float,
                "embalagem_base": dict,
                "u_m_preco": str,
                "royalties_tabela": float,
                "germoplasma_tabela": float,
                "custo_royalties": float,
                "custo_germoplasma": float,
                "preco_item_tabela": float,  # royalties + germoplasma (com juros)
                "fator_juros": float,
            }

        Raises:
            NotFoundError: produto não está na tabela.
        """
        doc = self.catalog.tabela_detalhe(tabela_id, safra_id)
        chave = normalizar_produto(nome_produto)
        prod: dict[str, Any] | None = None
        for p in doc.get("produtos", []):
            if p.get("deleted"):
                continue
            nm = normalizar_produto(p.get("nome"))
            if nm == chave or chave in nm or nm in chave:
                prod = p
                break
        if not prod:
            raise NotFoundError(
                f"produto '{nome_produto}' não está na tabela {doc.get('nome')}"
            )

        f = self.fator_juros(doc, vencimento_iso)
        base_r = parse_ptbr(prod.get("preco_royalties") or "0")
        base_g = parse_ptbr(prod.get("preco_germoplasma") or "0")
        base_cr = parse_ptbr(prod.get("custo_royalties") or "0")
        base_cg = parse_ptbr(prod.get("custo_germoplasma") or "0")

        return {
            "produto": {
                "id": prod.get("id") or prod.get("_id"),
                "nome": prod.get("nome"),
            },
            "peso_embalagem": parse_ptbr(prod.get("peso") or "0"),
            "embalagem_base": prod.get("embalagem_base") or {},
            "u_m_preco": prod.get("u_m_preco", "5 M"),
            "royalties_tabela": base_r * f,
            "germoplasma_tabela": base_g * f,
            "custo_royalties": base_cr * f,
            "custo_germoplasma": base_cg * f,
            "preco_item_tabela": (base_r + base_g) * f,
            "fator_juros": f,
        }
