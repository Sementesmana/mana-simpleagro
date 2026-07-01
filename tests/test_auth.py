"""Testes de auth (login + XSRF + cache token)."""

from __future__ import annotations

import time

import pytest

from mana_simpleagro import ConfigError, LoginError, SimpleAgroAuth


class _FakeSession:
    """Session fake pra testar SimpleAgroAuth sem monkeypatchar requests."""

    def __init__(self, get_returns=None, post_returns=None):
        self.headers = {}
        self._get_returns = get_returns or []
        self._post_returns = post_returns or []
        self._get_i = 0
        self._post_i = 0
        # cookies suporta .get e .clear
        self.cookies = _FakeCookies()

    def get(self, url, timeout=None):
        if self._get_i < len(self._get_returns):
            r = self._get_returns[self._get_i]
            self._get_i += 1
            return r
        return _FakeResp(200, {})

    def post(self, url, json=None, timeout=None):
        if self._post_i < len(self._post_returns):
            r = self._post_returns[self._post_i]
            self._post_i += 1
            return r
        return _FakeResp(200, {})


class _FakeCookies:
    def __init__(self):
        self._store = {}

    def get(self, key, default=""):
        return self._store.get(key, default)

    def clear(self):
        self._store.clear()

    def set(self, key, val):
        self._store[key] = val


class _FakeResp:
    def __init__(self, status, body):
        self.status_code = status
        self._body = body
        self.text = str(body)
        self.content = self.text.encode()

    def json(self):
        return self._body


def test_config_error_sem_username():
    with pytest.raises(ConfigError):
        SimpleAgroAuth(base_url="https://x", username="", password="p")


def test_config_error_sem_password():
    with pytest.raises(ConfigError):
        SimpleAgroAuth(base_url="https://x", username="u", password="")


def test_config_error_sem_base_url():
    with pytest.raises(ConfigError):
        SimpleAgroAuth(base_url="", username="u", password="p")


def test_login_sucesso_grava_token_em_session():
    login_resp = _FakeResp(200, {"token": "abc123"})
    session = _FakeSession(post_returns=[login_resp])
    auth = SimpleAgroAuth(
        base_url="https://sa.test:3333",
        username="u",
        password="p",
        session=session,
    )
    token = auth.get_token()
    assert token == "Bearer abc123"
    assert session.headers["Authorization"] == "Bearer abc123"


def test_login_token_ja_com_prefixo_bearer_nao_duplica():
    login_resp = _FakeResp(200, {"token": "Bearer XYZ"})
    session = _FakeSession(post_returns=[login_resp])
    auth = SimpleAgroAuth(
        base_url="https://sa.test:3333", username="u", password="p", session=session,
    )
    assert auth.get_token() == "Bearer XYZ"


def test_login_multiplas_chaves_de_token():
    """SA às vezes retorna em 'accessToken', 'access_token', ou 'data.token'."""
    for key_body in [
        {"accessToken": "T1"},
        {"access_token": "T2"},
        {"data": {"token": "T3"}},
    ]:
        session = _FakeSession(post_returns=[_FakeResp(200, key_body)])
        auth = SimpleAgroAuth(
            base_url="https://sa.test:3333", username="u", password="p", session=session,
        )
        token = auth.get_token()
        assert token.startswith("Bearer T")


def test_login_sem_token_na_resposta_levanta():
    login_resp = _FakeResp(200, {"outra_coisa": "x"})
    session = _FakeSession(post_returns=[login_resp])
    auth = SimpleAgroAuth(
        base_url="https://sa.test:3333", username="u", password="p", session=session,
    )
    with pytest.raises(LoginError, match="sem token"):
        auth.get_token()


def test_login_http_erro_levanta_login_error():
    login_resp = _FakeResp(401, {"error": "invalid"})
    session = _FakeSession(post_returns=[login_resp])
    auth = SimpleAgroAuth(
        base_url="https://sa.test:3333", username="u", password="p", session=session,
    )
    with pytest.raises(LoginError, match="HTTP 401"):
        auth.get_token()


def test_cache_token_evita_relogin():
    login_resp = _FakeResp(200, {"token": "T"})
    session = _FakeSession(post_returns=[login_resp, _FakeResp(500, {})])
    auth = SimpleAgroAuth(
        base_url="https://sa.test:3333", username="u", password="p", session=session,
    )
    t1 = auth.get_token()
    t2 = auth.get_token()  # não deve chamar login de novo (cache)
    assert t1 == t2
    assert session._post_i == 1


def test_invalidate_forca_relogin():
    login_resp1 = _FakeResp(200, {"token": "T1"})
    login_resp2 = _FakeResp(200, {"token": "T2"})
    session = _FakeSession(post_returns=[login_resp1, login_resp2])
    auth = SimpleAgroAuth(
        base_url="https://sa.test:3333", username="u", password="p", session=session,
    )
    assert auth.get_token() == "Bearer T1"
    auth.invalidate()
    assert auth.get_token() == "Bearer T2"


def test_force_relogin_sempre_chama_login():
    login_resp1 = _FakeResp(200, {"token": "T1"})
    login_resp2 = _FakeResp(200, {"token": "T2"})
    session = _FakeSession(post_returns=[login_resp1, login_resp2])
    auth = SimpleAgroAuth(
        base_url="https://sa.test:3333", username="u", password="p", session=session,
    )
    assert auth.get_token() == "Bearer T1"
    assert auth.get_token(force_relogin=True) == "Bearer T2"


def test_is_authenticated_false_antes_do_login():
    session = _FakeSession(post_returns=[_FakeResp(200, {"token": "T"})])
    auth = SimpleAgroAuth(
        base_url="https://sa.test:3333", username="u", password="p", session=session,
    )
    assert not auth.is_authenticated()
    auth.get_token()
    assert auth.is_authenticated()


def test_ttl_configuravel_expira_token():
    session = _FakeSession(post_returns=[
        _FakeResp(200, {"token": "T1"}),
        _FakeResp(200, {"token": "T2"}),
    ])
    auth = SimpleAgroAuth(
        base_url="https://sa.test:3333",
        username="u",
        password="p",
        session=session,
        token_ttl=0,   # expira imediatamente
    )
    auth.get_token()
    time.sleep(0.01)
    # Segundo get_token deve fazer relogin
    t2 = auth.get_token()
    assert t2 == "Bearer T2"
