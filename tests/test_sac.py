"""SAC — amortização constante, o sistema que crédito rural realmente usa.

O motor só tinha Price. Pronaf, Pronamp e custeio agrícola usam SAC, e a
diferença não é acadêmica aqui: no SAC a parcela mais pesada vence logo no
começo, quando o produtor ainda não vendeu a safra. Simular Price onde o
contrato é SAC suaviza a parcela do ano 1 e infla o DSCR do ano mais apertado
— o erro corre a favor de APROVAR.

Os testes verificam PROPRIEDADES da amortização (soma das amortizações =
principal, parcela decrescente, juros sobre saldo), não o que o código
devolve. Uma implementação errada passa por espelho de si mesma; não passa
pela identidade contábil.
"""
import pytest

from services.payment_capacity_engine.dscr import (
    PRICE, SAC,
    credito_maximo,
    cronograma_divida,
    cronograma_price,
    parcela_price,
    parcelas_sac,
)

PV = 1_000_000.0
JUROS = 0.125
PRAZO = 36


def _i_mensal(juros_aa=JUROS):
    return (1 + juros_aa) ** (1 / 12) - 1


# ── Identidade contábil ─────────────────────────────────────────────────────
def test_amortizacoes_somam_exatamente_o_principal():
    """A soma das amortizações tem de fechar o principal — se não fechar, o
    contrato não quita."""
    i = _i_mensal()
    parcelas = parcelas_sac(PV, JUROS, PRAZO)
    # Em cada parcela, a amortização é o que sobra depois dos juros do saldo.
    saldo, amortizado = PV, 0.0
    for p in parcelas:
        juros = saldo * i
        amort = p - juros
        amortizado += amort
        saldo -= amort
    assert amortizado == pytest.approx(PV, rel=1e-9)
    assert saldo == pytest.approx(0.0, abs=1e-6)


def test_amortizacao_e_constante_e_e_isso_que_define_o_sac():
    i = _i_mensal()
    parcelas = parcelas_sac(PV, JUROS, PRAZO)
    saldo = PV
    amortizacoes = []
    for p in parcelas:
        amort = p - saldo * i
        amortizacoes.append(amort)
        saldo -= amort
    assert all(a == pytest.approx(PV / PRAZO, rel=1e-9) for a in amortizacoes)


def test_parcela_e_estritamente_decrescente():
    parcelas = parcelas_sac(PV, JUROS, PRAZO)
    assert len(parcelas) == PRAZO
    assert all(a > b for a, b in zip(parcelas, parcelas[1:]))


def test_primeira_parcela_e_amortizacao_mais_juros_do_principal_cheio():
    i = _i_mensal()
    parcelas = parcelas_sac(PV, JUROS, PRAZO)
    assert parcelas[0] == pytest.approx(PV / PRAZO + PV * i, rel=1e-9)


# ── SAC contra Price ────────────────────────────────────────────────────────
def test_sac_aperta_o_primeiro_ano_mais_que_o_price():
    """O ponto do produto: a primeira parcela do SAC é maior."""
    price = cronograma_divida(PV, JUROS, PRAZO, sistema=PRICE)
    sac = cronograma_divida(PV, JUROS, PRAZO, sistema=SAC)

    assert sac['parcela_primeira'] > price['parcela_mensal']
    assert sac['parcela_ultima'] < price['parcela_mensal']
    # E o serviço do ano 1 — que decide o DSCR do ano mais apertado — é maior.
    assert sac['anos'][0]['servico_nova_operacao'] > price['anos'][0]['servico_nova_operacao']


def test_sac_paga_menos_juros_no_contrato_inteiro():
    price = cronograma_divida(PV, JUROS, PRAZO, sistema=PRICE)
    sac = cronograma_divida(PV, JUROS, PRAZO, sistema=SAC)
    total_price = sum(a['servico_nova_operacao'] for a in price['anos'])
    total_sac = sum(a['servico_nova_operacao'] for a in sac['anos'])
    assert total_sac < total_price


