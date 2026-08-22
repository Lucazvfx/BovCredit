"""Lavoura perene: a produção de cada ano, e o ano que decide o parecer.

Numa cultura anual a receita é um número por ano. Numa perene não é: o que um
talhão produz depende da idade dele, e o ano apertado do contrato raramente é o
ano 1. Café alterna carga alta e baixa; a soqueira da cana decai a cada corte
até a reforma, quando o talhão não produz nada.

Um DSCR calculado sobre o ano 1 de um cafezal em carga alta aprova operação que
quebra no ano seguinte. É esse erro que estes testes travam.

Nenhum número agronômico aqui é afirmação do projeto: as curvas são entrada
declarada, escolhidas para exercitar o mecanismo. Curva real entra pelo caminho
da proveniência, com fonte citável.
"""
import pytest

from services.perennial_engine import (
    ALTA, BAIXA, CurvaProdutividade, PerennialState, Talhao,
    project_perennial_production,
)

CAFE = CurvaProdutividade(
    cultura='CAFE', produtividade_plena=30, unidade='saca_60kg',
    fatores={1: 0, 2: 0, 3: 0.4, 4: 0.8, 5: 1.0}, bienalidade=0.15)

CANA = CurvaProdutividade(
    cultura='CANA', produtividade_plena=90, unidade='tonelada',
    fatores={1: 0, 2: 1.0, 3: 0.9, 4: 0.8, 5: 0.7, 6: 0.6}, ciclo_anos=6)


def _cafezal(*talhoes, ano_base=2026, years=6):
    estado = PerennialState(talhoes=tuple(talhoes), ano_base=ano_base)
    return project_perennial_production(estado, {'CAFE': CAFE}, years=years)


# ── O ano crítico ───────────────────────────────────────────────────────────

def test_cafe_alterna_carga_e_o_ano_critico_nao_e_o_primeiro():
    """O erro que o parecer cometeria olhando só o ano 1 de carga alta."""
    r = _cafezal(Talhao('CAFE', 10, 2021, 'T1', ALTA))

    producoes = [linha['producao_total'] for linha in r['anos']]
    assert producoes == [345.0, 255.0, 345.0, 255.0, 345.0, 255.0]
    assert r['ano_menor_producao'] == 2
    assert r['producao_no_ano_menor'] == 255.0


def test_cana_decai_a_cada_corte_ate_a_reforma():
    estado = PerennialState(talhoes=(Talhao('CANA', 100, 2024, 'C1'),), ano_base=2026)
    r = project_perennial_production(estado, {'CANA': CANA}, years=6)

    assert [l['producao_total'] for l in r['anos']] == [
        9000.0, 8100.0, 7200.0, 6300.0, 5400.0, 0.0]
    assert [l['talhoes'][0]['idade'] for l in r['anos']] == [2, 3, 4, 5, 6, 1]
    assert r['anos'][-1]['talhoes'][0]['estagio'] == 'reforma'


def test_o_ano_de_reforma_conta_como_ano_critico():
    """Esconder o ano sem produção devolveria um crítico confortável demais."""
    estado = PerennialState(talhoes=(Talhao('CANA', 100, 2024, 'C1'),), ano_base=2026)
    r = project_perennial_production(estado, {'CANA': CANA}, years=6)

    assert r['ano_menor_producao'] == 6
    assert r['producao_no_ano_menor'] == 0.0
    assert any('não produz' in aviso for aviso in r['avisos'])


# ── A soma dos talhões ──────────────────────────────────────────────────────

def test_a_soma_dos_talhoes_bate_com_a_conta_manual():
    """Talhões de idades diferentes no mesmo ano — o caso real de um cafezal."""
    r = _cafezal(
        Talhao('CAFE', 10, 2021, 'velho', ALTA),   # idade 5 -> fator 1,0
        Talhao('CAFE', 20, 2023, 'novo', ALTA),    # idade 3 -> fator 0,4
        Talhao('CAFE', 5, 2025, 'formando', ALTA), # idade 1 -> fator 0
        years=1)

    esperado = (10 * 30 * 1.0 + 20 * 30 * 0.4 + 5 * 30 * 0) * 1.15
    assert r['anos'][0]['producao_total'] == pytest.approx(esperado)
    assert r['anos'][0]['area_produtiva_ha'] == 30.0
    assert r['anos'][0]['area_em_formacao_ha'] == 5.0
    assert r['area_total_ha'] == 35.0


def test_talhao_ainda_nao_plantado_nao_produz():
    r = _cafezal(Talhao('CAFE', 10, 2030, 'futuro'), years=2)

    assert [l['producao_total'] for l in r['anos']] == [0.0, 0.0]
    assert r['anos'][0]['talhoes'][0]['estagio'] == 'nao_plantado'


# ── Bienalidade escalonada ──────────────────────────────────────────────────

def test_talhoes_em_fases_opostas_suavizam_a_lavoura():
    """Escalonar a carga é decisão de manejo com efeito direto no DSCR."""
    alinhado = _cafezal(
        Talhao('CAFE', 10, 2021, 'A', ALTA),
        Talhao('CAFE', 10, 2021, 'B', ALTA))
    escalonado = _cafezal(
        Talhao('CAFE', 10, 2021, 'A', ALTA),
        Talhao('CAFE', 10, 2021, 'B', BAIXA))

    assert alinhado['producao_acumulada'] == pytest.approx(
        escalonado['producao_acumulada'])
    # O total do período é o mesmo; o que muda é o fundo do poço.
    assert escalonado['producao_no_ano_menor'] > alinhado['producao_no_ano_menor']


def test_lavoura_alinhada_recebe_aviso():
    r = _cafezal(Talhao('CAFE', 10, 2021, 'A', ALTA), Talhao('CAFE', 10, 2021, 'B', ALTA))

    assert any('mesma fase de carga' in aviso for aviso in r['avisos'])


# ── O que o motor recusa fazer ──────────────────────────────────────────────

def test_cultura_sem_curva_nao_e_estimada():
    """Chutar a curva produziria um DSCR com cara de cálculo e conteúdo de palpite."""
    estado = PerennialState(
        talhoes=(Talhao('CAFE', 10, 2021, 'T1', ALTA), Talhao('LARANJA', 8, 2020, 'T2')),
        ano_base=2026)

    r = project_perennial_production(estado, {'CAFE': CAFE}, years=3)

    assert r['valido'] is False
    assert r['sem_curva'] == ('LARANJA',)
    assert any('LARANJA' in aviso for aviso in r['avisos'])
    # O café continua projetado; só a laranja fica de fora.
    assert r['anos'][0]['producao_total'] == pytest.approx(345.0)


def test_curva_sem_fatores_e_recusada_na_origem():
    with pytest.raises(ValueError, match='sem fatores'):
        CurvaProdutividade(cultura='CAFE', produtividade_plena=30,
                           unidade='saca_60kg', fatores={})


def test_area_invalida_e_recusada():
    with pytest.raises(ValueError, match='área inválida'):
        Talhao('CAFE', 0, 2021, 'T1')


def test_lavoura_sem_talhao_e_recusada():
    with pytest.raises(ValueError, match='sem talhões'):
        PerennialState(talhoes=(), ano_base=2026)


# ── Extrapolação ────────────────────────────────────────────────────────────

def test_idade_acima_da_curva_declarada_mantem_o_ultimo_ponto():
    """Extrapolar para cima seria inventar produtividade que ninguém declarou."""
    assert CAFE.fator(5) == 1.0
    assert CAFE.fator(40) == 1.0
    assert CAFE.fator(0) == 0.0
