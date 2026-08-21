"""Receita e custo da lavoura perene — e o buraco da formação.

O custo de um rebanho é por cabeça. O de uma lavoura perene é por hectare E
POR ESTÁGIO: o talhão em formação consome caixa durante anos sem devolver uma
saca. Um custo médio por hectare dilui esse buraco e faz a operação parecer
mais folgada do que é — justamente no período em que ela precisa de carência.

Como na fase 1, preço e custo ausentes não são estimados. As curvas e valores
aqui exercitam o mecanismo; não afirmam agronomia nem praça.
"""
import pytest

from services.perennial_engine import (
    ALTA, CurvaProdutividade, PerennialState, Talhao,
    calcular_custo, calcular_receita, project_perennial_production,
    resultado_economico,
)

CAFE = CurvaProdutividade(
    cultura='CAFE', produtividade_plena=30, unidade='saca_60kg',
    fatores={1: 0, 2: 0, 3: 0.4, 4: 0.8, 5: 1.0}, bienalidade=0.15)

CANA = CurvaProdutividade(
    cultura='CANA', produtividade_plena=90, unidade='tonelada',
    fatores={1: 0, 2: 1.0, 3: 0.9, 4: 0.8, 5: 0.7, 6: 0.6}, ciclo_anos=6)

CUSTO_CAFE = {'formacao': 14000, 'producao': 9000, 'por_unidade': 120}


def _projetar(*talhoes, curvas=None, ano_base=2026, years=6):
    estado = PerennialState(talhoes=tuple(talhoes), ano_base=ano_base)
    return project_perennial_production(estado, curvas or {'CAFE': CAFE}, years=years)


# ── Receita ─────────────────────────────────────────────────────────────────

def test_receita_de_saca_e_de_tonelada_saem_do_preco_declarado():
    """Cada cultura tem sua unidade; o preço é por unidade da curva."""
    projecao = _projetar(
        Talhao('CAFE', 10, 2021, 'C1', ALTA), Talhao('CANA', 100, 2024, 'K1'),
        curvas={'CAFE': CAFE, 'CANA': CANA}, years=1)

    r = calcular_receita(projecao['anos'][0], {'CAFE': 1400, 'CANA': 130})

    assert r['receita_por_cultura']['CAFE'] == pytest.approx(345.0 * 1400)
    assert r['receita_por_cultura']['CANA'] == pytest.approx(9000.0 * 130)
    assert r['receita_total'] == pytest.approx(345.0 * 1400 + 9000.0 * 130)
    assert r['valid'] is True


def test_cultura_sem_preco_nao_vira_receita():
    projecao = _projetar(
        Talhao('CAFE', 10, 2021, 'C1', ALTA), Talhao('CANA', 100, 2024, 'K1'),
        curvas={'CAFE': CAFE, 'CANA': CANA}, years=1)

    r = calcular_receita(projecao['anos'][0], {'CAFE': 1400})

    assert r['valid'] is False
    assert r['sem_preco'] == ('CANA',)
    assert r['receita_total'] == pytest.approx(345.0 * 1400)


# ── Custo por estágio ───────────────────────────────────────────────────────

def test_talhao_em_formacao_tem_custo_e_nao_tem_receita():
    """O caso que o financiamento de formação existe para cobrir."""
    projecao = _projetar(Talhao('CAFE', 20, 2025, 'novo', ALTA), years=1)
    linha = projecao['anos'][0]

    receita = calcular_receita(linha, {'CAFE': 1400})
    custo = calcular_custo(linha, {'CAFE': CUSTO_CAFE})

    assert linha['producao_total'] == 0.0
    assert receita['receita_total'] == 0.0
    assert custo['custo_por_estagio']['formacao'] == pytest.approx(20 * 14000)
    assert custo['custo_por_estagio']['producao'] == 0.0
    # Formação é investimento que ainda não devolve, não manutenção de lavoura.
    assert custo['custo_investimento'] == pytest.approx(20 * 14000)
    assert custo['custo_manutencao'] == 0.0


