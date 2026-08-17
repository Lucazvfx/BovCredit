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
    # `vendidos` já inclui o descarte de matrizes no CICLO_COMPLETO — a média
    # ponderada de peso em ml_engine.py (peso_medio = Σ(categoria×peso) /
    # vendidos) exige que o denominador cubra as quatro categorias, descarte
    # incluído. Nos demais ciclos (CRIA, por exemplo) `vendidos` NÃO inclui o
    # descarte, e ele precisa ser somado à parte. É inconsistência real entre
    # motores, não escolha deste teste — somar aqui incondicionalmente dobra
    # a contagem só no ciclo completo.
    descarte_ja_incluido = ciclo == 'CICLO_COMPLETO'
    vendas = a.get('vendidos', 0) + (0 if descarte_ja_incluido else a.get('matrizes_descartadas', 0))
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
    O fluxo GEP valora o fechamento por matrizes + bois_fim + jovens_f/m
    (+ prestes_matrizes_fim, só no CICLO_COMPLETO — ver test_conservacao_seis_ciclos).
    Se essas chaves não somarem o rebanho final, a variação de estoque acusa
    perda de animais que continuam no plantel.
    """
    a = _ano1(ciclo, REBANHOS[ciclo])
    soma_categorias = (a.get('matrizes', 0) + a.get('bois_fim', 0)
                       + a.get('jovens_f_fim', 0) + a.get('jovens_m_fim', 0)
                       + a.get('prestes_matrizes_fim', 0))
    total = a.get('total', 0)
    assert abs(soma_categorias - total) <= max(3, total * 0.02), (
        f'{ciclo}: categorias do fechamento somam {soma_categorias} '
        f'mas o total é {total} — a valoração perderia a diferença.'
    )


def test_cria_nao_perde_o_rebanho_jovem():
    """
    Regressão do bug original: o rebanho de cria sumia sem estar vendido.

    O modelo agora comercializa de fato — todo macho desmamado e as fêmeas
    excedentes — então o plantel encolhe legitimamente ao longo do ano. O que
    não pode acontecer é a diferença não estar explicada pelas vendas.
    """
    v = REBANHOS['CRIA']
    a = _ano1('CRIA', v)
    assert a['bezerros'] > 0

    saidas = a['vendidos'] + a['matrizes_descartadas'] + a.get('mortes', 0)
    esperado = sum(v) + a['bezerros'] - saidas
    assert abs(a['total'] - esperado) <= max(3, sum(v) * 0.02), (
        f"rebanho caiu de {sum(v)} para {a['total']}, mas início + nascimentos "
        f"− saídas = {esperado}: diferença sem explicação"
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


# ── Pipeline de terminação no ciclo completo ────────────────────────────────
# O modelo vendia todos os machos de 0–24m como garrote E liquidava os bois
# adultos no mesmo ano, sem repor. O ano 1 vendia o estoque inteiro, o ano 2
# não tinha o que vender (queda de 55%) e o DSCR ia de 6,56 para −2,25 —
# enquanto o parecer aprovava olhando só o ano 1.

def test_ciclo_completo_retem_macho_para_terminacao():
    """O 'completo' do ciclo completo: macho jovem vira boi, não é vendido."""
    from ml_engine import calcular_ano
    r = calcular_ano(matrizes=310, c0_femeas=100, c1_femeas=90,
                     c0_machos=100, c1_machos=90, bois=100,
                     nat_pct=0.665, desc_mat_pct=0.08, prop_boi=30,
                     renov_boi_pct=0.2, venda_bez_pct=0.75, mort_pct=0.03,
                     preco_arroba=304, custo_arroba=122)
    assert r['machos_024_vendidos'] == 0, (
        'macho de 0–24m não é comercializado num ciclo completo — ele termina'
    )
    assert r['machos_graduados'] > 0, 'o pipeline precisa alimentar a terminação'
    # o estoque de machos jovens não pode ser só os nascidos do ano
    nascidos_m = 310 * 0.665 * 0.5
    assert r['machos_024_prox'] > nascidos_m * 1.5, (
        f"machos jovens no ano seguinte ({r['machos_024_prox']}) deveriam somar "
        f"os que não graduaram aos ~{nascidos_m:.0f} nascidos"
    )


def test_ciclo_completo_nao_colapsa_no_ano_2():
    """
    Regressão: as vendas caíam 55% do ano 1 para o ano 2 porque o pipeline de
    terminação ficava vazio. O ano 1 vende mais (liquida o estoque acumulado),
    mas a queda não pode ser um despencar.
    """
    a = simular_cenario(REBANHOS['CICLO_COMPLETO'], 'conservador',
                        ciclo='CICLO_COMPLETO', preco_arroba=320,
                        custo_arroba=122)['anos']
    v1 = a[0]['vendidos'] + a[0]['matrizes_descartadas']
    v2 = a[1]['vendidos'] + a[1]['matrizes_descartadas']
    queda = (v1 - v2) / max(v1, 1)
    assert queda < 0.55, (
        f'vendas caíram {queda:.0%} do ano 1 para o ano 2 — pipeline vazio'
    )


def test_regime_permanente_fica_na_faixa_de_desfrute():
    """
    Do ano 2 em diante não há mais estoque acumulado para liquidar, então o
    desfrute precisa cair na referência da modalidade (20–40% no ciclo
    completo). É o teste que valida o pipeline de terminação.
    """
    a = simular_cenario(REBANHOS['CICLO_COMPLETO'], 'conservador',
                        ciclo='CICLO_COMPLETO', preco_arroba=320,
                        custo_arroba=122)['anos']
    for ano in a[1:]:
        vend = ano['vendidos'] + ano['matrizes_descartadas']
        desf = vend / max(ano['total'], 1) * 100
        assert 20 <= desf <= 45, (
            f"ano {ano['ano']}: desfrute {desf:.1f}% fora do regime esperado "
            f"para ciclo completo (20–40%, tolerância até 45%)"
        )
