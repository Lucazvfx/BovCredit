"""Testes unitários e de integração para o motor de Compliance Socioambiental & ESG (Bacen)."""
import pytest

from services.esg_engine import (
    Bioma,
    ParecerESG,
    StatusCAR,
    analisar_compliance_socioambiental,
    calcular_metricas_florestais,
    validar_sintaxe_car,
)


def test_validacao_sintaxe_car():
    # 1. Padrão SICAR válido MT
    valido, msg = validar_sintaxe_car('MT-5107602-C75A20B7631E44AA8BF0D382A13894E2')
    assert valido is True

    # 2. Padrão SICAR válido PR
    valido_pr, _ = validar_sintaxe_car('PR-4108304-4F1E9319B44B4C0BA7072E2E67590C28')
    assert valido_pr is True

    # 3. UF inexistente
    invalido_uf, msg_uf = validar_sintaxe_car('ZZ-1234567-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA')
    assert invalido_uf is False
    assert 'inválida' in msg_uf

    # 4. Formato sem separadores
    invalido_fmt, _ = validar_sintaxe_car('123456')
    assert invalido_fmt is False

    # 5. String vazia
    invalido_vazio, _ = validar_sintaxe_car('')
    assert invalido_vazio is False


def test_calculo_reserva_legal_por_bioma():
    # Amazônia Floresta (80% exigido)
    res_am = calcular_metricas_florestais(
        numero_car='PA-1505502-A1B2C3D4E5F6A1B2C3D4E5F6A1B2C3D4',
        status=StatusCAR.ATIVO,
        bioma=Bioma.AMAZONIA_FLORESTA,
        area_total_ha=1000.0,
        area_reserva_legal_ha=820.0,
        area_app_ha=50.0,
    )
    assert res_am.percentual_rl_exigido == 0.80
    assert res_am.percentual_rl_declarado == 0.82
    assert res_am.deficit_ou_excedente_rl_ha == 20.0
    assert res_am.em_conformidade_florestal is True

    # Cerrado na Amazônia Legal (35% exigido)
    res_mt = calcular_metricas_florestais(
        numero_car='MT-5107602-C75A20B7631E44AA8BF0D382A13894E2',
        status=StatusCAR.ATIVO,
        bioma=Bioma.AMAZONIA_CERRADO,
        area_total_ha=1000.0,
        area_reserva_legal_ha=300.0,  # abaixo de 35%
        area_app_ha=30.0,
    )
    assert res_mt.percentual_rl_exigido == 0.35
    assert res_mt.percentual_rl_declarado == 0.30
    assert res_mt.deficit_ou_excedente_rl_ha == -50.0
    assert res_mt.em_conformidade_florestal is False

    # Cerrado tradicional / demais biomas (20% exigido)
    res_go = calcular_metricas_florestais(
        numero_car='GO-5218805-B1C2D3E4F5A6B1C2D3E4F5A6B1C2D3E4',
        status=StatusCAR.ATIVO,
        bioma=Bioma.CERRADO,
        area_total_ha=500.0,
        area_reserva_legal_ha=110.0,  # 22%
        area_app_ha=20.0,
    )
    assert res_go.percentual_rl_exigido == 0.20
    assert res_go.percentual_rl_declarado == 0.22
    assert res_go.em_conformidade_florestal is True


def test_dossie_aprovado_conformidade_total():
    payload = {
        'numero_car': 'MT-5107602-C75A20B7631E44AA8BF0D382A13894E2',
        'status_car': 'ATIVO',
        'bioma': 'AMAZONIA_CERRADO',
        'area_total_ha': 1000.0,
        'area_reserva_legal_ha': 380.0,
        'area_app_ha': 40.0,
        'embargo_ibama': False,
        'embargo_icmbio': False,
        'trabalho_escravo_mte': False,
        'sobreposicao_terra_indigena': False,
        'sobreposicao_unidade_conservacao': False,
    }
    dossie = analisar_compliance_socioambiental(payload)

    assert dossie.parecer == ParecerESG.APROVADO
    assert dossie.score_esg == 100
    assert dossie.elegivel_credito_rural is True
    assert 'CMN 5.081' in dossie.selo_conformidade_cmn
    assert len(dossie.motivos_impedimento) == 0


def test_dossie_bloqueado_por_embargo_ibama():
    payload = {
        'numero_car': 'MT-5107602-C75A20B7631E44AA8BF0D382A13894E2',
        'status_car': 'ATIVO',
        'bioma': 'AMAZONIA_CERRADO',
        'area_total_ha': 1000.0,
        'area_reserva_legal_ha': 380.0,
        'embargo_ibama': True,  # Embargo ativo
    }
    dossie = analisar_compliance_socioambiental(payload)

    assert dossie.parecer == ParecerESG.IMPEDIDO_BACEN
    assert dossie.elegivel_credito_rural is False
    assert any('IBAMA' in m for m in dossie.motivos_impedimento)
    assert 'IMPEDIDO' in dossie.selo_conformidade_cmn


