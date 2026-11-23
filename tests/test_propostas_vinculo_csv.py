import csv
import io
import json
import uuid

import pytest

import app as app_module
import database as db
from services.exportacao_csv import neutralizar_celula

CAIXA, JUROS, PRAZO = 1_000_000.0, 0.10, 60


def _usuario(nome='Vin'):
    db.init_db()
    email = f'{nome}-{uuid.uuid4().hex[:8]}@example.com'
    uid = db.criar_usuario(email, nome, 'senha123')
    return uid, db.empresas_do_usuario(uid)[0]['id']


def _cliente(uid, empresa_id):
    c = app_module.app.test_client()
    with c.session_transaction() as s:
        s['_user_id'] = str(uid)
        s['empresa_ativa_id'] = empresa_id
    return c


def _parecer(uid, empresa_id, *, caixa=CAIXA, revisao=False, com_classificacao=True,
             credito=300_000, atipicidade=None):
    fid = db.criar_fazenda('Fazenda Teste', empresa_id=empresa_id, criado_por=uid)
    parecer = {'conclusao': {'geracao_caixa_anual': caixa, 'dscr': 1.5,
                             'recomendacao': 'aprovar'}}
    if com_classificacao:
        parecer['explicacao_classificacao'] = {
            'revisao_humana': revisao,
            'motivos_revisao': ['muito_atipico'] if atipicidade == 'muito_atipico' else [],
            'atipicidade_nivel': atipicidade}
    solicitacao = {'credito_valor': credito, 'prazo_meses': PRAZO, 'juros_aa': JUROS,
                   'carencia_meses': 0, 'dividas_mensais': 0}
    return db.salvar_parecer(uid, fid, solicitacao, parecer), fid


def _post(c, **corpo):
    base = {'referencia': 'CT-VIN-1'}
    base.update(corpo)
    return c.post('/api/propostas', json=base)


def test_proposta_vinculada_a_parecer_da_propria_empresa():
    uid, eid = _usuario()
    pid, _ = _parecer(uid, eid)
    c = _cliente(uid, eid)
    r = _post(c, parecer_id=pid)
    assert r.status_code == 201, r.get_json()
    prop = c.get('/api/propostas').get_json()['propostas'][0]
    assert prop['parecer_id'] == pid
    assert prop['valor_pretendido'] == 300_000
    assert prop['prazo_meses'] == PRAZO


def test_parecer_de_outra_empresa_retorna_404_na_proposta_e_na_simulacao():
    uid_a, eid_a = _usuario('A')
    uid_b, eid_b = _usuario('B')
    pid_b, _ = _parecer(uid_b, eid_b)
    c = _cliente(uid_a, eid_a)
    assert _post(c, parecer_id=pid_b).status_code == 404
    assert c.post('/api/simulacao-proposta', json={'parecer_id': pid_b}).status_code == 404
    assert c.get('/api/propostas').get_json()['propostas'] == []


@pytest.mark.parametrize('pid', [0, -1, 'x', True, 1.5])
def test_parecer_id_invalido_e_400(pid):
    uid, eid = _usuario()
    assert _post(_cliente(uid, eid), parecer_id=pid).status_code == 400


def test_dados_do_servidor_prevalecem_sobre_payload_adulterado():
    uid, eid = _usuario()
    # Caixa ínfimo no parecer: o pedido não cabe na capacidade.
    pid, _ = _parecer(uid, eid, caixa=10_000.0)
    c = _cliente(uid, eid)
    r = _post(c, parecer_id=pid, geracao_caixa_anual=900_000_000, juros_aa=0.01,
              prazo_meses=1, carencia_meses=0, dividas_mensais=0,
              revisao_humana=False, atipicidade_nivel='tipico', status_alcada='dentro_alcada')
    assert r.status_code == 201
    assert r.get_json()['status_alcada'] == 'fora_alcada'
    prop = c.get('/api/propostas').get_json()['propostas'][0]
    assert prop['prazo_meses'] == PRAZO
    assert any('capacidade' in t.lower() for t in prop['motivos_texto'])


def test_revisao_humana_e_atipicidade_do_parecer_valem():
    uid, eid = _usuario()
    pid, _ = _parecer(uid, eid, revisao=True, atipicidade='muito_atipico')
    c = _cliente(uid, eid)
    r = _post(c, parecer_id=pid, revisao_humana=False, atipicidade_nivel='tipico')
    assert r.status_code == 201
    assert r.get_json()['status_alcada'] == 'requer_comite'


def test_parecer_sem_classificacao_registrada_vai_a_comite():
    uid, eid = _usuario()
    pid, _ = _parecer(uid, eid, com_classificacao=False)
    r = _post(_cliente(uid, eid), parecer_id=pid)
    assert r.status_code == 201
    assert r.get_json()['status_alcada'] == 'requer_comite'


def test_parecer_sem_caixa_e_422():
    uid, eid = _usuario()
    pid, _ = _parecer(uid, eid, caixa=None)
    assert _post(_cliente(uid, eid), parecer_id=pid).status_code == 422


