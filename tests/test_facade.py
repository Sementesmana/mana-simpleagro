"""Testa a facade SimpleAgro e imports públicos."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


def test_import_facade():
    from mana_simpleagro import SimpleAgro
    assert SimpleAgro is not None


def test_facade_instancia_todos_apis(env_completo):
    from mana_simpleagro import SimpleAgro
    sa = SimpleAgro()
    assert sa.orders is not None
    assert sa.clients is not None
    assert sa.wallets is not None
    assert sa.catalog is not None
    assert sa.pricing is not None
    assert sa.companies is not None
    assert sa.safras is not None
    assert sa.geolocation is not None
    assert sa.erp is not None


def test_facade_compartilha_client(env_completo):
    """Todas as APIs devem apontar pro mesmo SimpleAgroClient."""
    from mana_simpleagro import SimpleAgro
    sa = SimpleAgro()
    assert sa.orders.client is sa.client
    assert sa.clients.client is sa.client
    assert sa.wallets.client is sa.client


def test_facade_sobrescreve_env_com_args(env_completo):
    from mana_simpleagro import SimpleAgro
    sa = SimpleAgro(safra_id="outra_safra", grupo_id="outro_grupo")
    assert sa.client.safra_id == "outra_safra"
    assert sa.client.grupo_id == "outro_grupo"


def test_import_helpers_publicos():
    from mana_simpleagro import (
        so_digitos, normalizar_cnpj, normalizar_produto,
        fmt_ptbr, parse_ptbr, parse_coord,
        extract_name, extract_str, sem_acento, fmt_data_br,
    )
    assert so_digitos("1.2.3") == "123"


def test_import_exceptions_publicas():
    from mana_simpleagro import (
        SimpleAgroError, ConfigError, LoginError,
        UnauthorizedError, NotFoundError, ValidationError,
        NetworkError, ServerError,
    )
    # Hierarquia: todas herdam de SimpleAgroError
    assert issubclass(LoginError, SimpleAgroError)
    assert issubclass(NotFoundError, SimpleAgroError)


def test_version_publica():
    from mana_simpleagro import __version__
    assert __version__ == "0.1.1"
