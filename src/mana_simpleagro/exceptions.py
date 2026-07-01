"""Exceptions do SDK Simple Agro."""

from __future__ import annotations


class SimpleAgroError(Exception):
    """Base — qualquer erro do SDK Simple Agro."""


class ConfigError(SimpleAgroError):
    """Env var faltando ou config inválida."""


class LoginError(SimpleAgroError):
    """Falha no login (credenciais inválidas, XSRF, sem token na resposta)."""


class UnauthorizedError(SimpleAgroError):
    """401 mesmo após relogin."""


class NotFoundError(SimpleAgroError):
    """Recurso não encontrado (cliente sem CPF, produto não catalogado, etc)."""


class ValidationError(SimpleAgroError):
    """SA rejeitou o payload (HTTP 400 com mensagem de negócio)."""


class NetworkError(SimpleAgroError):
    """Timeout, DNS, connection reset."""


class ServerError(SimpleAgroError):
    """HTTP 5xx do SA."""
