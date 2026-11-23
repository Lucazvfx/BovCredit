import uuid

import pytest

import app as app_module
import database as db
from services import papeis_empresa as pap

CAIXA, JUROS, PRAZO = 1_000_000.0, 0.10, 60


def _usuario(nome='Pap'):
    db.init_db()
    email = f'{nome}-{uuid.uuid4().hex[:8]}@example.com'
    uid = db.criar_usuario(email, nome, 'senha123')
    return uid, db.empresas_do_usuario(uid)[0]['id'], email


def _cliente(uid, empresa_id=None):
    c = app_module.app.test_client()
    with c.session_transaction() as s:
        s['_user_id'] = str(uid)
        if empresa_id:
            s['empresa_ativa_id'] = empresa_id
    return c


def _membro(empresa_id, papel):
    """Novo usuário vinculado à empresa com o papel dado."""
    uid, eid_propria, _ = _usuario('Membro')
    db._exec(f'UPDATE empresa_membros SET empresa_id={db._PH}, papel={db._PH} '
             f'WHERE user_id={db._PH}', (empresa_id, papel, uid), commit=True)
    return uid


def _corpo(valor=300_000, **kw):
    base = dict(referencia='CT-001', valor_pretendido=valor, prazo_meses=PRAZO,
                geracao_caixa_anual=CAIXA, juros_aa=JUROS)
    base.update(kw)
    return base


# ── Migração e padrão ────────────────────────────────────────────────────────

def test_criador_da_empresa_e_admin_e_provedor_e_analista():
    uid, eid, _ = _usuario()
    assert db.papel_do_membro(uid, eid) == 'admin'
    novo = db.criar_usuario_do_provedor(
        f'p-{uuid.uuid4().hex[:6]}@example.com', 'P', 'google', uuid.uuid4().hex, eid)
    assert db.papel_do_membro(novo, eid) == 'analista'


def test_migracao_preenche_papel_nulo_e_e_idempotente():
    uid, eid, _ = _usuario()
    # vínculo legado: empresa de um membro só, papel NULL -> admin
    db._exec(f'UPDATE empresa_membros SET papel=NULL WHERE user_id={db._PH}', (uid,), commit=True)
    db.init_db()
    assert db.papel_do_membro(uid, eid) == 'admin'
    # empresa com vários membros: ninguém é promovido por adivinhação
    outro = _membro(eid, 'analista')
    db._exec(f'UPDATE empresa_membros SET papel=NULL WHERE empresa_id={db._PH}', (eid,), commit=True)
    db.init_db()
    assert db.papel_do_membro(uid, eid) == 'analista'
    assert db.papel_do_membro(outro, eid) == 'analista'
    db.init_db()  # idempotente
    assert db.papel_do_membro(uid, eid) == 'analista'


def test_papel_nulo_ou_invalido_e_tratado_como_analista():
    assert pap.normalizar_papel(None) == 'analista'
    assert pap.normalizar_papel('root') == 'analista'


# ── Política de alçada por admin da empresa ──────────────────────────────────

def test_admin_da_empresa_edita_politica_e_analista_nao():
    uid, eid, _ = _usuario()
    analista = _membro(eid, 'analista')
    r = _cliente(uid).put('/api/politica-alcada', json={'alcada_comite': 900_000})
    assert r.status_code == 200
    assert db.obter_politica_alcada(eid)['alcada_comite'] == 900_000
    assert _cliente(analista, eid).get('/api/politica-alcada').get_json()['pode_editar'] is False
    r = _cliente(analista, eid).put('/api/politica-alcada', json={'alcada_comite': 1_000_000})
    assert r.status_code == 403
    assert db.obter_politica_alcada(eid)['alcada_comite'] == 900_000


def test_admin_de_outra_empresa_nao_edita_politica_alheia():
    uid_a, eid_a, _ = _usuario('A')
    uid_b, eid_b, _ = _usuario('B')
    # B tenta forçar a empresa ativa de A: a sessão é ignorada, vale a dele
    c = _cliente(uid_b, eid_a)
    c.put('/api/politica-alcada', json={'alcada_comite': 777_000})
    assert db.obter_politica_alcada(eid_a)['padrao'] is True
    assert db.obter_politica_alcada(eid_b)['alcada_comite'] == 777_000


# ── Gestão de papéis ─────────────────────────────────────────────────────────

def test_admin_gerencia_papeis_e_auditoria_sem_email():
    uid, eid, _ = _usuario()
    alvo = _membro(eid, 'analista')
    c = _cliente(uid)
    r = c.put(f'/api/empresa/membros/{alvo}/papel', json={'papel': 'aprovador'})
    assert r.status_code == 200 and db.papel_do_membro(alvo, eid) == 'aprovador'
    lista = c.get('/api/empresa/papeis').get_json()
    assert lista['meu_papel'] == 'admin' and len(lista['membros']) == 2
    ev = [a for a in db.listar_acessos(evento='papel_alterado') if a['recurso_id'] == str(eid)]
    assert ev and 'aprovador' in ev[0]['detalhe']
    assert '@' not in ev[0]['detalhe']


