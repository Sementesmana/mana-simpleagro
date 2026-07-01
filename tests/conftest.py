"""Fixtures compartilhadas dos testes."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def mock_session():
    """requests.Session mockado. Cada teste customiza .request.return_value."""
    session = MagicMock()
    session.headers = {}
    # cookies precisa suportar .get e .clear
    session.cookies.get = MagicMock(return_value="")
    session.cookies.clear = MagicMock()
    return session


def make_response(status: int = 200, body: dict | list | str | None = None):
    """Cria mock de requests.Response."""
    resp = MagicMock()
    resp.status_code = status
    if body is None:
        body = {}
    if isinstance(body, str):
        resp.text = body
        resp.json = MagicMock(side_effect=ValueError("not json"))
    else:
        resp.json = MagicMock(return_value=body)
        resp.text = json.dumps(body)
    resp.content = resp.text.encode("utf-8")
    resp.raise_for_status = MagicMock()
    if status >= 400:
        from requests import HTTPError
        resp.raise_for_status.side_effect = HTTPError(response=resp)
    return resp


@pytest.fixture
def resp_factory():
    return make_response


@pytest.fixture
def env_completo(monkeypatch):
    """Env vars completas do SA."""
    monkeypatch.setenv("SA_BASE_URL", "https://sa.test:3333")
    monkeypatch.setenv("SA_USERNAME", "user_test")
    monkeypatch.setenv("SA_PASSWORD", "pwd_test")
    monkeypatch.setenv("SA_SAFRA_ID", "safra_123")
    monkeypatch.setenv("SA_GRUPO_ID", "grupo_456")
