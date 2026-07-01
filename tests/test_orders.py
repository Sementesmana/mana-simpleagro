"""Testes de OrdersAPI (list, get, criar_pedido, mudar_status)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from mana_habilidade_simpleagro import OrdersAPI, ValidationError
from mana_habilidade_simpleagro.client import SimpleAgroClient


@pytest.fixture
def client(env_completo):
    c = SimpleAgroClient()
    c.get = MagicMock()
    c.post = MagicMock()
    c.put = MagicMock()
    c.patch = MagicMock()
    return c


def test_list_com_defaults_do_env(client):
    client.get.return_value = {"docs": [{"_id": "1"}, {"_id": "2"}]}
    result = OrdersAPI(client).list()
    assert len(result) == 2
    # Verifica params default (safra_id + grupo_id vieram do env)
    call = client.get.call_args
    assert call.args[0] == "/api/orders"
    assert call.kwargs["params"]["safra.id"] == "safra_123"
    assert call.kwargs["params"]["itens.grupo_produto.id"] == "grupo_456"
    assert call.kwargs["params"]["deleted"] == "false"


def test_list_com_status_erp_filtro(client):
    client.get.return_value = []
    OrdersAPI(client).list(status_erp="Erro Integração")
    params = client.get.call_args.kwargs["params"]
    assert params["status_erp"] == "Erro Integração"


def test_list_com_docs_direto(client):
    """SA às vezes retorna array direto, não {docs: [...]}"""
    client.get.return_value = [{"_id": "1"}]
    result = OrdersAPI(client).list()
    assert len(result) == 1


def test_list_com_extras(client):
    client.get.return_value = []
    OrdersAPI(client).list(extras={"vendedor.id": "abc"})
    params = client.get.call_args.kwargs["params"]
    assert params["vendedor.id"] == "abc"


def test_get_por_id(client):
    client.get.return_value = {"_id": "pid1", "numero": "260000230001"}
    result = OrdersAPI(client).get("pid1")
    assert result["numero"] == "260000230001"


def test_list_por_cnpj_normaliza_dígitos(client):
    client.get.return_value = []
    OrdersAPI(client).list_por_cnpj("12.345.678/0001-99")
    params = client.get.call_args.kwargs["params"]
    assert params["cliente.cpf_cnpj"] == "12345678000199"


def test_list_com_erro_integracao_atalho(client):
    client.get.return_value = []
    OrdersAPI(client).list_com_erro_integracao()
    params = client.get.call_args.kwargs["params"]
    assert params["status_erp"] == "Erro Integração"


# ── Escrita ──────────────────────────────────────────────────────


def test_criar_cabecalho_faz_post(client):
    client.post.return_value = {"_id": "novo_pid", "numero": "260000000001"}
    result = OrdersAPI(client).criar_cabecalho({"cliente": {"id": "x"}})
    assert result["_id"] == "novo_pid"
    client.post.assert_called_once()


def test_adicionar_item(client):
    client.post.return_value = {"_id": "item1"}
    result = OrdersAPI(client).adicionar_item("pid1", {"produto": {"id": "p"}})
    assert result["_id"] == "item1"
    assert "pid1" in client.post.call_args.args[0]
    assert "/items" in client.post.call_args.args[0]


def test_mudar_status(client):
    OrdersAPI(client).mudar_status("pid1", "Cancelado", observacao="teste")
    args, kwargs = client.patch.call_args
    assert "pid1" in args[0]
    assert "/status" in args[0]
    assert kwargs["json"]["status_pedido"] == "Cancelado"
    assert kwargs["json"]["observacao"] == "teste"


def test_cancelar_com_operador_e_motivo(client):
    OrdersAPI(client).cancelar("pid1", motivo="cliente desistiu", operador="Alice")
    obs = client.patch.call_args.kwargs["json"]["observacao"]
    assert "Alice" in obs
    assert "cliente desistiu" in obs


def test_finalizar(client):
    OrdersAPI(client).finalizar("pid1")
    assert client.patch.call_args.kwargs["json"]["status_pedido"] == "Aguardando Aprovação"


def test_criar_pedido_completo_orquestra_4_chamadas(client):
    """POST cabeçalho → POST itens → PUT payment → PATCH status."""
    client.post.side_effect = [
        {"_id": "novo_pid", "numero": "260000000001"},   # cabeçalho
        {"_id": "item1"},                                  # 1º item
    ]
    client.put.return_value = None
    client.patch.return_value = None

    pid, numero = OrdersAPI(client).criar_pedido(
        cabecalho={"cliente": {"id": "c"}},
        itens=[{"produto": {"id": "p1"}}],
        parcelas=[{"data_vencimento": "2026-09-30", "valor": 100}],
    )
    assert pid == "novo_pid"
    assert numero == "260000000001"
    # 2 POSTs (1 cabeçalho + 1 item), 2 PUTs (recalc + payment), 1 PATCH
    assert client.post.call_count == 2


def test_criar_pedido_sem_id_no_cabecalho_levanta(client):
    """Se SA não retornar _id no cabeçalho, aborta com ValidationError."""
    client.post.return_value = {"numero": "1"}   # sem _id
    with pytest.raises(ValidationError, match="não retornou _id"):
        OrdersAPI(client).criar_pedido(
            cabecalho={}, itens=[], parcelas=[]
        )


def test_criar_pedido_sem_finalizar_nao_manda_status(client):
    client.post.side_effect = [
        {"_id": "novo_pid", "numero": "260000000001"},
    ]
    OrdersAPI(client).criar_pedido(
        cabecalho={}, itens=[], parcelas=[], finalizar=False
    )
    client.patch.assert_not_called()
