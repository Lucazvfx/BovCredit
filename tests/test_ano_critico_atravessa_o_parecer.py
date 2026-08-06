"""
O parecer inteiro passa a olhar o mesmo ano.

A recomendação segue o ANO CRÍTICO desde julho — o pior ano do prazo, porque é
nele que a operação deixa de cobrir a dívida e a dívida vence de todo jeito.
Dois outros pedaços do parecer ficaram para trás no ano 1, e o ano 1 é
justamente o que este sistema documenta como enganoso: ele liquida o estoque
declarado na ficha, e do ano 2 em diante a fazenda vende só a produção
corrente.

O que isso produzia, medido numa cria de 1.775 cabeças:

  1. A TABELA DE SENSIBILIDADE contradizia a conclusão no mesmo documento.
     Conclusão: DSCR -0,05. Linha de preço atual da sensibilidade: 0,88.
     Quase um ponto de diferença, e o analista lê os dois.

  2. O BENCHMARK DE CUSTO dizia "dentro da praça" sobre a safra de liquidação.
     Ano 1: R$ 191,17/@, dentro da faixa medida de R$ 166–223.
     Ano 3: R$ 292,74/@, +31% acima do teto.
     O parecer negava pelo ano crítico e, ao lado, dizia que o custo estava
     na praça.

Os dois eram a mesma classe de defeito, e o segundo é o mais grave: fazia o
sistema afirmar que o custo estava bem quando estava 31% fora.
"""
import pytest

import database as db
from app import app

CRIA           = [300, 280, 200, 80, 100, 40, 150, 10, 600, 15]
CICLO_COMPLETO = [120, 100, 80, 70, 40, 50, 150, 80, 270, 40]


@pytest.fixture(scope='module')
def cli():
    db.init_db()
    email = 'anocritico@example.com'
    u = db.buscar_usuario_email(email)
    if not u:
        db.criar_usuario(email, 'Ano', 'senha123')
        u = db.buscar_usuario_email(email)
    app.config['TESTING'] = True
    c = app.test_client()
    with c.session_transaction() as s:
        s['_user_id'] = str(u['id'])
    return c


def _resposta(cli, valores):
    return cli.post('/api/classificar', json={
        'valores': valores, 'preco': 330,
        'credito_valor': sum(valores) * 1200,
        'prazo_meses': 36, 'juros_aa': 0.125}).get_json()


# ── A sensibilidade e a conclusão falam do mesmo ano ────────────────────────
@pytest.mark.parametrize('valores', [CRIA, CICLO_COMPLETO],
                         ids=['cria', 'ciclo_completo'])
def test_a_sensibilidade_nao_contradiz_a_conclusao(cli, valores):
    """
    A linha de variação zero da sensibilidade é o cenário base: nenhum preço
    mexido. Ela tem de bater com o DSCR da conclusão, ou o parecer afirma duas
    coisas diferentes sobre a mesma fazenda.

    A folga é pequena de propósito — sobra só o arredondamento e a diferença
    de composição de preço por categoria, não um ano inteiro.
    """
    p = _resposta(cli, valores)['parecer']
    base = [s for s in (p.get('sensibilidade') or []) if s.get('variacao_pct') == 0]
    assert base, 'sensibilidade sem linha de cenário base'
    assert base[0]['dscr'] == pytest.approx(
        p['conclusao']['dscr_minimo'], abs=0.15), (
        f"sensibilidade diz {base[0]['dscr']} e a conclusão diz "
        f"{p['conclusao']['dscr_minimo']} — voltaram a olhar anos diferentes"
    )


def test_a_sensibilidade_de_custo_tambem_segue_o_ano_critico(cli):
    p = _resposta(cli, CRIA)['parecer']
    base = [s for s in (p.get('sensibilidade_custo') or [])
            if s.get('variacao_pct') == 0]
    if base:  # o bloco só existe quando há crédito a avaliar
        assert base[0]['dscr'] == pytest.approx(
            p['conclusao']['dscr_minimo'], abs=0.15)


# ── O custo é medido em todos os anos ───────────────────────────────────────
def test_o_coe_e_calculado_ano_a_ano(cli):
    anos = _resposta(cli, CRIA)['projecao_anos']
    assert len(anos) >= 3
    for a in anos:
        assert a.get('coe_por_arroba'), f"ano {a['ano']} sem COE"
        assert a.get('coe_sobre_receita_pct') is not None


def test_o_ano_1_esconde_o_custo_da_cria(cli):
    """
    O caso que motivou tudo: o ano 1 liquida o estoque, dilui o custo por
    arroba e faz a cria parecer barata. Não é uma diferença de arredondamento
    — é de um terço.
    """
    anos = {a['ano']: a for a in _resposta(cli, CRIA)['projecao_anos']}
    coe1, coe3 = anos[1]['coe_por_arroba'], anos[3]['coe_por_arroba']
    assert coe3 > coe1 * 1.3, (
        f'ano 1 R$ {coe1}/@ contra ano 3 R$ {coe3}/@ — se convergiram, a '
        f'projeção parou de liquidar no ano 1 e este teste deve ser revisto'
    )