def test_parcela_mensal_do_sac_e_a_primeira_a_maior():
    """Conservador de propósito: é a maior que precisa caber no caixa."""
    sac = cronograma_divida(PV, JUROS, PRAZO, sistema=SAC)
    assert sac['parcela_mensal'] == sac['parcela_primeira']
    assert sac['parcela_mensal'] > sac['parcela_ultima']


# ── Compatibilidade: nada que já existia mudou ──────────────────────────────
def test_default_continua_price():
    sem_sistema = cronograma_divida(PV, JUROS, PRAZO)
    explicito = cronograma_divida(PV, JUROS, PRAZO, sistema=PRICE)
    assert sem_sistema == explicito
    assert sem_sistema['sistema'] == PRICE


def test_cronograma_price_historico_nao_mudou():
    antigo = cronograma_price(PV, JUROS, PRAZO, 6)
    novo = cronograma_divida(PV, JUROS, PRAZO, 6, PRICE)
    assert antigo['parcela_mensal'] == novo['parcela_mensal']
    assert antigo['anos'] == novo['anos']
    # E continua batendo com a fórmula fechada do Price.
    from services.payment_capacity_engine.dscr import principal_apos_carencia
    principal = principal_apos_carencia(PV, JUROS, 6)
    assert antigo['parcela_mensal'] == pytest.approx(
        parcela_price(principal, JUROS, PRAZO - 6), abs=0.01)


def test_sistema_desconhecido_cai_em_price_sem_levantar():
    assert cronograma_divida(PV, JUROS, PRAZO, sistema='xyz')['sistema'] == PRICE
    assert cronograma_divida(PV, JUROS, PRAZO, sistema=None)['sistema'] == PRICE


# ── Carência ────────────────────────────────────────────────────────────────
def test_carencia_capitaliza_no_sac_tambem():
    sem = cronograma_divida(PV, JUROS, 36, 0, SAC)
    com = cronograma_divida(PV, JUROS, 36, 12, SAC)
    assert com['principal_amortizado'] > sem['principal_amortizado']
    # Menos parcelas para amortizar um saldo maior → primeira parcela sobe.
    assert com['parcela_primeira'] > sem['parcela_primeira']


def test_ano_de_carencia_nao_tem_parcela():
    c = cronograma_divida(PV, JUROS, 36, 12, SAC)
    assert c['anos'][0]['parcelas_nova_operacao'] == 0
    assert c['anos'][0]['servico_nova_operacao'] == 0.0
    assert c['anos'][1]['parcelas_nova_operacao'] == 12


def test_soma_das_parcelas_do_cronograma_bate_com_a_lista():
    """O cronograma anual não pode perder nem duplicar parcela."""
    c = cronograma_divida(PV, JUROS, 30, 6, SAC)
    assert sum(a['parcelas_nova_operacao'] for a in c['anos']) == 30 - 6


# ── O inverso: crédito máximo ───────────────────────────────────────────────
def test_credito_maximo_no_sac_e_menor_que_no_price():
    """Para o mesmo caixa, o SAC comporta menos crédito — é a parcela inicial,
    maior, que precisa caber."""
    caixa = 500_000.0
    cap_price = credito_maximo(caixa, JUROS, PRAZO, sistema=PRICE)
    cap_sac = credito_maximo(caixa, JUROS, PRAZO, sistema=SAC)
    assert 0 < cap_sac < cap_price


def test_credito_maximo_e_o_inverso_do_cronograma_no_sac():
    """As duas funções precisam concordar sobre a mesma operação: o crédito
    máximo, posto no cronograma, tem de consumir exatamente o caixa alvo."""
    from services.payment_capacity_engine.dscr import DSCR_APROVAR
    caixa = 500_000.0
    pv = credito_maximo(caixa, JUROS, PRAZO, sistema=SAC)
    c = cronograma_divida(pv, JUROS, PRAZO, sistema=SAC)
    # Serviço do ano 1 (o mais pesado no SAC) contra o caixa que o DSCR alvo
    # deixa disponível.
    servico_alvo = caixa / DSCR_APROVAR
    assert 12 * c['parcela_primeira'] == pytest.approx(servico_alvo, rel=0.01)


