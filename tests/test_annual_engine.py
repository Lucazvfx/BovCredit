"""Testes para o motor de culturas anuais e grãos (Soja / Milho Safrinha / Algodão).

Valida:
1. Modelos de dados e validações defensivas (área > 0, produtividade > 0, COT >= COE).
2. Fórmulas de Breakeven em produtividade (sc/ha) e preço (R$/sc), além de margens.
3. Consolidação econômica da safra (área física vs área plantada safra/safrinha).
4. Encadeamento com o motor de crédito (capacidade de pagamento, DSCR, SAC e Price).
5. Execução dos testes de estresse específicos de grãos (quebra de safra, queda de preço).
"""
import pytest

from services.annual_engine import (
    CulturaSafra,
    PlanoSafra,
    SAFRA_SAFRINHA,
    SAFRA_VERAO,
    analisar_culturas_anuais,
    calcular_economico_safra,
    detalhar_cultura,
)


def test_cultura_safra_calculos_basicos():
    """Valida cálculos individuais de uma cultura de soja."""
    soja = CulturaSafra(
        cultura='SOJA',
        safra_tipo=SAFRA_VERAO,
        area_ha=1000.0,
        produtividade_ha=60.0,  # 60 sc/ha
        preco_unitario=120.0,   # R$ 120/sc
        coe_ha=4200.0,          # R$ 4.200/ha
        cot_ha=4800.0,          # R$ 4.800/ha
        unidade='sc',
    )

    assert soja.producao_total == 60_000.0
    assert soja.receita_bruta == 7_200_000.0
    assert soja.coe_total == 4_200_000.0
    assert soja.cot_total == 4_800_000.0
    assert soja.margem_contribuicao_total == 3_000_000.0
    assert soja.resultado_operacional_total == 2_400_000.0

    # Breakeven COE: 4200 / 120 = 35 sc/ha
    assert soja.breakeven_produtividade == 35.0
    # Breakeven preço: 4200 / 60 = R$ 70/sc
    assert soja.breakeven_preco == 70.0
    # Margem de segurança: 60 - 35 = 25 sc/ha
    assert soja.margem_seguranca_sc_ha == 25.0


def test_cultura_safra_validacoes_defensivas():
    """Garante recusa de dados inválidos."""
    with pytest.raises(ValueError, match='cultura não pode ser vazia'):
        CulturaSafra('', SAFRA_VERAO, 100, 50, 100, 3000)

    with pytest.raises(ValueError, match='área inválida'):
        CulturaSafra('SOJA', SAFRA_VERAO, -10, 50, 100, 3000)

    with pytest.raises(ValueError, match='COT/ha .* não pode ser menor que o COE/ha'):
        CulturaSafra('SOJA', SAFRA_VERAO, 100, 50, 100, coe_ha=4000, cot_ha=3500)


def test_plano_safra_soja_mais_milho_safrinha():
    """Valida fazenda típica com sucessão Soja Verão + Milho Safrinha."""
    soja = CulturaSafra(
        cultura='SOJA',
        safra_tipo=SAFRA_VERAO,
        area_ha=1000.0,
        produtividade_ha=62.0,
        preco_unitario=125.0,
        coe_ha=4200.0,
        cot_ha=4600.0,
    )
    milho = CulturaSafra(
        cultura='MILHO',
        safra_tipo=SAFRA_SAFRINHA,
        area_ha=750.0,
        produtividade_ha=95.0,
        preco_unitario=52.0,
        coe_ha=3100.0,
        cot_ha=3400.0,
    )

    plano = PlanoSafra(
        culturas=(soja, milho),
        ano_agricola='2026/27',
        ano_base=2026,
        despesas_administrativas=150_000.0,
    )

    # Área física é a maior safra sobreposta (1000 ha), plantada é a soma (1750 ha)
    assert plano.area_fisica_estimada_ha == 1000.0
    assert plano.area_plantada_total_ha == 1750.0

    economico = calcular_economico_safra(plano)

    # Receita Soja: 1000 * 62 * 125 = 7.750.000
    # Receita Milho: 750 * 95 * 52 = 3.705.000
    # Total: 11.455.000
    assert economico['receita_total'] == 11_455_000.0

    # COE Soja: 1000 * 4200 = 4.200.000
    # COE Milho: 750 * 3100 = 2.325.000
    # Total COE: 6.525.000
    assert economico['coe_total'] == 6_525_000.0

    # COT Soja: 4.600.000, Milho: 2.550.000, Adm: 150.000 -> Total: 7.300.000
    assert economico['cot_total'] == 7_300_000.0

    # Resultado operacional: 11.455.000 - 7.300.000 = 4.155.000
    assert economico['resultado_operacional'] == 4_155_000.0


