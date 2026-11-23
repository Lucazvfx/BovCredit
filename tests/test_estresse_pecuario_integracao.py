"""Estresse pecuário dentro do parecer e de /api/classificar.

O motor (`stress_engine/pecuaria.py`) tem testes próprios. Aqui se prova a
COLA: campos opcionais, números do ano crítico do DSCR do parecer, entrada
inválida vira 400 (nunca 500) e o isolamento por empresa não muda.
"""
import json
import uuid

import pytest

import database as db
from app import app
from services.parecer_credito import montar_parecer
from services.payment_capacity_engine.dscr import DSCR_APROVAR, DSCR_RESSALVA

CRIA = [300, 280, 200, 80, 100, 40, 150, 10, 600, 15]
ENTRADA = {'preco_arroba_base': 300.0, 'custo_reposicao_anual': 60000.0,
           'custo_suplementacao_anual': 40000.0}
ANO = {'ano': 1, 'receita': 600000.0, 'custo': 300000.0,
       'resultado': 300000.0, 'dscr': 1.39, 'viavel': True,
       'servico_divida_anual': 216000.0}


def _login(nome='Estresse'):
    db.init_db()
    email = f'{nome}-{uuid.uuid4().hex[:8]}@example.com'
    db.criar_usuario(email, nome, 'senha123')
    u = db.buscar_usuario_email(email)
    client = app.test_client()
    with client.session_transaction() as s:
        s['_user_id'] = str(u['id'])
    return client, u


@pytest.fixture
def cli():
    return _login()[0]


def _payload(**extra):
    p = {'valores': CRIA, 'preco': 330, 'credito_valor': sum(CRIA) * 1200,
         'prazo_meses': 36, 'juros_aa': 0.125}
    p.update(extra)
    return p


def _direto(anos, entrada=ENTRADA, ano_critico=None):
    return montar_parecer(
        identificacao={}, composicao={}, indicadores={}, benchmarks=[],
        consistencia={'score_consistencia': 90, 'flags': [],
                      'resumo': {'erros': 0}},
        financeiro={}, geracao_caixa_anual=300000,
        credito={'credito_valor': 1000000, 'prazo_meses': 36, 'juros_aa': 0.125,
                 'carencia_meses': 0},
        projecao_anos=anos, estresse_pecuario_entrada=entrada)


# ── Retrocompatibilidade ─────────────────────────────────────────────────────
def test_sem_campos_o_parecer_nao_muda(cli):
    r = cli.post('/api/classificar', json=_payload())
    assert r.status_code == 200
    p = r.get_json()['parecer']
    assert 'estresse_pecuario' not in p
    assert 'estresse_pecuario' not in p['secoes']


@pytest.mark.parametrize('vazio', [None, ''])
def test_campos_vazios_ou_nulos_equivalem_a_ausentes(cli, vazio):
    r = cli.post('/api/classificar', json=_payload(
        **{c: vazio for c in ENTRADA}))
    assert r.status_code == 200
    assert 'estresse_pecuario' not in r.get_json()['parecer']


def test_mesmas_chaves_e_conclusao_com_e_sem_estresse():
    sem = _login()[0].post('/api/classificar', json=_payload()).get_json()
    com = _login()[0].post('/api/classificar',
                           json=_payload(**ENTRADA)).get_json()
    assert set(com['parecer']) - set(sem['parecer']) == {'estresse_pecuario'}
    for k in ('recomendacao', 'dscr', 'dscr_minimo', 'ano_critico'):
        assert com['parecer']['conclusao'].get(k) == sem['parecer']['conclusao'].get(k)


def test_sem_entrada_montar_parecer_nao_tem_o_bloco():
    assert 'estresse_pecuario' not in _direto([ANO], entrada=None)


# ── Com dados ────────────────────────────────────────────────────────────────
def test_via_api_traz_seis_cenarios_e_ruptura_coerentes_com_o_parecer(cli):
    r = cli.post('/api/classificar', json=_payload(**ENTRADA))
    assert r.status_code == 200
    p = r.get_json()['parecer']
    e = p['estresse_pecuario']
    assert e['disponivel'] is True
    assert set(e['cenarios']) == {
        'queda_arroba', 'alta_reposicao', 'alta_suplementacao', 'seca_severa',
        'tesoura_margem_moderada', 'tesoura_margem_severa'}
    # Base do motor == DSCR do ano crítico do parecer (que o arredonda).
    assert e['base']['dscr'] is not None
    assert e['base']['dscr'] == pytest.approx(e['base']['dscr_parecer'], abs=0.006)
    assert e['base']['dscr_parecer'] == pytest.approx(
        p['conclusao']['dscr_minimo'], abs=0.006)
    assert json.dumps(e)  # serializável


