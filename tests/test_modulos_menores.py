"""Testes de wallets, catalog, pricing, companies, safras, geolocation, erp.

1 arquivo combinado — testes mais curtos, foco em happy path + edge cases.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from mana_simpleagro import (
    CatalogAPI,
    CompaniesAPI,
    ErpAPI,
    GeolocationAPI,
    NotFoundError,
    OrdersAPI,
    PricingAPI,
    SafrasAPI,
    WalletsAPI,
)
from mana_simpleagro.client import SimpleAgroClient


@pytest.fixture
def client(env_completo):
    c = SimpleAgroClient()
    c.get = MagicMock()
    c.post = MagicMock()
    c.put = MagicMock()
    c.patch = MagicMock()
    return c


# ─────────────────────────────────────────────────────────────────────
# Wallets
# ─────────────────────────────────────────────────────────────────────


def test_wallets_listar(client):
    client.get.return_value = {"docs": [{"_id": "w1"}, {"_id": "w2"}]}
    result = WalletsAPI(client).listar()
    assert len(result) == 2


def test_wallets_get_consultant(client):
    client.get.return_value = [{
        "_id": "vend1", "nome": "Alice", "codref": "V001",
        "carteira": {"id": "w1"},
    }]
    result = WalletsAPI(client).get_consultant("c1", "prop1")
    assert result[0]["vendedor_nome"] == "Alice"
    assert result[0]["carteira_id"] == "w1"


def test_wallets_get_consultant_erro_retorna_vazio(client):
    client.get.side_effect = Exception("timeout")
    assert WalletsAPI(client).get_consultant("c1") == []


def test_wallets_do_cliente_filtra_carteiras_com_o_cliente(client):
    client.get.return_value = {"docs": [
        {"_id": "w1", "nome": "Cart [Alice]", "consultor_id": "vend1",
         "clientes": [{"cliente_id": "c1"}, {"cliente_id": "c2"}]},
        {"_id": "w2", "nome": "Cart [Bob]", "consultor_id": "vend2",
         "clientes": [{"cliente_id": "c3"}]},
    ]}
    result = WalletsAPI(client).do_cliente("c1")
    assert len(result) == 1
    assert result[0]["vendedor_nome"] == "Alice"


def test_wallets_adicionar_cliente_idempotente(client):
    """Se cliente já tá na carteira, PUT não é chamado."""
    carteira = {
        "_id": "w1",
        "clientes": [{"cliente_id": "c1"}],
    }
    client.get.return_value = carteira
    result = WalletsAPI(client).adicionar_cliente(
        "w1", {"_id": "c1", "nome": "X"}, ["prop1"]
    )
    assert result == carteira
    client.put.assert_not_called()


def test_wallets_adicionar_cliente_novo_faz_put(client):
    client.get.return_value = {"_id": "w1", "clientes": []}
    client.put.return_value = {"_id": "w1", "clientes": [{"cliente_id": "c1"}]}
    result = WalletsAPI(client).adicionar_cliente(
        "w1", {"_id": "c1", "nome": "N", "cpf_cnpj": "111"}, ["p1"]
    )
    client.put.assert_called_once()
    body = client.put.call_args.kwargs["json"]
    assert body["clientes"][0]["cliente_id"] == "c1"


# ─────────────────────────────────────────────────────────────────────
# Catalog
# ─────────────────────────────────────────────────────────────────────


def test_catalog_grupo_produto_cacheia(client):
    client.get.return_value = {"_id": "grupo_456", "nome": "Soja", "produtos": []}
    cat = CatalogAPI(client)
    cat.grupo_produto()
    cat.grupo_produto()  # 2ª chamada não deve bater no client
    assert client.get.call_count == 1


def test_catalog_produtos_do_grupo_indexa_por_nome_e_id(client):
    client.get.return_value = {
        "_id": "g",
        "nome": "Soja",
        "produtos": [
            {"_id": "p1", "nome": "O790IPRO"},
            {"_id": "p2", "nome": "NEO 791"},
        ],
    }
    by_name, by_id = CatalogAPI(client).produtos_do_grupo()
    assert "O790IPRO" in by_name
    assert "NEO791" in by_name   # normalizado
    assert "p1" in by_id
    assert "p2" in by_id


def test_catalog_obter_produto_match_exato(client):
    client.get.return_value = {
        "_id": "g", "nome": "Soja",
        "produtos": [{"_id": "p1", "nome": "O790IPRO"}],
    }
    result = CatalogAPI(client).obter_produto("O790IPRO")
    assert result is not None
    assert result["produto"]["nome"] == "O790IPRO"


def test_catalog_obter_produto_match_parcial(client):
    """'NEO 790 IPRO' com espaço deve casar com 'O790IPRO' (fuzzy)."""
    client.get.return_value = {
        "_id": "g", "nome": "Soja",
        "produtos": [{"_id": "p1", "nome": "O790IPRO"}],
    }
    result = CatalogAPI(client).obter_produto("O790IPRO")
    assert result is not None


def test_catalog_obter_produto_nao_encontrado(client):
    client.get.return_value = {"_id": "g", "nome": "Soja", "produtos": []}
    assert CatalogAPI(client).obter_produto("INEXISTENTE") is None


def test_catalog_descricoes_generico(client):
    client.get.return_value = {"docs": [
        {"descricao": "À Vista"},
        {"descricao": "Prazo"},
    ]}
    result = CatalogAPI(client).descricoes("form-of-payment")
    assert result == ["À Vista", "Prazo"]


# ─────────────────────────────────────────────────────────────────────
# Pricing
# ─────────────────────────────────────────────────────────────────────


def test_pricing_fator_juros_sem_juros_quando_sem_data(client):
    p = PricingAPI(client)
    doc = {"data_base": "", "taxa_adicao": "1,5"}
    assert p.fator_juros(doc, "2026-08-30") == 1.0


def test_pricing_fator_juros_sem_juros_taxa_zero(client):
    p = PricingAPI(client)
    doc = {"data_base": "2026-06-01", "taxa_adicao": "0"}
    assert p.fator_juros(doc, "2026-08-30") == 1.0


def test_pricing_fator_juros_positivo(client):
    p = PricingAPI(client)
    doc = {"data_base": "2026-06-01", "taxa_adicao": "1,5"}
    fator = p.fator_juros(doc, "2026-08-30")
    # 90 dias, 1,5% ao mês → fator > 1
    assert fator > 1.0
    assert fator < 1.1   # sanity


def test_pricing_dados_produto_com_juros(client):
    catalog = CatalogAPI(client)
    catalog._cache["tabela:tab1"] = {
        "_id": "tab1",
        "nome": "Tabela X",
        "data_base": "2026-06-01",
        "taxa_adicao": "1,5",
        "produtos": [{
            "_id": "p1",
            "id": "p1",
            "nome": "O790IPRO",
            "preco_royalties": "100,00",
            "preco_germoplasma": "50,00",
            "custo_royalties": "10",
            "custo_germoplasma": "5",
            "peso": "40,000",
            "u_m_preco": "5 M",
        }],
    }
    p = PricingAPI(client, catalog)
    dados = p.dados_produto("O790IPRO", "tab1", "2026-08-30")
    assert dados["produto"]["nome"] == "O790IPRO"
    assert dados["royalties_tabela"] > 100.0   # com juros
    assert dados["preco_item_tabela"] > 150.0


def test_pricing_dados_produto_nao_encontrado(client):
    catalog = CatalogAPI(client)
    catalog._cache["tabela:tab1"] = {
        "_id": "tab1", "nome": "X", "data_base": "2026-06-01",
        "taxa_adicao": "0", "produtos": [],
    }
    with pytest.raises(NotFoundError):
        PricingAPI(client, catalog).dados_produto("X", "tab1", "2026-08-30")


# ─────────────────────────────────────────────────────────────────────
# Companies
# ─────────────────────────────────────────────────────────────────────


def test_companies_filial_faturamento(client):
    client.get.return_value = {"docs": [{
        "_id": "e1",
        "filiais": [
            {"_id": "f1", "nome_fantasia": "Loja 1", "filial_faturamento": False},
            {"_id": "f2", "nome_fantasia": "Matriz", "filial_faturamento": True,
             "cpf_cnpj": "12.345/0001", "codref": "M001"},
        ],
    }]}
    result = CompaniesAPI(client).filial_faturamento()
    assert result["nome"] == "Matriz"
    assert result["codref"] == "M001"


def test_companies_filial_faturamento_nao_existe(client):
    client.get.return_value = {"docs": []}
    with pytest.raises(NotFoundError):
        CompaniesAPI(client).filial_faturamento()


def test_companies_filial_faturamento_cacheia(client):
    client.get.return_value = {"docs": [{
        "filiais": [{"_id": "f1", "filial_faturamento": True, "nome_fantasia": "M"}]
    }]}
    comp = CompaniesAPI(client)
    comp.filial_faturamento()
    comp.filial_faturamento()
    assert client.get.call_count == 1


# ─────────────────────────────────────────────────────────────────────
# Safras
# ─────────────────────────────────────────────────────────────────────


def test_safras_listar_primeiro_endpoint_funciona(client):
    client.get.return_value = [{"_id": "s1", "nome": "26/27"}]
    result = SafrasAPI(client).listar()
    assert len(result) == 1


def test_safras_listar_fallback_endpoints(client):
    """Se /api/safras 404, tenta /api/seasons."""
    client.get.side_effect = [
        NotFoundError(),
        [{"_id": "s1"}],
    ]
    result = SafrasAPI(client).listar()
    assert len(result) == 1


def test_safras_listar_nenhum_endpoint_funciona(client):
    client.get.side_effect = Exception("erro")
    result = SafrasAPI(client).listar()
    assert result == []


def test_safras_listar_cacheia(client):
    client.get.return_value = [{"_id": "s1"}]
    api = SafrasAPI(client)
    api.listar()
    api.listar()
    assert client.get.call_count == 1


def test_safras_get_ativa(client):
    client.get.return_value = [
        {"_id": "s1", "nome": "25/26"},
        {"_id": "safra_123", "nome": "26/27"},
    ]
    result = SafrasAPI(client).get_ativa()
    assert result is not None
    assert result["nome"] == "26/27"


# ─────────────────────────────────────────────────────────────────────
# Geolocation
# ─────────────────────────────────────────────────────────────────────


def test_geolocation_extrai_lat_lng(client):
    orders_api = OrdersAPI(client)
    orders_api.list = MagicMock(return_value=[
        {"numero": "1", "geolocalizacao_entrega": {"latitude": -17.5, "longitude": -50.5},
         "cliente": {"nome": "Alice", "cpf_cnpj": "12345"}, "vendedor": {"nome": "V"},
         "cidade": "Jataí", "estado": "GO", "status": "Aprovado", "tipo_frete": "CIF"},
    ])
    result = GeolocationAPI(client, orders_api).listar_coordenadas_pedidos()
    assert len(result) == 1
    assert result[0]["lat"] == -17.5


def test_geolocation_zero_vira_none(client):
    orders_api = OrdersAPI(client)
    orders_api.list = MagicMock(return_value=[
        {"numero": "1", "geolocalizacao_entrega": {"latitude": 0, "longitude": 0},
         "cliente": {}, "vendedor": {}},
    ])
    result = GeolocationAPI(client, orders_api).listar_coordenadas_pedidos()
    assert result[0]["lat"] is None
    assert result[0]["lng"] is None


def test_geolocation_pedidos_sem_coordenadas(client):
    orders_api = OrdersAPI(client)
    orders_api.list = MagicMock(return_value=[
        {"numero": "1", "geolocalizacao_entrega": {"latitude": -17.5, "longitude": -50.5},
         "cliente": {}, "vendedor": {}},
        {"numero": "2", "geolocalizacao_entrega": {"latitude": 0, "longitude": 0},
         "cliente": {}, "vendedor": {}},
    ])
    result = GeolocationAPI(client, orders_api).pedidos_sem_coordenadas()
    assert len(result) == 1
    assert result[0]["numero"] == "2"


# ─────────────────────────────────────────────────────────────────────
# ERP
# ─────────────────────────────────────────────────────────────────────


def test_erp_classifica_senha_expirada(client):
    subtipo, sev = ErpAPI(client).classificar("Senha ERP expirada")
    assert subtipo == "SENHA_ERP_EXPIRADA"
    assert sev == "CRITICO"


def test_erp_classifica_saldo(client):
    subtipo, _ = ErpAPI(client).classificar("Saldo insuficiente no armazém 99")
    assert subtipo == "SALDO_ARMAZEM_99"


def test_erp_classifica_codigo_produto(client):
    subtipo, sev = ErpAPI(client).classificar("Cód produto não cadastrado")
    assert subtipo == "CODIGO_PRODUTO_NAO_MAPEADO"
    assert sev == "ALTO"


def test_erp_classifica_outro(client):
    subtipo, sev = ErpAPI(client).classificar("erro exotico não mapeado")
    assert subtipo == "OUTRO"
    assert sev == "MEDIO"


def test_erp_listar_classificado_enriquece(client):
    orders_api = OrdersAPI(client)
    orders_api.list_com_erro_integracao = MagicMock(return_value=[
        {"numero": "N1", "erro_erp": "Senha ERP expirada",
         "cliente": {"nome": "Alice", "cpf_cnpj": "12345"}, "vendedor": {}},
    ])
    result = ErpAPI(client, orders_api).listar_classificado()
    assert len(result) == 1
    assert result[0]["subtipo"] == "SENHA_ERP_EXPIRADA"
    assert result[0]["severidade"] == "CRITICO"
    assert result[0]["cliente"] == "Alice"
