"""
Desfrute real — o indicador que separa vender produção de vender plantel.

O sistema media desfrute como `vendas ÷ rebanho inicial`. É a forma
simplificada, é a base das faixas de referência e é a que a ficha real de
recria usa (declara 45%, a projeção bate 43,4%) — por isso ela continua sendo
a comparada com o benchmark.

O que ela não faz é distinguir duas situações opostas. Uma projeção de ciclo
completo que vendia 2.268 de 4.250 cabeças e fechava o ano com 2.494 marcava
53,4% — dentro da faixa de um bom produtor. Descontadas as compras e a queda
de estoque, o número real era 12,0%: 41 pontos eram plantel virando caixa, e
plantel vendido não se repete no ano seguinte.

Fórmula da literatura (Embrapa / Scot Consultoria):

    desfrute = [(estoque_final − estoque_inicial − compras + vendas)
                ÷ estoque_inicial] × 100
"""
import pytest

from services.benchmarks_nacionais import (
    calcular_desfrute, alerta_liquidacao, DESFRUTE_AFASTAMENTO_ALERTA,
)


# ── A fórmula ───────────────────────────────────────────────────────────────
def test_rebanho_estavel_sem_compra_as_duas_formas_coincidem():
    """
    Com estoque final = inicial e nenhuma compra, a fórmula da literatura se
    reduz a vendas ÷ inicial. É o que garante que o indicador novo não
    contradiga as faixas de referência num rebanho equilibrado.
    """
    d = calcular_desfrute(vendas=300, estoque_inicial=1000,
                          estoque_final=1000, compras=0)
    assert d['simplificado'] == d['real'] == 30.0
    assert d['afastamento'] == 0.0


def test_venda_de_plantel_derruba_o_desfrute_real():
    """O caso medido: ciclo completo de 4.250 fechando o ano em 2.494."""
    d = calcular_desfrute(vendas=2268, estoque_inicial=4250,
                          estoque_final=2494, compras=0)
    assert d['simplificado'] == 53.4
    assert d['real'] == 12.0


def test_compra_nao_conta_como_producao():
    """
    Comprar 300 e vender 300 com o rebanho parado é desfrute zero: nada foi
    produzido. Sem descontar a compra, o indicador marcaria 30%.
    """
    d = calcular_desfrute(vendas=300, estoque_inicial=1000,
                          estoque_final=1000, compras=300)
    assert d['simplificado'] == 30.0
    assert d['real'] == 0.0


def test_sem_estoque_final_a_forma_real_nao_e_inventada():
    d = calcular_desfrute(vendas=300, estoque_inicial=1000)
    assert d['simplificado'] == 30.0
    assert d['real'] is None and d['afastamento'] is None


def test_rebanho_inicial_zero_nao_divide_por_zero():
    d = calcular_desfrute(vendas=10, estoque_inicial=0, estoque_final=5)
    assert d['simplificado'] == 0.0 and d['real'] is None


# ── O alerta ────────────────────────────────────────────────────────────────
def test_alerta_dispara_onde_o_rebanho_deveria_se_reproduzir():
    d = calcular_desfrute(vendas=2268, estoque_inicial=4250,
                          estoque_final=2494, compras=0)
    a = alerta_liquidacao('CICLO_COMPLETO', d)
    assert a is not None
    assert a['severidade'] == 'alerta'
    assert 'plantel' in a['mensagem']


def test_desfrute_real_negativo_e_erro_nao_alerta():
    """Real abaixo de zero significa que o rebanho encolheu mais do que vendeu."""
    d = calcular_desfrute(vendas=200, estoque_inicial=1000,
                          estoque_final=500, compras=0)
    assert d['real'] < 0
    assert alerta_liquidacao('CRIA', d)['severidade'] == 'erro'


@pytest.mark.parametrize('modalidade', ['RECRIA', 'ENGORDA', 'RECRIA_ENGORDA'])
def test_recria_e_engorda_nao_disparam_o_alerta(modalidade):
    """
    Compram uma cabeça e vendem uma cabeça: em número de animais o desfrute
    real é ~zero por construção, porque o que elas produzem é ARROBA. Alertar
    aqui seria ruído em toda análise de confinamento.
    """
    d = calcular_desfrute(vendas=304, estoque_inicial=700,
                          estoque_final=677, compras=304)
    assert d['real'] < 0, 'o caso precisa ser daqueles que alertariam'
    assert alerta_liquidacao(modalidade, d) is None


def test_afastamento_pequeno_nao_alerta():
    """Oscilação normal de plantel não pode virar aviso no parecer."""
    d = calcular_desfrute(vendas=300, estoque_inicial=1000,
                          estoque_final=960, compras=0)
    assert d['afastamento'] < DESFRUTE_AFASTAMENTO_ALERTA
    assert alerta_liquidacao('CRIA', d) is None


# ── Tetos de desfrute: três arquivos, um limiar ─────────────────────────────
# O mesmo teto vive em DESFRUTE_MODALIDADE (benchmarks_nacionais), em
# teto_por_ciclo (BENCHMARKS_RO, ml_engine) e no ponto médio derivado em
# DESFRUTE_PCT (parametros_zootecnicos). Subir um e esquecer os outros produz
# um parecer que alerta e não alerta ao mesmo tempo, dependendo do caminho.

def test_faixa_e_teto_nao_divergem():
    from services.benchmarks_nacionais import DESFRUTE_MODALIDADE
    from ml_engine import BENCHMARKS_RO

    tetos = BENCHMARKS_RO['desfrute']['teto_por_ciclo']
    for modalidade, (_, hi) in DESFRUTE_MODALIDADE.items():
        assert tetos[modalidade] == hi, (
            f'{modalidade}: faixa termina em {hi}% mas o teto que dispara o '
            f'alerta é {tetos[modalidade]}%'
        )


def test_referencia_fica_dentro_da_propria_faixa():
    from services.benchmarks_nacionais import DESFRUTE_MODALIDADE
    from services.parametros_zootecnicos import DESFRUTE_PCT

    for modalidade, (lo, hi) in DESFRUTE_MODALIDADE.items():
        ref = float(DESFRUTE_PCT[modalidade])
        assert lo <= ref <= hi, (
            f'{modalidade}: referência {ref}% fora da faixa {lo}–{hi}%'
        )


def test_bom_desempenho_nao_e_marcado_como_anomalia():
    """
    Uma cria a 35% e um ciclo completo a 45% são bom desempenho pelo setor
    (Scot Consultoria). Antes desta revisão os tetos eram 30% e 40%, e os dois
    casos disparavam alerta — alerta que soa em desempenho bom é alerta que o
    analista aprende a ignorar.
    """
    from ml_engine import BENCHMARKS_RO
    tetos = BENCHMARKS_RO['desfrute']['teto_por_ciclo']
    assert tetos['CRIA'] >= 35.0
    assert tetos['CICLO_COMPLETO'] >= 45.0
