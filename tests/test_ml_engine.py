import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import pytest
from ml_engine import _classificar_faixa, avaliar_benchmarks, BENCHMARKS_RO


def test_classificar_faixa_normal_abaixo():
    faixas = {'abaixo': 65.0, 'medio': 78.0, 'bom': 88.0}
    faixa, proximo, falta = _classificar_faixa(60.0, faixas)
    assert faixa == 'abaixo'
    assert proximo == 'medio'
    assert falta == 5.0


def test_classificar_faixa_normal_medio():
    faixas = {'abaixo': 65.0, 'medio': 78.0, 'bom': 88.0}
    faixa, proximo, falta = _classificar_faixa(70.0, faixas)
    assert faixa == 'medio'
    assert proximo == 'bom'
    assert falta == 8.0


def test_classificar_faixa_normal_bom():
    faixas = {'abaixo': 65.0, 'medio': 78.0, 'bom': 88.0}
    faixa, proximo, falta = _classificar_faixa(82.0, faixas)
    assert faixa == 'bom'
    assert proximo == 'excelente'
    assert falta == 6.0


def test_classificar_faixa_normal_excelente():
    faixas = {'abaixo': 65.0, 'medio': 78.0, 'bom': 88.0}
    faixa, proximo, falta = _classificar_faixa(90.0, faixas)
    assert faixa == 'excelente'
    assert proximo is None
    assert falta == 0.0


def test_classificar_faixa_inverso_abaixo():
    # mortalidade: menor é melhor
    faixas = {'abaixo': 5.0, 'medio': 3.0, 'bom': 1.5}
    faixa, proximo, falta = _classificar_faixa(6.0, faixas, inverso=True)
    assert faixa == 'abaixo'
    assert proximo == 'medio'
    assert falta == 1.0


def test_classificar_faixa_inverso_excelente():
    faixas = {'abaixo': 5.0, 'medio': 3.0, 'bom': 1.5}
    faixa, proximo, falta = _classificar_faixa(1.0, faixas, inverso=True)
    assert faixa == 'excelente'
    assert falta == 0.0


def test_avaliar_benchmarks_cria_filtra_ciclo():
    indicadores = {
        'natalidade': 75.0, 'mortalidade': 3.0, 'desmama': 80.0,
        'relacao_fm': 2.2, 'pct_matrizes': 35.0,
        'ganho_peso_arr': 0.7, 'rend_carcaca': 52.0,
    }
    resultado = avaliar_benchmarks('CRIA', indicadores)
    keys = [r['key'] for r in resultado]
    # CRIA não deve incluir ganho_peso_arr (só RECRIA)
    assert 'ganho_peso_arr' not in keys
    # CRIA deve incluir natalidade e pct_matrizes
    assert 'natalidade' in keys
    assert 'pct_matrizes' in keys


def test_avaliar_benchmarks_engorda_filtra_ciclo():
    indicadores = {
        'natalidade': 75.0, 'mortalidade': 2.0, 'rend_carcaca': 53.0,
        'ganho_peso_arr': 0.7, 'relacao_fm': 2.0, 'pct_matrizes': 30.0,
        'desmama': 80.0,
    }
    resultado = avaliar_benchmarks('ENGORDA', indicadores)
    keys = [r['key'] for r in resultado]
    assert 'rend_carcaca' in keys
    assert 'natalidade' not in keys
    assert 'ganho_peso_arr' not in keys


def test_avaliar_benchmarks_retorna_estrutura_correta():
    indicadores = {'natalidade': 75.0, 'mortalidade': 3.0, 'desmama': 82.0,
                   'relacao_fm': 2.0, 'pct_matrizes': 30.0}
    resultado = avaliar_benchmarks('CRIA', indicadores)
    assert len(resultado) > 0
    item = resultado[0]
    assert 'key' in item
    assert 'label' in item
    assert 'valor' in item
    assert 'unidade' in item
    assert 'faixa' in item
    assert 'proximo_nivel' in item
    assert 'falta' in item


from ml_engine import simular_cenario, calcular_breakeven_simples, calcular_ano


def test_simular_cria_retorna_breakeven():
    v = [300, 280, 200, 80, 100, 40, 150, 10, 600, 15]
    result = simular_cenario(v, 'crescimento', ciclo='CRIA', preco_arroba_bezerro=300,
                             nat_pct=75, mort_pct=3, desmama_pct=80,
                             venda_bez_pct=60, custo_arroba=57)
    assert 'preco_breakeven' in result
    assert result['preco_breakeven'] > 0
    assert result['preco_breakeven_unidade'] == 'R$/cabeça'
    assert 'slider_units' in result
    assert 'slider_custo_ano1' in result
    assert 'margem_atual_pct' in result


