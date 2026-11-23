"""
Integridade do loop de dado real: confirmação, descarte, isolamento e
sinais de atipicidade.

Invariante central: só o que um humano confirmou, do próprio registro, e que
não foi descartado depois, chega a `db.exportar_treino`.
"""
import random
import uuid

import pytest

import database as db
import ml_engine
from app import app


V_TESTE = [80, 80, 50, 50, 60, 60, 90, 40, 220, 60]


def _cliente():
    db.init_db()
    email = f'integridade-{uuid.uuid4().hex}@example.com'
    db.criar_usuario(email, 'Integridade ML', 'senha123')
    user = db.buscar_usuario_email(email)
    c = app.test_client()
    with c.session_transaction() as s:
        s['_user_id'] = str(user['id'])
    return c, user['id']


@pytest.fixture
def client():
    return _cliente()[0]


def _vetor_inedito():
    """O banco local persiste entre execuções: sorteia um vetor ainda não treinado."""
    existentes = {tuple(float(x) for x in v) for v in db.exportar_treino()[0]}
    for _ in range(100):
        v = [random.randint(20, 400) for _ in range(10)]
        if tuple(float(x) for x in v) not in existentes:
            return v
    pytest.skip('não foi possível sortear um rebanho inédito')


def _classificar(client, v):
    r = client.post('/api/classificar', json={'valores': v, 'preco': 320})
    assert r.status_code == 200
    return r.get_json()


def _no_treino(v):
    return [float(x) for x in v] in [[float(x) for x in a] for a in db.exportar_treino()[0]]


# ── Confirmação cai no caso certo ───────────────────────────────────────────
def test_confirmar_ciclo_rotula_o_caso_do_proprio_registro(client):
    """
    `casos_reais.id` e `registros.id` são sequências independentes. A rota
    precisa achar o caso por `registro_id`, não tratar um id como o outro.
    """
    d_a = _classificar(client, _vetor_inedito())
    d_b = _classificar(client, _vetor_inedito())

    r = client.post('/api/confirmar-ciclo',
                    json={'registro_id': d_b['registro_id'], 'ciclo': 'CRIA'})
    assert r.status_code == 200

    caso_a = db.buscar_caso_real_por_registro(d_a['registro_id'])
    caso_b = db.buscar_caso_real_por_registro(d_b['registro_id'])
    assert caso_b['status'] == 'CONFIRMADO' and caso_b['classificacao_humana'] == 'CRIA'
    assert caso_a['status'] == 'PENDENTE' and not caso_a['classificacao_humana']


def _max_id(tabela):
    return int(dict(db._exec(f'SELECT COALESCE(MAX(id), 0) AS n FROM {tabela}',
                             fetch='one'))['n'])


def _trocar_id(tabela, de, para):
    db._exec(f'UPDATE {tabela} SET id={db._PH} WHERE id={db._PH}', (para, de), commit=True)


def test_caso_com_id_igual_ao_registro_nao_e_confundido():
    """
    Monta os ids de propósito, sem depender do estado do banco: o registro R
    tem o caso vinculado K (K != R), e existe um caso INTRUSO de id == R, do
    mesmo usuário e sem vínculo. O código antigo (que tratava registro_id como
    casos_reais.id) rotularia o intruso e deixaria o caso certo PENDENTE.
    """
    client, uid = _cliente()
    base = max(_max_id('registros'), _max_id('casos_reais')) + 1000
    R, K = base, base + 1

    rid = db.salvar(valores=V_TESTE, class_ml='CRIA', confianca=50, user_id=uid)
    _trocar_id('registros', rid, R)
    cid = db.criar_caso_real(V_TESTE, 'CRIA', user_id=uid, registro_id=R)
    _trocar_id('casos_reais', cid, K)
    iid = db.criar_caso_real(V_TESTE, 'CRIA', user_id=uid)          # sem registro
    _trocar_id('casos_reais', iid, R)

    assert db.buscar_caso_real(R)['registro_id'] is None
    assert db.buscar_caso_real_por_registro(R)['id'] == K

    r = client.post('/api/confirmar-ciclo', json={'registro_id': R, 'ciclo': 'ENGORDA'})
    assert r.status_code == 200

    certo, intruso = db.buscar_caso_real(K), db.buscar_caso_real(R)
    assert certo['status'] == 'CONFIRMADO' and certo['classificacao_humana'] == 'ENGORDA'
    assert intruso['status'] == 'PENDENTE' and not intruso['classificacao_humana']


