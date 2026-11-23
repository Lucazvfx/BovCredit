"""Fluxo sazonal do ciclo pecuário dentro do parecer e de /api/classificar.

O motor (`ciclo_pecuario.py`) já tem testes próprios. Aqui se prova a COLA:
os campos são opcionais, os números do fluxo saem do mesmo ano e do mesmo
serviço da dívida que sustentam o DSCR do parecer, a entrada inválida vira 400
e o isolamento por empresa não muda.
"""
import json
import uuid

import pytest

import database as db
from app import app
from services.parecer_credito import montar_parecer

CRIA = [300, 280, 200, 80, 100, 40, 150, 10, 600, 15]
CICLO_COMPLETO = [120, 100, 80, 70, 40, 50, 150, 80, 270, 40]


def _login(nome='Ciclo'):
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


def _payload(valores=CRIA, **extra):
    p = {'valores': valores, 'preco': 330,
         'credito_valor': sum(valores) * 1200,
         'prazo_meses': 36, 'juros_aa': 0.125}
    p.update(extra)
    return p


def _parecer_direto(projecao_anos, **ciclo):
    return montar_parecer(
        identificacao={}, composicao={}, indicadores={}, benchmarks=[],
        consistencia={'score_consistencia': 90, 'flags': [],
                      'resumo': {'erros': 0}},
        financeiro={}, geracao_caixa_anual=300000,
        credito={'credito_valor': 1_000_000, 'prazo_meses': 12,
                 'juros_aa': 0.10, 'carencia_meses': 0, 'dividas_mensais': 0},
        projecao_anos=projecao_anos, **ciclo)


# Cria com DSCR anual 1,39 (>= 1,30): receita 600 mil, caixa 300 mil, serviço
# 216 mil (18 mil/mês). O vale de jan–abr é causado pela parcela.
ANO_CRIA_DSCR_OK = [{'ano': 1, 'receita': 600000.0, 'custo': 300000.0,
                     'resultado': 300000.0, 'dscr': 1.39, 'viavel': True,
                     'servico_divida_anual': 216000.0}]


# ── Retrocompatibilidade ─────────────────────────────────────────────────────
def test_sem_sistema_produtivo_o_parecer_nao_muda(cli):
    r = cli.post('/api/classificar', json=_payload())
    assert r.status_code == 200
    p = r.get_json()['parecer']
    assert 'ciclo_pecuario' not in p
    assert 'ciclo_pecuario' not in p['secoes']


@pytest.mark.parametrize('vazio', [None, ''])
def test_sistema_produtivo_vazio_ou_nulo_equivale_a_ausente(cli, vazio):
    r = cli.post('/api/classificar',
                 json=_payload(sistema_produtivo=vazio,
                               frequencia_pagamento=vazio,
                               capital_giro_inicial=vazio))
    assert r.status_code == 200
    assert 'ciclo_pecuario' not in r.get_json()['parecer']


def test_conclusao_e_identica_com_e_sem_o_fluxo_sazonal():
    # O fluxo é informativo: não pode mexer no veredito nem no DSCR.
    sem = _login()[0].post('/api/classificar', json=_payload()).get_json()
    com = _login()[0].post(
        '/api/classificar', json=_payload(sistema_produtivo='cria')).get_json()
    for k in ('recomendacao', 'dscr', 'dscr_minimo', 'ano_critico',
              'servico_divida_anual'):
        assert com['parecer']['conclusao'].get(k) == sem['parecer']['conclusao'].get(k)


def test_montar_parecer_sem_sistema_mantem_chaves_e_secoes():
    p = _parecer_direto(ANO_CRIA_DSCR_OK)
    assert 'ciclo_pecuario' not in p
    assert 'ciclo_pecuario' not in p['secoes']


# ── Com sistema produtivo ────────────────────────────────────────────────────
@pytest.mark.parametrize('sistema, valores',
                         [('cria', CRIA), ('engorda', CICLO_COMPLETO)])
