"""Testes de ClientsAPI (buscar, criar, propriedades)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from mana_simpleagro import ClientsAPI, ValidationError
from mana_simpleagro.client import SimpleAgroClient


@pytest.fixture
def client(env_completo):
    c = SimpleAgroClient()
    c.get = MagicMock()
    c.post = MagicMock()
    c.put = MagicMock()
    return c


def test_buscar_por_cpf_cnpj_normaliza_e_usa_regex(client):
    client.get.return_value = {"docs": [{"_id": "c1", "nome": "Alice"}]}
    result = ClientsAPI(client).buscar_por_cpf_cnpj("12.345.678/0001-99")
    assert len(result) == 1
    params = client.get.call_args.kwargs["params"]
    assert params["cpf_cnpj"] == "/12345678000199/"


def test_buscar_por_nome_regex_case_insensitive(client):
    client.get.return_value = {"docs": [{"_id": "c1"}]}
    ClientsAPI(client).buscar_por_nome("Fazenda Boa Vista")
    params = client.get.call_args.kwargs["params"]
    assert "/i" in params["nome"]   # case insensitive


def test_buscar_por_nome_zero_resultados_retry_palavras(client):
    """Se busca principal deu 0, tenta com palavras significativas."""
    client.get.side_effect = [
        {"docs": []},                       # busca original: vazia
        {"docs": [{"_id": "c1"}]},          # retry palavra 1
        {"docs": []},                       # retry palavra 2 (dedup)
    ]
    result = ClientsAPI(client).buscar_por_nome("Fazenda Guimaraes")
    assert len(result) == 1
    assert client.get.call_count >= 2


def test_buscar_por_nome_vazio_retorna_lista_vazia(client):
    assert ClientsAPI(client).buscar_por_nome("") == []
    client.get.assert_not_called()


def test_buscar_por_nome_sem_retry_quando_desativado(client):
    client.get.return_value = {"docs": []}
    ClientsAPI(client).buscar_por_nome("Fazenda Boa", retry_palavras=False)
    assert client.get.call_count == 1


def test_buscar_inteligente_prioriza_cpf(client):
    client.get.return_value = {"docs": [{"_id": "c1"}]}
    ClientsAPI(client).buscar(cpf_cnpj="123", nome="Foo")
    # Foi só 1 chamada (por CPF)
    assert client.get.call_count == 1
    assert "cpf_cnpj" in client.get.call_args.kwargs["params"]


def test_buscar_inteligente_sem_criterio_retorna_vazio(client):
    assert ClientsAPI(client).buscar() == []


def test_criar_cliente_ok(client):
    client.post.return_value = {"_id": "c_novo", "nome": "Novo"}
    result = ClientsAPI(client).criar(
        nome="Fazenda Nova",
        cpf_cnpj="12345678000199",
        email="a@b.com",
        tel_cel="(64) 99999-0000",
    )
    assert result["_id"] == "c_novo"
    # Verifica que enviou multipart
    files = client.post.call_args.kwargs["files"]
    assert files["nome"][1] == "Fazenda Nova"
    assert files["tel_cel"][1] == "64999990000"   # so_digitos


def test_criar_cliente_400_extrai_msg_amigavel(client):
    client.post.side_effect = ValidationError(
        '400 em /api/clients: {"error":{"cpf_cnpj":{"message":"CPF inválido"}}}'
    )
    with pytest.raises(ValidationError, match="CPF inválido"):
        ClientsAPI(client).criar(nome="X", cpf_cnpj="000")


def test_listar_propriedades_via_endpoint_dedicado(client):
    client.get.return_value = {
        "docs": [{
            "_id": "p1", "nome": "Fazenda 1", "cidade": "Rio Verde",
            "estado": "GO", "latitude": -17.7, "longitude": -50.9,
        }]
    }
    result = ClientsAPI(client).listar_propriedades("c1")
    assert len(result) == 1
    assert result[0]["nome"] == "Fazenda 1"


def test_listar_propriedades_ignora_deletadas(client):
    client.get.return_value = {"docs": [
        {"_id": "p1", "nome": "Ativa"},
        {"_id": "p2", "nome": "Deletada", "deleted": True},
    ]}
    result = ClientsAPI(client).listar_propriedades("c1")
    assert len(result) == 1


def test_criar_propriedade_sem_geoloc(client):
    client.post.return_value = {"_id": "p_novo"}
    result = ClientsAPI(client).criar_propriedade(
        cliente_id="c1",
        nome="Nova",
        area=500,
        cidade="Jataí",
        estado="GO",
    )
    assert result["_id"] == "p_novo"
    body = client.post.call_args.kwargs["json"]
    assert body["nome"] == "Nova"
    assert "latitude" not in body   # não passou lat/lng


def test_criar_propriedade_com_geoloc(client):
    client.post.return_value = {"_id": "p_novo"}
    ClientsAPI(client).criar_propriedade(
        cliente_id="c1", nome="X", latitude=-17.5, longitude=-50.5,
    )
    body = client.post.call_args.kwargs["json"]
    assert body["latitude"] == -17.5
    assert body["longitude"] == -50.5


def test_criar_propriedade_ie_default_quando_vazio(client):
    client.post.return_value = {"_id": "p"}
    ClientsAPI(client).criar_propriedade(cliente_id="c1", nome="X")
    body = client.post.call_args.kwargs["json"]
    assert body["ie"] == "00000000000"