def test_base_do_motor_bate_com_a_linha_do_ano_critico():
    e = _direto([ANO])['estresse_pecuario']
    b = e['base']
    assert b['receita'] == pytest.approx(600000.0)
    assert b['custo'] == pytest.approx(300000.0)
    assert b['dscr'] == pytest.approx(300000.0 / 216000.0)
    assert b['custo_outros'] == pytest.approx(200000.0)
    assert b['arrobas_equivalentes'] == pytest.approx(2000.0)


def test_usa_o_ano_critico_e_nao_o_primeiro_ano():
    pior = {**ANO, 'ano': 2, 'receita': 500000.0, 'resultado': 150000.0,
            'dscr': 0.69}
    p = _direto([ANO, pior])
    assert p['conclusao']['ano_critico'] == 2
    e = p['estresse_pecuario']
    assert e['ano_referencia'] == 2
    assert e['base']['receita'] == pytest.approx(500000.0)
    assert e['base']['dscr'] == pytest.approx(150000.0 / 216000.0)


def test_faixa_de_arredondamento_nao_contradiz_em_silencio():
    # 1,297 arredonda para 1,30: o parecer aprova, o motor exato diz ressalva.
    ano = {**ANO, 'resultado': 129700.0, 'servico_divida_anual': 100000.0,
           'dscr': 1.30}
    p = _direto([ano])
    assert p['conclusao']['recomendacao'] == 'aprovar'
    e = p['estresse_pecuario']
    assert e['base']['classificacao'] == 'ressalva'
    assert e['avisos'] and 'arredondado' in e['avisos'][0]


def test_sem_divergencia_nao_ha_avisos():
    assert _direto([ANO])['estresse_pecuario']['avisos'] == []


def test_ruptura_prova_inversa_e_cenarios_classificam_pelos_limiares():
    e = _direto([ANO])['estresse_pecuario']
    rup = e['ponto_ruptura_arroba']
    b = e['base']
    for chave, alvo in (('aprovar', DSCR_APROVAR), ('ressalva', DSCR_RESSALVA)):
        r = rup[chave]
        assert r['dscr_alvo'] == alvo and r['status'] == 'folga'
        dscr = (b['arrobas_equivalentes'] * r['preco_minimo'] - b['custo']) \
            / b['servico_divida_anual']
        assert dscr == pytest.approx(alvo)
        assert r['queda_maxima_suportada_pct'] == pytest.approx(
            (300.0 - r['preco_minimo']) / 300.0 * 100)
    q = e['cenarios']['queda_arroba']
    assert q['premissas']['arroba_pct']['origem'] == 'politica'
    assert q['impacto_margem_pp'] < 0


def test_sem_divida_e_sem_ruptura():
    e = _direto([{**ANO, 'servico_divida_anual': 0.0}])['estresse_pecuario']
    assert e['ponto_ruptura_arroba']['aprovar']['status'] == 'sem_divida'
    assert e['base']['dscr'] is None
    assert all(c['classificacao'] == 'sem_divida' for c in e['cenarios'].values())


def test_operacao_ja_em_ruptura_na_base():
    ano = {**ANO, 'resultado': 100000.0, 'dscr': 0.46}
    e = _direto([ano], entrada={**ENTRADA, 'custo_reposicao_anual': 1000.0})['estresse_pecuario']
    assert e['ponto_ruptura_arroba']['aprovar']['em_ruptura'] is True
    assert e['ponto_ruptura_arroba']['aprovar']['status'] == 'ja_em_ruptura'
    assert e['base']['classificacao'] == 'negar'


def test_receita_zero_vira_sem_volume():
    ano = {**ANO, 'receita': 0.0, 'resultado': -50000.0, 'dscr': -0.23}
    e = _direto([ano], entrada={**ENTRADA, 'custo_reposicao_anual': 0.0,
                                'custo_suplementacao_anual': 0.0})['estresse_pecuario']
    assert e['ponto_ruptura_arroba']['aprovar']['status'] == 'sem_volume'