# ── Ponta a ponta pela rota ─────────────────────────────────────────────────
def test_a_rota_aceita_sac_e_aperta_o_parecer():
    import database as db
    from app import app

    db.init_db()
    email = 'sacteste@example.com'
    u = db.buscar_usuario_email(email)
    if not u:
        db.criar_usuario(email, 'SAC', 'senha123')
        u = db.buscar_usuario_email(email)
    app.config['TESTING'] = True
    cli = app.test_client()
    with cli.session_transaction() as s:
        s['_user_id'] = str(u['id'])

    base = {
        'valores': [40, 40, 40, 40, 50, 50, 80, 35, 275, 50],
        'preco': 320, 'custo_arroba': 119,
        'credito_valor': 1_000_000, 'prazo_meses': 36, 'juros_aa': 0.125,
    }
    price = cli.post('/api/classificar', json=base).get_json()
    sac = cli.post('/api/classificar',
                   json={**base, 'sistema_amortizacao': 'sac'}).get_json()

    c_price = price['parecer']['conclusao']
    c_sac = sac['parecer']['conclusao']
    assert c_price['sistema_amortizacao'] == 'price'
    assert c_sac['sistema_amortizacao'] == 'sac'
    # A parcela e o serviço do PRIMEIRO ano são maiores no SAC. Isso é
    # aritmética do mesmo PV, prazo e taxa — vale sempre.
    assert c_sac['parcela_mensal'] > c_price['parcela_mensal']
    assert (c_sac['cronograma_divida'][0]['servico_nova_operacao']
            > c_price['cronograma_divida'][0]['servico_nova_operacao'])
    # E o serviço do ÚLTIMO ano é menor, porque a parcela decresce.
    assert (c_sac['cronograma_divida'][-1]['servico_nova_operacao']
            < c_price['cronograma_divida'][-1]['servico_nova_operacao'])


def test_o_dscr_minimo_do_sac_nao_e_necessariamente_pior():
    """Esta é a armadilha: o DSCR mínimo depende de QUAL ano é o crítico.

    Uma versão anterior deste arquivo afirmava que o DSCR mínimo do SAC seria
    sempre menor ou igual ao do Price, "porque a parcela começa maior". Passou
    por acaso, no cenário escolhido. Não é lei.

    Medido num ciclo completo de 700 cabeças, crédito de R$ 600.000:

        ano   caixa      serviço Price   DSCR    serviço SAC   DSCR
          1   636.175          238.580   2,67        260.168   2,45
          2   312.847          238.580   1,31        236.495   1,32
          3   297.568          238.580   1,25        212.823   1,40

    O ano 1 liquida o estoque declarado e sobra caixa; o aperto está no ano 3.
    Lá a parcela do SAC já caiu abaixo da do Price, e o DSCR mínimo do SAC
    fica MELHOR (1,32 contra 1,25) — o ano crítico muda de 3 para 2.

    Ou seja: SAC não é uniformemente mais conservador. Ele desloca o peso para
    o começo, e se o começo for o ano de caixa forte, ajuda. É por isso que o
    parecer avalia todos os anos do prazo em vez do primeiro isolado.
    """
    import database as db
    from app import app

    db.init_db()
    email = 'sacdscr@example.com'
    u = db.buscar_usuario_email(email)
    if not u:
        db.criar_usuario(email, 'SACdscr', 'senha123')
        u = db.buscar_usuario_email(email)
    app.config['TESTING'] = True
    cli = app.test_client()
    with cli.session_transaction() as s:
        s['_user_id'] = str(u['id'])

    base = {
        'valores': [40, 40, 40, 40, 50, 50, 80, 35, 275, 50],
        'preco': 320, 'custo_arroba': 57,
        'credito_valor': 600_000, 'prazo_meses': 36, 'juros_aa': 0.125,
    }
    price = cli.post('/api/classificar', json=base).get_json()
    sac = cli.post('/api/classificar',
                   json={**base, 'sistema_amortizacao': 'sac'}).get_json()

    anos_price = {a['ano']: a for a in price['projecao_anos'] if a['dscr'] is not None}
    anos_sac = {a['ano']: a for a in sac['projecao_anos'] if a['dscr'] is not None}

    # Ano 1: SAC aperta mais — o serviço é maior e o DSCR é menor.
    assert anos_sac[1]['servico_divida_anual'] > anos_price[1]['servico_divida_anual']
    assert anos_sac[1]['dscr'] < anos_price[1]['dscr']
    # Último ano: a parcela do SAC já decresceu abaixo da do Price, e alivia.
    ultimo = max(anos_price)
    assert anos_sac[ultimo]['servico_divida_anual'] < anos_price[ultimo]['servico_divida_anual']
    assert anos_sac[ultimo]['dscr'] > anos_price[ultimo]['dscr']


