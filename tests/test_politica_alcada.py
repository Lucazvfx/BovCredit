import uuid

import pytest

import app as app_module
import database as db
from services import politica_alcada as alc
from services.payment_capacity_engine.dscr import credito_maximo

CAIXA, JUROS, PRAZO = 1_000_000.0, 0.10, 60


def _empresa_nova(nome='Alcada'):
    db.init_db()
    email = f'{nome}-{uuid.uuid4().hex[:8]}@example.com'
    uid = db.criar_usuario(email, nome, 'senha123')
    return uid, db.empresas_do_usuario(uid)[0]['id'], email


def _simular(politica, **kw):
    base = dict(valor_pretendido=300_000.0, prazo_meses=PRAZO,
                geracao_caixa_anual=CAIXA, juros_aa=JUROS)
    base.update(kw)
    return alc.simular_proposta(politica, **base)


# ── Persistência e isolamento ────────────────────────────────────────────────

def test_empresa_sem_politica_recebe_padrao_sem_gravar():
    _, eid, _ = _empresa_nova()
    p = db.obter_politica_alcada(eid)
    assert p['padrao'] is True
    assert {k: p[k] for k in alc.politica_padrao()} == alc.politica_padrao()
    # leitura não grava
    assert db._exec(f'SELECT 1 FROM politica_alcada WHERE empresa_id={db._PH}',
                    (eid,), fetch='one') is None


def test_politica_salva_e_atualizada_por_empresa():
    uid, eid, _ = _empresa_nova()
    pol, erro = alc.validar_politica({'alcada_analista': 100_000,
                                      'alcada_comite': 900_000,
                                      'prazo_max_meses': 36})
    assert erro is None
    db.salvar_politica_alcada(eid, pol, user_id=uid)
    lida = db.obter_politica_alcada(eid)
    assert lida['padrao'] is False
    assert lida['alcada_comite'] == 900_000 and lida['prazo_max_meses'] == 36
    pol['alcada_comite'] = 1_200_000.0
    db.salvar_politica_alcada(eid, pol, user_id=uid)  # update, não duplica
    assert db.obter_politica_alcada(eid)['alcada_comite'] == 1_200_000
    n = db._exec(f'SELECT COUNT(*) AS n FROM politica_alcada WHERE empresa_id={db._PH}',
                 (eid,), fetch='one')['n']
    assert n == 1


def test_politica_isolada_entre_empresas():
    uid_a, eid_a, _ = _empresa_nova('IsoA')
    _, eid_b, _ = _empresa_nova('IsoB')
    pol, _ = alc.validar_politica({'alcada_analista': 50_000, 'alcada_comite': 80_000})
    db.salvar_politica_alcada(eid_a, pol, user_id=uid_a)
    assert db.obter_politica_alcada(eid_a)['alcada_comite'] == 80_000
    b = db.obter_politica_alcada(eid_b)
    assert b['padrao'] is True
    assert b['alcada_comite'] == alc.politica_padrao()['alcada_comite']


# ── Validação ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize('dados', [
    {'alcada_analista': -1},
    {'alcada_analista': True},
    {'alcada_comite': 'abc'},
    {'alcada_comite': float('inf')},
    {'alcada_analista': 2_000_000, 'alcada_comite': 1_000_000},
    {'prazo_max_meses': 0},
    {'prazo_max_meses': 12.5},
    {'prazo_max_meses': 361},
    {'margem_capacidade_pct': 5},
    {'margem_capacidade_pct': 101},
    {'comite_se_revisao_humana': 'sim'},
    {'alcada_comite': 10**400},
    [],
])
def test_politica_invalida_e_rejeitada(dados):
    pol, erro = alc.validar_politica(dados)
    assert pol is None and erro