def test_reposicao_mais_suplementacao_acima_do_custo_nao_quebra():
    e = _direto([ANO], entrada={**ENTRADA, 'custo_reposicao_anual': 9e6})['estresse_pecuario']
    assert e['disponivel'] is False and e['motivo']


def test_sem_projecao_fica_indisponivel_sem_quebrar():
    e = _direto(None)['estresse_pecuario']
    assert e['disponivel'] is False and e['motivo']


def test_resultado_maior_que_receita_nao_quebra():
    e = _direto([{**ANO, 'resultado': 700000.0}])['estresse_pecuario']
    assert e['disponivel'] is False and e['motivo']


# ── Validação de entrada: sempre 400, nunca 500 ──────────────────────────────
INVALIDOS = [-1, 'abc', '300', True, [], {}, 10**400, 1e16, float('nan'),
             float('inf'), float('-inf')]


@pytest.mark.parametrize('campo', list(ENTRADA))
@pytest.mark.parametrize('valor', INVALIDOS)
def test_entrada_invalida_vira_400(cli, campo, valor):
    corpo = json.dumps(_payload(**{**ENTRADA, campo: valor}),
                       allow_nan=True)
    r = cli.post('/api/classificar', data=corpo,
                 content_type='application/json')
    assert r.status_code == 400
    assert r.get_json()['erro']


def test_preco_zero_e_rejeitado(cli):
    r = cli.post('/api/classificar',
                 json=_payload(**{**ENTRADA, 'preco_arroba_base': 0}))
    assert r.status_code == 400


@pytest.mark.parametrize('faltando', list(ENTRADA))
def test_dados_parciais_vira_400(cli, faltando):
    parcial = {k: v for k, v in ENTRADA.items() if k != faltando}
    r = cli.post('/api/classificar', json=_payload(**parcial))
    assert r.status_code == 400 and faltando in r.get_json()['erro']


def test_apenas_um_campo_vira_400(cli):
    r = cli.post('/api/classificar', json=_payload(preco_arroba_base=300))
    assert r.status_code == 400


def test_zero_em_custos_e_aceito(cli):
    r = cli.post('/api/classificar', json=_payload(
        **{**ENTRADA, 'custo_reposicao_anual': 0,
           'custo_suplementacao_anual': 0}))
    assert r.status_code == 200


def test_sem_login_continua_negado():
    r = app.test_client().post('/api/classificar', json=_payload(**ENTRADA))
    assert r.status_code in (301, 302, 401, 403)


# ── Isolamento por empresa ───────────────────────────────────────────────────
def test_parecer_persistido_guarda_o_estresse_e_outra_empresa_nao_o_alcanca():
    a, ua = _login('EmpresaA')
    b, ub = _login('EmpresaB')
    ea = db.empresas_do_usuario(ua['id'])[0]['id']
    eb = db.empresas_do_usuario(ub['id'])[0]['id']
    assert ea != eb
    fid = db.criar_fazenda('Faz Estresse A', empresa_id=ea, criado_por=ua['id'])

    ra = a.post('/api/classificar', json=_payload(fazenda_id=fid, **ENTRADA))
    assert ra.status_code == 200
    itens = a.get(f'/api/fazendas/{fid}/pareceres').get_json()['pareceres']
    assert len(itens) == 1
    assert 'estresse_pecuario' in json.dumps(
        db.listar_pareceres(fazenda_id=fid)[0], default=str)

    # B aponta para a fazenda de A: campos novos não abrem brecha.
    rb = b.post('/api/classificar', json=_payload(fazenda_id=fid, **ENTRADA))
    assert rb.status_code == 200
    assert len(db.listar_pareceres(fazenda_id=fid)) == 1  # nada gravado por B
    assert b.get(f'/api/fazendas/{fid}/pareceres').status_code == 404


def test_motor_rejeita_int_gigante_com_valueerror_e_nao_overflow():
    from services.stress_engine.pecuaria import BasePecuaria
    with pytest.raises(ValueError):
        BasePecuaria(10**400, 300, 0, 0, 0, 0)
