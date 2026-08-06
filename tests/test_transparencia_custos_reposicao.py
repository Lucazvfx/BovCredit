import database as db

from app import app


def _client():
    db.init_db()
    email = 'transparencia_reposicao@example.com'
    usuario = db.buscar_usuario_email(email)
    if not usuario:
        db.criar_usuario(email, 'Transparência Reposição', 'senha123')
        usuario = db.buscar_usuario_email(email)
    cliente = app.test_client()
    with cliente.session_transaction() as sessao:
        sessao['_user_id'] = str(usuario['id'])
    return cliente


def test_api_separa_manutencao_reposicao_e_resultado_antes_da_reposicao():
    resposta = _client().post('/api/classificar', json={
        'valores': [11, 110, 11, 109, 105, 234, 45, 16, 59, 0],
        'preco': 320,
        'custo_arroba': 57,
    })

    assert resposta.status_code == 200
    fluxo = resposta.get_json()['fluxo_gep']

    assert fluxo['custo_manutencao'] > 0
    assert fluxo['custo_reposicao'] > 0
    assert fluxo['custo_operacional'] == round(
        fluxo['custo_manutencao'] + fluxo['custo_reposicao'], 2)
    assert fluxo['resultado_antes_reposicao'] == round(
        fluxo['receita_vendas'] - fluxo['custo_manutencao'], 2)
    assert fluxo['resultado_operacional'] == round(
        fluxo['receita_vendas'] - fluxo['custo_operacional']
        - fluxo['reposicao_reprodutores'], 2)