def test_analista_nao_gerencia_papeis_nem_lista_membros():
    uid, eid, _ = _usuario()
    analista = _membro(eid, 'analista')
    c = _cliente(analista, eid)
    assert c.put(f'/api/empresa/membros/{uid}/papel', json={'papel': 'analista'}).status_code == 403
    assert c.get('/api/empresa/papeis').get_json()['membros'] == []


def test_papel_nao_atravessa_empresas():
    uid_a, eid_a, _ = _usuario('A')
    uid_b, eid_b, _ = _usuario('B')
    r = _cliente(uid_a).put(f'/api/empresa/membros/{uid_b}/papel', json={'papel': 'aprovador'})
    assert r.status_code == 404
    assert db.papel_do_membro(uid_b, eid_b) == 'admin'


def test_nao_remove_ultimo_admin_e_valida_papel():
    uid, eid, _ = _usuario()
    c = _cliente(uid)
    assert c.put(f'/api/empresa/membros/{uid}/papel', json={'papel': 'analista'}).status_code == 400
    assert c.put(f'/api/empresa/membros/{uid}/papel', json={'papel': 'root'}).status_code == 400
    assert db.papel_do_membro(uid, eid) == 'admin'


# ── Propostas e alçada ───────────────────────────────────────────────────────

def _registrar(c, **kw):
    r = c.post('/api/propostas', json=_corpo(**kw))
    assert r.status_code == 201, r.get_json()
    return r.get_json()


def test_fluxo_completo_dentro_da_alcada_analista_decide():
    uid, eid, _ = _usuario()
    analista = _membro(eid, 'analista')
    ca = _cliente(analista, eid)
    p = _registrar(ca, valor=200_000)
    assert p['status'] == 'em_analise' and p['status_alcada'] == 'dentro_alcada'
    r = ca.post(f"/api/propostas/{p['id']}/decisao",
                json={'decisao': 'aprovado', 'parecer': 'Capacidade folgada.'})
    assert r.status_code == 200
    item = ca.get('/api/propostas').get_json()['propostas'][0]
    assert item['status'] == 'aprovado' and item['parecer_decisor'] == 'Capacidade folgada.'
    assert item['decidido_por_nome'] and item['decidido_em'] and item['criado_por_nome']
    # decisão final: não se decide duas vezes
    r = ca.post(f"/api/propostas/{p['id']}/decisao",
                json={'decisao': 'reprovado', 'parecer': 'x'})
    assert r.status_code == 409


def test_requer_comite_bloqueia_analista_e_aprovador_decide():
    uid, eid, _ = _usuario()
    analista = _membro(eid, 'analista')
    aprovador = _membro(eid, 'aprovador')
    ca, cp = _cliente(analista, eid), _cliente(aprovador, eid)
    p = _registrar(ca, valor=800_000)   # acima de 500k, abaixo do comitê
    assert p['status_alcada'] == 'requer_comite'
    corpo = {'decisao': 'aprovado_com_ressalva', 'parecer': 'Com garantia adicional.'}
    assert ca.post(f"/api/propostas/{p['id']}/decisao", json=corpo).status_code == 403
    assert ca.get('/api/propostas').get_json()['propostas'][0]['status'] == 'em_analise'
    assert ca.get('/api/propostas').get_json()['propostas'][0]['pode_decidir'] is False
    # a recusa fica na trilha, sem o texto do parecer
    neg = [a for a in db.listar_acessos(evento='proposta_decisao_negada')
           if a['recurso_id'] == str(p['id'])]
    assert neg and neg[0]['sucesso'] in (0, False)
    assert 'garantia' not in (neg[0]['detalhe'] or '')
    assert cp.post(f"/api/propostas/{p['id']}/decisao", json=corpo).status_code == 200
    assert cp.get('/api/propostas').get_json()['propostas'][0]['status'] == 'aprovado_com_ressalva'


def test_fora_alcada_reprovacao_pelo_admin_e_analista_bloqueado():
    uid, eid, _ = _usuario()
    analista = _membro(eid, 'analista')
    p = _registrar(_cliente(analista, eid), valor=5_000_000)
    assert p['status_alcada'] == 'fora_alcada'
    corpo = {'decisao': 'reprovado', 'parecer': 'Acima da alçada do comitê.'}
    assert _cliente(analista, eid).post(f"/api/propostas/{p['id']}/decisao", json=corpo).status_code == 403
    assert _cliente(uid).post(f"/api/propostas/{p['id']}/decisao", json=corpo).status_code == 200
    ev = [a for a in db.listar_acessos(evento='proposta_decidida') if a['recurso_id'] == str(p['id'])]
    assert ev and 'reprovado' in ev[0]['detalhe']


