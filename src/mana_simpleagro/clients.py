"""Clientes e propriedades — Simple Agro.

Endpoints:
    GET  /api/clients?cpf_cnpj=/digits/         busca regex Mongo por CPF/CNPJ
    GET  /api/clients?nome=/regex/i             busca por nome (case-insensitive)
    POST /api/clients                           FormData/multipart (400 = CPF inválido)
    GET  /api/clients/{id}/properties           propriedades (fazendas) do cliente
    POST /api/clients/{id}/properties           criar propriedade
"""

from __future__ import annotations

import logging
import re
from typing import Any

from .client import SimpleAgroClient
from .exceptions import ValidationError
from .helpers import so_digitos

log = logging.getLogger("mana-simpleagro.clients")


class ClientsAPI:
    """API de clientes.

    Args:
        client: SimpleAgroClient.
    """

    def __init__(self, client: SimpleAgroClient) -> None:
        self.client = client

    # ── Busca ───────────────────────────────────────────────────────

    def buscar_por_cpf_cnpj(
        self,
        cpf_cnpj: str,
        fields: str = "-propriedades,-gestao_area_plantada",
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Busca cliente por CPF/CNPJ. SA usa regex Mongo — digitos escapados.

        Args:
            cpf_cnpj: com ou sem formatação (só dígitos são usados).
            fields: campos a excluir (default: propriedades pra resposta magra).
            limit: quantos resultados.

        Returns:
            Lista de clientes (dict com _id, nome, cpf_cnpj, tipo, propriedades, ...).
        """
        params = {
            "fields": fields,
            "limit": str(limit),
            "page": "1",
            "sort": "",
            "cpf_cnpj": f"/{so_digitos(cpf_cnpj)}/",
        }
        data = self.client.get("/api/clients", params=params)
        return _docs(data)

    def buscar_por_nome(
        self,
        nome: str,
        fields: str = "-propriedades,-gestao_area_plantada",
        limit: int = 10,
        retry_palavras: bool = True,
    ) -> list[dict[str, Any]]:
        """Busca cliente por nome (regex case-insensitive).

        Se retry_palavras=True e zero resultados, tenta com palavras mais distintivas
        (útil pra transcrição de áudio com acentos/erros).
        """
        if not nome or not nome.strip():
            return []
        nome = nome.strip()
        docs = self._query_por_nome(nome, fields, limit)
        if docs or not retry_palavras:
            return docs

        # Retry: palavras significativas (ignora conectivos), da mais longa
        palavras = sorted(
            [p for p in re.split(r"\s+", nome) if len(p) > 3],
            key=len, reverse=True,
        )
        vistos: set[str] = set()
        out: list[dict[str, Any]] = []
        for p in palavras[:3]:
            for d in self._query_por_nome(p, fields, limit):
                if d.get("_id") not in vistos:
                    vistos.add(d["_id"])
                    out.append(d)
            if len(out) >= limit:
                break
        log.info("busca nome '%s': retry palavras → %d", nome[:20], len(out))
        return out

    def buscar(
        self, cpf_cnpj: str | None = None, nome: str | None = None
    ) -> list[dict[str, Any]]:
        """Busca inteligente: CPF/CNPJ tem prioridade; senão por nome."""
        if cpf_cnpj:
            return self.buscar_por_cpf_cnpj(cpf_cnpj)
        if nome:
            return self.buscar_por_nome(nome)
        return []

    def get(self, cliente_id: str) -> dict[str, Any]:
        """GET /api/clients/{id} — cliente completo com propriedades embutidas."""
        return self.client.get(f"/api/clients/{cliente_id}")

    def _query_por_nome(
        self, termo: str, fields: str, limit: int
    ) -> list[dict[str, Any]]:
        params = {
            "fields": fields,
            "limit": str(limit),
            "page": "1",
            "sort": "",
            "nome": f"/{re.escape(termo)}/i",
        }
        data = self.client.get("/api/clients", params=params)
        return _docs(data)

    # ── Escrita ─────────────────────────────────────────────────────

    def criar(
        self,
        nome: str,
        cpf_cnpj: str,
        tipo: str = "PRODUTOR",
        perfil_compra: str = "Relacionamento",
        email: str = "",
        tel_cel: str = "",
        tel_fixo: str = "",
        endereco: str = "",
        estado: str = "",
        cidade: str = "",
        salva_semente: bool = False,
    ) -> dict[str, Any]:
        """POST /api/clients — cria cliente novo (multipart, formato do painel).

        Args:
            nome: razão social ou nome completo.
            cpf_cnpj: com ou sem formatação (SA valida server-side).
            tipo: 'PRODUTOR' | 'REVENDA' | 'COOPERATIVA' etc.
            perfil_compra: 'Relacionamento' | 'Preço' | 'Prazo' etc.
            email, tel_cel, tel_fixo, endereco, estado, cidade: opcionais.
            salva_semente: se cliente comercializa semente própria.

        Returns:
            Cliente criado (dict com _id e demais campos).

        Raises:
            ValidationError: HTTP 400 — SA rejeitou (CPF inválido, campos faltando).
        """
        campos = {
            "nome": nome,
            "tipo": tipo,
            "perfil_compra": perfil_compra,
            "cpf_cnpj": cpf_cnpj,
            "email": email,
            "tel_cel": so_digitos(tel_cel),
            "tel_fixo": so_digitos(tel_fixo),
            "endereco": endereco,
            "estado": estado,
            "cidade": cidade,
            "salva_semente": "true" if salva_semente else "false",
            "gerenciarCarteiraPorPropriedade": "false",
        }
        try:
            return self.client.post(
                "/api/clients",
                files={k: (None, str(v)) for k, v in campos.items()},
            )
        except ValidationError as e:
            # Extrai mensagem amigável do SA se possível
            msg = str(e)
            m = re.search(r'"message"\s*:\s*"([^"]+)"', msg)
            if m:
                raise ValidationError(f"SA recusou cadastro: {m.group(1)}") from e
            raise

    # ── Propriedades (fazendas) ────────────────────────────────────

    def listar_propriedades(
        self,
        cliente_id: str,
        cpf_cnpj: str | None = None,
    ) -> list[dict[str, Any]]:
        """Propriedades (fazendas) do cliente.

        Estratégia dupla:
        1) GET /api/clients/{id}/properties
        2) Fallback: doc completo do cliente via busca por CPF (propriedades embutidas)
        """
        # Tentativa 1: endpoint dedicado
        try:
            data = self.client.get(f"/api/clients/{cliente_id}/properties")
            lst = data.get("docs") if isinstance(data, dict) else data
            if isinstance(lst, list) and lst:
                return _fmt_propriedades(lst)
        except Exception as e:
            log.warning("GET /properties falhou: %s", e)

        # Fallback: pega doc completo
        if cpf_cnpj:
            docs = self.buscar_por_cpf_cnpj(
                cpf_cnpj, fields="", limit=1
            )
            if docs:
                return _fmt_propriedades(docs[0].get("propriedades") or [])
        return []

    def criar_propriedade(
        self,
        cliente_id: str,
        nome: str,
        ie: str = "",
        area: float | str = 0,
        endereco: str = "",
        cidade: str = "",
        estado: str = "",
        latitude: float | None = None,
        longitude: float | None = None,
    ) -> dict[str, Any]:
        """POST /api/clients/{id}/properties — cria fazenda.

        Args:
            cliente_id: _id do cliente.
            nome: nome da fazenda.
            ie: inscrição estadual (só dígitos usados; default '00000000000').
            area: hectares.
            endereco, cidade, estado: endereço da fazenda.
            latitude, longitude: opcionais (só usa se ambos presentes).

        Returns:
            Propriedade criada (dict com _id).
        """
        body: dict[str, Any] = {
            "nome": nome,
            "ie": so_digitos(ie) or "00000000000",
            "area": str(area),
            "endereco": endereco,
            "cidade": cidade,
            "estado": estado,
        }
        if latitude is not None and longitude is not None:
            body["latitude"] = latitude
            body["longitude"] = longitude
        return self.client.post(f"/api/clients/{cliente_id}/properties", json=body)


# ── Helpers internos ─────────────────────────────────────────────


def _docs(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, dict):
        return data.get("docs") or data.get("data") or []
    if isinstance(data, list):
        return data
    return []


def _fmt_propriedades(lst: list[dict]) -> list[dict[str, Any]]:
    """Padroniza shape das propriedades pra consumidores."""
    return [
        {
            "id": p.get("_id"),
            "nome": p.get("nome", ""),
            "ie": p.get("ie", ""),
            "cidade": p.get("cidade", ""),
            "estado": p.get("estado", ""),
            "latitude": p.get("latitude"),
            "longitude": p.get("longitude"),
            "area": p.get("area"),
        }
        for p in lst
        if isinstance(p, dict) and not p.get("deleted")
    ]
