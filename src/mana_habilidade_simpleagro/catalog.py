"""Catálogos do Simple Agro: grupos de produto, tabelas de preço, TSI, descrições.

Endpoints:
    GET  /api/productgroups/{id}                    — grupo de produto (com variedades)
    GET  /api/productgroups                         — todos os grupos
    GET  /api/price-table?safra.id=X                — tabelas de preço vigentes
    GET  /api/price-table.mobile?filter={"_id":...} — 1 tabela COM produtos (preços base)
    GET  /api/feature-table-prices?safra.id=X       — TSI (tratamento de sementes)
    GET  /api/types-of-warranty                     — descrições (garantia, forma pgto, etc)
    GET  /api/types-of-sale
    GET  /api/form-of-payment
    GET  /api/seed-use

Todos os catálogos suportam cache (idempotente durante a vida da instância).
"""

from __future__ import annotations

import logging
from typing import Any

from .client import SimpleAgroClient
from .exceptions import NotFoundError
from .helpers import normalizar_produto

log = logging.getLogger("mana-habilidade-simpleagro.catalog")


class CatalogAPI:
    """API de catálogos com cache.

    Args:
        client: SimpleAgroClient (usa safra_id / grupo_id do client como defaults).
    """

    def __init__(self, client: SimpleAgroClient) -> None:
        self.client = client
        self._cache: dict[str, Any] = {}   # cache genérico por chave

    def clear_cache(self) -> None:
        """Limpa cache de catálogos (útil se safra mudar)."""
        self._cache.clear()

    # ── Grupos de produto ───────────────────────────────────────────

    def grupo_produto(self, grupo_id: str | None = None) -> dict[str, Any]:
        """GET /api/productgroups/{id} — grupo com produtos/variações.

        Retorna o doc raw. Use `produtos_do_grupo` pra indexado por nome.
        """
        gid = grupo_id or self.client.grupo_id
        if not gid:
            raise NotFoundError("grupo_id não configurado")
        key = f"grupo:{gid}"
        if key not in self._cache:
            self._cache[key] = self.client.get(f"/api/productgroups/{gid}", timeout=60)
        return self._cache[key]

    def produtos_do_grupo(
        self, grupo_id: str | None = None
    ) -> tuple[dict[str, dict], dict[str, dict]]:
        """Indexa produtos do grupo por nome (upper) e por id.

        Returns:
            (by_name, by_id) — dois dicts com dicts crus dos produtos.
        """
        gid = grupo_id or self.client.grupo_id
        by_name: dict[str, dict] = {}
        by_id: dict[str, dict] = {}
        try:
            data = self.grupo_produto(gid)
            itens = (
                data.get("produtos")
                or data.get("variacoes")
                or data.get("products")
                or data.get("itens")
                or []
            )
            for p in itens:
                if not isinstance(p, dict):
                    continue
                nome = normalizar_produto(p.get("nome"))
                pid = str(p.get("_id") or p.get("id") or "")
                if nome:
                    by_name[nome] = p
                if pid:
                    by_id[pid] = p
                for sub in ("variacoes", "variações", "produtos", "products", "items"):
                    for v in (p.get(sub) or []):
                        if isinstance(v, dict):
                            vid = str(v.get("_id") or v.get("id") or "")
                            if vid and vid not in by_id:
                                by_id[vid] = v
            log.info("catálogo: %d por nome, %d por id", len(by_name), len(by_id))
        except Exception as e:
            log.warning("carregar produtos_do_grupo falhou: %s", e)
        return by_name, by_id

    def obter_produto(
        self, nome_produto: str, grupo_id: str | None = None
    ) -> dict[str, Any] | None:
        """Resolve produto pelo nome (com match parcial fuzzy).

        Retorna: {"produto": {id, nome}, "grupo_produto": {id, nome}} ou None.
        """
        by_name, _ = self.produtos_do_grupo(grupo_id)
        if not by_name:
            return None
        chave = normalizar_produto(nome_produto)
        p = by_name.get(chave)
        if not p:
            # Match parcial (áudio: "NEO 790 IPRO" vs "O790IPRO")
            cands = [v for k, v in by_name.items() if chave in k or k in chave]
            p = cands[0] if len(cands) == 1 else None
        if not p:
            return None
        grupo = self.grupo_produto(grupo_id or self.client.grupo_id)
        return {
            "produto": {"id": p.get("_id") or p.get("id"), "nome": p.get("nome")},
            "grupo_produto": {"id": grupo.get("_id"), "nome": grupo.get("nome", "")},
        }

    def listar_produtos_nomes(self, grupo_id: str | None = None) -> list[str]:
        """Lista de nomes de produtos do grupo — pra menu numerado no WhatsApp."""
        by_name, _ = self.produtos_do_grupo(grupo_id)
        return sorted(p.get("nome", "") for p in by_name.values())

    # ── Tabelas de preço ────────────────────────────────────────────

    def tabelas_preco(self, safra_id: str | None = None) -> list[dict[str, Any]]:
        """Tabelas de preço base vigentes da safra: [{id, nome, versao}]."""
        sid = safra_id or self.client.safra_id
        key = f"tabelas:{sid}"
        if key in self._cache:
            return self._cache[key]
        params = {
            "limit": "-1",
            "safra.id": sid,
            "filter": '{"$or":[{"status":true}]}',
            "fields": "nome,versao",
        }
        data = self.client.get("/api/price-table", params=params)
        docs = data.get("docs") if isinstance(data, dict) else []
        out = [
            {"id": d["_id"], "nome": d.get("nome", ""), "versao": d.get("versao", "")}
            for d in docs
        ]
        self._cache[key] = out
        return out

    def tabela_detalhe(
        self, tabela_id: str, safra_id: str | None = None
    ) -> dict[str, Any]:
        """Doc da tabela COM produtos (preços base). Cache por id.

        SA tem lazy loading — se resposta vier sem 'produtos', retry sem 'fields'.
        """
        key = f"tabela:{tabela_id}"
        if key in self._cache:
            return self._cache[key]
        sid = safra_id or self.client.safra_id
        filtro = '{"_id":"oid(\'%s\')"}' % tabela_id

        def _buscar(fields: str | None) -> dict | None:
            params: dict[str, Any] = {
                "limit": "-1",
                "safra.id": sid,
                "filter": filtro,
            }
            if fields:
                params["fields"] = fields
            data = self.client.get("/api/price-table.mobile", params=params)
            docs = data.get("docs") if isinstance(data, dict) else []
            return docs[0] if docs else None

        doc = _buscar("-estados")
        if doc is not None and not doc.get("produtos"):
            log.warning(
                "tabela %s SEM produtos — retry sem fields", tabela_id
            )
            doc = _buscar(None)
        if doc is None:
            raise NotFoundError(f"tabela de preço {tabela_id} não encontrada")
        if not doc.get("produtos"):
            raise NotFoundError(
                f"tabela {doc.get('nome')} retornada sem produtos"
            )
        self._cache[key] = doc
        return doc

    def produtos_da_tabela(
        self, tabela_id: str, safra_id: str | None = None
    ) -> list[str]:
        """Variedades disponíveis NA TABELA (nomes, sorted)."""
        doc = self.tabela_detalhe(tabela_id, safra_id)
        return sorted(
            p.get("nome", "") for p in doc.get("produtos", [])
            if not p.get("deleted") and p.get("nome")
        )

    # ── TSI (Tratamento de Sementes) ────────────────────────────────

    def tratamentos_tsi(
        self, safra_id: str | None = None
    ) -> list[dict[str, Any]]:
        """Opções de TSI da safra: [{value, label, valor}]."""
        sid = safra_id or self.client.safra_id
        key = f"tsi:{sid}"
        if key in self._cache:
            return self._cache[key]
        params = {
            "limit": "-1",
            "safra.id": sid,
            "precos.deleted": "false",
            "fields": "nome,caracteristica,precos,u_m_preco,taxa_adicao,data_base,tipo_juros",
        }
        data = self.client.get("/api/feature-table-prices", params=params)
        docs = data.get("docs") if isinstance(data, dict) else []
        out: list[dict[str, Any]] = []
        tsi_doc: dict[str, Any] = {"id": None, "nome": "TSI 1.0"}
        for d in docs:
            if (d.get("caracteristica") or {}).get("chave") == "tratamento":
                tsi_doc = {"id": d.get("_id"), "nome": d.get("nome", "TSI 1.0")}
                for p in d.get("precos", []):
                    if not p.get("deleted"):
                        out.append({
                            "value": p.get("opcao_chave", ""),
                            "label": p.get("opcao_label", ""),
                            "valor": p.get("valor", ""),
                        })
                break
        self._cache[key] = out
        self._cache[f"tsi_doc:{sid}"] = tsi_doc
        return out

    def tsi_ref(self, safra_id: str | None = None) -> dict[str, Any]:
        """{id, nome} da tabela TSI vinculada."""
        sid = safra_id or self.client.safra_id
        key = f"tsi_doc:{sid}"
        if key not in self._cache:
            self.tratamentos_tsi(sid)
        return self._cache.get(key, {"id": None, "nome": "TSI 1.0"})

    # ── Listas genéricas de descrição ───────────────────────────────

    def descricoes(self, endpoint: str) -> list[str]:
        """Puxa lista de descrições de qualquer endpoint tipo /api/types-of-...

        endpoint: 'types-of-warranty', 'form-of-payment', 'seed-use', etc.
        """
        key = f"desc:{endpoint}"
        if key in self._cache:
            return self._cache[key]
        params = {"limit": "-1", "status": "true", "fields": "descricao"}
        data = self.client.get(f"/api/{endpoint}", params=params)
        docs = data.get("docs") if isinstance(data, dict) else (
            data if isinstance(data, list) else []
        )
        out = [d.get("descricao", "") for d in docs if isinstance(d, dict) and d.get("descricao")]
        self._cache[key] = out
        return out

    # ── Atalhos comuns ──────────────────────────────────────────────

    def formas_pagamento(self) -> list[str]:
        return self.descricoes("form-of-payment")

    def tipos_venda(self) -> list[str]:
        return self.descricoes("types-of-sale")

    def tipos_garantia(self) -> list[str]:
        return self.descricoes("types-of-warranty")

    def usos_semente(self) -> list[str]:
        return self.descricoes("seed-use")
