from app import app


def test_healthz_nao_exige_login_e_nao_expoe_segredos():
    resposta = app.test_client().get('/healthz')

    assert resposta.status_code == 200
    assert resposta.get_json() == {'status': 'ok'}
    assert 'SECRET_KEY' not in resposta.get_data(as_text=True)