def test_a_rota_recusa_sistema_invalido():
    import database as db
    from app import app

    db.init_db()
    email = 'sacteste@example.com'
    u = db.buscar_usuario_email(email)
    if not u:
        db.criar_usuario(email, 'SAC', 'senha123')
        u = db.buscar_usuario_email(email)
    app.config['TESTING'] = True
    cli = app.test_client()
    with cli.session_transaction() as s:
        s['_user_id'] = str(u['id'])

    r = cli.post('/api/classificar', json={
        'valores': [40, 40, 40, 40, 50, 50, 80, 35, 275, 50],
        'preco': 320, 'sistema_amortizacao': 'juros_compostos_do_agiota',
    })
    assert r.status_code == 400


# ── A tela ──────────────────────────────────────────────────────────────────
def test_a_tela_deixa_escolher_o_sistema_e_envia():
    """De nada adianta o motor aceitar se o analista não consegue informar."""
    from pathlib import Path
    html = (Path(__file__).parents[1] / 'templates' / 'index.html').read_text(
        encoding='utf-8')

    assert 'id="credito_sistema"' in html
    assert 'value="sac"' in html
    assert "body.sistema_amortizacao=document.getElementById('credito_sistema').value" in html


# ── Periodicidade ───────────────────────────────────────────────────────────
# Crédito rural raramente é mensal: a receita chega na venda do lote, e o
# contrato acompanha. Parcela semestral ou anual muda de novo o perfil de
# caixa — e o `12 × parcela_mensal` que todo o cálculo a jusante faz deixaria
# de valer se `parcela_mensal` virasse a parcela real do período.
from services.payment_capacity_engine.dscr import (  # noqa: E402
    ANUAL, MENSAL, SEMESTRAL, TRIMESTRAL, taxa_do_periodo,
)


def test_taxa_do_periodo_e_composta_nao_proporcional():
    """Um semestre a 12,5% a.a. rende 6,07%, não 6,25%."""
    assert taxa_do_periodo(0.125, SEMESTRAL) == pytest.approx(
        (1.125) ** 0.5 - 1, rel=1e-12)
    assert taxa_do_periodo(0.125, ANUAL) == pytest.approx(0.125, rel=1e-12)
    assert taxa_do_periodo(0.125, MENSAL) == pytest.approx(_i_mensal(), rel=1e-12)


@pytest.mark.parametrize('p,esperado', [(MENSAL, 36), (TRIMESTRAL, 12),
                                        (SEMESTRAL, 6), (ANUAL, 3)])
def test_numero_de_parcelas_sai_da_periodicidade(p, esperado):
    c = cronograma_divida(PV, JUROS, 36, 0, SAC, p)
    assert sum(a['parcelas_nova_operacao'] for a in c['anos']) == esperado


def test_anual_concentra_uma_parcela_por_ano():
    c = cronograma_divida(PV, JUROS, 36, 0, SAC, ANUAL)
    assert [a['parcelas_nova_operacao'] for a in c['anos']] == [1, 1, 1]


def test_semestral_concentra_duas_por_ano():
    c = cronograma_divida(PV, JUROS, 36, 0, SAC, SEMESTRAL)
    assert [a['parcelas_nova_operacao'] for a in c['anos']] == [2, 2, 2]