@pytest.mark.parametrize('campo,valor', [
    ('valor_pretendido', 0), ('valor_pretendido', -5), ('valor_pretendido', 'x'),
    ('prazo_meses', 0), ('prazo_meses', 361), ('juros_aa', 0), ('juros_aa', 1),
    ('juros_aa', 10.5), ('carencia_meses', 60), ('dividas_mensais', -1),
    ('revisao_humana', 'true'), ('motivos_revisao', ['x']),
    ('atipicidade_nivel', 'extremo'), ('geracao_caixa_anual', float('nan')),
    ('valor_pretendido', 10**400), ('geracao_caixa_anual', 10**400),
    ('carencia_meses', False), ('dividas_mensais', None), ('carencia_meses', ''),
])
def test_simulacao_invalida_e_rejeitada(campo, valor):
    dados = dict(valor_pretendido=300_000, prazo_meses=PRAZO,
                 geracao_caixa_anual=CAIXA, juros_aa=JUROS)
    dados[campo] = valor
    params, erro = alc.validar_simulacao(dados)
    assert params is None and erro


# ── Simulação ────────────────────────────────────────────────────────────────

def test_proposta_dentro_da_alcada():
    r = _simular(alc.politica_padrao())
    assert r['status'] == 'dentro_alcada' and r['nivel_decisor'] == 'analista'
    assert r['motivos'] == []
    assert r['capacidade_maxima'] == credito_maximo(CAIXA, JUROS, PRAZO)
    assert r['dscr'] >= 1.30


def test_valor_acima_da_alcada_do_analista_vai_ao_comite():
    cap = credito_maximo(CAIXA, JUROS, PRAZO)
    pol = {**alc.politica_padrao(), 'alcada_analista': 100_000.0,
           'alcada_comite': cap * 2}
    r = _simular(pol, valor_pretendido=cap * 0.5)
    assert r['status'] == 'requer_comite' and r['nivel_decisor'] == 'comite'
    assert 'acima_alcada_analista' in r['motivos']


def test_valor_acima_da_alcada_do_comite_esta_fora():
    pol = {**alc.politica_padrao(), 'alcada_analista': 10_000.0,
           'alcada_comite': 200_000.0}
    r = _simular(pol, valor_pretendido=300_000.0)
    assert r['status'] == 'fora_alcada'
    assert 'acima_alcada_comite' in r['motivos']


def test_valor_acima_da_capacidade_esta_fora_mesmo_com_alcada_folgada():
    cap = credito_maximo(CAIXA, JUROS, PRAZO)
    pol = {**alc.politica_padrao(), 'alcada_comite': cap * 10}
    r = _simular(pol, valor_pretendido=cap * 1.5)
    assert r['status'] == 'fora_alcada' and 'acima_capacidade' in r['motivos']


def test_margem_de_capacidade_reduz_o_teto():
    cap = credito_maximo(CAIXA, JUROS, PRAZO)
    pol = {**alc.politica_padrao(), 'alcada_comite': cap * 10,
           'alcada_analista': cap * 10, 'margem_capacidade_pct': 50.0}
    assert _simular(pol, valor_pretendido=cap * 0.4)['status'] == 'dentro_alcada'
    r = _simular(pol, valor_pretendido=cap * 0.6)
    assert r['status'] == 'fora_alcada'
    assert r['capacidade_permitida'] == pytest.approx(cap * 0.5, abs=0.01)


def test_prazo_acima_da_politica_esta_fora():
    pol = {**alc.politica_padrao(), 'prazo_max_meses': 24}
    r = _simular(pol, prazo_meses=36)
    assert r['status'] == 'fora_alcada' and 'prazo_acima_politica' in r['motivos']


def test_sem_caixa_nao_ha_capacidade():
    r = _simular(alc.politica_padrao(), geracao_caixa_anual=0.0)
    assert r['status'] == 'fora_alcada' and 'sem_capacidade' in r['motivos']
    assert r['uso_da_capacidade_pct'] is None


def test_revisao_humana_exige_comite_mesmo_dentro_da_alcada():
    r = _simular(alc.politica_padrao(), revisao_humana=True,
                 motivos_revisao=['dados_incompletos'])
    assert r['status'] == 'requer_comite'
    assert 'revisao_humana' in r['motivos'] and r['revisao_humana'] is True


def test_muito_atipico_conta_como_revisao():
    r = _simular(alc.politica_padrao(), atipicidade_nivel='muito_atipico')
    assert r['status'] == 'requer_comite' and r['revisao_humana'] is True