def test_cliente_nao_define_a_classificacao_de_alcada():
    uid, eid, _ = _usuario()
    p = _registrar(_cliente(uid), valor=5_000_000, status_alcada='dentro_alcada')
    assert p['status_alcada'] == 'fora_alcada'


def test_proposta_isolada_entre_empresas():
    uid_a, eid_a, _ = _usuario('A')
    uid_b, eid_b, _ = _usuario('B')
    p = _registrar(_cliente(uid_a), valor=100_000)
    cb = _cliente(uid_b)
    assert cb.get('/api/propostas').get_json()['propostas'] == []
    r = cb.post(f"/api/propostas/{p['id']}/decisao", json={'decisao': 'aprovado', 'parecer': 'x'})
    assert r.status_code == 404
    assert _cliente(uid_a).get('/api/propostas').get_json()['propostas'][0]['status'] == 'em_analise'


@pytest.mark.parametrize('corpo', [
    {'decisao': 'em_analise', 'parecer': 'x'},
    {'decisao': 'aprovado', 'parecer': ''},
    {'decisao': 'aprovado', 'parecer': 'x' * 2001},
    {'decisao': 'aprovado'},
])
def test_decisao_invalida_e_rejeitada(corpo):
    uid, eid, _ = _usuario()
    c = _cliente(uid)
    p = _registrar(c, valor=100_000)
    assert c.post(f"/api/propostas/{p['id']}/decisao", json=corpo).status_code == 400


def test_registro_valida_entrada():
    uid, eid, _ = _usuario()
    c = _cliente(uid)
    assert c.post('/api/propostas', json=_corpo(referencia='')).status_code == 400
    assert c.post('/api/propostas', json=_corpo(referencia='x' * 121)).status_code == 400
    assert c.post('/api/propostas', json=_corpo(valor=-1)).status_code == 400
    assert c.get('/api/propostas?status=qualquer').status_code == 400
    assert app_module.app.test_client().get('/api/propostas').status_code in (302, 401)


# ── Navegador: sem overflow horizontal em 1440x900 e 390x844 ─────────────────

def test_ui_papeis_e_propostas_em_navegador_sem_overflow(tmp_path):
    import pathlib
    import shutil
    import subprocess
    root = pathlib.Path(__file__).resolve().parent.parent
    node = shutil.which('node')
    if not node or subprocess.run([node, '-e', "require('playwright')"],
                                  capture_output=True).returncode != 0:
        pytest.skip('Node/Playwright indisponível')
    site, shots = tmp_path / 'site', tmp_path / 'shots'
    site.mkdir(), shots.mkdir()
    uid, _, _ = _usuario('UiAlc')
    r = _cliente(uid).get('/app')
    assert r.status_code == 200
    (site / 'index.html').write_bytes(r.data)
    shutil.copytree(root / 'static', site / 'static')
    out = subprocess.run([node, str(root / 'tests' / 'browser' / 'alcada_layout.js'),
                          str(site), str(shots)], capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stdout + out.stderr
    assert len([ln for ln in out.stdout.splitlines() if ' OK ' in ln]) == 4, out.stdout


# ── Correções da revisão crítica ─────────────────────────────────────────────

def test_rebaixar_ultimo_admin_e_recusado_no_proprio_update():
    uid, eid, _ = _usuario()
    assert db.definir_papel_membro(eid, uid, 'analista') is False
    assert db.papel_do_membro(uid, eid) == 'admin'
    outro = _membro(eid, 'admin')
    assert db.definir_papel_membro(eid, uid, 'analista') is True
    assert db.definir_papel_membro(eid, outro, 'analista') is False   # agora é o último
    assert db.contar_admins_empresa(eid) == 1


def test_migracao_com_vinculo_duplicado_conta_um_usuario_so():
    uid, eid, _ = _usuario()
    db._exec(f'INSERT INTO empresa_membros (empresa_id, user_id) VALUES ({db._PH},{db._PH})',
             (eid, uid), commit=True)
    db._exec(f'UPDATE empresa_membros SET papel=NULL WHERE user_id={db._PH}', (uid,), commit=True)
    db.init_db()
    assert db.papel_do_membro(uid, eid) == 'admin'


def test_status_de_alcada_desconhecido_exige_autorizado():
    assert pap.pode_decidir('analista', 'dentro_alcada') is True
    assert pap.pode_decidir('analista', 'qualquer') is False
    assert pap.pode_decidir('aprovador', 'qualquer') is True


@pytest.mark.parametrize('ref', ['123.456.789-09', '12345678909', '12.345.678/0001-95', 'CT 12345678000195'])
def test_referencia_rejeita_cpf_cnpj(ref):
    uid, eid, _ = _usuario()
    r = _cliente(uid).post('/api/propostas', json=_corpo(referencia=ref))
    assert r.status_code == 400
