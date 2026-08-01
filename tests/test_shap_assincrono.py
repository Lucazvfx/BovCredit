"""
SHAP fora do caminho crítico — a correção de verdade do 502.

Produção devolvia 502 na tela de classificar. Medido em processo real:
construir os TreeExplainer dos quatro estimadores do ensemble aloca ~160 MB,
e esse pico coincidia com a classificação. Com o modelo compartilhado por
`preload_app`, dois workers classificando ao mesmo tempo davam 620 MB contra
um teto de 512 — o processo morria e o gateway respondia 502.

O paliativo foi descer para um worker. A correção é a mesma arquitetura já
usada para a narrativa da IA: calcular sob demanda numa segunda requisição.

    /api/classificar   antes 459 MB e 10,1 s  →  agora 330 MB e 0,04 s
    /api/shap          o pico de ~130 MB acontece aqui, sozinho

O QUE NÃO PODE SE PERDER

A explicabilidade da CMN 4.966/2021 vai no PDF, e o PDF é montado a partir do
`window._lastParecer` do frontend. Se o SHAP saísse do parecer sem ser fundido
de volta, o documento que vai ao comitê perderia os fatores da classificação —
que é exatamente o que a norma exige. Por isso o front funde a resposta no
parecer antes de qualquer download.
"""
import pytest

import database as db
from app import app


@pytest.fixture(scope='module')
def cli():
    db.init_db()
    email = 'shapasync@example.com'
    u = db.buscar_usuario_email(email)
    if not u:
        db.criar_usuario(email, 'Shap', 'senha123')
        u = db.buscar_usuario_email(email)
    app.config['TESTING'] = True
    c = app.test_client()
    with c.session_transaction() as s:
        s['_user_id'] = str(u['id'])
    return c


REBANHO = [300, 280, 400, 200, 900, 1200, 250, 80, 600, 40]
PAYLOAD = {'valores': REBANHO, 'credito_valor': 1_500_000,
           'prazo_meses': 36, 'juros_aa': 0.125}


@pytest.fixture(scope='module')
def resposta(cli):
    return cli.post('/api/classificar', json=PAYLOAD).get_json()


# ── O caminho crítico ficou leve ────────────────────────────────────────────
def test_classificar_nao_calcula_shap_por_padrao(resposta):
    assert resposta['shap_pendente'] is True
    assert resposta['shap_explicacao'] == {}
    assert (resposta['parecer']['shap_explicacao'] or {}) == {}


def test_classificar_devolve_o_contexto_para_a_segunda_chamada(resposta):
    ctx = resposta['shap_contexto']
    assert ctx['valores'] == REBANHO
    assert ctx['tipo'] == resposta['tipo']
    # A proveniência da decisão viaja junto: sem ela o SHAP seria apresentado
    # como causa mesmo quando quem decidiu foi uma regra determinística.
    assert 'origem_decisao' in ctx and 'regra_aplicada' in ctx


# ── A segunda requisição entrega o que a norma pede ─────────────────────────
def test_rota_shap_devolve_os_fatores(cli, resposta):
    r = cli.post('/api/shap', json={'contexto': resposta['shap_contexto']})
    assert r.status_code == 200
    fatores = (r.get_json().get('shap_explicacao') or {}).get('fatores') or []
    assert len(fatores) > 0, 'a explicabilidade sumiu junto com o pico'


def test_shap_preserva_a_proveniencia_da_decisao(cli, resposta):
    """
    Quando a classificação veio de regra, o SHAP é contexto do modelo — não
    justificativa. Apresentá-lo como causa descolaria a explicação do
    processo real, que é o oposto do que a CMN 4.966 pede.
    """
    ctx = dict(resposta['shap_contexto'])
    ctx['origem_decisao'] = 'regra'
    ctx['regra_aplicada'] = 'guarda_ciclo_completo'
    d = cli.post('/api/shap', json={'contexto': ctx}).get_json()
    assert d['shap_explicacao'].get('decisao_por_regra') is True


@pytest.mark.parametrize('corpo', [
    {}, {'contexto': {}}, {'contexto': {'tipo': 'CRIA'}},
    {'contexto': {'valores': [1, 2, 3], 'tipo': 'CRIA'}},
])
def test_contexto_invalido_e_recusado_sem_500(cli, corpo):
    """Entrada ruim vira 400, não erro de servidor."""
    assert cli.post('/api/shap', json=corpo).status_code == 400


def test_rota_shap_exige_login():
    c = app.test_client()
    r = c.post('/api/shap', json={'contexto': {'valores': REBANHO, 'tipo': 'CRIA'}})
    assert r.status_code in (302, 401), 'SHAP de rebanho alheio sem login'


# ── A reversão ──────────────────────────────────────────────────────────────
def test_shap_inline_continua_disponivel():
    """
    `SHAP_INLINE=1` volta a calcular dentro da classificação — saída para
    quem tiver memória sobrando e preferir uma requisição só.
    """
    import app as A
    fonte = open(A.__file__, encoding='utf-8').read()
    assert "os.environ.get('SHAP_INLINE'" in fonte


# ── O que o frontend não pode esquecer ──────────────────────────────────────
def test_frontend_funde_o_shap_no_parecer_antes_do_pdf():
    """
    O PDF é montado do `window._lastParecer`. Sem a fusão, o documento que vai
    ao comitê sai sem os fatores da classificação — perder isso é perder a
    conformidade, não um detalhe de tela.
    """
    html = open('templates/index.html', encoding='utf-8').read()
    assert '_lastParecer.shap_explicacao = shap' in html, (
        'o SHAP assíncrono não está sendo fundido no parecer usado pelo PDF'
    )
    assert 'carregarShap' in html and 'shap_pendente' in html
