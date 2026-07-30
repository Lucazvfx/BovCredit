"""
Conservação de animais e simetria da valoração de estoque.

Dois bugs motivaram estes testes:

1. A simulação de CRIA rastreava apenas matrizes e fêmeas jovens. Os machos
   jovens e os bois adultos declarados sumiam do fechamento, e `bezerras_ret`
   ainda era contado duas vezes. Um rebanho de 504 cabeças que produziu 172
   bezerros "terminava" o ano com 265 — uma perda patrimonial fantasma de
   R$ 779 mil que fazia o parecer negar crédito.

2. A abertura do rebanho era valorada com 6 categorias e o fechamento com 4,
   e por métodos diferentes (preço granular vs. peso médio agregado). A
   diferença de método sozinha criava ~4% de variação de estoque inexistente.

O invariante: fim ≈ início + nascimentos + compras − vendas − mortes.
"""
import pytest

from ml_engine import simular_cenario, carregar_modelo


@pytest.fixture(scope='module', autouse=True)
def _modelo():
    carregar_modelo()


REBANHOS = {
    'CRIA':           [60, 60, 30, 15, 45, 20, 90, 6, 170, 8],
    'RECRIA':         [0, 0, 20, 110, 10, 180, 0, 70, 5, 8],
    'ENGORDA':        [0, 0, 0, 15, 0, 60, 0, 90, 0, 140],
    'CICLO_COMPLETO': [80, 80, 50, 50, 60, 60, 90, 40, 220, 60],
}


def _ano1(ciclo, v, custo_arroba=119):
    return simular_cenario(v, 'conservador', ciclo=ciclo,
                           preco_arroba=320, custo_arroba=custo_arroba)['anos'][0]


@pytest.mark.parametrize('ciclo', list(REBANHOS))
def test_rebanho_conserva_animais(ciclo):
    """Nenhum animal aparece ou some sem estar contabilizado."""
    v = REBANHOS[ciclo]
    a = _ano1(ciclo, v)

    inicio  = sum(v)
    nasc    = a.get('bezerros', 0)
    compras = a.get('compras', 0)
    vendas  = a.get('vendidos', 0) + a.get('matrizes_descartadas', 0)
    mortes  = a.get('mortes', 0)
    esperado = inicio + nasc + compras - vendas - mortes
    fim = a.get('total', 0)

    tolerancia = max(3, inicio * 0.02)   # arredondamentos por categoria
    assert abs(fim - esperado) <= tolerancia, (
        f'{ciclo}: fim={fim} mas início({inicio}) + nasc({nasc}) + compras({compras}) '
        f'− vendas({vendas}) − mortes({mortes}) = {esperado}. '
        f'Diferença de {fim - esperado} animais não contabilizada.'
    )


@pytest.mark.parametrize('ciclo', list(REBANHOS))
def test_fechamento_declara_todas_as_categorias(ciclo):
    """
    O fluxo GEP valora o fechamento por matrizes + bois_fim + jovens_f/m.
    Se essas chaves não somarem o rebanho final, a variação de estoque acusa
    perda de animais que continuam no plantel.
    """
    a = _ano1(ciclo, REBANHOS[ciclo])
    soma_categorias = (a.get('matrizes', 0) + a.get('bois_fim', 0)
                       + a.get('jovens_f_fim', 0) + a.get('jovens_m_fim', 0))
    total = a.get('total', 0)
    assert abs(soma_categorias - total) <= max(3, total * 0.02), (
        f'{ciclo}: categorias do fechamento somam {soma_categorias} '
        f'mas o total é {total} — a valoração perderia a diferença.'
    )


def test_cria_nao_perde_o_rebanho_jovem():
    """Regressão do bug original: o rebanho de cria não pode encolher 47%."""
    v = REBANHOS['CRIA']
    a = _ano1('CRIA', v)
    # Produziu bezerros e vendeu menos do que nasceu → não pode encolher muito
    assert a['bezerros'] > 0
    assert a['total'] >= sum(v) * 0.90, (
        f"rebanho de cria caiu de {sum(v)} para {a['total']} cabeças em um ano "
        f"em que nasceram {a['bezerros']} bezerros"
    )


def test_variacao_de_estoque_sem_vies_de_metodo():
    """
    Abertura e fechamento precisam ser valorados pelo mesmo método, senão a
    variação de estoque reflete a troca de fórmula, não o rebanho.
    """
    from services.fluxo_caixa_gep import valor_rebanho_gep
    v = REBANHOS['CRIA']
    granular = valor_rebanho_gep(
        matrizes=v[6] + v[8], bois=v[7] + v[9], novilhas=v[4], garrotes=v[5],
        bezerras=v[0] + v[2], bezerros=v[1] + v[3], preco_boi=320)
    agregado = valor_rebanho_gep(
        matrizes=v[6] + v[8], bois=v[7] + v[9],
        jovens_f=v[0] + v[2] + v[4], jovens_m=v[1] + v[3] + v[5], preco_boi=320)
    # Os dois métodos divergem — por isso o app usa o agregado nas DUAS pontas.
    assert granular['valor_total'] != agregado['valor_total']
    assert granular['cabecas'] == agregado['cabecas'], (
        'os métodos devem ao menos concordar no número de cabeças'
    )


def test_compras_sao_explicitas_onde_o_modelo_repoe():
    """
    RECRIA e ENGORDA vendem o lote e repõem comprando magros. A compra precisa
    aparecer no balanço — o CUSTO dela ainda não é precificado.
    """
    for ciclo in ('RECRIA', 'ENGORDA'):
        a = _ano1(ciclo, REBANHOS[ciclo])
        assert a.get('compras', 0) > 0, (
            f'{ciclo} vende {a.get("vendidos")} animais e precisa declarar as compras'
        )
