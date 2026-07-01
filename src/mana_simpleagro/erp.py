"""Erros de integração ERP — pedidos com status_erp='Erro Integração'.

Classifica os erros por subtipo via regex no campo `erro_erp`. Padrão portado
do agente-gestor-comercial (5ª categoria).
"""

from __future__ import annotations

import logging
import re
from typing import Any

from .client import SimpleAgroClient
from .helpers import extract_name, so_digitos
from .orders import OrdersAPI

log = logging.getLogger("mana-simpleagro.erp")


# Subtipos de erro ERP (classificação por regex — 5 categorias validadas em produção)
SUBTIPOS_ERP = [
    ("SENHA_ERP_EXPIRADA", r"senha.*(expir|inv[aá]lida)|password"),
    ("SALDO_ARMAZEM_99", r"saldo.*insufic|armaz[eé]m 99"),
    ("CODIGO_PRODUTO_NAO_MAPEADO", r"produto.*n[aã]o.*cadastr|c[oó]d.*produto"),
    ("CLIENTE_SEM_CODREF", r"cliente.*sem c[oó]d|codref.*cliente"),
    ("PROPRIEDADE_SEM_CODREF", r"propriedade.*sem c[oó]d|codref.*propriedade"),
    ("ERRO_PYTHON", r"traceback|nameerror|attribute[a-z]+error"),
]

SEVERIDADE = {
    "SENHA_ERP_EXPIRADA": "CRITICO",
    "CODIGO_PRODUTO_NAO_MAPEADO": "ALTO",
    "SALDO_ARMAZEM_99": "MEDIO",
    "CLIENTE_SEM_CODREF": "MEDIO",
    "PROPRIEDADE_SEM_CODREF": "MEDIO",
    "ERRO_PYTHON": "MEDIO",
    "OUTRO": "MEDIO",
}


class ErpAPI:
    """API de erros ERP.

    Args:
        client: SimpleAgroClient.
        orders: OrdersAPI (opcional).
    """

    def __init__(
        self,
        client: SimpleAgroClient,
        orders: OrdersAPI | None = None,
    ) -> None:
        self.client = client
        self.orders = orders or OrdersAPI(client)

    def listar_com_erro(self, safra_id: str | None = None) -> list[dict[str, Any]]:
        """Lista raw dos pedidos com status_erp='Erro Integração'."""
        return self.orders.list_com_erro_integracao(safra_id=safra_id)

    def classificar(self, erro_erp: str) -> tuple[str, str]:
        """Regex → (subtipo, severidade). 'OUTRO' se nada bater.

        >>> ErpAPI(...).classificar("Senha ERP expirada")
        ('SENHA_ERP_EXPIRADA', 'CRITICO')
        """
        txt = (erro_erp or "").lower()
        for subtipo, padrao in SUBTIPOS_ERP:
            if re.search(padrao, txt, re.IGNORECASE):
                return subtipo, SEVERIDADE.get(subtipo, "MEDIO")
        return "OUTRO", SEVERIDADE["OUTRO"]

    def listar_classificado(
        self, safra_id: str | None = None
    ) -> list[dict[str, Any]]:
        """Lista pedidos com erro ERP, cada um enriquecido com subtipo+severidade.

        Returns:
            [{numero, cnpj, cliente, vendedor, erro_erp, subtipo, severidade,
              item_com_erro, cultivar_com_erro}, ...]
        """
        out = []
        for o in self.listar_com_erro(safra_id):
            erro = str(o.get("erro_erp") or "")
            subtipo, sev = self.classificar(erro)

            cliente = o.get("cliente") or {}
            cnpj = so_digitos(cliente.get("cpf_cnpj") or "")

            # Extrai item/cultivar do erro (se der pra parsear)
            item = ""
            cultivar = ""
            m_item = re.search(r"item[:\s]+(\S+)", erro, re.IGNORECASE)
            if m_item:
                item = m_item.group(1)
            m_cult = re.search(r"cultivar[:\s]+([A-Z0-9 ]+)", erro, re.IGNORECASE)
            if m_cult:
                cultivar = m_cult.group(1).strip()

            out.append({
                "numero": str(o.get("numero") or ""),
                "cnpj": cnpj,
                "cliente": extract_name(cliente),
                "vendedor": extract_name(o.get("vendedor")),
                "erro_erp": erro,
                "subtipo": subtipo,
                "severidade": sev,
                "item_com_erro": item,
                "cultivar_com_erro": cultivar,
                "valor_total": o.get("valor_total") or o.get("total_liq_frete") or 0,
                "data_emissao": o.get("data_emissao") or o.get("created_at") or "",
            })
        return out
