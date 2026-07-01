"""Utilitários: normalizações, formatação pt-BR, extração de campos aninhados."""

from __future__ import annotations

import re
import unicodedata
from typing import Any


# ─────────────────────────────────────────────────────────────────────
# Normalização de identificadores
# ─────────────────────────────────────────────────────────────────────


def so_digitos(doc: str | None) -> str:
    """Remove tudo que não é dígito. CPF/CNPJ vira só números."""
    return re.sub(r"\D", "", doc or "")


# Alias mantido pra compatibilidade com código legado dos agentes
def normalizar_cnpj(doc: str | None) -> str:
    """Normaliza CPF/CNPJ removendo pontuação. Alias de so_digitos."""
    return so_digitos(doc)


# ─────────────────────────────────────────────────────────────────────
# Formato pt-BR (SA usa "10.000,000000" em vez de "10000.000000")
# ─────────────────────────────────────────────────────────────────────


def fmt_ptbr(valor: float | str | int, casas: int = 6) -> str:
    """Float → string pt-BR ('1234.56' → '1.234,560000').

    SA aceita valores como STRING no formato pt-BR.
    """
    s = f"{float(valor):,.{casas}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def parse_ptbr(s: Any) -> float:
    """String pt-BR ou número → float ('1.234,56' → 1234.56, '1234.56' → 1234.56)."""
    if s is None or s == "":
        return 0.0
    if isinstance(s, (int, float)):
        return float(s)
    txt = str(s).strip()
    # Formato brasileiro: ponto como milhar, vírgula como decimal
    if "," in txt:
        txt = txt.replace(".", "").replace(",", ".")
    try:
        return float(txt)
    except (ValueError, AttributeError):
        return 0.0


# ─────────────────────────────────────────────────────────────────────
# Extração de campos aninhados (SA aninha objetos e às vezes retorna dict/string)
# ─────────────────────────────────────────────────────────────────────


def extract_name(val: Any) -> str:
    """Extrai nome de campo que pode ser string OU dict {nome, label, name, value}."""
    if not val:
        return ""
    if isinstance(val, dict):
        return (
            val.get("nome")
            or val.get("label")
            or val.get("name")
            or val.get("value")
            or ""
        )
    return str(val)


def extract_str(obj: dict, *keys: str) -> str:
    """Tenta múltiplas chaves (com notação 'a.b') e retorna o 1º não-vazio.

    >>> extract_str({"a": {"b": "x"}}, "a.b")
    'x'
    """
    for key in keys:
        parts = key.split(".")
        val: Any = obj
        for p in parts:
            if isinstance(val, dict):
                val = val.get(p)
            else:
                val = None
                break
        if val is None:
            continue
        if isinstance(val, dict):
            extracted = val.get("label") or val.get("nome") or val.get("value") or ""
            if str(extracted).strip():
                return str(extracted).strip()
            continue
        if str(val).strip():
            return str(val).strip()
    return ""


# ─────────────────────────────────────────────────────────────────────
# Coordenadas (lat/lng — SA às vezes retorna "0000" ou 0 pra vazio)
# ─────────────────────────────────────────────────────────────────────


def parse_coord(v: Any) -> float | None:
    """Converte coordenada SA para float; trata 0/0, '0000', None como ausente."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if abs(f) < 0.01 else f


# ─────────────────────────────────────────────────────────────────────
# Normalização de texto (busca sem acento / case-insensitive)
# ─────────────────────────────────────────────────────────────────────


def sem_acento(s: str | None) -> str:
    """Remove acentos e devolve string lowercase."""
    s = unicodedata.normalize("NFD", str(s or "")).encode("ascii", "ignore").decode("ascii")
    return " ".join(s.lower().split())


def normalizar_produto(nome: str | None) -> str:
    """Chave de comparação de nome de produto (upper + sem espaço).

    SA às vezes tem 'NEO 790 IPRO' e outras 'NEO790IPRO' — mesma coisa.
    """
    return (nome or "").upper().replace(" ", "")


# ─────────────────────────────────────────────────────────────────────
# Data
# ─────────────────────────────────────────────────────────────────────


def fmt_data_br(raw: str | None) -> str:
    """AAAA-MM-DD → DD/MM/AAAA. Deixa outros formatos inalterados."""
    if not raw:
        return ""
    if re.match(r"\d{4}-\d{2}-\d{2}", raw):
        return raw[8:10] + "/" + raw[5:7] + "/" + raw[:4]
    return raw
