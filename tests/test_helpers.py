"""Testes dos helpers puros."""

from mana_habilidade_simpleagro.helpers import (
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


# so_digitos / normalizar_cnpj
def test_so_digitos_remove_pontuacao():
    assert so_digitos("12.345.678/0001-99") == "12345678000199"


def test_so_digitos_string_vazia():
    assert so_digitos("") == ""
    assert so_digitos(None) == ""


def test_normalizar_cnpj_e_alias_de_so_digitos():
    assert normalizar_cnpj("111.222.333-44") == "11122233344"


# fmt_ptbr / parse_ptbr
def test_fmt_ptbr_formato_brasileiro():
    assert fmt_ptbr(1234.56, 2) == "1.234,56"


def test_fmt_ptbr_6_casas_default():
    assert fmt_ptbr(10.0) == "10,000000"


def test_parse_ptbr_vg_decimal():
    assert parse_ptbr("1.234,56") == 1234.56


def test_parse_ptbr_ponto_decimal():
    assert parse_ptbr("1234.56") == 1234.56


def test_parse_ptbr_numero_puro():
    assert parse_ptbr(42) == 42.0


def test_parse_ptbr_vazio():
    assert parse_ptbr("") == 0.0
    assert parse_ptbr(None) == 0.0
    assert parse_ptbr("abc") == 0.0


# parse_coord
def test_parse_coord_valida():
    assert parse_coord("-16.5") == -16.5
    assert parse_coord(-15.7) == -15.7


def test_parse_coord_zero_e_ausente():
    assert parse_coord(0) is None
    assert parse_coord("0000") is None
    assert parse_coord(None) is None
    assert parse_coord("abc") is None


# extract_name / extract_str
def test_extract_name_de_dict():
    assert extract_name({"nome": "Alice"}) == "Alice"
    assert extract_name({"label": "Bob"}) == "Bob"


def test_extract_name_de_string():
    assert extract_name("Carlos") == "Carlos"


def test_extract_name_vazio():
    assert extract_name(None) == ""
    assert extract_name({}) == ""


def test_extract_str_multiplas_chaves():
    obj = {"a": "", "b": {"nome": "x"}}
    assert extract_str(obj, "a", "b") == "x"


def test_extract_str_notacao_ponto():
    obj = {"a": {"b": {"c": "profundo"}}}
    assert extract_str(obj, "a.b.c") == "profundo"


def test_extract_str_nao_encontrado():
    assert extract_str({"a": ""}, "b", "c") == ""


# normalizar_produto
def test_normalizar_produto_upper_sem_espaco():
    assert normalizar_produto("NEO 790 IPRO") == "NEO790IPRO"


def test_normalizar_produto_vazio():
    assert normalizar_produto("") == ""
    assert normalizar_produto(None) == ""


# sem_acento
def test_sem_acento_remove_acentos_lowercase():
    assert sem_acento("Crédito") == "credito"


def test_sem_acento_colapsa_espacos():
    assert sem_acento("  Ola  Mundo  ") == "ola mundo"


# fmt_data_br
def test_fmt_data_br_converte():
    assert fmt_data_br("2026-06-30") == "30/06/2026"


def test_fmt_data_br_ja_br_deixa():
    assert fmt_data_br("30/06/2026") == "30/06/2026"


def test_fmt_data_br_vazio():
    assert fmt_data_br("") == ""
    assert fmt_data_br(None) == ""
