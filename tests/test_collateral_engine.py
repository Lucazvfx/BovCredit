"""Testes unitários e de integração para o motor de Matriz de Garantias e LTV B2B."""
import pytest

from services.collateral_engine import (
    ClassificacaoGarantia,
    TipoGarantia,
    TipoGravame,
    avaliar_matriz_garantias,
    calcular_item_garantia,
    consolidar_matriz_garantias,
)


def test_calculo_item_garantia_alienacao_e_dividas():
    # Fazenda de R$ 5.000.000 com dívida prévia de R$ 1.000.000 em Alienação Fiduciária (deságio 20%)
    item = calcular_item_garantia(
        tipo=TipoGarantia.IMOVEL_RURAL,
        gravame=TipoGravame.ALIENACAO_FIDUCIARIA,
        descricao='Fazenda Santa Maria - Matrícula 1234',
        identificador_registro='Matrícula 1234 - CRI Sorriso/MT',
        valor_mercado_bruto=5_000_000.0,
        dividas_previas_averbadas=1_000_000.0,
        area_ha=1000.0,
    )
    # Base líquida disponível: 5M - 1M = 4M
    # Deságio de 20% -> 4M * 0.80 = 3.2M
    assert item.valor_mercado_bruto == 5_000_000.0
    assert item.dividas_previas_averbadas == 1_000_000.0
    assert item.desagio_aplicado_pct == 20.0
    assert item.valor_liquidacao_forcada == 3_200_000.0


def test_calculo_item_garantia_penhor_safra_e_aval():
    # Penhor de Safra de R$ 1.000.000 (deságio 25%)
    safra = calcular_item_garantia(
        tipo=TipoGarantia.PENHOR_SAFRA,
        gravame=TipoGravame.PENHOR_PRIMEIRO_GRAU,
        descricao='Penhor de Soja',
        identificador_registro='CPR-2026-01',
        valor_mercado_bruto=1_000_000.0,
    )
    assert safra.valor_liquidacao_forcada == 750_000.0

    # Aval pessoal de R$ 800.000 (deságio 50%)
    aval = calcular_item_garantia(
        tipo=TipoGarantia.AVAL_PESSOAL,
        gravame=TipoGravame.AVAL_SOLIDARIO,
        descricao='Avalista João',
        identificador_registro='CPF 000.000.000-00',
        valor_mercado_bruto=800_000.0,
    )
    assert aval.valor_liquidacao_forcada == 400_000.0


def test_consolidacao_faixas_ltv():
    item1 = calcular_item_garantia(
        tipo=TipoGarantia.IMOVEL_RURAL,
        gravame=TipoGravame.ALIENACAO_FIDUCIARIA,
        descricao='Fazenda',
        identificador_registro='Matrícula 1',
        valor_mercado_bruto=2_500_000.0,  # 2.5M * 0.80 = 2.0M de liquidação
    )

    # 1. Excelente: Crédito de R$ 1.000.000 / 2.000.000 -> LTV 50%
    matriz_exc = consolidar_matriz_garantias([item1], credito_solicitado=1_000_000.0)
    assert matriz_exc.ltv_pct == 50.0
    assert matriz_exc.indice_cobertura_pct == 200.0
    assert matriz_exc.classificacao_risco == ClassificacaoGarantia.EXCELENTE
    assert matriz_exc.suficiente_para_aprovacao is True

    # 2. Adequada: Crédito de R$ 1.400.000 / 2.000.000 -> LTV 70%
    matriz_adeq = consolidar_matriz_garantias([item1], credito_solicitado=1_400_000.0)
    assert matriz_adeq.ltv_pct == 70.0
    assert matriz_adeq.classificacao_risco == ClassificacaoGarantia.ADEQUADA
    assert matriz_adeq.suficiente_para_aprovacao is True

    # 3. Ajustada: Crédito de R$ 1.700.000 / 2.000.000 -> LTV 85%
    matriz_ajust = consolidar_matriz_garantias([item1], credito_solicitado=1_700_000.0)
    assert matriz_ajust.ltv_pct == 85.0
    assert matriz_ajust.classificacao_risco == ClassificacaoGarantia.AJUSTADA
    assert matriz_ajust.suficiente_para_aprovacao is False

    # 4. Insuficiente: Crédito de R$ 2.200.000 / 2.000.000 -> LTV 110%
    matriz_insuf = consolidar_matriz_garantias([item1], credito_solicitado=2_200_000.0)
    assert matriz_insuf.ltv_pct == 110.0
    assert matriz_insuf.classificacao_risco == ClassificacaoGarantia.INSUFICIENTE
    assert matriz_insuf.suficiente_para_aprovacao is False


