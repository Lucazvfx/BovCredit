"""
Testes de regressão com PDFs REAIS do INDEA-MT (boletim "Saldo Atual da
Exploração"). Estes fixtures pegaram um bug real de produção: o regex de
captura de quantidade exigia 2+ dígitos, descartando silenciosamente
qualquer linha com 1-9 animais (ex.: "BOVINO 25 A 36 MESES FEMEA 2").

Os PDFs ficam em tests/fixtures_pdf/ e são versionados com o repositório
para que este teste rode em qualquer máquina, sem depender de caminho local.
"""
import os
import subprocess
import pytest

from pdf_parsers import detectar_origem, parsear_indea

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), 'fixtures_pdf')


def _extrair_texto(pdf_path: str) -> str:
    result = subprocess.run(
        ['pdftotext', '-layout', pdf_path, '-'],
        capture_output=True, text=True,
    )
    return result.stdout


# (nome_do_arquivo, total_esperado_so_bovinos, dict_animais_esperado)
CASOS = [
    (
        '51000168416_-_FAZENDA_SANTA_ELIZA.pdf', 603,
        {'f05_M': 120, 'f13_M': 483},
    ),
    (
        '51000170037_-_FAZENDA_NOSSO_SENHOR_BOM_JESUS_I.pdf', 460,
        {'f05_F': 225, 'f05_M': 55, 'f13_F': 175, 'f25_F': 5},
    ),
    (
        '51000170042_-_FAZENDA_CATUAI.pdf', 478,
        {'f05_M': 25, 'f13_F': 210, 'f13_M': 100, 'f25_F': 113, 'f25_M': 30},
    ),
    (
        # Regressão direta do bug: ficheiro só tinha 3 linhas, 2 delas com
        # quantidade de 1 dígito (15 e 9 também conta, mas o caso crítico
        # era ITAIPU com '9' isolado na linha 13 A 24 MESES MACHO).
        '51000170437_-_FAZENDA_ITAIPU_IV.pdf', 77,
        {'f05_M': 15, 'f13_M': 9, 'fac_F': 53},
    ),
    (
        '51000737470_-_FAZENDA_VALE_DO_GIBEAO.pdf', 3292,
        {
            'f00_F': 340, 'f00_M': 325, 'f05_F': 102,
            'f13_F': 308, 'fac_F': 2200, 'fac_M': 17,
        },
    ),
    (
        # Regressão direta do bug: ÚNICA linha do PDF tem quantidade "2"
        # (1 dígito) — o parser zerava o rebanho inteiro antes da correção.
        '51001153859_-_ESTANCIA_BARBOSINHA.pdf', 2,
        {'f25_F': 2},
    ),
]


@pytest.mark.parametrize('arquivo,total_esperado,animais_esperados', CASOS)
def test_parsear_indea_pdf_real(arquivo, total_esperado, animais_esperados):
    path = os.path.join(FIXTURES_DIR, arquivo)
    assert os.path.exists(path), f'Fixture não encontrada: {path}'

    text = _extrair_texto(path)
    assert detectar_origem(text) == 'INDEA'

    dados = parsear_indea(text, pdf_path=path)
    assert dados['total'] == total_esperado, (
        f'{arquivo}: total extraído {dados["total"]} != esperado {total_esperado} '
        f'(animais: {dados["animais"]})'
    )
    for campo, qtd in animais_esperados.items():
        assert dados['animais'][campo] == qtd, (
            f'{arquivo}: campo {campo} = {dados["animais"][campo]} != esperado {qtd}'
        )


def test_parsear_indea_nao_descarta_quantidade_de_1_digito():
    """Regressão específica do bug: quantidade de 1 algarismo não pode
    ser descartada silenciosamente pelo regex de captura."""
    texto = (
        "PROPRIEDADE: 99999999999 - FAZENDA TESTE\n"
        "MUNICÍPIO: TESTE - MT\n"
        "BOVINO                25 A 36 MESES        FEMEA              2\n"
    )
    dados = parsear_indea(texto)
    assert dados['total'] == 2
    assert dados['animais']['f25_F'] == 2
