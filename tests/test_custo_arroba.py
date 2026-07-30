import pytest

from ml_engine import calcular_ano
from services.pesos_rebanho import arrobas_categorias


def test_calcular_ano_custo_em_arroba():
    r = calcular_ano(
        matrizes=100, femeas_024=40, machos_024=40, bois=5,
        nat_pct=0.75, desc_mat_pct=0.15, prop_boi=25, renov_boi_pct=0.2,
        venda_bez_pct=0.3, mort_pct=0.03, preco_arroba=320, custo_arroba=57,
        peso_boi=20, peso_vaca=17, peso_bezerra=8, peso_garrote=12,
    )
    # custo = arrobas do rebanho projetado × 57 (não mais cabeças × 850)
    arrobas = arrobas_categorias(
        matrizes=r['matrizes_prox'], bois=r['bois_prox'],
        jovens_f=r['femeas_024_prox'], jovens_m=r['machos_024_prox'],
        peso_vaca=17, peso_boi=20, peso_bezerra=8, peso_garrote=12)
    assert abs(r['custo'] - arrobas * 57) < 1.0


def test_simular_cria_custo_arroba():
    from ml_engine import _simular_cria
    r = _simular_cria(
        [10,10, 8,8, 6,6, 30,2, 40,3], 'conservador',
        nat_pct=75, mort_pct=3, desmama_pct=85, venda_bez_pct=30,
        preco_arroba_bezerro=300, custo_arroba=57, anos=1,
        peso_matriz=17, peso_bezerra=8)
    ano1 = r['anos'][0]
    # custo = (matrizes×17 + jovens(F+M)×8 + touros×20.53) × 57
    #
    # Antes o custo somava só as fêmeas jovens: os machos 0–25m declarados
    # pastavam de graça no modelo. E estimava touros por 1:30 mesmo quando o
    # rebanho já declarava bois — cobrando touros que não existiam e ignorando
    # os que existiam. Agora o custo cobre o rebanho efetivamente mantido.
    matrizes   = 30 + 40                 # v[6] + v[8]
    fem_recria = 10 + 8 + 6              # v[0] + v[2] + v[4]
    mac_recria = 10 + 8 + 6              # v[1] + v[3] + v[5]
    touros     = 2 + 3                   # v[7] + v[9] — bois declarados
    esperado = (matrizes*17 + (fem_recria + mac_recria)*8 + touros*20.53) * 57
    assert abs(ano1['custo'] - esperado) < 1.0
    assert r['preco_breakeven_unidade'] == 'R$/arroba'


def test_simular_recria_custo_arroba_prorata():
    from ml_engine import _simular_recria
    r = _simular_recria(
        [0,0, 0,50, 0,30, 0,0, 0,0], 'conservador', mort_pct=3,
        preco_arroba=320, peso_entrada_arr=8, peso_saida_arr=14,
        meses_recria=12, custo_arroba=57, anos=1)
    ano1 = r['anos'][0]
    animais = 50 + 30; peso_medio = (8 + 14) / 2
    esperado = animais * peso_medio * 57 * (12/12)
    # `custo` passou a somar manutenção + reposição 1:1 (a recria vende o lote
    # e repõe comprando desmamados). O rateio pro-rata é a parte de manutenção.
    assert abs(ano1['custo_manutencao'] - esperado) < 1.0
    assert ano1['custo'] == pytest.approx(
        ano1['custo_manutencao'] + ano1['custo_reposicao'], abs=1.0)


def test_simular_engorda_custo_arroba_prorata():
    from ml_engine import _simular_engorda
    r = _simular_engorda(
        [0,0, 0,0, 0,0, 0,20, 0,10], 'conservador', mort_pct=3,
        preco_arroba=320, peso_entrada_kg=350, peso_saida_kg=500,
        rendimento_carcaca=54, custo_arroba=57, dias_engorda=120, anos=1)
    ano1 = r['anos'][0]
    assert ano1['custo'] > 0  # sanidade: custo em @ pró-rata calculado


def test_simular_cenario_aceita_custo_arroba():
    from ml_engine import simular_cenario
    r = simular_cenario([10,10, 8,8, 6,6, 30,2, 40,3], 'conservador',
                        preco_arroba=320, custo_arroba=57)
    assert 'anos' in r and r['anos'][0]['custo'] > 0


def test_breakeven_simples_em_arroba():
    from ml_engine import calcular_breakeven_simples
    r = calcular_breakeven_simples([10,10, 8,8, 6,6, 30,2, 40,3], 'CRIA')
    assert r['preco_breakeven'] > 0
