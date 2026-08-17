"""O mesmo PDF tem de dar o mesmo vetor nos dois caminhos de leitura.

`/api/ler-pdf` usa o parser direto e distribui a faixa de 0–12 meses entre as
duas posições jovens. `/api/ler-ficha` passa pelo catálogo estadual e
consolidava por CLASSIFICAÇÃO — e como '00 A 04 MESES' e '05 A 12 MESES'
carregam a mesma classificação ('Bezerra'), as duas caíam na posição 0. A
divisão feita pelo parser era jogada fora no caminho novo.

Medido com 100 fêmeas e 80 machos de 0–12 meses:

    parser direto ......... [50, 40, 50, 40, ...]
    consolidação estadual . [100, 80, 0, 0, ...]

Não é detalhe de representação: `gestao_model.pkl` foi treinado com as
posições 2/3 povoadas (mediana f05F/f00F = 0,545; só 14% das linhas com f05F
zerado). Zerá-las joga a entrada na cauda da distribuição de treino, e a
classificação muda conforme o endpoint que o analista usou.
"""
import pytest

from pdf_parsers import parsear_generico
from services.faixa_0_12 import dividir_0_12
from services.fichas_rebanho.base_reader import registros_do_parse
from services.fichas_rebanho.consolidator import consolidar_registros

# Cinco faixas separadas na origem (MT) e quatro faixas unificadas (MS, GO IR)
# têm de chegar no mesmo vetor.
ANIMAIS = {
    'f00_F': 50, 'f05_F': 50, 'f13_F': 200, 'f25_F': 0, 'fac_F': 400,
    'f00_M': 40, 'f05_M': 40, 'f13_M': 0, 'f25_M': 0, 'fac_M': 0,
}
ESPERADO = [50, 40, 50, 40, 200, 0, 0, 0, 400, 0]


@pytest.mark.parametrize('modelo', ['MT_DECLARACAO', 'MS', 'GO IR', 'MA', 'RO_DECLARACAO'])
def test_consolidacao_estadual_preserva_as_duas_posicoes_jovens(modelo):
    registros = registros_do_parse(
        {'fazenda': 'T', 'animais': ANIMAIS}, estado=modelo, modelo=modelo)

    consolidado = consolidar_registros(registros)

    assert consolidado, f'{modelo} não consolidou nenhuma fazenda'
    assert consolidado[0]['valores'] == ESPERADO, (
        f"{modelo} devolveu {consolidado[0]['valores']} — a faixa de 0–12 "
        f'meses voltou a desabar na primeira posição'
    )


def test_os_dois_caminhos_de_leitura_concordam():
    """Parser direto e consolidação estadual, mesma ficha, mesmo vetor."""
    texto = (
        'Fazenda Teste\n'
        'Fêmea 0 a 12 meses     100\n'
        'Macho 0 a 12 meses      80\n'
        'Fêmea 13 a 24 meses    200\n'
        'Vaca acima de 36       400\n'
    )
    legado = parsear_generico(texto)['valores']

    registros = registros_do_parse(
        {'fazenda': 'T', 'animais': parsear_generico(texto)['animais']},
        estado='MS', modelo='MS')
    novo = consolidar_registros(registros)[0]['valores']

    assert legado == novo, f'legado {legado} contra consolidado {novo}'


def test_o_total_nao_muda_na_divisao():
    registros = registros_do_parse(
        {'fazenda': 'T', 'animais': ANIMAIS}, estado='MS', modelo='MS')

    consolidado = consolidar_registros(registros)[0]

    assert sum(consolidado['valores']) == sum(ANIMAIS.values())


# ── A regra em si ───────────────────────────────────────────────────────────
def test_divisao_manda_o_impar_para_a_faixa_mais_velha():
    assert dividir_0_12(100) == (50, 50)
    assert dividir_0_12(101) == (50, 51)
    assert dividir_0_12(1) == (0, 1)
    assert dividir_0_12(0) == (0, 0)


def test_divisao_nao_inventa_animal():
    for qtd in (0, 1, 7, 100, 101, 9999):
        f00, f05 = dividir_0_12(qtd)
        assert f00 + f05 == qtd
