"""
Ficha real de recria — 700 cabeças.

Praticamente todo o resto da validação do projeto é sintético: geramos o
conjunto de treino das faixas que nós mesmos escrevemos. Esta é uma ficha de
verdade, com composição por faixa etária, destino declarado por categoria,
projeção de venda e desfrute — e ela pegou um bug que nenhum teste sintético
pegaria.

O que o modelo fazia antes: tratava 5–25 meses como pool único e vendia 100%
dele todo ano, incluindo os de 5–12 meses recém-entrados, precificados pelo
peso de SAÍDA da recria. Tudo fora dessa faixa (25–36m e >36m) nunca era
vendido, em ano nenhum. Resultado: 443 vendas (desfrute 63,3%, acima da
própria faixa de referência 35–55%) contra as 315 da ficha — receita ~41%
superestimada, e o DSCR junto.

A ficha não modela mortalidade; nós modelamos. As comparações abaixo toleram
essa diferença, e só essa.
"""
import pytest

from ml_engine import simular_cenario, classificar, carregar_modelo, BENCHMARKS_RO

#  faixa        M    F        destino declarado na ficha
#  0–12       219   22        permanência / evolução
#  13–24      234  105        recria / venda conforme peso
#  25–36       16   45        venda
#  >36          0   59        venda
FICHA = [11, 110, 11, 109, 105, 234, 45, 16, 59, 0]

FICHA_TOTAL     = 700
FICHA_VENDAS    = 315
FICHA_MACHOS    = 211      # 16 (25–36m) + 195 (13–24m conforme peso)
FICHA_FEMEAS    = 104      # 59 (>36m) + 45 (25–36m)
FICHA_DESFRUTE  = 45.0
FICHA_REPOSICAO = 315      # 1:1 por aquisição

# Mortalidade do cenário conservador — a ficha ignora, o modelo não.
TOL_MORTALIDADE = 0.06


@pytest.fixture(scope='module', autouse=True)
def _modelo():
    carregar_modelo()


@pytest.fixture(scope='module')
def ano1():
    return simular_cenario(FICHA, 'conservador', ciclo='RECRIA',
                           preco_arroba=320, custo_arroba=119)['anos'][0]


def test_a_ficha_soma_700():
    """Guarda contra erro de transcrição da ficha para o vetor de 10 posições."""
    assert sum(FICHA) == FICHA_TOTAL


def test_classifica_como_recria():
    r = classificar(FICHA)
    assert r['tipo'] == 'RECRIA', f"classificado como {r['tipo']}"
    assert r['confianca'] > 80


def test_volume_de_vendas_bate_com_a_ficha(ano1):
    """O bug: 443 projetadas contra 315 declaradas."""
    assert ano1['vendidos'] == pytest.approx(FICHA_VENDAS, rel=TOL_MORTALIDADE), (
        f"projetou {ano1['vendidos']} vendas, ficha declara {FICHA_VENDAS}"
    )


def test_composicao_das_vendas_bate_com_a_ficha(ano1):
    """
    Não basta o total: o modelo antigo vendia 100% dos machos e ZERO fêmeas.
    A ficha vende 104 fêmeas — todas as de 25m+.
    """
    assert ano1['machos_vendidos'] == pytest.approx(FICHA_MACHOS, rel=TOL_MORTALIDADE)
    assert ano1['femeas_vendidas'] == pytest.approx(FICHA_FEMEAS, rel=TOL_MORTALIDADE)


def test_desfrute_dentro_da_faixa_de_referencia(ano1):
    """A ficha declara 45%; a referência do material é 35% a 55%."""
    desfrute = ano1['vendidos'] / FICHA_TOTAL * 100
    assert 35.0 <= desfrute <= 55.0, f'desfrute projetado {desfrute:.1f}% fora da faixa'
    assert desfrute == pytest.approx(FICHA_DESFRUTE, abs=5.0)


def test_desfrute_respeita_o_teto_do_proprio_benchmark(ano1):
    """
    A guarda de desfrute existia e acusava 63,3% > 55 — ou seja, o sistema já
    denunciava o próprio simulador. Não pode voltar a disparar.
    """
    teto = BENCHMARKS_RO['desfrute']['teto_por_ciclo']['RECRIA']
    assert ano1['vendidos'] / FICHA_TOTAL * 100 <= teto


def test_os_de_0_12_meses_permanecem(ano1):
    """
    'Permanência / evolução' na ficha. Vender um bezerro de 5 meses pelo peso
    de saída da recria era o erro que mais inflava a receita.
    """
    jovens_declarados = FICHA[0] + FICHA[1] + FICHA[2] + FICHA[3]   # 241
    assert ano1['vendidos'] < FICHA_TOTAL - jovens_declarados + 10


def test_animais_terminados_sao_vendidos(ano1):
    """
    O outro lado do bug: as 120 cabeças de 25–36m e >36m caíam num balde que
    não era vendido em ano nenhum, e acumulavam para sempre.

    A prova é a venda de fêmeas: TODAS as fêmeas vendidas vêm de 25m+, porque
    as de 13–24m ficam. Se o balde voltasse, esse número seria zero — que era
    exatamente o valor do modelo antigo.

    (bois_fim/matrizes ao FECHAMENTO não servem de prova: são os de 13–24m que
    ficaram e envelheceram para 25–36m.)
    """
    femeas_25m_mais = FICHA[6] + FICHA[8]   # 45 + 59 = 104
    assert ano1['femeas_vendidas'] > 0, 'nenhuma fêmea vendida — o balde voltou'
    assert ano1['femeas_vendidas'] == pytest.approx(femeas_25m_mais,
                                                    rel=TOL_MORTALIDADE)


def test_reposicao_e_um_para_um(ano1):
    """A ficha: venda 315 → reposição por compra 315."""
    assert ano1['compras'] == pytest.approx(ano1['vendidos'], rel=0.01)


def test_rebanho_conserva(ano1):
    """fim = início + compras − vendas − mortes. Sem folga."""
    esperado = (FICHA_TOTAL + ano1['compras'] - ano1['vendidos']
                - ano1['matrizes_descartadas'] - ano1['mortes'])
    assert abs(ano1['total'] - esperado) <= 2


def test_projecao_nao_colapsa_no_ano_2():
    """
    O ano 1 liquida o estoque de animais prontos declarado na ficha. Se o ano 2
    despencar, a projeção do prazo do crédito não se sustenta — foi assim que
    o ciclo completo escondia um DSCR negativo atrás de um ano 1 folgado.
    """
    anos = simular_cenario(FICHA, 'conservador', ciclo='RECRIA',
                           preco_arroba=320, custo_arroba=119)['anos']
    assert len(anos) >= 2
    assert anos[1]['vendidos'] > 0, 'ano 2 não vende nada'
    assert anos[1]['total'] > FICHA_TOTAL * 0.5, 'plantel colapsa no ano 2'
