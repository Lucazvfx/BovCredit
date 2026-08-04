"""Regressões do parser INDEA com dados integralmente sintéticos.

Documentos reais não pertencem ao repositório: nomes, inscrições e CPF devem
ficar no acervo protegido da instituição, nunca em fixtures públicas.
"""
from pdf_parsers import detectar_origem, parsear_indea


def test_parsear_indea_categorias_e_quantidades_sinteticas():
    texto = (
        "INDEA MT - SALDO ATUAL DA EXPLORACAO\n"
        "PROPRIEDADE: 00000000000 - FAZENDA SINTETICA\n"
        "MUNICIPIO: MUNICIPIO TESTE - MT\n"
        "BOVINO 5 A 12 MESES MACHO 120\n"
        "BOVINO 13 A 24 MESES MACHO 483\n"
    )
    assert detectar_origem(texto) == 'INDEA'
    dados = parsear_indea(texto)
    assert dados['animais']['f05_M'] == 120
    assert dados['animais']['f13_M'] == 483
    assert dados['total'] == 603


def test_parsear_indea_nao_descarta_quantidade_de_1_digito():
    texto = (
        "INDEA MT - SALDO ATUAL DA EXPLORACAO\n"
        "PROPRIEDADE: 00000000000 - FAZENDA SINTETICA\n"
        "MUNICIPIO: MUNICIPIO TESTE - MT\n"
        "BOVINO 25 A 36 MESES FEMEA 2\n"
    )
    dados = parsear_indea(texto)
    assert dados['total'] == 2
    assert dados['animais']['f25_F'] == 2
