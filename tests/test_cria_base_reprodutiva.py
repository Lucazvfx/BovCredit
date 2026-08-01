"""
Cria sem vaca não é cria.

Caso de campo, reportado por analista sobre um rebanho real (Fazenda Vale do
Coco, 753 cabeças):

    fêmeas 0–12m ..... 150        machos 0–12m ..... 15
    fêmeas 13–24m .... 374        machos ........... 0
    fêmeas 25–36m .... 209        machos ........... 0
    fêmeas  >36m .....   5        machos ........... 0

O sistema classificava CRIA. O relato foi direto ao ponto: "como o rebanho é
predominante fêmea, ele entende como cria".

Predominância feminina não é cria. Cria é produzir bezerro, e bezerro vem de
vaca — cinco matrizes não parem 700 cabeças. O que existe ali é recria de
fêmeas: fêmea jovem comprada para ganhar peso ou para virar matriz DEPOIS.
Projetar como cria inventa uma safra de bezerros que não vai nascer.

POR QUE A CONTAGEM DE MATRIZES NÃO BASTAVA

`matrizes` no classificador soma 25–36m e acima de 36m. É defensável — aos 25
meses a fêmea já cobre. Mas a soma esconde a FORMA da pirâmide, e é a forma
que distingue os dois sistemas:

    vaca de cria vive de 8 a 10 anos e SE ACUMULA acima dos 36 meses
    fêmea de recria é vendida ANTES de parir, e essa faixa fica vazia

No Vale do Coco a soma dá 28,4% do rebanho — acima do limiar de 18% — e mesmo
assim não é cria. A razão fêmeas>36m ÷ fêmeas 25–36m dá 0,02 contra 1,31 a
5,00 nos rebanhos de cria observados: duas ordens de grandeza.

POR QUE A GUARDA É ÚNICA E FICA NO FIM

Havia mais de um caminho chegando em CRIA — `guarda_ciclo_completo` e
`descarte_engorda_sem_venda` escolhiam entre CRIA/RECRIA/CRIA_RECRIA por
probabilidade — e nenhum perguntava se havia base reprodutiva. Corrigir só um
ramo deixaria o outro passando.
"""
import pytest

from ml_engine import (
    classificar, carregar_modelo,
    P_MATRIZES_CRIA, RAZAO_MATRIZ_MADURA_CRIA,
)


@pytest.fixture(scope='module', autouse=True)
def _modelo():
    carregar_modelo()


# [f00F, f00M, f05F, f05M, f13F, f13M, f25F, f25M, facF, facM]
VALE_DO_COCO = [0, 0, 150, 15, 374, 0, 209, 0, 5, 0]

CRIAS_LEGITIMAS = {
    'cria 504 cabeças':   [60, 60, 30, 15, 45, 20, 90, 6, 170, 8],
    'cria 1.705 cabeças': [200, 190, 180, 170, 150, 60, 120, 10, 600, 25],
}


def test_o_caso_relatado_deixa_de_ser_cria():
    r = classificar(VALE_DO_COCO)
    assert r['tipo'] != 'CRIA', (
        'rebanho com 5 matrizes para 753 cabeças voltou a ser classificado '
        'como cria'
    )
    assert r['tipo'] == 'RECRIA'


def test_a_recusa_e_explicada_ao_analista():
    """
    Um parecer que muda de ciclo sem dizer por quê é pior que um errado: o
    analista não tem como concordar nem discordar.
    """
    r = classificar(VALE_DO_COCO)
    assert r.get('regra_aplicada') == 'cria_sem_base_reprodutiva'
    texto = ' '.join(r.get('explicacao') or [])
    assert 'recria de fêmeas' in texto
    assert '36m' in texto, 'a explicação precisa citar a faixa que está vazia'


def test_a_soma_de_matrizes_sozinha_nao_pegaria_o_caso():
    """
    Prende o motivo de existir a razão da pirâmide: pelo critério antigo este
    rebanho passa. Se alguém remover a razão achando que é redundante, este
    teste mostra que não é.
    """
    total = sum(VALE_DO_COCO)
    matrizes = VALE_DO_COCO[6] + VALE_DO_COCO[8]
    assert matrizes / total > P_MATRIZES_CRIA, (
        'o caso deixou de ser aquele em que a contagem de matrizes engana'
    )
    razao = VALE_DO_COCO[8] / VALE_DO_COCO[6]
    assert razao < RAZAO_MATRIZ_MADURA_CRIA


@pytest.mark.parametrize('nome', list(CRIAS_LEGITIMAS))
def test_cria_de_verdade_continua_cria(nome):
    """
    A guarda tem de ser cirúrgica. Recusar cria legítima seria trocar um erro
    por outro — e este é o erro que apareceria em muito mais pareceres.
    """
    r = classificar(CRIAS_LEGITIMAS[nome])
    assert r['tipo'] == 'CRIA', f'{nome} deixou de ser reconhecida como cria'


def test_ciclo_completo_nao_e_afetado():
    r = classificar([80, 80, 50, 50, 60, 60, 90, 40, 220, 60])
    assert r['tipo'] == 'CICLO_COMPLETO'


def test_rebanho_sem_femea_de_25_36m_nao_divide_por_zero():
    """Denominador zero: engorda de machos não pode explodir a guarda."""
    r = classificar([0, 0, 0, 300, 0, 900, 0, 400, 0, 50])
    assert r['tipo'] in ('ENGORDA', 'RECRIA_ENGORDA', 'RECRIA')
