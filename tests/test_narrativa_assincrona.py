"""
Narrativa IA fora do caminho crítico do parecer.

A chamada ao Groq leva até 20s; o parecer de crédito não pode esperar por ela.
Estes testes garantem que /api/classificar não bloqueia e que o contexto
necessário para buscar a narrativa depois viaja na resposta.
"""
import database as db
from app import app


def _client():
    db.init_db()
    email = 'narrativa@example.com'
    if not db.buscar_usuario_email(email):
        db.criar_usuario(email, 'Narrativa Test', 'senha123')
    u = db.buscar_usuario_email(email)
    c = app.test_client()
    with c.session_transaction() as s:
        s['_user_id'] = str(u['id'])
    return c


PAYLOAD = {
    'valores': [90, 90, 40, 20, 60, 25, 120, 8, 300, 10],
    'preco': 320, 'credito_valor': 200000, 'prazo_meses': 36, 'juros_aa': 0.11,
}


def test_classificar_nao_gera_narrativa_inline():
    """Modo padrão: o parecer sai sem esperar o Groq."""
    r = _client().post('/api/classificar', json=PAYLOAD)
    assert r.status_code == 200
    d = r.get_json()
    assert d['narrativa_ia'] is None, 'narrativa não deve ser gerada no caminho crítico'


def test_contexto_da_narrativa_viaja_na_resposta():
    """O frontend precisa do contexto para pedir a narrativa depois."""
    d = _client().post('/api/classificar', json=PAYLOAD).get_json()
    ctx = d.get('narrativa_contexto')
    assert ctx, 'contexto ausente — o frontend não conseguiria buscar a narrativa'
    for campo in ('tipo', 'recomendacao', 'total_rebanho', 'geracao_caixa_anual'):
        assert campo in ctx, f'contexto sem {campo}'


def test_endpoint_narrativa_exige_contexto():
    r = _client().post('/api/narrativa', json={'contexto': {}})
    # 400 (contexto vazio) ou 503 (IA desligada) — nunca 500
    assert r.status_code in (400, 503)


def test_endpoint_narrativa_exige_login():
    r = app.test_client().post('/api/narrativa', json={'contexto': {'tipo': 'CRIA'}})
    assert r.status_code in (302, 401)


def test_narrativa_pendente_falso_sem_chave():
    """Sem GROQ_API_KEY o frontend não deve tentar buscar nada."""
    d = _client().post('/api/classificar', json=PAYLOAD).get_json()
    from services.groq_narrativa import _feature_ativa
    if not _feature_ativa():
        assert d['narrativa_pendente'] is False
