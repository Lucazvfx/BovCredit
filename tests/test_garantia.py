"""
Garantia pecuária: valor de execução, não valor de mercado.

O LTV era calculado no frontend contra a cotação cheia do rebanho. Isso
superestima a cobertura, porque rebanho em penhor não se realiza pelo preço do
dia: entre a inadimplência e o caixa há apreensão, transporte, mortalidade no
período e venda forçada. O deságio é o que separa "o boi vale X" de "conseguimos
X se precisarmos executar".
"""
import pytest

from services.fluxo_caixa_gep import valor_rebanho_gep
from services.garantia import (
    avaliar_garantia, DESAGIO_PADRAO, LTV_APROVAR, LTV_RESSALVA,
)


@pytest.fixture
def valoracao():
    return valor_rebanho_gep(
        matrizes=280, bois=90, novilhas=60, garrotes=60,
        bezerras=130, bezerros=130, preco_boi=320)


def test_valor_de_execucao_e_menor_que_o_de_mercado(valoracao):
    """O ponto inteiro do módulo. Se forem iguais, o deságio não foi aplicado."""
    g = avaliar_garantia(valoracao, 1_000_000)
    assert g['valor_garantia'] < g['valor_mercado']
    assert g['desagio_medio_pct'] > 0


def test_desagio_medio_reflete_a_composicao_do_rebanho():
    """
    Um plantel de bois prontos deságia menos que um de bezerros. Se o deságio
    médio não se mover com a composição, ele virou constante e perdeu o sentido.
    """
    so_bois = valor_rebanho_gep(matrizes=0, bois=500, preco_boi=320)
    so_bez  = valor_rebanho_gep(matrizes=0, bois=0, bezerras=500, bezerros=500,
                                preco_boi=320)
    g_bois = avaliar_garantia(so_bois, 1_000_000)
    g_bez  = avaliar_garantia(so_bez, 1_000_000)
    assert g_bois['desagio_medio_pct'] < g_bez['desagio_medio_pct'], (
        'boi pronto para abate é mais líquido que bezerro — o deságio precisa '
        'ser menor'
    )
    assert g_bois['desagio_medio_pct'] == pytest.approx(DESAGIO_PADRAO['bois'] * 100)


def test_ltv_e_medido_sobre_o_valor_desagiado_nao_sobre_o_de_mercado(valoracao):
    """A troca que motivou o módulo — o LTV antigo era otimista por construção."""
    g = avaliar_garantia(valoracao, 1_000_000)
    ltv_ingenuo = 1_000_000 / g['valor_mercado'] * 100
    assert g['ltv'] > ltv_ingenuo, (
        'LTV sobre valor de execução tem que ser MAIOR que sobre valor de '
        'mercado — é o mesmo crédito sobre uma base menor'
    )


@pytest.mark.parametrize('fracao,esperado', [
    (0.40, 'suficiente'),    # bem abaixo do teto
    (0.70, 'ajustada'),      # entre 60% e 80%
    (1.20, 'insuficiente'),  # garantia não cobre
])
def test_veredito_por_faixa_de_ltv(valoracao, fracao, esperado):
    base = avaliar_garantia(valoracao, 1)['valor_garantia']
    g = avaliar_garantia(valoracao, base * fracao)
    assert g['veredito'] == esperado, f"LTV {g['ltv']}% classificado como {g['veredito']}"


def test_credito_maximo_pela_garantia_fecha_no_teto(valoracao):
    """O teto precisa ser exatamente o valor que produz LTV = LTV_APROVAR."""
    g = avaliar_garantia(valoracao, 1)
    teto = g['credito_maximo_garantia']
    no_teto = avaliar_garantia(valoracao, teto)
    assert no_teto['ltv'] == pytest.approx(LTV_APROVAR * 100, abs=0.1)
    assert no_teto['veredito'] == 'suficiente'


def test_sem_credito_avalia_a_garantia_mas_nao_o_ltv(valoracao):
    """O valor de execução interessa mesmo sem pedido em análise."""
    g = avaliar_garantia(valoracao, 0)
    assert g['valor_garantia'] > 0
    assert g['ltv'] is None
    assert g['veredito'] is None


def test_rebanho_vazio_nao_quebra():
    g = avaliar_garantia(valor_rebanho_gep(matrizes=0, bois=0, preco_boi=320), 500_000)
    assert g['valor_garantia'] == 0
    assert g['ltv'] is None


def test_composicao_lista_cada_categoria_com_seu_desagio(valoracao):
    """Sem isso o analista não consegue defender o número no comitê."""
    g = avaliar_garantia(valoracao, 1_000_000)
    assert g['composicao'], 'a composição não pode vir vazia'
    for linha in g['composicao']:
        assert linha['valor_garantia'] < linha['valor_mercado']
        assert linha['rotulo'] and not linha['rotulo'].startswith('valor_')
    soma = sum(l['valor_garantia'] for l in g['composicao'])
    assert soma == pytest.approx(g['valor_garantia'], abs=1.0)


def test_desagio_customizado_e_respeitado(valoracao):
    """A instituição precisa poder calibrar a política sem editar o código."""
    padrao = avaliar_garantia(valoracao, 1_000_000)
    frouxo = avaliar_garantia(valoracao, 1_000_000, desagios={'bois': 0.05})
    assert frouxo['valor_garantia'] > padrao['valor_garantia']


def test_memoria_de_calculo_explica_cada_passo(valoracao):
    g = avaliar_garantia(valoracao, 1_000_000)
    passos = ' '.join(m['passo'] for m in g['memoria'])
    assert 'mercado' in passos.lower()
    assert 'deságio' in passos.lower() or 'desagio' in passos.lower()
    assert 'LTV' in passos
    for m in g['memoria']:
        assert m['detalhe'], f'passo "{m["passo"]}" sem explicação'


def test_faixas_de_politica_sao_coerentes():
    assert 0 < LTV_APROVAR < LTV_RESSALVA < 1
    assert all(0 <= d < 1 for d in DESAGIO_PADRAO.values())
    assert DESAGIO_PADRAO['bois'] == min(DESAGIO_PADRAO.values()), (
        'boi pronto para abate é o ativo mais líquido do rebanho'
    )
