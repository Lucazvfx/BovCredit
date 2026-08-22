"""Parecer de lavoura perene ponta a ponta, pela rota.

O que esta fase entrega não é fórmula nova: é o motor de perenes ligado nos
mesmos motores de crédito, fluxo e stress que a análise pecuária usa. O teste
que importa é o do ano crítico — numa perene ele não é o ano 1, e uma análise
que olhasse só o primeiro ano aprovaria crédito que não se paga depois.
"""
import pytest

import database as db
from services.perennial_engine import analisar_lavoura_perene, cenarios_perene_padrao

CURVA_CAFE = {
    'produtividade_plena': 30, 'unidade': 'saca_60kg',
    'fatores': {'1': 0, '2': 0, '3': 0.4, '4': 0.8, '5': 1.0},
    'bienalidade': 0.15,
}
CUSTO_CAFE = {'formacao': 14000, 'producao': 9000, 'por_unidade': 120}


def _payload(**extra):
    base = {
        'ano_base': 2026,
        'anos': 6,
        'talhoes': [
            {'cultura': 'CAFE', 'area_ha': 40, 'ano_plantio': 2021,
             'identificacao': 'A', 'fase_bienal': 'alta'},
        ],
        'curvas': {'CAFE': CURVA_CAFE},
        'precos': {'CAFE': 1400},
        'custos': {'CAFE': CUSTO_CAFE},
        'credito': {
            'credito_valor': 1_500_000, 'prazo_meses': 72, 'juros_aa': 0.105,
            'carencia_meses': 24, 'sistema_amortizacao': 'sac',
            'periodicidade_meses': 12,
        },
    }
    base.update(extra)
    return base


def _login():
    db.init_db()
    email = 'perene@example.com'
    usuario = db.buscar_usuario_email(email)
    if not usuario:
        db.criar_usuario(email, 'Perene', 'senha123')
        usuario = db.buscar_usuario_email(email)
    from app import app
    app.config['TESTING'] = True
    cliente = app.test_client()
    with cliente.session_transaction() as sessao:
        sessao['_user_id'] = str(usuario['id'])
    return cliente


# ── A análise ───────────────────────────────────────────────────────────────

def test_o_ano_critico_do_dscr_nao_e_o_primeiro():
    """O motivo de existir a fase inteira."""
    r = analisar_lavoura_perene(_payload())
    analise = r['credito']['analysis']

    assert analise['pior_periodo']['ano'] > 1
    assert analise['dscr_minimo'] < analise['dscr_medio']
    assert any('não o primeiro' in aviso for aviso in r['avisos'])


def test_a_analise_entrega_dscr_cronograma_fluxo_e_cenarios():
    r = analisar_lavoura_perene(_payload())

    assert r['credito']['analysis']['dscr_minimo'] is not None
    assert r['credito']['analysis']['cronograma_divida']
    assert len(r['fluxo_mensal']['meses']) == 72
    assert r['stress']['scenarios']
    assert len(r['projecao_anos']) == 6


def test_o_pior_ano_do_dscr_e_um_ano_de_carga_baixa():
    """Liga o fenômeno agronômico ao número que vai a comitê."""
    r = analisar_lavoura_perene(_payload())
    pior = r['credito']['analysis']['pior_periodo']['ano']

    linha = next(a for a in r['economico']['anos'] if a['ano'] == pior)
    talhao = next(t for t in r['producao']['anos'][pior - 1]['talhoes'])
    assert talhao['fase_bienal'] == 'baixa'
    assert linha['receita'] < r['economico']['anos'][0]['receita']


# ── Cenários de estresse ────────────────────────────────────────────────────

def test_os_cenarios_sao_da_lavoura_e_nao_do_rebanho():
    """Parecer de cafezal listando "mortalidade_alta" perde credibilidade."""
    nomes = {c['nome'] for c in cenarios_perene_padrao()}

    assert 'quebra_safra' in nomes
    assert not {'natalidade_baixa', 'mortalidade_alta', 'gmd_baixo'} & nomes


def test_quebra_de_safra_derruba_a_receita_sem_mexer_no_preco():
    r = analisar_lavoura_perene(_payload())
    quebra = next(c for c in r['stress']['scenarios'] if c['nome'] == 'quebra_safra')

    assert quebra['applied_changes'] == ['revenue_pct -20%']


# ── A rota ──────────────────────────────────────────────────────────────────

def test_a_rota_devolve_a_analise_completa():
    resposta = _login().post('/api/perene/analisar', json=_payload())

    assert resposta.status_code == 200
    corpo = resposta.get_json()
    assert corpo['valido'] is True
    assert corpo['credito']['analysis']['pior_periodo']['ano'] > 1


def test_a_rota_recusa_lavoura_sem_curva_declarada():
    payload = _payload()
    payload.pop('curvas')

    resposta = _login().post('/api/perene/analisar', json=payload)

    assert resposta.status_code == 400
    assert 'curva' in resposta.get_json()['erro'].lower()


def test_a_rota_recusa_juros_em_percentual():
    """10.5 no lugar de 0.105 devolvia serviço de dívida na casa dos bilhões."""
    payload = _payload()
    payload['credito'] = dict(payload['credito'], juros_aa=10.5)

    resposta = _login().post('/api/perene/analisar', json=payload)

    assert resposta.status_code == 400
    assert 'fração' in resposta.get_json()['erro']


def test_a_rota_recusa_lavoura_sem_talhao():
    payload = _payload()
    payload['talhoes'] = []

    resposta = _login().post('/api/perene/analisar', json=payload)

    assert resposta.status_code == 400


def test_cultura_sem_preco_nao_vira_parecer_valido():
    payload = _payload()
    payload['talhoes'] = payload['talhoes'] + [
        {'cultura': 'CANA', 'area_ha': 100, 'ano_plantio': 2024, 'identificacao': 'K'}]
    payload['curvas'] = dict(payload['curvas'], CANA={
        'produtividade_plena': 90, 'unidade': 'tonelada',
        'fatores': {'1': 0, '2': 1.0, '3': 0.9}, 'ciclo_anos': 6})

    resposta = _login().post('/api/perene/analisar', json=payload)

    assert resposta.status_code == 200
    assert resposta.get_json()['valido'] is False


# ── Conversão de payload ────────────────────────────────────────────────────

def test_idade_da_curva_chega_como_texto_no_json():
    """Sem converter, toda idade daria fator zero e a lavoura pareceria nova."""
    r = analisar_lavoura_perene(_payload())

    assert r['producao']['anos'][0]['producao_total'] > 0
