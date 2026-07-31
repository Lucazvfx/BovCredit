"""
Compra de desmama na cria — a suposição que estava implícita.

Uma coorte de 0–12 meses acima do que as matrizes entregam só pode ter sido
comprada. `services.consistencia_rebanho.estimar_compra_animais` já detectava e
sinalizava isso, mas o fluxo de caixa nunca debitava nada — e o modelo, ao
projetar o ano seguinte só com produção própria, assumia em SILÊNCIO que o
produtor para de comprar.

Essa suposição não é neutra: é ela que faz o rebanho encolher e produz a
variação de estoque negativa. Num parecer real de 1.775 cabeças (750 matrizes,
860 animais de 0–12m) ela sozinha respondia por R$ 1,6 milhão de perda
patrimonial projetada, sem uma linha explicando de onde vinha.

As duas leituras são legítimas e dão pareceres diferentes. O que estes testes
garantem é que a escolha seja explícita, não implícita.
"""
import importlib

import pytest

import ml_engine


# Caso real: 750 matrizes, 500 bezerras + 360 bezerros (0–12m), 100 novilhas,
# 40 garrotes, 25 touros = 1.775 cabeças.
REBANHO = [250, 180, 250, 180, 100, 40, 0, 0, 750, 25]


def _ano1(modulo, ciclo='CRIA'):
    return modulo.simular_cenario(REBANHO, 'conservador', ciclo=ciclo,
                                  preco_arroba=322.62, custo_arroba=93.21)['anos']


@pytest.fixture(scope='module', autouse=True)
def _modelo():
    ml_engine.carregar_modelo()


@pytest.fixture
def repondo(monkeypatch):
    """Liga a reposição sem depender da variável de ambiente do processo."""
    monkeypatch.setattr(ml_engine, '_REPOR_COMPRA_DESMAMA', True)
    return ml_engine


def test_a_compra_e_detectada_e_reportada():
    """
    750 matrizes a 70% de natalidade entregam ~525 bezerros, mas a ficha
    declara 860 de 0–12m. A diferença foi comprada, e o parecer precisa dizer.
    """
    a = _ano1(ml_engine)[0]
    assert a['compra_desmama_estimada'] > 300, (
        'a compra implícita na ficha não foi estimada'
    )


def test_por_padrao_nao_repoe_e_declara_isso():
    """O comportamento histórico é mantido — o que muda é ele ficar visível."""
    a = _ano1(ml_engine)[0]
    assert a['repoe_compra_desmama'] is False
    assert a['custo_compra_desmama'] == 0.0


def test_sem_repor_o_rebanho_converge_para_a_producao_propria(repondo):
    """
    A causa da variação de estoque negativa: sem comprar, o plantel encolhe
    para o tamanho que as próprias matrizes sustentam.
    """
    ml_engine._REPOR_COMPRA_DESMAMA = False
    sem = _ano1(ml_engine)[0]
    ml_engine._REPOR_COMPRA_DESMAMA = True
    com = _ano1(ml_engine)[0]
    assert com['total'] > sem['total'], (
        f'repor deveria segurar o rebanho: sem={sem["total"]} com={com["total"]}'
    )


def test_repor_cobra_a_compra_no_caixa(repondo):
    """
    O outro lado: manter a estrutura custa dinheiro, e esse dinheiro não
    aparecia em lugar nenhum do fluxo.
    """
    a = _ano1(repondo)[0]
    assert a['repoe_compra_desmama'] is True
    assert a['custo_compra_desmama'] > 0
    assert a['custo'] > a['custo_manutencao']


def test_as_duas_leituras_dao_resultados_diferentes(repondo):
    """
    Se dessem o mesmo, a suposição seria irrelevante e não valeria declarar.
    Repor piora o operacional (custo de compra) e melhora o patrimônio.
    """
    ml_engine._REPOR_COMPRA_DESMAMA = False
    sem = _ano1(ml_engine)[0]
    ml_engine._REPOR_COMPRA_DESMAMA = True
    com = _ano1(ml_engine)[0]

    assert com['resultado'] < sem['resultado'], (
        'repor tem que piorar o resultado operacional — é saída de caixa'
    )
    assert com['total'] > sem['total'], (
        'repor tem que preservar o rebanho — é o outro lado da moeda'
    )


def test_rebanho_sem_compra_implicita_nao_e_afetado(repondo):
    """
    Rebanho coerente (coorte jovem dentro da produção própria) não pode ganhar
    custo de compra nenhum, com a flag ligada ou não.
    """
    coerente = [80, 80, 80, 80, 60, 40, 0, 0, 500, 20]   # 500 matrizes, 320 jovens
    a = repondo.simular_cenario(coerente, 'conservador', ciclo='CRIA',
                                preco_arroba=322.62, custo_arroba=93.21)['anos'][0]
    assert a['compra_desmama_estimada'] == 0
    assert a['custo_compra_desmama'] == 0.0


def test_balanco_continua_fechando_nas_duas_leituras(repondo):
    for valor in (False, True):
        ml_engine._REPOR_COMPRA_DESMAMA = valor
        a = _ano1(ml_engine)[0]
        esperado = (sum(REBANHO) + a.get('bezerros', 0) + a.get('compras', 0)
                    - a.get('vendidos', 0) - a.get('matrizes_descartadas', 0)
                    - a.get('mortes', 0))
        # Com reposição o plantel jovem é recomposto pela compra, que não passa
        # por `compras` (os animais já estavam declarados na abertura).
        folga = a.get('compra_desmama_estimada', 0) if valor else 0
        assert abs(a['total'] - esperado - folga) <= max(3, sum(REBANHO) * 0.02), (
            f'repoe={valor}: fim={a["total"]}, esperado={esperado + folga}'
        )


def test_custo_de_manutencao_e_separado_do_de_compra(repondo):
    """Sem separar, o analista não consegue defender nenhum dos dois."""
    a = _ano1(repondo)[0]
    assert a['custo'] == pytest.approx(
        a['custo_manutencao'] + a['custo_compra_desmama'], abs=1.0)