def test_pipeline_analisar_culturas_anuais_com_credito():
    """Testa análise completa ponta a ponta com capacidade de pagamento de financiamento."""
    payload = {
        'ano_agricola': '2026/27',
        'ano_base': 2026,
        'despesas_administrativas': 100000,
        'culturas': [
            {
                'cultura': 'SOJA',
                'safra_tipo': '1_SAFRA',
                'area_ha': 800,
                'produtividade_ha': 65,
                'preco_unitario': 130,
                'coe_ha': 4500,
                'cot_ha': 5000,
                'unidade': 'sc',
            },
            {
                'cultura': 'MILHO',
                'safra_tipo': '2_SAFRA',
                'area_ha': 600,
                'produtividade_ha': 90,
                'preco_unitario': 50,
                'coe_ha': 3000,
                'cot_ha': 3300,
                'unidade': 'sc',
            },
        ],
        'credito': {
            'valor': 2_000_000,
            'prazo_meses': 60,
            'carencia_meses': 12,
            'juros_aa': 0.115,
            'sistema': 'sac',
        },
    }

    resultado = analisar_culturas_anuais(payload)

    assert resultado['valido'] is True
    assert resultado['tipo'] == 'CULTURAS_ANUAIS_GRAOS'
    assert resultado['area_fisica_ha'] == 800.0
    assert resultado['area_plantada_total_ha'] == 1400.0

    # Verifica se os motores dependentes foram executados
    assert 'credito' in resultado
    assert 'analysis' in resultado['credito']
    assert resultado['credito']['analysis']['dscr_minimo'] is not None

    assert 'stress' in resultado
    assert len(resultado['stress']['scenarios']) >= 3

    assert 'dicas' in resultado
    assert isinstance(resultado['dicas'], list)
    assert any(d['titulo'] == 'Capacidade de pagamento confortável' for d in resultado['dicas'])


def test_dicas_graos_alerta_margem_estreita_e_prejuizo():
    """Valida disparo de alertas de breakeven estreito e déficit operacional."""
    payload_estreito = {
        'ano_agricola': '2026/27',
        'culturas': [
            {
                'cultura': 'SOJA',
                'safra_tipo': '1_SAFRA',
                'area_ha': 500,
                'produtividade_ha': 50,  # 50 sc/ha
                'preco_unitario': 100,   # R$ 100/sc
                'coe_ha': 4500,          # breakeven = 45 sc/ha (90% da safra)
                'cot_ha': 4800,
            }
        ],
    }
    res = analisar_culturas_anuais(payload_estreito)
    titulos = [d['titulo'] for d in res['dicas']]
    assert any('Margem de segurança estreita' in t for t in titulos)

    payload_deficit = {
        'ano_agricola': '2026/27',
        'culturas': [
            {
                'cultura': 'MILHO',
                'safra_tipo': '2_SAFRA',
                'area_ha': 300,
                'produtividade_ha': 60,
                'preco_unitario': 40,
                'coe_ha': 2800,          # breakeven = 70 sc/ha > 60 sc/ha
            }
        ],
    }
    res_def = analisar_culturas_anuais(payload_deficit)
    titulos_def = [d['titulo'] for d in res_def['dicas']]
    assert any('Operação deficitária' in t for t in titulos_def)


def test_cenarios_de_estresse_graos():
    """Valida que todos os cenários de estresse de grãos são simulados."""
    payload = {
        'culturas': [
            {
                'cultura': 'SOJA',
                'safra_tipo': '1_SAFRA',
                'area_ha': 1000,
                'produtividade_ha': 60,
                'preco_unitario': 120,
                'coe_ha': 4000,
            }
        ],
        'credito': {
            'valor': 3_000_000,
            'prazo_meses': 36,
            'juros_aa': 0.12,
        },
    }
    res = analisar_culturas_anuais(payload)
    nomes_cenarios = [s['nome'] for s in res['stress']['scenarios']]
    assert 'quebra_safra_20pct' in nomes_cenarios
    assert 'queda_preco_graos_15pct' in nomes_cenarios
    assert 'alta_custo_insumos_15pct' in nomes_cenarios


def test_rota_agricola_graos_analisar_sucesso_e_validacoes():
    """Valida a rota /api/agricola/graos/analisar via Flask test client."""
    import database as db
    db.init_db()
    email = 'graos@example.com'
    usuario = db.buscar_usuario_email(email)
    if not usuario:
        db.criar_usuario(email, 'Produtor Graos', 'senha123')
        usuario = db.buscar_usuario_email(email)
    from app import app
    app.config['TESTING'] = True
    cliente = app.test_client()
    with cliente.session_transaction() as sessao:
        sessao['_user_id'] = str(usuario['id'])

    # 1. Sucesso
    payload = {
        'ano_agricola': '2026/27',
        'culturas': [
            {
                'cultura': 'SOJA',
                'safra_tipo': '1_SAFRA',
                'area_ha': 1000,
                'produtividade_ha': 62,
                'preco_unitario': 125,
                'coe_ha': 4200,
                'cot_ha': 4600,
            }
        ],
        'credito': {
            'valor': 1_500_000,
            'prazo_meses': 48,
            'juros_aa': 0.115,
        }
    }
    resp = cliente.post('/api/agricola/graos/analisar', json=payload)
    assert resp.status_code == 200
    dados = resp.get_json()
    assert dados['valido'] is True
    assert dados['tipo'] == 'CULTURAS_ANUAIS_GRAOS'
    assert dados['economico']['receita_total'] == 7_750_000.0

    # 2. Recusa sem culturas
    resp_vazia = cliente.post('/api/agricola/graos/analisar', json={'culturas': []})
    assert resp_vazia.status_code == 400

    # 3. Recusa juros não fração (ex: 11.5)
    payload_juros = dict(payload, credito={'juros_aa': 11.5})
    resp_juros = cliente.post('/api/agricola/graos/analisar', json=payload_juros)
    assert resp_juros.status_code == 400
    assert 'fração' in resp_juros.get_json()['erro']