def test_parcela_mensal_e_equivalente_e_preserva_o_calculo_a_jusante():
    """`12 × parcela_mensal` tem de continuar dando o serviço do ano — é o que
    endividamento e capacidade de pagamento fazem."""
    for p in (MENSAL, TRIMESTRAL, SEMESTRAL, ANUAL):
        c = cronograma_divida(PV, JUROS, 36, 0, PRICE, p)
        assert 12 * c['parcela_mensal'] == pytest.approx(
            c['anos'][0]['servico_nova_operacao'], rel=0.01), f'periodicidade {p}'


def test_parcela_periodica_e_a_de_verdade_e_e_maior_que_a_mensal():
    c = cronograma_divida(PV, JUROS, 36, 0, SAC, ANUAL)
    assert c['parcela_periodica'] == pytest.approx(c['parcela_mensal'] * 12, rel=1e-6)
    assert c['parcela_periodica'] > c['parcela_mensal']


def test_amortizacao_fecha_o_principal_em_qualquer_periodicidade():
    for p in (MENSAL, TRIMESTRAL, SEMESTRAL, ANUAL):
        i = taxa_do_periodo(JUROS, p)
        parcelas = parcelas_sac(PV, JUROS, 36, p)
        saldo = PV
        for parcela in parcelas:
            saldo -= parcela - saldo * i
        assert saldo == pytest.approx(0.0, abs=1e-6), f'periodicidade {p}'


def test_prazo_incompativel_com_a_periodicidade_falha_alto():
    """30 meses com parcela anual não tem interpretação única — recusar é
    melhor que adivinhar."""
    with pytest.raises(ValueError, match='múltiplo da periodicidade'):
        cronograma_divida(PV, JUROS, 30, 0, SAC, ANUAL)


def test_default_continua_mensal():
    assert cronograma_divida(PV, JUROS, 36)['periodicidade_meses'] == MENSAL
    assert cronograma_price(PV, JUROS, 36)['periodicidade_meses'] == MENSAL


def test_credito_maximo_e_o_inverso_em_qualquer_periodicidade():
    from services.payment_capacity_engine.dscr import DSCR_APROVAR
    caixa = 500_000.0
    for p in (MENSAL, TRIMESTRAL, SEMESTRAL, ANUAL):
        pv = credito_maximo(caixa, JUROS, 36, sistema=SAC, periodicidade_meses=p)
        c = cronograma_divida(pv, JUROS, 36, 0, SAC, p)
        assert 12 * c['parcela_mensal'] == pytest.approx(
            caixa / DSCR_APROVAR, rel=0.01), f'periodicidade {p}'


def test_a_rota_aceita_periodicidade_e_recusa_prazo_incompativel():
    import database as db
    from app import app

    db.init_db()
    email = 'sacteste@example.com'
    u = db.buscar_usuario_email(email)
    if not u:
        db.criar_usuario(email, 'SAC', 'senha123')
        u = db.buscar_usuario_email(email)
    app.config['TESTING'] = True
    cli = app.test_client()
    with cli.session_transaction() as s:
        s['_user_id'] = str(u['id'])

    base = {
        'valores': [40, 40, 40, 40, 50, 50, 80, 35, 275, 50],
        'preco': 320, 'custo_arroba': 119,
        'credito_valor': 1_000_000, 'juros_aa': 0.125,
        'sistema_amortizacao': 'sac',
    }
    ok = cli.post('/api/classificar',
                  json={**base, 'prazo_meses': 36, 'periodicidade_meses': 12})
    assert ok.status_code == 200
    assert ok.get_json()['parecer']['conclusao']['periodicidade_meses'] == 12

    ruim = cli.post('/api/classificar',
                    json={**base, 'prazo_meses': 30, 'periodicidade_meses': 12})
    assert ruim.status_code == 400
    assert 'múltiplo' in ruim.get_json()['erro']

    invalida = cli.post('/api/classificar',
                        json={**base, 'prazo_meses': 36, 'periodicidade_meses': 5})
    assert invalida.status_code == 400


def test_a_tela_deixa_escolher_a_periodicidade():
    from pathlib import Path
    html = (Path(__file__).parents[1] / 'templates' / 'index.html').read_text(
        encoding='utf-8')
    assert 'id="credito_periodicidade"' in html
    assert 'value="12"' in html
    assert "body.periodicidade_meses=+document.getElementById('credito_periodicidade').value" in html
