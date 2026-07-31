"""
A região precisa atravessar TODA a cadeia de cálculo.

Ajustar o preço e não propagar seria pior que não ajustar: o parecer diria
"preço de RO" e calcularia a garantia com preço de SP. Estes testes rodam
/api/classificar com o mesmo rebanho em praças diferentes e conferem que os
números derivados de preço acompanham — valoração, receita, fluxo e LTV.
"""
import pytest

import database as db
from app import app

REBANHO = [65, 65, 65, 65, 60, 60, 90, 40, 220, 60]


@pytest.fixture(scope='module')
def client():
    db.init_db()
    email = 'regional@example.com'
    if not db.buscar_usuario_email(email):
        db.criar_usuario(email, 'Regional Test', 'senha123')
    u = db.buscar_usuario_email(email)
    c = app.test_client()
    with c.session_transaction() as s:
        s['_user_id'] = str(u['id'])
    return c


def _analisar(client, municipio, **extra):
    payload = {'valores': REBANHO, 'municipio': municipio,
               'credito_valor': 1_500_000, 'prazo_meses': 36, 'juros_aa': 0.125}
    payload.update(extra)
    r = client.post('/api/classificar', json=payload)
    assert r.status_code == 200, r.get_data(as_text=True)[:300]
    return r.get_json()


@pytest.fixture(scope='module')
def sp(client):
    return _analisar(client, 'Araçatuba - SP')


@pytest.fixture(scope='module')
def ro(client):
    return _analisar(client, 'Ariquemes - RO')


def test_a_praca_e_identificada_e_reportada(sp, ro):
    assert sp['parecer']['precos_regional']['uf'] == 'SP'
    assert ro['parecer']['precos_regional']['uf'] == 'RO'
    assert ro['parecer']['precos_regional']['ajustado'] is True
    assert ro['parecer']['precos_regional']['basis_pct'] < 0


def test_valor_do_rebanho_acompanha_a_praca(sp, ro):
    """A valoração é a base de tudo — se ela não mudar, nada mudou."""
    v_sp = sp['fluxo_gep']['valor_rebanho_ini']
    v_ro = ro['fluxo_gep']['valor_rebanho_ini']
    assert v_ro < v_sp, 'o mesmo rebanho não pode valer igual em SP e RO'


def test_receita_de_vendas_acompanha_a_praca(sp, ro):
    assert ro['fluxo_gep']['receita_vendas'] < sp['fluxo_gep']['receita_vendas']


def test_garantia_acompanha_a_praca(sp, ro):
    """
    O ponto que mais importa: um LTV com preço paulista numa fazenda de RO
    diria que a garantia cobre quando ela não cobre.
    """
    g_sp = sp['parecer']['garantia']
    g_ro = ro['parecer']['garantia']
    assert g_ro['valor_mercado'] < g_sp['valor_mercado']
    assert g_ro['valor_garantia'] < g_sp['valor_garantia']
    assert g_ro['ltv'] > g_sp['ltv'], (
        'mesmo crédito sobre garantia menor tem que dar LTV maior'
    )


def test_preco_digitado_ignora_a_praca(client):
    """
    Preço informado pelo analista já é o da praça dele. Se o sistema aplicasse
    o diferencial em cima, descontaria duas vezes — e o erro seria invisível.
    """
    d = _analisar(client, 'Ariquemes - RO', preco_boi=400.0)
    cats = {c['categoria'] for c in d['parecer']['precos_regional']['categorias']}
    assert 'preco_boi' not in cats, 'o preço digitado foi descontado indevidamente'


def test_sem_municipio_usa_nacional_e_declara(client):
    d = _analisar(client, '')
    reg = d['parecer']['precos_regional']
    assert reg['ajustado'] is False
    assert reg['situacao'] == 'sem_uf'
    assert 'nacional' in reg['resumo'].lower()


def test_memoria_de_calculo_carrega_o_diferencial(ro):
    mem = ro['parecer']['precos_regional']['memoria']
    assert mem
    assert any('diferencial' in m['passo'].lower() for m in mem)


def test_secao_entra_no_parecer(ro):
    assert 'precos_regional' in ro['parecer']['secoes']


def test_cotacao_auto_preenchida_pela_tela_ainda_recebe_o_diferencial(client):
    """
    O bug que só apareceu no navegador: a tela preenche os campos de cotação
    com o indicador nacional e os envia. Tratar isso como "digitado" fazia o
    diferencial de praça nunca ser aplicado na interface — e os testes de API,
    que não mandavam preços, não pegavam.

    `precos_manuais` é a autoridade sobre o que o analista realmente alterou.
    """
    d = _analisar(client, 'Ariquemes - RO',
                  preco_boi=330.0, preco_vaca=308.0,
                  preco_bezerro=3000.0, preco_bezerra=2700.0,
                  precos_manuais=[])          # nenhum foi digitado
    reg = d['parecer']['precos_regional']
    assert reg['ajustado'] is True, (
        'cotação auto-preenchida foi confundida com preço digitado'
    )
    cats = {c['categoria'] for c in reg['categorias']}
    assert 'preco_boi' in cats


def test_precos_manuais_protege_apenas_o_que_foi_digitado(client):
    d = _analisar(client, 'Ariquemes - RO',
                  preco_boi=400.0, preco_vaca=308.0,
                  preco_bezerro=3000.0, preco_bezerra=2700.0,
                  precos_manuais=['preco_boi'])
    cats = {c['categoria'] for c in d['parecer']['precos_regional']['categorias']}
    assert 'preco_boi' not in cats, 'o preço digitado foi descontado'
    assert 'preco_vaca' in cats, 'a cotação automática deveria ter sido ajustada'


def test_sem_precos_manuais_mantem_comportamento_antigo(client):
    """Quem chama a API direto e manda um preço está mesmo informando um preço."""
    d = _analisar(client, 'Ariquemes - RO', preco_boi=400.0)
    cats = {c['categoria'] for c in d['parecer']['precos_regional']['categorias']}
    assert 'preco_boi' not in cats