def test_sistema_valido_devolve_projecao_sazonal(sistema, valores):
    r = _login()[0].post('/api/classificar',
                         json=_payload(valores, sistema_produtivo=sistema))
    assert r.status_code == 200
    c = r.get_json()['parecer']['ciclo_pecuario']
    assert c['disponivel'] is True
    assert c['sistema'] == sistema and c['frequencia'] == 'mensal'
    assert len(c['meses']) == 12
    for k in ('vale_caixa', 'meses_deficit', 'quebra_caixa_com_dscr_ok',
              'recomendacao', 'justificativa', 'proveniencia'):
        assert k in c
    assert c['proveniencia']['origem'] == 'referencia'
    json.dumps(c)  # serializável: é o que vai para o histórico e o front


@pytest.mark.parametrize('sistema, valores',
                         [('cria', CRIA), ('engorda', CICLO_COMPLETO)])
def test_dscr_e_servico_do_fluxo_batem_com_os_do_parecer(sistema, valores):
    """O servidor da dívida do fluxo é o do DSCR, não uma segunda conta."""
    d = _login()[0].post(
        '/api/classificar',
        json=_payload(valores, sistema_produtivo=sistema)).get_json()
    concl, c = d['parecer']['conclusao'], d['parecer']['ciclo_pecuario']
    assert c['ano_referencia'] == concl['ano_critico']
    assert c['dscr_anual'] == pytest.approx(concl['dscr_minimo'], abs=0.01)
    # Parcela arredondada ao centavo × pagamentos/ano: no máximo 12 centavos.
    assert c['servico_divida_anual'] == pytest.approx(
        c['servico_divida_anual_parecer'], abs=0.12)
    linha = next(a for a in d['projecao_anos'] if a['ano'] == c['ano_referencia'])
    assert c['servico_divida_anual_parecer'] == linha['servico_divida_anual']
    assert c['receita_anual'] == linha['receita']


def test_frequencia_semestral_mantem_o_servico_anual():
    d = _login()[0].post('/api/classificar', json=_payload(
        sistema_produtivo='cria', frequencia_pagamento='semestral')).get_json()
    c = d['parecer']['ciclo_pecuario']
    assert c['frequencia'] == 'semestral' and len(c['meses_pagamento']) == 2
    assert c['servico_divida_anual'] == pytest.approx(
        c['servico_divida_anual_parecer'], abs=0.02)


def test_descasamento_dscr_ok_mas_caixa_quebra_gera_alerta_e_recomendacao():
    p = _parecer_direto(ANO_CRIA_DSCR_OK, sistema_produtivo='cria')
    c = p['ciclo_pecuario']
    assert c['disponivel'] is True
    assert c['dscr_anual'] == pytest.approx(1.3889, abs=1e-4)
    assert c['dscr_anual_suficiente'] is True
    assert c['quebra_caixa_com_dscr_ok'] is True
    assert c['meses_deficit_por_divida']
    assert c['recomendacao']['estrutura_recomendada'] in ('semestral', 'anual')
    assert c['servico_divida_anual'] == 216000.0


def test_limiar_130_alerta_segue_o_dscr_arredondado_do_parecer():
    # 1,2996 arredonda para 1,30: o parecer aprova, então o alerta não pode
    # sumir nem se contradizer.
    ano = [{**ANO_CRIA_DSCR_OK[0], 'resultado': 1.2996 * 216000, 'dscr': 1.30}]
    c = _parecer_direto(ano, sistema_produtivo='cria')['ciclo_pecuario']
    assert c['dscr_anual_suficiente'] is True
    assert c['quebra_caixa_com_dscr_ok'] is True
    assert any('arredondado' in j for j in c['justificativa'])


def test_resultado_maior_que_a_receita_nao_quebra_o_parecer():
    ano = [{**ANO_CRIA_DSCR_OK[0], 'resultado': 700000.0}]
    c = _parecer_direto(ano, sistema_produtivo='cria')['ciclo_pecuario']
    assert c['disponivel'] is False and c['motivo']


def test_capital_de_giro_entra_no_fluxo():
    sem = _parecer_direto(ANO_CRIA_DSCR_OK, sistema_produtivo='cria')
    com = _parecer_direto(ANO_CRIA_DSCR_OK, sistema_produtivo='cria',
                          capital_giro_inicial=200000.0)
    assert com['ciclo_pecuario']['vale_caixa'] > sem['ciclo_pecuario']['vale_caixa']
    assert com['ciclo_pecuario']['capital_giro_inicial'] == 200000.0