def test_revisao_humana_nao_exige_comite_quando_politica_desliga():
    pol = {**alc.politica_padrao(), 'comite_se_revisao_humana': False}
    r = _simular(pol, revisao_humana=True)
    assert r['status'] == 'dentro_alcada'
    assert 'revisao_humana' in r['motivos']  # continua sinalizado


def test_revisao_humana_nao_rebaixa_bloqueio():
    pol = {**alc.politica_padrao(), 'alcada_analista': 10_000.0,
           'alcada_comite': 20_000.0}
    r = _simular(pol, revisao_humana=True)
    assert r['status'] == 'fora_alcada'


# ── API ──────────────────────────────────────────────────────────────────────

def _cliente(email, uid):  # noqa: ARG001
    c = app_module.app.test_client()
    with c.session_transaction() as s:
        s['_user_id'] = str(uid)
    return c


def _corpo(**kw):
    base = dict(valor_pretendido=300_000, prazo_meses=PRAZO,
                geracao_caixa_anual=CAIXA, juros_aa=JUROS)
    base.update(kw)
    return base


def test_api_exige_login():
    c = app_module.app.test_client()
    assert c.get('/api/politica-alcada').status_code in (302, 401)
    assert c.post('/api/simulacao-proposta', json=_corpo()).status_code in (302, 401)


def test_api_get_padrao_e_nao_admin_nao_edita(monkeypatch):
    uid, eid, email = _empresa_nova('ApiGet')
    # o criador da empresa nasce admin dela; aqui o caso é o do analista
    db.definir_papel_membro(eid, uid, 'analista', permitir_sem_admin=True)
    monkeypatch.setattr(app_module, '_ADMIN_EMAILS', set())
    c = _cliente(email, uid)
    d = c.get('/api/politica-alcada').get_json()
    assert d['politica']['padrao'] is True and d['pode_editar'] is False
    assert c.put('/api/politica-alcada', json={'alcada_comite': 1}).status_code == 403


def test_api_admin_salva_e_empresas_ficam_isoladas(monkeypatch):
    uid_a, _, email_a = _empresa_nova('ApiA')
    uid_b, _, email_b = _empresa_nova('ApiB')
    monkeypatch.setattr(app_module, '_ADMIN_EMAILS', {email_a.lower()})
    ca, cb = _cliente(email_a, uid_a), _cliente(email_b, uid_b)
    r = ca.put('/api/politica-alcada',
               json={'alcada_analista': 1000, 'alcada_comite': 2000})
    assert r.status_code == 200
    assert ca.get('/api/politica-alcada').get_json()['politica']['alcada_comite'] == 2000
    assert cb.get('/api/politica-alcada').get_json()['politica']['padrao'] is True
    # simulação de B usa a política padrão de B, não a de A
    assert cb.post('/api/simulacao-proposta', json=_corpo()).get_json()['status'] == 'dentro_alcada'
    assert ca.post('/api/simulacao-proposta', json=_corpo()).get_json()['status'] == 'fora_alcada'


def test_api_put_invalido_400_sem_vazar_detalhe(monkeypatch):
    uid, _, email = _empresa_nova('ApiPut')
    monkeypatch.setattr(app_module, '_ADMIN_EMAILS', {email.lower()})
    c = _cliente(email, uid)
    r = c.put('/api/politica-alcada', json={'alcada_analista': 9, 'alcada_comite': 1})
    assert r.status_code == 400 and 'erro' in r.get_json()
    assert c.put('/api/politica-alcada', data='nao json',
                 content_type='text/plain').status_code == 400


def test_api_simulacao_com_revisao_humana_e_entrada_invalida():
    uid, _, email = _empresa_nova('ApiSim')
    c = _cliente(email, uid)
    r = c.post('/api/simulacao-proposta',
               json=_corpo(revisao_humana=True, motivos_revisao=['muito_atipico']))
    d = r.get_json()
    assert r.status_code == 200
    assert d['status'] == 'requer_comite' and d['revisao_humana'] is True
    assert c.post('/api/simulacao-proposta',
                  json=_corpo(valor_pretendido=-1)).status_code == 400