def test_confirmar_caso_gravado_em_outra_empresa_nao_deixa_pela_metade(client):
    """O caso guarda a empresa em que nasceu; a confirmação usa essa, não a ativa agora."""
    d = _classificar(client, _vetor_inedito())
    caso = db.buscar_caso_real_por_registro(d['registro_id'])
    db._exec(f"UPDATE casos_reais SET empresa_id=987654 WHERE id={db._PH}",
             (caso['id'],), commit=True)
    r = client.post('/api/confirmar-ciclo',
                    json={'registro_id': d['registro_id'], 'ciclo': 'CRIA'})
    assert r.status_code == 200
    assert db.buscar_caso_real(caso['id'])['status'] == 'CONFIRMADO'
    assert db.buscar_registro_por_id(d['registro_id'])['class_conf'] == 'CRIA'


def test_reconfirmar_caso_descartado_devolve_409(client):
    v = _vetor_inedito()
    d = _classificar(client, v)
    caso = db.buscar_caso_real_por_registro(d['registro_id'])
    client.post(f"/api/casos-reais/{caso['id']}/descartar", json={'motivo': 'Erro'})
    r = client.post('/api/confirmar-ciclo',
                    json={'registro_id': d['registro_id'], 'ciclo': 'CRIA'})
    assert r.status_code == 409
    assert db.buscar_caso_real(caso['id'])['status'] == 'DESCARTADO'
    assert db.buscar_registro_por_id(d['registro_id'])['class_conf'] is None
    assert not _no_treino(v)


# ── Isolamento multi-tenant ─────────────────────────────────────────────────
def test_usuario_nao_rotula_registro_de_outro(client):
    outro, _ = _cliente()
    v = _vetor_inedito()
    d = _classificar(outro, v)

    r = client.post('/api/confirmar-ciclo',
                    json={'registro_id': d['registro_id'], 'ciclo': 'CRIA'})
    assert r.status_code == 404
    assert db.buscar_registro_por_id(d['registro_id'])['class_conf'] is None
    assert not _no_treino(v), 'rótulo de outro tenant entrou no treino'


@pytest.mark.parametrize('rid', ['abc', [1], {'a': 1}, True, 0, -3, 2**40])
def test_registro_id_malformado_devolve_400(client, rid):
    r = client.post('/api/confirmar-ciclo', json={'registro_id': rid, 'ciclo': 'CRIA'})
    assert r.status_code == 400


# ── Descarte retira do treino ───────────────────────────────────────────────
def test_descartar_caso_confirmado_retira_do_treino(client):
    v = _vetor_inedito()
    d = _classificar(client, v)
    client.post('/api/confirmar-ciclo',
                json={'registro_id': d['registro_id'], 'ciclo': d['tipo']})
    assert _no_treino(v)

    caso = db.buscar_caso_real_por_registro(d['registro_id'])
    r = client.post(f"/api/casos-reais/{caso['id']}/descartar",
                    json={'motivo': 'Ficha com erro de digitação'})
    assert r.status_code == 200
    assert not _no_treino(v), (
        'caso descartado voltou ao treino pela via legada (registros.class_conf)'
    )


def test_nao_confirmado_nunca_entra_mesmo_descartado_ou_pendente(client):
    v1, v2 = _vetor_inedito(), _vetor_inedito()
    _classificar(client, v1)                       # fica PENDENTE
    d2 = _classificar(client, v2)
    caso2 = db.buscar_caso_real_por_registro(d2['registro_id'])
    client.post(f"/api/casos-reais/{caso2['id']}/descartar", json={'motivo': 'Duplicada'})
    assert not _no_treino(v1) and not _no_treino(v2)