def test_sem_projecao_por_ano_o_fluxo_fica_indisponivel_sem_quebrar():
    c = _parecer_direto(None, sistema_produtivo='cria')['ciclo_pecuario']
    assert c['disponivel'] is False and c['motivo']


# ── Validação de entrada ─────────────────────────────────────────────────────
@pytest.mark.parametrize('campo, valor', [
    ('sistema_produtivo', 'pecuaria'),
    ('sistema_produtivo', 7),
    ('sistema_produtivo', ['cria']),
    ('sistema_produtivo', True),
    ('frequencia_pagamento', 'trimestral'),
    ('frequencia_pagamento', 12),
    ('frequencia_pagamento', {'a': 1}),
    ('capital_giro_inicial', -1),
    ('capital_giro_inicial', 'abc'),
    ('capital_giro_inicial', '1000'),
    ('capital_giro_inicial', True),
    ('capital_giro_inicial', [1]),
    ('capital_giro_inicial', 1e13),
    ('capital_giro_inicial', 10 ** 400),
    ('capital_giro_inicial', float('inf')),
])
def test_entradas_invalidas_viram_400_com_mensagem_clara(cli, campo, valor):
    corpo = _payload(sistema_produtivo='cria')
    corpo[campo] = valor
    # json.dumps do Flask aceita inf/nan como Infinity/NaN, que o servidor lê.
    r = cli.post('/api/classificar', json=corpo)
    assert r.status_code == 400
    assert campo in r.get_json()['erro']


def test_nan_em_capital_de_giro_vira_400(cli):
    r = cli.post('/api/classificar',
                 data='{"valores": %s, "credito_valor": 100000, "prazo_meses": 24, '
                      '"juros_aa": 0.1, "sistema_produtivo": "cria", '
                      '"capital_giro_inicial": NaN}' % json.dumps(CRIA),
                 content_type='application/json')
    assert r.status_code == 400


def test_frequencia_invalida_e_rejeitada_mesmo_sem_sistema(cli):
    r = cli.post('/api/classificar',
                 json=_payload(frequencia_pagamento='quinzenal'))
    assert r.status_code == 400


def test_valores_validos_com_caixa_e_espacos_sao_normalizados(cli):
    r = cli.post('/api/classificar', json=_payload(
        sistema_produtivo=' Ciclo_Completo ', frequencia_pagamento='ANUAL',
        capital_giro_inicial=0))
    assert r.status_code == 200
    c = r.get_json()['parecer']['ciclo_pecuario']
    assert c['sistema'] == 'ciclo_completo' and c['frequencia'] == 'anual'


def test_sem_login_continua_negado():
    r = app.test_client().post('/api/classificar',
                               json=_payload(sistema_produtivo='cria'))
    assert r.status_code in (301, 302, 401, 403)


# ── Isolamento por empresa ───────────────────────────────────────────────────
def test_parecer_persistido_guarda_o_fluxo_e_outra_empresa_nao_o_alcanca():
    a, ua = _login('EmpresaA')
    b, ub = _login('EmpresaB')
    ea = db.empresas_do_usuario(ua['id'])[0]['id']
    eb = db.empresas_do_usuario(ub['id'])[0]['id']
    assert ea != eb
    fid = db.criar_fazenda('Faz Ciclo A', empresa_id=ea, criado_por=ua['id'])

    # A grava na própria fazenda: o fluxo vai junto no histórico.
    ra = a.post('/api/classificar', json=_payload(
        fazenda_id=fid, sistema_produtivo='cria'))
    assert ra.status_code == 200
    itens = a.get(f'/api/fazendas/{fid}/pareceres').get_json()['pareceres']
    assert len(itens) == 1
    salvo = db.listar_pareceres(fazenda_id=fid)[0]
    assert 'ciclo_pecuario' in json.dumps(salvo, default=str)

    # B aponta para a fazenda de A: o campo novo não abre brecha.
    rb = b.post('/api/classificar', json=_payload(
        fazenda_id=fid, sistema_produtivo='cria'))
    assert rb.status_code == 200
    assert len(db.listar_pareceres(fazenda_id=fid)) == 1  # nada gravado por B
    assert b.get(f'/api/fazendas/{fid}/pareceres').status_code == 404