def test_simular_engorda_retorna_breakeven():
    v = [10, 8, 20, 18, 50, 80, 20, 120, 10, 400]
    result = simular_cenario(v, 'crescimento', ciclo='ENGORDA', preco_arroba=330,
                             mort_pct=2, peso_entrada_kg=300, peso_saida_kg=520,
                             rendimento_carcaca=52, custo_arroba=57, dias_engorda=90)
    assert 'preco_breakeven' in result
    # memorial §7/§12: receita sobre peso TOTAL na saída (não ganho) —
    # breakeven em R$/arroba comparável diretamente ao preço de mercado.
    assert result['preco_breakeven_unidade'] == 'R$/arroba'
    assert result['preco_breakeven'] < result['preco_usado']  # deve ser lucrativo
    assert result['preco_breakeven'] > 0


def test_simular_recria_retorna_breakeven():
    v = [50, 45, 80, 70, 400, 600, 100, 80, 80, 20]
    result = simular_cenario(v, 'crescimento', ciclo='RECRIA', preco_arroba=300,
                             mort_pct=2, peso_entrada_arr=8, peso_saida_arr=14,
                             meses_recria=12, custo_arroba=57)
    assert 'preco_breakeven' in result
    # memorial §6/§12: receita sobre peso TOTAL na saída (não ganho)
    assert result['preco_breakeven_unidade'] == 'R$/arroba'


def test_simular_ciclo_completo_retorna_breakeven():
    v = [300, 280, 400, 200, 900, 1200, 250, 80, 600, 40]
    result = simular_cenario(v, 'crescimento')
    assert 'preco_breakeven' in result
    assert result['preco_breakeven'] > 0


def test_calcular_breakeven_simples_cria():
    v = [300, 280, 200, 80, 100, 40, 150, 10, 600, 15]
    result = calcular_breakeven_simples(v, 'CRIA')
    assert 'preco_breakeven' in result
    assert result['unidade'] == 'R$/cabeça'
    assert result['preco_breakeven'] > 0


def test_calcular_breakeven_simples_engorda():
    v = [10, 8, 20, 18, 50, 80, 20, 120, 10, 400]
    result = calcular_breakeven_simples(v, 'ENGORDA')
    assert result['unidade'] == 'R$/arroba'
    assert result['preco_breakeven'] > 0


def test_calcular_ano_pesos_separados():
    r = calcular_ano(
        matrizes=500, femeas_024=300, machos_024=200, bois=20,
        nat_pct=0.75, desc_mat_pct=0.30, prop_boi=30, renov_boi_pct=0.20,
        venda_bez_pct=0.30, mort_pct=0.03,
        preco_arroba=350.0, custo_arroba=57.0,
        peso_boi=20.0, peso_vaca=17.0, peso_bezerra=8.0, peso_garrote=13.0,
    )
    assert r['receita'] > 0
    bois_vend = r['bois_vendidos']
    desc_mat  = r['descarte_matrizes']
    bez_vend  = r['bezerras_vendidas']
    mac_vend  = r['machos_024_vendidos']
    # Machos jovens excedentes (garrotes, mais próximos de 25m) valem mais
    # por cabeça que bezerras recém-desmamadas — pesos diferenciados.
    esperado  = (bois_vend * 20 + desc_mat * 17 + bez_vend * 8 + mac_vend * 13) * 350
    assert abs(r['receita'] - esperado) < 1.0


def test_calcular_ano_sem_peso_arroba():
    import inspect
    sig = inspect.signature(calcular_ano)
    assert 'peso_arroba' not in sig.parameters
    assert 'peso_boi'     in sig.parameters
    assert 'peso_vaca'    in sig.parameters
    assert 'peso_bezerra' in sig.parameters


def test_simular_cenario_ciclo_completo_peso_boi_vaca():
    v = [300, 280, 400, 200, 900, 1200, 250, 80, 600, 40]
    r1 = simular_cenario(v, 'crescimento', peso_boi=20.0, peso_vaca=17.0)
    r2 = simular_cenario(v, 'crescimento', peso_boi=25.0, peso_vaca=22.0)
    assert r2['acumulado']['receita'] > r1['acumulado']['receita']