def test_dossie_bloqueado_por_trabalho_escravo():
    payload = {
        'numero_car': 'GO-5218805-B1C2D3E4F5A6B1C2D3E4F5A6B1C2D3E4',
        'status_car': 'ATIVO',
        'bioma': 'CERRADO',
        'area_total_ha': 500.0,
        'area_reserva_legal_ha': 150.0,
        'trabalho_escravo_mte': True,
    }
    dossie = analisar_compliance_socioambiental(payload)

    assert dossie.parecer == ParecerESG.IMPEDIDO_BACEN
    assert dossie.elegivel_credito_rural is False
    assert any('Trabalho Escravo' in m or 'MTE' in m for m in dossie.motivos_impedimento)


def test_dossie_bloqueado_por_car_suspenso_ou_cancelado():
    payload = {
        'numero_car': 'MS-5002704-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA',
        'status_car': 'CANCELADO',
        'bioma': 'CERRADO',
        'area_total_ha': 800.0,
        'area_reserva_legal_ha': 200.0,
    }
    dossie = analisar_compliance_socioambiental(payload)

    assert dossie.parecer == ParecerESG.IMPEDIDO_BACEN
    assert dossie.elegivel_credito_rural is False
    assert any('CANCELADO' in m for m in dossie.motivos_impedimento)


def test_dossie_com_alerta_reserva_legal_ou_pendente():
    payload = {
        'numero_car': 'MT-5107602-C75A20B7631E44AA8BF0D382A13894E2',
        'status_car': 'PENDENTE',
        'bioma': 'AMAZONIA_CERRADO',
        'area_total_ha': 1000.0,
        'area_reserva_legal_ha': 250.0,  # Déficit (precisa de 350)
        'embargo_ibama': False,
        'trabalho_escravo_mte': False,
    }
    dossie = analisar_compliance_socioambiental(payload)

    assert dossie.parecer == ParecerESG.ALERTA
    assert dossie.elegivel_credito_rural is True  # Não bloqueia preventivamente, exige PRA
    assert len(dossie.alertas_monitoramento) >= 2
    assert dossie.score_esg < 100


def test_rotas_api_compliance_socioambiental():
    import database as db
    db.init_db()
    email = 'esgtest@example.com'
    usuario = db.buscar_usuario_email(email)
    if not usuario:
        db.criar_usuario(email, 'Usuario ESG', 'senha123')
        usuario = db.buscar_usuario_email(email)
    from app import app
    app.config['TESTING'] = True
    cliente = app.test_client()
    with cliente.session_transaction() as sessao:
        sessao['_user_id'] = str(usuario['id'])

    # 1. Rota analisar
    payload = {
        'numero_car': 'MT-5107602-C75A20B7631E44AA8BF0D382A13894E2',
        'status_car': 'ATIVO',
        'bioma': 'AMAZONIA_CERRADO',
        'area_total_ha': 1000.0,
        'area_reserva_legal_ha': 360.0,
    }
    resp = cliente.post('/api/compliance/socioambiental/analisar', json=payload)
    assert resp.status_code == 200
    dados = resp.get_json()
    assert dados['parecer'] == 'APROVADO'
    assert dados['elegivel_credito_rural'] is True

    # 2. Rota validar CAR
    resp_car = cliente.post('/api/compliance/car/validar', json=payload)
    assert resp_car.status_code == 200
    dados_car = resp_car.get_json()
    assert dados_car['sintaxe_valida'] is True
    assert dados_car['percentual_rl_exigido'] == 0.35


def test_gerar_pdf_com_secao_esg():
    from services.annual_engine import analisar_culturas_anuais
    from services.parecer_pdf_graos import gerar_pdf_parecer_graos

    analise = analisar_culturas_anuais({
        'ano_agricola': '2026/27',
        'culturas': [{'cultura': 'SOJA', 'safra_tipo': '1_SAFRA', 'area_ha': 800, 'produtividade_ha': 60, 'preco_unitario': 144, 'coe_ha': 4100}],
        'credito': {'valor': 800_000, 'prazo_meses': 36, 'juros_aa': 0.115},
    })
    dossie = analisar_compliance_socioambiental({
        'numero_car': 'MT-5107602-C75A20B7631E44AA8BF0D382A13894E2',
        'status_car': 'ATIVO',
        'bioma': 'AMAZONIA_CERRADO',
        'area_total_ha': 1000.0,
        'area_reserva_legal_ha': 380.0,
        'area_app_ha': 50.0,
    })
    identificacao = {'fazenda': 'Fazenda Verde', 'municipio': 'Sorriso / MT', 'proprietario': 'Agro Produtor'}
    pdf_bytes = gerar_pdf_parecer_graos(analise, identificacao=identificacao, esg=dossie.to_dict())

    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes.startswith(b'%PDF')
    assert len(pdf_bytes) > 2500