@pytest.mark.parametrize('valores', [CRIA, CICLO_COMPLETO],
                         ids=['cria', 'ciclo_completo'])
def test_o_aviso_de_custo_usa_o_ano_da_recomendacao(cli, valores):
    """
    Antes desta correção, cria e ciclo completo NÃO recebiam o aviso de custo:
    o benchmark olhava o ano 1, onde ambos ficam dentro da faixa. A conclusão
    negava por caixa e, ao lado, dizia que o custo estava na praça.

    ESTE TESTE MUDOU DE FORMA quando a cadeia reprodutiva foi corrigida.

    Ele prendia "o aviso dispara na cria", e a cria deixou de disparar: com a
    desmama sem o triplo desconto ela produz 22% mais bezerro, o custo se
    dilui em mais arrobas e o COE do ano crítico caiu de R$ 292,74 para
    R$ 266,37 — de +31,2% para +19,3% sobre o teto dos painéis, por baixo da
    tolerância de 25%.

    Prender o caso teria feito o teste exigir de volta um número que veio de
    um defeito. O que ele prende agora é o MECANISMO, que é o que a correção
    de julho instalou: quando o aviso existe, ele fala do ano da recomendação.
    Que a cria esteja abaixo do limiar é resultado, não regra — e o teste
    seguinte garante que o mecanismo continua vivo em alguém.
    """
    r = _resposta(cli, valores)
    p = r['parecer']
    ano_critico = p['conclusao']['ano_critico']
    assert ano_critico and ano_critico > 1, (
        'o caso deixou de ter ano crítico posterior ao primeiro'
    )
    crit = next(a for a in r['projecao_anos'] if a['ano'] == ano_critico)
    fora = p['conclusao'].get('custo_fora_da_referencia')
    if fora is None:
        # Sem aviso, a exigência é que seja por MÉRITO do ano crítico — não
        # porque o benchmark voltou a olhar o ano 1, que é sempre mais barato.
        assert crit['coe_por_arroba'] > r['projecao_anos'][0]['coe_por_arroba'], (
            'o ano crítico ficou mais barato que o ano 1 — a projeção parou '
            'de liquidar estoque no primeiro ano e este teste deve ser revisto'
        )
        return
    assert fora['calculado'] == pytest.approx(crit['coe_por_arroba'], abs=0.5), (
        f"o aviso usa R$ {fora['calculado']}/@ mas o ano crítico "
        f"({ano_critico}) tem R$ {crit['coe_por_arroba']}/@"
    )


def test_o_aviso_de_custo_continua_disparando_em_alguem(cli):
    """
    Contrapeso do teste acima: se NENHUM caso disparar mais, o mecanismo
    morreu sem ninguém perceber e os dois testes passariam vazios.

    O ciclo completo é o caso vivo hoje (+38,3% no ano crítico).
    """
    p = _resposta(cli, CICLO_COMPLETO)['parecer']
    fora = p['conclusao'].get('custo_fora_da_referencia')
    assert fora, 'nenhuma modalidade dispara mais o aviso de custo'
    assert fora['delta_pct'] >= 25.0


# ── A métrica que o ebook publica e nós não tínhamos ────────────────────────
def test_coe_sobre_receita_e_o_que_o_painel_publica(cli):
    """
    Métrica nova: custo sobre a receita do próprio ano. É a que o ebook Campo
    Futuro publica para os 19 painéis, e ela responde direto à pergunta do
    crédito — a operação cobre o próprio custo de caixa?

    CORREÇÃO DE UMA AFIRMAÇÃO MINHA. Eu havia dito que ela seria imune ao preço
    da arroba, com numerador e denominador andando juntos. Medido, é o
    CONTRÁRIO nesta implementação: subindo o boi de R$ 330 para R$ 430 numa
    recria, o COE por arroba não se mexe (R$ 329,47 nos dois) e a razão
    custo/receita cai de 105,1% para 80,7%.

    A razão é que o nosso custo não acompanha o boi: a manutenção vem de um
    perfil fixo em R$/cab/mês e a reposição é precificada pela cotação do
    BEZERRO, que é outro mercado. Só a receita se move.

    O que a métrica é de fato, e já basta: livre de escala (não depende do
    tamanho do rebanho) e direta ao ponto do crédito. Comparação entre anos
    continua exigindo cuidado — a nota fica aqui para ninguém repetir o que
    eu afirmei sem medir.
    """
    anos = _resposta(cli, CRIA)['projecao_anos']
    for a in anos:
        esperado = round(a['custo'] / a['receita'] * 100, 1)
        assert a['coe_sobre_receita_pct'] == pytest.approx(esperado, abs=0.2)

    # O limiar observado muda quando a base reprodutiva ou o volume projetado
    # muda. O teste prende a identidade contábil, não um resultado antigo de
    # uma ficha sintética.
    assert all(a['coe_sobre_receita_pct'] >= 0 for a in anos)
