"""
mana-simpleagro — SDK oficial do Simple Agro para o ecossistema Maná.

Consolida em 1 pacote reutilizável o padrão que estava copiado em ~10 agentes:
    - Login OAuth AdonisJS + XSRF + cache token 50min
    - Auto-relogin em 401
    - CRUD de Orders, Clients, Wallets, Properties
    - Catálogos (Product Groups, Price Tables, TSI, tipos de venda/garantia/pagamento)
    - Engine de preço com juros no vencimento (fórmula validada bit-a-bit)
    - Filiais (Companies), Safras (Seasons)
    - Geolocalização + Erros de integração ERP com classificação

Habilidade canônica da Maná Builder, sub-categoria emergente "dados/sdk".

USO TÍPICO

  # Config via env vars (recomendado):
  #   SA_BASE_URL, SA_USERNAME, SA_PASSWORD, SA_SAFRA_ID, SA_GRUPO_ID
  >>> from mana_simpleagro import SimpleAgro
  >>> sa = SimpleAgro()
  >>> sa.login()

  # Leitura de pedidos
  >>> pedidos = sa.orders.list()
  >>> pedidos_do_cliente = sa.orders.list_por_cnpj("12345678000199")
  >>> pedidos_com_erro = sa.orders.list_com_erro_integracao()

  # Escrita de pedido
  >>> order_id, numero = sa.orders.criar_pedido(cabecalho, itens, parcelas)
  >>> sa.orders.cancelar(order_id, motivo="cliente desistiu")

  # Clientes
  >>> cliente = sa.clients.buscar(cpf_cnpj="12345678000199")[0]
  >>> propriedades = sa.clients.listar_propriedades(cliente["_id"])

  # Carteiras / Vendedor
  >>> vendedores = sa.wallets.do_cliente(cliente["_id"])

  # Catálogo + preço
  >>> produto = sa.catalog.obter_produto("O790IPRO")
  >>> dados = sa.pricing.dados_produto("O790IPRO", tabela_id, "2026-08-30")

  # Geoloc / ERP
  >>> pedidos_sem_geoloc = sa.geolocation.pedidos_sem_coordenadas()
  >>> erros_classificados = sa.erp.listar_classificado()

USO AVANÇADO — instâncias diretas dos APIs

  >>> from mana_simpleagro import SimpleAgroClient, OrdersAPI
  >>> client = SimpleAgroClient()  # lê env
  >>> orders = OrdersAPI(client)
  >>> orders.list()
"""

from __future__ import annotations

__version__ = "0.1.1"

# ── Exceções ────────────────────────────────────────────────────────
from .exceptions import (
    ConfigError,
    LoginError,
    NetworkError,
    NotFoundError,
    ServerError,
    SimpleAgroError,
    UnauthorizedError,
    ValidationError,
)

# ── Helpers públicos ────────────────────────────────────────────────
from .helpers import (
    extract_name,
    extract_str,
    fmt_data_br,
    fmt_ptbr,
    normalizar_cnpj,
    normalizar_produto,
    parse_coord,
    parse_ptbr,
    sem_acento,
    so_digitos,
)

# ── Auth + Client base ──────────────────────────────────────────────
from .auth import SimpleAgroAuth
from .client import SimpleAgroClient

# ── APIs modulares ──────────────────────────────────────────────────
from .catalog import CatalogAPI
from .clients import ClientsAPI
from .companies import CompaniesAPI
from .erp import ErpAPI
from .geolocation import GeolocationAPI
from .orders import OrdersAPI
from .pricing import PricingAPI
from .safras import SafrasAPI
from .wallets import WalletsAPI


# ── Facade principal (agrega tudo) ──────────────────────────────────


class SimpleAgro:
    """Facade principal — instancia um cliente + todos os APIs em cima dele.

    Args:
        base_url, username, password: default lê env (SA_BASE_URL, SA_USERNAME,
                                       SA_PASSWORD). Passe explícito pra sobrescrever.
        safra_id, grupo_id: contexto default de safra/grupo pra filtros.
        timeout: HTTP timeout default em segundos.
        session: requests.Session opcional pra reuso.

    Uso:
        >>> sa = SimpleAgro()
        >>> sa.login()
        >>> sa.orders.list()
    """

    def __init__(
        self,
        base_url: str | None = None,
        username: str | None = None,
        password: str | None = None,
        safra_id: str | None = None,
        grupo_id: str | None = None,
        timeout: int = 30,
        session=None,
    ) -> None:
        self.client = SimpleAgroClient(
            base_url=base_url,
            username=username,
            password=password,
            timeout=timeout,
            session=session,
            safra_id=safra_id,
            grupo_id=grupo_id,
        )
        # APIs modulares — todas compartilham o mesmo client
        self.orders = OrdersAPI(self.client)
        self.clients = ClientsAPI(self.client)
        self.wallets = WalletsAPI(self.client)
        self.catalog = CatalogAPI(self.client)
        self.pricing = PricingAPI(self.client, self.catalog)
        self.companies = CompaniesAPI(self.client)
        self.safras = SafrasAPI(self.client)
        self.geolocation = GeolocationAPI(self.client, self.orders)
        self.erp = ErpAPI(self.client, self.orders)

    def login(self) -> str:
        """Login on-demand (não é obrigatório — cada request chama login sozinho)."""
        return self.client.login()

    def health(self) -> bool:
        """Health check: True se consegue autenticar + fazer GET simples."""
        return self.client.health()

    def is_authenticated(self) -> bool:
        return self.client.is_authenticated()


__all__ = [
    # Facade principal
    "SimpleAgro",
    # Client + Auth
    "SimpleAgroClient",
    "SimpleAgroAuth",
    # APIs modulares
    "OrdersAPI",
    "ClientsAPI",
    "WalletsAPI",
    "CatalogAPI",
    "PricingAPI",
    "CompaniesAPI",
    "SafrasAPI",
    "GeolocationAPI",
    "ErpAPI",
    # Exceptions
    "SimpleAgroError",
    "ConfigError",
    "LoginError",
    "UnauthorizedError",
    "NotFoundError",
    "ValidationError",
    "NetworkError",
    "ServerError",
    # Helpers
    "so_digitos",
    "normalizar_cnpj",
    "normalizar_produto",
    "fmt_ptbr",
    "parse_ptbr",
    "parse_coord",
    "extract_name",
    "extract_str",
    "sem_acento",
    "fmt_data_br",
]