def test_simulacao_avulsa_continua_funcionando():
    uid, eid = _usuario()
    c = _cliente(uid, eid)
    r = _post(c, valor_pretendido=300_000, prazo_meses=PRAZO,
              geracao_caixa_anual=CAIXA, juros_aa=JUROS)
    assert r.status_code == 201
    assert c.get('/api/propostas').get_json()['propostas'][0]['parecer_id'] is None


def test_lista_de_pareceres_salvos_e_isolada_por_empresa():
    uid_a, eid_a = _usuario('A')
    uid_b, eid_b = _usuario('B')
    pid_a, _ = _parecer(uid_a, eid_a)
    _parecer(uid_b, eid_b)
    ids = [p['id'] for p in _cliente(uid_a, eid_a).get('/api/pareceres-salvos')
           .get_json()['pareceres']]
    assert ids == [pid_a]


# ── CSV ──────────────────────────────────────────────────────────────────────

def _linhas(resp):
    texto = resp.get_data(as_text=True)
    assert texto.startswith('\ufeff')
    return list(csv.reader(io.StringIO(texto[1:]), delimiter=';'))


def test_csv_exporta_so_a_empresa_ativa_com_colunas_fixas():
    uid_a, eid_a = _usuario('A')
    uid_b, eid_b = _usuario('B')
    pid, _ = _parecer(uid_a, eid_a)
    ca, cb = _cliente(uid_a, eid_a), _cliente(uid_b, eid_b)
    _post(ca, referencia='CT-A', parecer_id=pid)
    _post(cb, referencia='CT-B', valor_pretendido=1000, prazo_meses=12,
          geracao_caixa_anual=CAIXA, juros_aa=JUROS)
    r = ca.get('/api/propostas/exportar.csv')
    assert r.status_code == 200
    assert r.headers['Content-Type'].startswith('text/csv')
    assert 'attachment' in r.headers['Content-Disposition']
    assert r.headers['Cache-Control'] == 'no-store'
    linhas = _linhas(r)
    assert linhas[0][:3] == ['Data de registro', 'Referência', 'Parecer vinculado']
    assert len(linhas) == 2 and linhas[1][1] == 'CT-A' and linhas[1][2] == str(pid)
    assert linhas[1][3] == '300000,00'
    corpo = r.get_data(as_text=True)
    assert '@example.com' not in corpo and 'CT-B' not in corpo


def test_csv_exige_login():
    r = app_module.app.test_client().get('/api/propostas/exportar.csv')
    assert r.status_code in (301, 302, 401)


def test_csv_neutraliza_injecao_de_formula():
    for gatilho in ('=1+1', '+1', '-1', '@SUM(A1)', ' =1', '\t=1', '\r=1', ' \t=1', '\x0b=1'):
        assert neutralizar_celula(gatilho).startswith("'")
    assert neutralizar_celula('CT-001') == 'CT-001'
    assert neutralizar_celula(None) == ''


def test_csv_neutraliza_referencia_e_decisor_maliciosos():
    uid, eid = _usuario('=cmd')
    c = _cliente(uid, eid)
    r = _post(c, referencia='=HYPERLINK("http://x")', valor_pretendido=1000,
              prazo_meses=12, geracao_caixa_anual=CAIXA, juros_aa=JUROS)
    assert r.status_code == 201
    pid = r.get_json()['id']
    d = c.post(f'/api/propostas/{pid}/decisao', json={'decisao': 'aprovado',
                                                     'parecer': 'ok'})
    assert d.status_code == 200
    linha = _linhas(c.get('/api/propostas/exportar.csv'))[1]
    assert linha[1].startswith("'=")
    assert linha[7].startswith("'=") and linha[8] != ''


def test_parecer_com_classificacao_sem_atipicidade_registrada_vai_a_comite():
    uid, eid = _usuario()
    pid, _ = _parecer(uid, eid)
    # Parecer de antes de `atipicidade_nivel`: bloco existe, mas sem a chave nova.
    p = db.buscar_parecer_empresa(pid, eid)['parecer']
    del p['explicacao_classificacao']['atipicidade_nivel']
    del p['explicacao_classificacao']['motivos_revisao']
    db._exec(f'UPDATE pareceres SET parecer={db._PH} WHERE id={db._PH}',
             (json.dumps(p), pid), commit=True)
    r = _post(_cliente(uid, eid), parecer_id=pid)
    assert r.status_code == 201
    assert r.get_json()['status_alcada'] == 'requer_comite'


def test_valor_invalido_do_cliente_e_400_e_sem_valor_usa_o_do_parecer():
    uid, eid = _usuario()
    pid, _ = _parecer(uid, eid)
    c = _cliente(uid, eid)
    assert _post(c, parecer_id=pid, valor_pretendido=0).status_code == 400
    assert _post(c, parecer_id=pid, valor_pretendido='abc').status_code == 400
    assert _post(c, parecer_id=pid).status_code == 201


def test_simulacao_com_parecer_usa_dados_do_servidor():
    uid, eid = _usuario()
    pid, _ = _parecer(uid, eid, caixa=10_000.0)
    r = _cliente(uid, eid).post('/api/simulacao-proposta',
                                json={'parecer_id': pid, 'geracao_caixa_anual': 9e9})
    assert r.status_code == 200 and r.get_json()['status'] == 'fora_alcada'