# ── Linha corrompida não derruba o retreino ─────────────────────────────────
def test_exportar_treino_ignora_vetor_de_tamanho_errado():
    db.init_db()
    antes = len(db.exportar_treino()[0])
    rid = db.salvar(valores=[1, 2, 3], class_ml='CRIA', confianca=50)
    db.confirmar(rid, 'CRIA')
    X, y = db.exportar_treino()
    assert len(X) == antes and len(X) == len(y)
    assert all(len(x) == 10 for x in X)


def test_exportar_treino_ignora_nan_e_bool():
    db.init_db()
    antes = len(db.exportar_treino()[0])
    for vetor in ([1, 2, 3, 4, 5, 6, 7, 8, 9, float('nan')],
                  [True, 2, 3, 4, 5, 6, 7, 8, 9, 10]):
        rid = db.salvar(valores=vetor, class_ml='CRIA', confianca=50)
        db.confirmar(rid, 'CRIA')
    assert len(db.exportar_treino()[0]) == antes


# ── Atipicidade vira sinal de revisão humana ────────────────────────────────
def _atip(nivel):
    return {'distancia': 99.0, 'nivel': nivel, 'mensagem': 'x',
            'limiar_p95': 10.0, 'limiar_p99': 15.0}


def test_muito_atipico_exige_revisao_humana(monkeypatch):
    monkeypatch.setattr(ml_engine, 'calcular_atipicidade', lambda v: _atip('muito_atipico'))
    r = ml_engine.classificar(V_TESTE, bois_vendidos=10)
    assert r['revisao_humana'] is True
    assert r['motivos_revisao'] == ['muito_atipico']


@pytest.mark.parametrize('nivel', ['tipico', 'atipico'])
def test_nivel_nao_extremo_com_dados_completos_nao_exige_revisao(monkeypatch, nivel):
    monkeypatch.setattr(ml_engine, 'calcular_atipicidade', lambda v: _atip(nivel))
    r = ml_engine.classificar(V_TESTE, bois_vendidos=10)
    assert r['revisao_humana'] is False
    assert r['motivos_revisao'] == []


def test_atipicidade_indisponivel_nao_inventa_motivo(monkeypatch):
    monkeypatch.setattr(ml_engine, 'calcular_atipicidade', lambda v: None)
    r = ml_engine.classificar(V_TESTE, bois_vendidos=10)
    assert r['atipicidade'] is None
    assert r['revisao_humana'] is False


def test_dados_incompletos_e_atipicos_acumulam_motivos(monkeypatch):
    monkeypatch.setattr(ml_engine, 'calcular_atipicidade', lambda v: _atip('muito_atipico'))
    r = ml_engine.classificar(V_TESTE)          # sem bois_vendidos
    assert r['revisao_humana'] is True
    assert set(r['motivos_revisao']) == {'dados_incompletos', 'muito_atipico'}


def test_rebanho_zerado_exige_revisao_humana():
    r = ml_engine.classificar([0] * 10, bois_vendidos=10)
    assert r['revisao_humana'] is True
    assert 'rebanho_zerado' in r['motivos_revisao']


@pytest.mark.parametrize('escala', [10_000, 100_000])
def test_rebanho_fora_de_faixa_exige_revisao_humana(escala):
    r = ml_engine.classificar([escala] * 10, bois_vendidos=10)
    assert r['revisao_humana'] is True
    assert 'rebanho_fora_faixa' in r['motivos_revisao']


def test_rebanho_plausivel_nao_ganha_motivo_novo():
    r = ml_engine.classificar(V_TESTE, bois_vendidos=10)
    assert not {'rebanho_zerado', 'rebanho_fora_faixa'} & set(r['motivos_revisao'])


def test_classificar_continua_sem_shap_inline():
    """Guarda do isolamento: os campos novos não podem puxar o SHAP para o caminho síncrono."""
    r = ml_engine.classificar(V_TESTE, bois_vendidos=10)
    assert 'shap' not in r and 'shap_valores' not in r
