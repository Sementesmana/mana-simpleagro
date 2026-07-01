"""Testes do SimpleAgroClient (request + auto-relogin em 401)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from mana_simpleagro import (
    NetworkError,
    NotFoundError,
    ServerError,
    UnauthorizedError,
    ValidationError,
)
from mana_simpleagro.client import SimpleAgroClient


def _resp(status, body=None):
    r = MagicMock()
    r.status_code = status
    r.json.return_value = body or {}
    r.text = str(body)
    r.content = str(body).encode()
    return r


@pytest.fixture
def client(env_completo):
    """SimpleAgroClient com env vars mockadas + auth mockado."""
    c = SimpleAgroClient()
    # Mock auth pra não fazer login real
    c.auth.get_token = MagicMock(return_value="Bearer FAKE")
    c.auth.invalidate = MagicMock()
    c.auth.is_authenticated = MagicMock(return_value=True)
    # Mock session
    c.session = MagicMock()
    return c


def test_get_ok_retorna_json(client):
    client.session.request.return_value = _resp(200, {"foo": "bar"})
    assert client.get("/api/x") == {"foo": "bar"}


def test_post_com_json(client):
    client.session.request.return_value = _resp(200, {"created": True})
    result = client.post("/api/x", json={"a": 1})
    assert result == {"created": True}
    # Confirma que method+json foram passados
    call = client.session.request.call_args
    assert call.kwargs["method"] == "POST"
    assert call.kwargs["json"] == {"a": 1}


def test_401_dispara_relogin_uma_vez(client):
    """401 → relogin → retry. Se retry deu 200, retorna."""
    client.session.request.side_effect = [
        _resp(401, {"error": "expired"}),
        _resp(200, {"ok": True}),
    ]
    result = client.get("/api/x")
    assert result == {"ok": True}
    assert client.auth.invalidate.call_count == 1


def test_401_persistente_apos_relogin_levanta(client):
    client.session.request.side_effect = [
        _resp(401, {"error": "e1"}),
        _resp(401, {"error": "e2"}),   # relogin não resolveu
    ]
    with pytest.raises(UnauthorizedError):
        client.get("/api/x")


def test_404_levanta_not_found(client):
    client.session.request.return_value = _resp(404, {})
    with pytest.raises(NotFoundError):
        client.get("/api/inexistente")


def test_400_levanta_validation_error(client):
    client.session.request.return_value = _resp(400, {"error": "bad"})
    with pytest.raises(ValidationError):
        client.post("/api/x", json={})


def test_500_levanta_server_error(client):
    client.session.request.return_value = _resp(500, {})
    with pytest.raises(ServerError):
        client.get("/api/x")


def test_network_error_levanta_network_error(client):
    import requests
    client.session.request.side_effect = requests.ConnectionError("DNS fail")
    with pytest.raises(NetworkError):
        client.get("/api/x")


def test_health_true_se_get_clients_ok(client):
    client.session.request.return_value = _resp(200, {"docs": []})
    assert client.health() is True


def test_health_false_se_erro(client):
    import requests
    client.session.request.side_effect = requests.ConnectionError("x")
    assert client.health() is False