def test_pipeline_avaliar_matriz_shorthand():
    payload = {
        'credito_solicitado': 1_500_000.0,
        'imovel_rural': {
            'denominacao': 'Fazenda Primavera',
            'matricula': '45.890',
            'cartorio': 'CRI Rondonópolis/MT',
            'area_ha': 500.0,
            'valor_ha': 40_000.0,  # 20.000.000
            'gravame': 'ALIENACAO_FIDUCIARIA',
            'dividas_previas': 0.0,
        },
        'penhor_safra': {
            'cultura': 'Soja',
            'sacas': 10_000.0,
            'preco_saca': 144.0,  # 1.440.000
        },
        'avalista': {
            'nome': 'Carlos Silva',
            'cpf_cnpj': '111.222.333-44',
            'patrimonio_liquido': 2_000_000.0,
        }
    }
    res = avaliar_matriz_garantias(payload)

    assert len(res.itens) == 3
    assert res.valor_mercado_total == 20_000_000.0 + 1_440_000.0 + 2_000_000.0
    assert res.valor_liquidacao_total > 15_000_000.0
    assert res.ltv_pct < 15.0
    assert res.classificacao_risco == ClassificacaoGarantia.EXCELENTE
    assert res.suficiente_para_aprovacao is True


def test_rota_api_garantias_matriz_avaliar():
    import database as db
    db.init_db()
    email = 'garantiatest@example.com'
    usuario = db.buscar_usuario_email(email)
    if not usuario:
        db.criar_usuario(email, 'Usuario Garantia', 'senha123')
        usuario = db.buscar_usuario_email(email)
    from app import app
    app.config['TESTING'] = True
    cliente = app.test_client()
    with cliente.session_transaction() as sessao:
        sessao['_user_id'] = str(usuario['id'])

    payload = {
        'credito_solicitado': 1_000_000.0,
        'imovel_rural': {
            'area_ha': 200.0,
            'valor_ha': 30_000.0,
            'matricula': '1010',
            'cartorio': 'CRI Lucas do Rio Verde',
        }
    }
    resp = cliente.post('/api/garantias/matriz/avaliar', json=payload)
    assert resp.status_code == 200
    d = resp.get_json()
    assert d['credito_solicitado'] == 1_000_000.0
    assert d['valor_mercado_total'] == 6_000_000.0
    assert d['valor_liquidacao_total'] == 4_800_000.0
    assert d['classificacao_risco'] == 'EXCELENTE'
    assert d['suficiente_para_aprovacao'] is True


def test_pdf_graos_com_matriz_garantias():
    from services.annual_engine import analisar_culturas_anuais
    from services.parecer_pdf_graos import gerar_pdf_parecer_graos

    analise = analisar_culturas_anuais({
        'ano_agricola': '2026/27',
        'culturas': [{'cultura': 'SOJA', 'safra_tipo': '1_SAFRA', 'area_ha': 500, 'produtividade_ha': 60, 'preco_unitario': 144, 'coe_ha': 4000}],
        'credito': {'valor': 1_000_000, 'prazo_meses': 36, 'juros_aa': 0.115},
    })
    garantias = avaliar_matriz_garantias({
        'credito_solicitado': 1_000_000.0,
        'imovel_rural': {'area_ha': 200.0, 'valor_ha': 25_000.0, 'matricula': '123', 'cartorio': 'CRI'},
        'penhor_safra': {'sacas': 5000, 'preco_saca': 144.0},
    })
    identificacao = {'fazenda': 'Fazenda Modelo', 'municipio': 'Rondonópolis', 'proprietario': 'Produtor'}
    pdf_bytes = gerar_pdf_parecer_graos(analise, identificacao=identificacao, garantias=garantias.to_dict())

    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes.startswith(b'%PDF')
    assert len(pdf_bytes) > 2500

