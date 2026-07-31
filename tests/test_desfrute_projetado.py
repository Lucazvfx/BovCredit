"""
Desfrute projetado: o sistema precisa enxergar e avaliar a própria projeção.

Dois defeitos motivaram estes testes:

1. O desfrute só entrava no painel de benchmarks se o analista o digitasse.
   A simulação calculava as vendas do ano e ninguém confrontava o resultado
   com a faixa de referência da modalidade — uma projeção que vendia 291% do
   rebanho passava sem alarme e inflava o DSCR.

2. Desfrute era avaliado como "quanto maior melhor", então 291% virava
   "EXCELENTE". O material de treinamento diz o oposto: "desfrute muito alto
   pode aumentar riscos sanitários, de mercado e de custo — ideal é
   equilíbrio".
"""
import pytest

import database as db
from app import app


@pytest.fixture(scope='module')
def client():
    db.init_db()
    email = 'desfrute@example.com'
    if not db.buscar_usuario_email(email):
        db.criar_usuario(email, 'Desfrute Test', 'senha123')
    u = db.buscar_usuario_email(email)
    c = app.test_client()
    with c.session_transaction() as s:
        s['_user_id'] = str(u['id'])
    return c


REBANHOS = {
    'cria':            [60, 60, 30, 15, 45, 20, 90, 6, 170, 8],
    'ciclo_completo':  [80, 80, 50, 50, 60, 60, 90, 40, 220, 60],
    'engorda':         [0, 0, 0, 15, 0, 60, 0, 90, 0, 140],
}


def _analisa(client, v, **extra):
    payload = {'valores': v, 'preco': 320}
    payload.update(extra)
    r = client.post('/api/classificar', json=payload)
    assert r.status_code == 200
    return r.get_json()


def _item_desfrute(d):
    for b in (d.get('benchmarks') or []):
        if isinstance(b, dict) and b.get('key') == 'desfrute':
            return b
    return None


@pytest.mark.parametrize('nome', list(REBANHOS))
def test_desfrute_projetado_viaja_na_resposta(client, nome):
    """A projeção precisa declarar quanto do rebanho ela vende."""
    d = _analisa(client, REBANHOS[nome])
    dp = d.get('desfrute_projetado')
    assert dp, 'desfrute_projetado ausente'
    assert dp['rebanho'] == sum(REBANHOS[nome])
    assert dp['vendidos'] >= 0
    assert dp['origem'] == 'projetado'
    # confere a aritmética contra os próprios campos
    esperado = round(dp['vendidos'] / dp['rebanho'] * 100, 1)
    assert dp['valor'] == pytest.approx(esperado, abs=0.2)


@pytest.mark.parametrize('nome', list(REBANHOS))
def test_desfrute_entra_no_painel_sem_o_analista_digitar(client, nome):
    """
    Regressão: antes o desfrute só era avaliado se viesse no payload, então a
    projeção nunca era confrontada com a referência da modalidade.
    """
    d = _analisa(client, REBANHOS[nome])
    item = _item_desfrute(d)
    assert item is not None, 'desfrute não chegou ao painel de benchmarks'
    assert item['valor'] == pytest.approx(d['desfrute_projetado']['valor'], abs=0.2)


def test_giro_excessivo_nao_e_excelencia(client):
    """
    Uma engorda que gira 4 lotes/ano vende ~290% do rebanho. Isso não pode ser
    rotulado "excelente" — o material trata giro excessivo como risco.
    """
    d = _analisa(client, REBANHOS['engorda'])
    item = _item_desfrute(d)
    assert item is not None
    assert item['valor'] > 120, 'este rebanho deve exceder o teto da engorda'
    assert item['faixa'] == 'acima', (
        f"desfrute de {item['valor']}% foi classificado como '{item['faixa']}' "
        f"— giro acima do teto precisa virar sinal de atenção"
    )
    assert item.get('alerta'), 'a faixa "acima" precisa explicar o motivo ao analista'


def test_valor_informado_pelo_analista_prevalece(client):
    """Se o analista digita o desfrute, o número dele manda."""
    d = _analisa(client, REBANHOS['cria'], desfrute_pct=22)
    item = _item_desfrute(d)
    assert item is not None
    assert item['valor'] == pytest.approx(22, abs=0.1)
    assert d['desfrute_projetado']['origem'] == 'informado'


def test_desfrute_dentro_da_faixa_nao_alerta(client):
    """Não pode alarmar quem está dentro da referência."""
    d = _analisa(client, REBANHOS['cria'], desfrute_pct=25)   # CRIA: 18–30%
    item = _item_desfrute(d)
    assert item['faixa'] != 'acima'
    assert not item.get('alerta')