def test_custo_separa_os_estagios_no_mesmo_ano():
    projecao = _projetar(
        Talhao('CAFE', 10, 2021, 'velho', ALTA),
        Talhao('CAFE', 20, 2025, 'novo', ALTA), years=1)

    custo = calcular_custo(projecao['anos'][0], {'CAFE': CUSTO_CAFE})

    assert custo['custo_por_estagio']['producao'] == pytest.approx(10 * 9000)
    assert custo['custo_por_estagio']['formacao'] == pytest.approx(20 * 14000)
    assert custo['custo_colheita'] == pytest.approx(345.0 * 120)
    assert custo['custo_operacional'] == pytest.approx(
        10 * 9000 + 20 * 14000 + 345.0 * 120)


def test_custo_de_colheita_acompanha_a_producao_nao_a_area():
    """Cafezal de carga baixa colhe menos e gasta menos para colher."""
    projecao = _projetar(Talhao('CAFE', 10, 2021, 'C1', ALTA), years=2)

    alta = calcular_custo(projecao['anos'][0], {'CAFE': CUSTO_CAFE})
    baixa = calcular_custo(projecao['anos'][1], {'CAFE': CUSTO_CAFE})

    assert alta['custo_colheita'] > baixa['custo_colheita']
    assert alta['custo_por_estagio']['producao'] == baixa['custo_por_estagio']['producao']


def test_estagio_sem_custo_declarado_nao_e_estimado():
    projecao = _projetar(Talhao('CAFE', 20, 2025, 'novo', ALTA), years=1)

    custo = calcular_custo(projecao['anos'][0], {'CAFE': {'producao': 9000}})

    assert custo['valid'] is False
    assert custo['sem_custo'] == ('CAFE/formacao',)
    assert any('custo zero' in aviso for aviso in custo['warnings'])


# ── A série anual ───────────────────────────────────────────────────────────

def test_a_formacao_derruba_o_resultado_e_o_motor_aponta_a_carencia():
    """Ano negativo em perene não é sinal de recusa — é sinal de carência."""
    projecao = _projetar(
        Talhao('CAFE', 10, 2021, 'velho', ALTA),
        Talhao('CAFE', 20, 2025, 'novo', ALTA))

    r = resultado_economico(projecao, {'CAFE': 1400}, {'CAFE': CUSTO_CAFE})

    assert r['anos_negativos'] == (2,)
    assert r['ano_pior_resultado'] == 2
    assert any('carência' in aviso for aviso in r['avisos'])
    # O talhão novo começa a produzir no ano 3 e vira o jogo.
    assert r['anos'][2]['resultado'] > r['anos'][1]['resultado']


def test_a_serie_tem_a_mesma_forma_da_projecao_pecuaria():
    """Fluxo mensal, DSCR e stress consomem sem saber de que lavoura veio."""
    projecao = _projetar(Talhao('CAFE', 10, 2021, 'C1', ALTA))

    r = resultado_economico(projecao, {'CAFE': 1400}, {'CAFE': CUSTO_CAFE})

    for ano in r['anos']:
        assert {'receita', 'custo', 'resultado'} <= set(ano)
    assert r['acumulado']['resultado'] == pytest.approx(
        r['acumulado']['receita'] - r['acumulado']['custo'])


def test_projecao_invalida_contamina_o_resultado():
    """Curva faltando na fase 1 não pode virar resultado válido na fase 2."""
    projecao = _projetar(
        Talhao('CAFE', 10, 2021, 'C1', ALTA), Talhao('LARANJA', 8, 2020, 'L1'),
        years=2)

    r = resultado_economico(projecao, {'CAFE': 1400}, {'CAFE': CUSTO_CAFE})

    assert projecao['valido'] is False
    assert r['valido'] is False
