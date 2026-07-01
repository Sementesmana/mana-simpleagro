# mana-simpleagro

> **SDK oficial do Simple Agro para o ecossistema Maná.** Consolida em 1 pacote reusável o padrão de integração com o Simple Agro que estava espalhado em ~10 agentes (login OAuth AdonisJS, CRUD de Orders/Clients/Wallets/Properties, catálogos, engine de preço, geolocalização, erros ERP). SDK canônico da [Maná Builder](https://github.com/Sementesmana/plugin-mana-skills) — **Camada 2A** (clientes completos de sistemas legados).

## Por que existe

Antes do SDK, cada agente Maná que precisava falar com o Simple Agro copiava:
- Login OAuth com XSRF + cookie + Bearer
- Cache de token 50min
- Retry em 401 com relogin transparente
- Headers "que parecem browser" (senão SA retorna respostas magras)
- Fórmula de juros pt-BR (validada bit-a-bit no painel)

Isso levou a **~8.500 linhas de código SA** duplicadas em 12 arquivos ativos. Este SDK consolida tudo:

| Arquivo original | Linhas | Coberto agora por |
|---|---|---|
| `agente-pedidos/agente_simpleagro.py` | 1391 | `OrdersAPI`, `CatalogAPI`, `ClientsAPI` |
| `agente-financeiro-sa/agente_financeiro_sa.py` | 1162 | `OrdersAPI`, `CatalogAPI` (enrichment) |
| `agente-lancamento-pedido/sa_client.py` | 624 | `OrdersAPI`, `ClientsAPI`, `WalletsAPI`, `PricingAPI` |
| `agente-tms/agente_tms.py` (partes SA) | ~200 | `OrdersAPI`, `GeolocationAPI` |
| `agente-*/sa_client.py` (4 agentes) | ~1200 | Facade `SimpleAgro` completa |
| `agente-gestor-comercial/coordenadas_sa.py + erros_erp_sa.py` | 268 | `GeolocationAPI`, `ErpAPI` |

## Instalação

Distribuição por **git tag** (padrão Maná Builder):

```bash
pip install "git+https://github.com/Sementesmana/mana-simpleagro.git@v0.1.1"
```

Dependência única: `requests>=2.31`.

## Setup — env vars

```bash
SA_BASE_URL=https://sementesmana.api.simpleagro.com.br:3333
SA_USERNAME=usuario_automacao
SA_PASSWORD=senha
SA_SAFRA_ID=69a5d85cae03f50036ee2531   # ID da safra ativa (26/27)
SA_GRUPO_ID=610a8b743829fd00385c48c9   # ID grupo Semente de Soja
```

## Uso típico — facade `SimpleAgro`

```python
from mana_simpleagro import SimpleAgro

sa = SimpleAgro()  # lê env vars automaticamente
sa.login()          # opcional — cada request faz login on-demand

# Leitura de pedidos
pedidos = sa.orders.list()                          # todos da safra ativa
pedidos_cliente = sa.orders.list_por_cnpj("12.345.678/0001-99")
pedidos_erro = sa.orders.list_com_erro_integracao()

# Clientes
cliente = sa.clients.buscar(cpf_cnpj="12345678000199")[0]
propriedades = sa.clients.listar_propriedades(cliente["_id"])

# Vendedor do cliente (via carteira)
vendedores = sa.wallets.do_cliente(cliente["_id"])

# Catálogo + preço com juros
produto = sa.catalog.obter_produto("O790IPRO")
dados = sa.pricing.dados_produto("O790IPRO", tabela_id, "2026-08-30")
print(dados["preco_item_tabela"])   # royalties + germoplasma com juros

# Geolocalização
sem_geoloc = sa.geolocation.pedidos_sem_coordenadas()

# ERP
erros_classificados = sa.erp.listar_classificado()
for e in erros_classificados:
    print(e["subtipo"], e["severidade"], e["cliente"])
```

## Uso avançado — instâncias diretas dos APIs

```python
from mana_simpleagro import SimpleAgroClient, OrdersAPI, ClientsAPI

client = SimpleAgroClient()   # lê env
orders = OrdersAPI(client)
clients = ClientsAPI(client)

# Reusa a mesma session (login compartilhado)
orders.list()
clients.buscar_por_cpf_cnpj("...")
```

## Escrita: criar pedido completo

```python
pid, numero = sa.orders.criar_pedido(
    cabecalho={
        "filial": {"id": filial_id},
        "safra": {"id": sa.client.safra_id},
        "cliente": {"id": cliente_id, "nome": nome},
        "vendedor": {"id": vendedor_id, "nome": vendedor_nome},
        "propriedade": {"id": propriedade_id},
        "tipo_frete": "CIF",
        "tabela_preco_base": {"id": tabela_id},
        # ... outros campos
    },
    itens=[{
        "produto": {"id": produto_id, "nome": "O790IPRO"},
        "grupo_produto": {"id": sa.client.grupo_id},
        # ... preços em string pt-BR
    }],
    parcelas=[{
        "data_vencimento": "2026-08-30",
        "valor": "5000,00",
    }],
    observacao="Lançado via WhatsApp por Alice",
)
print(f"Pedido {numero} ({pid}) submetido pra aprovação")
```

## Módulos disponíveis

| API | Cobertura |
|---|---|
| `orders` (OrdersAPI) | list, get, list_por_cnpj, list_com_erro_integracao, criar_pedido, criar_cabecalho, adicionar_item, atualizar_item, atualizar_payment, mudar_status, finalizar, cancelar, reabrir |
| `clients` (ClientsAPI) | buscar (CPF/nome), buscar_por_cpf_cnpj, buscar_por_nome (com retry palavras), get, criar (multipart), listar_propriedades, criar_propriedade |
| `wallets` (WalletsAPI) | listar, get, get_consultant, do_vendedor, do_cliente, adicionar_cliente (idempotente) |
| `catalog` (CatalogAPI) | grupo_produto, produtos_do_grupo, obter_produto (fuzzy match), listar_produtos_nomes, tabelas_preco, tabela_detalhe, produtos_da_tabela, tratamentos_tsi, tsi_ref, descricoes, formas_pagamento, tipos_venda, tipos_garantia, usos_semente |
| `pricing` (PricingAPI) | fator_juros, dados_produto (com juros no vencimento) |
| `companies` (CompaniesAPI) | filial_faturamento (cacheada), listar |
| `safras` (SafrasAPI) | listar (com fallback multi-endpoint), get_ativa |
| `geolocation` (GeolocationAPI) | listar_coordenadas_pedidos, pedidos_sem_coordenadas |
| `erp` (ErpAPI) | listar_com_erro, classificar (6 subtipos por regex), listar_classificado |

## Padrões que o SDK resolve

### Login OAuth AdonisJS
- Puxa XSRF-TOKEN via GET `/sales/login` no painel
- POST `/api/auth/login` com Origin/Referer/User-Agent do painel
- Aceita token em `token`, `accessToken`, `access_token`, `data.token`
- Adiciona `Bearer` se não vier
- Cache 50min (JWT expira em 60min)
- **Relogin transparente em 401** — retry uma vez

### Formato pt-BR
SA envia/recebe valores como STRING em formato pt-BR: `"1.234,56"`.
Helpers `fmt_ptbr(1234.56)` e `parse_ptbr("1.234,56")` convertem.

### Engine de preço com juros
Fórmula validada bit-a-bit no painel:
```
preço(venc) = preço_base × (1 + taxa/100) ^ (dias(data_base→venc) / 30)
```
`PricingAPI.dados_produto("O790IPRO", tabela_id, venc)` já aplica.

### Erros ERP classificados
Regex sobre `erro_erp` classifica em 6 subtipos:
- `SENHA_ERP_EXPIRADA` (CRITICO)
- `SALDO_ARMAZEM_99` (MEDIO)
- `CODIGO_PRODUTO_NAO_MAPEADO` (ALTO)
- `CLIENTE_SEM_CODREF` (MEDIO)
- `PROPRIEDADE_SEM_CODREF` (MEDIO)
- `ERRO_PYTHON` (MEDIO)
- `OUTRO` (MEDIO)

### Retry inteligente em busca por nome
`ClientsAPI.buscar_por_nome("Fazenda Guimarães")` — se 0 resultados, retenta com palavras mais distintivas (útil pra transcrição de áudio com acento/erros).

### Fuzzy match de produto
`CatalogAPI.obter_produto("NEO 790 IPRO")` casa com `"O790IPRO"` no catálogo (normalização + match parcial).

## Exceções

Todas herdam de `SimpleAgroError`:

| Exception | Quando |
|---|---|
| `ConfigError` | env var faltando ou config inválida |
| `LoginError` | falha no login (401 no auth, sem token, network) |
| `UnauthorizedError` | 401 mesmo após relogin |
| `NotFoundError` | 404 (recurso não existe) |
| `ValidationError` | 400 (SA rejeitou payload — CPF inválido, campos faltando) |
| `NetworkError` | timeout, DNS, connection reset |
| `ServerError` | 5xx |

## LGPD

Este SDK **trafega PII**: CPF/CNPJ, nome, telefone, endereço.

Consumidor decide se **pseudonimiza** antes de mandar pro LLM. Use [`mana-habilidade-pseudonimizar-pii`](https://github.com/Sementesmana/mana-habilidade-pseudonimizar-pii).

## Estado

**v0.1.1** (2026-06-30) — primeira release oficial como SDK (rename de mana-habilidade-simpleagro).

- ✅ 14 módulos, 817 statements
- ✅ **116 testes pytest, 82% cobertura**
- ✅ Login OAuth + auto-relogin
- ✅ CRUD completo Orders/Clients/Wallets/Properties
- ✅ Catálogos + engine de preço
- ✅ Geoloc + ERP classificado
- ⏳ **`alpha`** — pendente migração de 1º consumidor pra cumprir gate consumidor real

**Roadmap pro gate:**
1. Migrar `agente-financeiro-sa` (mais isolado) → `beta`
2. Migrar `agente-pedidos` (mais grande) → `producao`
3. Migração progressiva dos outros 6 agentes

## Dono

Xayer (@xayer-mana, Sementes Maná LTDA). Mudanças via PR (semver: PATCH=fix, MINOR=compatível, MAJOR=breaking + ADR).