# ── Revisão crítica: bordas adicionais ───────────────────────────────────────

def test_carencia_e_dividas_reduzem_a_capacidade():
    base = _simular(alc.politica_padrao())['capacidade_maxima']
    assert _simular(alc.politica_padrao(), dividas_mensais=30_000.0)['capacidade_maxima'] < base
    assert _simular(alc.politica_padrao(), carencia_meses=12)['capacidade_maxima'] != base


def test_uso_da_capacidade_e_nivel_fora_da_alcada():
    cap = credito_maximo(CAIXA, JUROS, PRAZO)
    pol = {**alc.politica_padrao(), 'alcada_comite': cap * 10,
           'alcada_analista': cap * 10}
    r = _simular(pol, valor_pretendido=cap / 2)
    assert r['uso_da_capacidade_pct'] == pytest.approx(50.0, abs=0.1)
    assert _simular(pol, valor_pretendido=cap * 2)['nivel_decisor'] == 'fora_alcada'


def test_faixa_ressalva_do_motor_fica_acima_da_capacidade_por_politica():
    # Fixa o comportamento documentado: o teto usa o DSCR de aprovação (1,30).
    cap = credito_maximo(CAIXA, JUROS, PRAZO)
    pol = {**alc.politica_padrao(), 'alcada_comite': cap * 10,
           'alcada_analista': cap * 10}
    r = _simular(pol, valor_pretendido=cap * 1.1)
    assert r['recomendacao_capacidade'] == 'ressalva'
    assert r['status'] == 'fora_alcada' and 'acima_capacidade' in r['motivos']


def test_put_parcial_preserva_o_que_ja_foi_configurado(monkeypatch):
    uid, eid, email = _empresa_nova('ApiParcial')
    monkeypatch.setattr(app_module, '_ADMIN_EMAILS', {email.lower()})
    c = _cliente(email, uid)
    assert c.put('/api/politica-alcada', json={
        'alcada_analista': 1000, 'alcada_comite': 2000}).status_code == 200
    assert c.put('/api/politica-alcada', json={'prazo_max_meses': 36}).status_code == 200
    p = db.obter_politica_alcada(eid)
    assert p['alcada_analista'] == 1000 and p['alcada_comite'] == 2000
    assert p['prazo_max_meses'] == 36
    # compara com a política gravada, não com o padrão
    assert c.put('/api/politica-alcada', json={'alcada_comite': 500}).status_code == 400


def test_put_registra_auditoria_sem_dado_pessoal(monkeypatch):
    uid, eid, email = _empresa_nova('ApiAud')
    monkeypatch.setattr(app_module, '_ADMIN_EMAILS', {email.lower()})
    c = _cliente(email, uid)
    c.put('/api/politica-alcada', json={'prazo_max_meses': 48})
    linhas = db._exec(
        f"SELECT recurso, recurso_id, detalhe FROM auditoria_acessos "
        f"WHERE evento={db._PH} AND user_id={db._PH}",
        ('alcada_alterada', uid), fetch='all')
    assert len(linhas) == 1 and linhas[0]['recurso'] == 'empresa'
    assert str(linhas[0]['recurso_id']) == str(eid)


def test_api_rejeita_sem_csrf_e_corpo_nulo():
    uid, _, email = _empresa_nova('ApiCsrf')
    c = _cliente(email, uid)
    r = c.post('/api/simulacao-proposta', data='null', content_type='application/json')
    assert r.status_code == 400
    c.csrf = False
    assert c.post('/api/simulacao-proposta', json=_corpo()).status_code == 403


def test_api_inteiro_gigante_devolve_400_e_nao_500():
    uid, _, email = _empresa_nova('ApiBig')
    c = _cliente(email, uid)
    raw = '{"valor_pretendido": 1' + '0' * 400 + ', "prazo_meses": 60, "geracao_caixa_anual": 1, "juros_aa": 0.1}'
    r = c.post('/api/simulacao-proposta', data=raw, content_type='application/json')
    assert r.status_code == 400
