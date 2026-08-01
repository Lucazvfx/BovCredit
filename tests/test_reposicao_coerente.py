"""
O mesmo animal, comprado e valorado pelo mesmo preço.

O sistema precificava um bezerro desmamado de TRÊS formas, com boi gordo a
R$ 320/@:

    compra pela relação de troca ....... 9,26@  = R$ 2.963
    estoque de fechamento pelo peso .... 6,00@  = R$ 1.920
    cotação de bezerro da interface .... 7,00@  = R$ 2.241

Nenhuma está errada em si. A relação de troca tem fonte de mercado (Notícias
Agrícolas, Scot, Portal DBO); o peso é peso; a cotação é cotação. O defeito é
usar bases DIFERENTES nas duas pontas da mesma transação: cada reposição
criava ou destruía valor no papel sem que nada tivesse acontecido na fazenda.

Medido num rebanho real de 753 cabeças classificado como recria: R$ 1.043 por
cabeça reposta, R$ 215.942 no ano 1 — o bastante para inverter o sinal do
resultado, de −R$ 51.068 para +R$ 90.910.

A regra passa a ser: havendo cotação de bezerro, ela vale para as duas pontas.
A relação de troca fica como fallback, porque é referência de mercado e não
cotação da praça.

NÃO COBERTO AQUI, DE PROPÓSITO

A engorda tem a mesma incoerência em escala menor — compra boi magro a 12,40@
(R$ 3.968) e o estoque valora garrote a 10,67@ (R$ 3.413), R$ 555 de
diferença. Não foi corrigida porque não existe cotação de boi magro no
sistema para ancorar as duas pontas, e escolher um dos dois números sem fonte
seria trocar uma incoerência por um palpite.
"""
import pytest

from ml_engine import simular_cenario, carregar_modelo, CENARIOS
from services.parametros_zootecnicos import (
    TROCA_ARROBAS_BEZERRO, TROCA_ARROBAS_BOI_MAGRO, PESO_GARROTE_ARR,
)

# Rebanho real de 753 cabeças (recria de fêmeas).
REBANHO = [0, 0, 150, 15, 374, 0, 209, 0, 5, 0]
PRECO_ARROBA = 320.0
COTACAO_BEZERRO = 2241.0


@pytest.fixture(scope='module', autouse=True)
def _modelo():
    carregar_modelo()


# O cenário conservador aplica um modificador de preço (0,95) sobre TODAS as
# pontas — venda, estoque e reposição. Ele entra nas contas esperadas abaixo
# porque a coerência que se testa é entre as bases, não a ausência do cenário.
MOD_CONSERVADOR = CENARIOS['conservador']['mods']['preco']


def _ano1(**kw):
    return simular_cenario(REBANHO, cenario='conservador', ciclo='RECRIA',
                           anos=1, preco_arroba=PRECO_ARROBA, **kw)['anos'][0]


def test_cotacao_de_bezerro_manda_na_reposicao():
    """Havendo cotação, ela é o preço — não a relação de troca."""
    a = _ano1(preco_bezerro_cab=COTACAO_BEZERRO)
    esperado = a['compras'] * COTACAO_BEZERRO * MOD_CONSERVADOR
    assert a['custo_reposicao'] == pytest.approx(esperado, rel=0.01)


def test_sem_cotacao_cai_na_relacao_de_troca():
    """
    O fallback continua existindo: sem cotação da praça, a referência de
    mercado é melhor que nada — mas é fallback, não o padrão.
    """
    a = _ano1()
    esperado = (a['compras'] * TROCA_ARROBAS_BEZERRO
                * PRECO_ARROBA * MOD_CONSERVADOR)
    assert a['custo_reposicao'] == pytest.approx(esperado, rel=0.01)


def test_a_diferenca_entre_as_duas_bases_e_material():
    """
    Prende a magnitude: se alguém achar que as duas bases dão no mesmo e
    remover a passagem da cotação, este teste mostra que não dão.
    """
    sem = _ano1()
    com = _ano1(preco_bezerro_cab=COTACAO_BEZERRO)
    assert sem['compras'] == com['compras'], 'o volume não pode mudar'

    delta = sem['custo_reposicao'] - com['custo_reposicao']
    assert delta > 100_000, f'diferença de apenas R$ {delta:,.0f}'

    # A diferença de custo tem de aparecer INTEIRA no resultado — nada da
    # troca de base pode se perder pelo caminho.
    #
    # A primeira versão deste teste prendia "o resultado inverte de sinal".
    # Isso era artefato da configuração de peso da recria vigente na época
    # (saída a 18@), não a propriedade em teste: quando o peso de saída foi
    # corrigido para 13,5@, a receita caiu e os dois lados ficaram negativos
    # sem que nada da coerência de preço tivesse mudado. A asserção abaixo
    # mede o que o teste sempre quis medir e não depende do peso.
    assert com['resultado'] - sem['resultado'] == pytest.approx(delta, rel=0.01)


def test_reposicao_desligada_nao_cobra_nada():
    """`REPOSICAO_PRECIFICADA=0` continua sendo a saída de emergência."""
    import ml_engine
    original = ml_engine._REPOSICAO_PRECIFICADA
    try:
        ml_engine._REPOSICAO_PRECIFICADA = False
        assert _ano1(preco_bezerro_cab=COTACAO_BEZERRO)['custo_reposicao'] == 0.0
    finally:
        ml_engine._REPOSICAO_PRECIFICADA = original


def test_a_incoerencia_da_engorda_segue_conhecida_e_medida():
    """
    Documenta o que NÃO foi corrigido. Se alguém acrescentar cotação de boi
    magro ao sistema, este teste é o lembrete de que há uma ponta esperando.
    """
    diferenca = (TROCA_ARROBAS_BOI_MAGRO - float(PESO_GARROTE_ARR)) * PRECO_ARROBA
    assert diferenca == pytest.approx(555.0, abs=5.0), (
        'a diferença mudou — reavaliar se a correção da engorda ficou viável'
    )
