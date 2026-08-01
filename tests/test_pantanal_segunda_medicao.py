"""
A segunda medição, no extremo oposto da escala.

Todos os parâmetros medidos do projeto vinham de UM sistema: Embrapa Brasil
Central, pastagem cultivada, 1,4 UA/ha, 468 matrizes Nelore. Uma medição só
não distingue o que é da espécie do que é do manejo.

O painel do Pantanal de Corumbá (Embrapa Pantanal, Circular Técnica 126, 2024,
dados de 2023) mede uma cria extensiva modal de 4.657 cabeças em 10.000 ha —
0,30 UA/ha, quase cinco vezes menos lotação. É o contraponto útil.

    índice                Brasil Central     Pantanal
    idade à 1ª cria       36,3 meses         40,0 meses
    peso desmama macho    177 kg             180 kg
    peso desmama fêmea    162 kg             165 kg
    lotação               1,4 UA/ha          0,30 UA/ha

Os PESOS à desmama quase não mudam entre os dois; a IDADE à primeira cria, sim.
É o que se espera — a fêmea atinge peso de cobertura mais tarde onde há menos
pasto — e é o que estes testes prendem, porque é disso que depende a guarda de
36 meses do classificador.
"""
import pytest

from services.proveniencia import MEDIDO
from services.parametros_zootecnicos import (
    IDADE_PRIMEIRA_PARICAO_MESES,
    IDADE_PRIMEIRA_CRIA_EXTENSIVO_MESES,
    DESFRUTE_CRIA_MEDIDO_PCT,
    NATALIDADE_MATRIZES_EXTENSIVO_PCT,
    MORTALIDADE_PRE_DESMAMA_MEDIDA_PCT,
    MORTALIDADE_BEZERRA_PCT,
    PESO_DESMAMA_MACHO_KG, PESO_DESMAMA_FEMEA_KG,
)

NOVOS = [
    IDADE_PRIMEIRA_CRIA_EXTENSIVO_MESES,
    DESFRUTE_CRIA_MEDIDO_PCT,
    NATALIDADE_MATRIZES_EXTENSIVO_PCT,
    MORTALIDADE_PRE_DESMAMA_MEDIDA_PCT,
]


@pytest.mark.parametrize('p', NOVOS, ids=lambda p: p.rotulo)
def test_toda_medicao_nova_tem_fonte_e_escopo(p):
    """
    A regra do projeto: medição sem fonte não existe, e medição de um sistema
    não pode passar por medição da fazenda em análise.
    """
    assert p.origem == MEDIDO
    assert 'Circular Técnica 126' in p.fonte
    assert 'Corumbá' in p.fonte
    assert p.nota and 'extensivo' in p.nota.lower(), (
        'sem o escopo declarado, o número vira medição do proponente'
    )


# ── O que as duas medições, juntas, estabelecem ─────────────────────────────
def test_a_guarda_de_36_meses_fica_mais_segura_no_extensivo():
    """
    A guarda do classificador conta a fêmea como matriz só depois dos 36
    meses. Brasil Central mediu 36,3; o Pantanal extensivo mediu 40,0.

    Isso importa para o SENTIDO do erro: se o sistema extensivo parisse mais
    CEDO, a guarda estaria cortando matriz de verdade. Como pare mais TARDE, o
    erro de contar a faixa de 25–36m como matriz é maior no extensivo, não
    menor — a guarda protege mais justamente onde o crédito é mais frágil.
    """
    assert float(IDADE_PRIMEIRA_CRIA_EXTENSIVO_MESES) > float(IDADE_PRIMEIRA_PARICAO_MESES)
    assert float(IDADE_PRIMEIRA_PARICAO_MESES) > 36.0


def test_o_peso_a_desmama_quase_nao_muda_entre_os_dois_sistemas():
    """
    Pantanal: 180 kg macho, 165 kg fêmea, aos 8 meses.
    Brasil Central: 177 kg macho, 162 kg fêmea, aos 202 dias.

    Menos de 2% de diferença com quase cinco vezes menos lotação. O manejo
    move a IDADE, não o peso de desmama — que é o que autoriza usar um peso de
    desmama único no motor sem perguntar o sistema ao analista.
    """
    for medido_bc, pantanal in ((PESO_DESMAMA_MACHO_KG, 180.0),
                                (PESO_DESMAMA_FEMEA_KG, 165.0)):
        desvio = abs(pantanal - float(medido_bc)) / float(medido_bc)
        assert desvio < 0.02, f'{medido_bc.rotulo}: {desvio:.1%} de desvio'


def test_o_desfrute_medido_cai_dentro_da_faixa_que_adotamos():
    """
    O teto de 35% da cria foi elevado antes com base em bibliografia. Uma cria
    real medida a 31,67% cai dentro e perto do teto — sustenta a decisão em
    vez de contradizê-la.
    """
    from services.benchmarks_nacionais import DESFRUTE_MODALIDADE
    lo, hi = DESFRUTE_MODALIDADE['CRIA']
    assert lo < float(DESFRUTE_CRIA_MEDIDO_PCT) < hi


def test_a_mortalidade_de_bezerro_ganhou_confirmacao_independente():
    """
    MORTALIDADE_BEZERRA_PCT era ponto médio de faixa bibliográfica (5–10%). O
    Pantanal mediu 7,00%. O número não muda; o que muda é o quanto se pode
    defendê-lo num comitê.
    """
    assert float(MORTALIDADE_PRE_DESMAMA_MEDIDA_PCT) == float(MORTALIDADE_BEZERRA_PCT)


def test_a_natalidade_real_fica_abaixo_do_que_o_manual_recomenda():
    """
    62,39% sobre matrizes, numa fazenda MODAL — abaixo da faixa "adequado
    65–75%" que a bibliografia usa. Vale registrar porque é a diferença entre
    avaliar contra o que o campo entrega e contra o que o manual pede.
    """
    assert float(NATALIDADE_MATRIZES_EXTENSIVO_PCT) < 65.0
