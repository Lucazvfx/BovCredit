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


def test_barter_calculo_matematica_e_risco():
    """Valida cálculo de troca (barter) e termômetro de penhor de safra."""
    from services.annual_engine import calcular_barter, gerar_minuta_cpr

    # Caso Real: R$ 720.000 em insumos com Soja a R$ 144/sc em Rondonópolis
    payload = {
        'valor_insumos': 720_000.0,
        'praca': 'SOJA_RONDONOPOLIS_MT',
        'produtividade_esperada_ha': 60.0,
        'area_total_ha': 1000.0,
    }
    resultado = calcular_barter(payload)

    assert resultado['valido'] is True
    assert resultado['preco_saca_referencia'] == 144.0
    # 720.000 / 144 = 5.000 sacas
    assert resultado['sacas_a_entregar'] == 5000.0
    assert resultado['toneladas_a_entregar'] == 300.0
    # 5.000 / 60 = 83.33 ha
    assert resultado['area_travada_ha'] == 83.33
    # 5.000 / 60.000 = 8.3%
    assert resultado['comprometimento_safra_pct'] == 8.3
    assert resultado['classificacao_risco'] == 'BAIXO'

    # Caso de Alto Risco: Penhor excessivo
    payload_alto = {
        'valor_insumos': 4_320_000.0,  # 30.000 sacas em área de 40.000 sacas = 75%
        'preco_saca': 144.0,
        'produtividade_esperada_ha': 50.0,
        'area_total_ha': 800.0,
    }
    res_alto = calcular_barter(payload_alto)
    assert res_alto['comprometimento_safra_pct'] == 75.0
    assert res_alto['classificacao_risco'] == 'CRITICO'
    assert 'não recomendado' in res_alto['recomendacao_comite'].lower()


def test_minuta_cpr_conformidade_legal():
    """Valida presença dos requisitos obrigatórios da Lei nº 8.929/94 na minuta."""
    from services.annual_engine import gerar_minuta_cpr

    payload = {
        'barter': {
            'valor_insumos': 500_000,
            'praca': 'SOJA_RONDONOPOLIS_MT',
            'produtividade_esperada_ha': 62,
            'area_total_ha': 1000,
        },
        'emitente': {
            'nome': 'João da Silva Agro',
            'cpf_cnpj': '123.456.789-00',
            'fazenda': 'Fazenda Esperança',
            'municipio_uf': 'Sorriso / MT',
            'car': 'MT-5107909-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA',
        },
        'credor': {
            'nome': 'Agro Insumos e Distribuição S/A',
            'cnpj': '11.222.333/0001-44',
        },
    }

    cpr = gerar_minuta_cpr(payload)

    assert cpr['modalidade'] == 'CPR_FISICA'
    texto = cpr['texto_minuta']
    assert 'CÉDULA DE PRODUTO RURAL' in texto
    assert 'Lei nº 8.929/94' in texto
    assert 'João da Silva Agro' in texto
    assert 'Agro Insumos e Distribuição S/A' in texto
    assert 'PENHOR CEDULAR' in texto
    assert 'B3 ou CERC' in texto


def test_rotas_barter_e_cpr_endpoint():
    """Valida as rotas HTTP de barter e minuta de CPR."""
    import database as db
    db.init_db()
    email = 'barter@example.com'
    usuario = db.buscar_usuario_email(email)
    if not usuario:
        db.criar_usuario(email, 'Operador Barter', 'senha123')
        usuario = db.buscar_usuario_email(email)
    from app import app
    app.config['TESTING'] = True
    cliente = app.test_client()
    with cliente.session_transaction() as sessao:
        sessao['_user_id'] = str(usuario['id'])

    # Teste Barter Endpoint
    resp_b = cliente.post('/api/agricola/barter/calcular', json={
        'valor_insumos': 288_000,
        'praca': 'SOJA_RONDONOPOLIS_MT',
        'produtividade_esperada_ha': 60,
        'area_total_ha': 500,
    })
    assert resp_b.status_code == 200
    db_res = resp_b.get_json()
    assert db_res['sacas_a_entregar'] == 2000.0  # 288.000 / 144
    assert db_res['comprometimento_safra_pct'] == 6.7

    # Teste CPR Minuta Endpoint
    resp_c = cliente.post('/api/agricola/cpr/minuta', json={
        'barter': {
            'valor_insumos': 288_000,
            'praca': 'SOJA_RONDONOPOLIS_MT',
            'produtividade_esperada_ha': 60,
            'area_total_ha': 500,
        },
        'emitente': {'nome': 'Produtor Teste', 'cpf_cnpj': '123'},
        'credor': {'nome': 'Revenda Teste', 'cnpj': '456'},
    })
    assert resp_c.status_code == 200
    dc_res = resp_c.get_json()
    assert 'CÉDULA DE PRODUTO RURAL' in dc_res['texto_minuta']
    assert 'Produtor Teste' in dc_res['texto_minuta']


def test_gerar_pdf_parecer_graos():
    """Valida geração dos bytes válidos do PDF do parecer de grãos e CPR."""
    from services.annual_engine import analisar_culturas_anuais, calcular_barter, gerar_minuta_cpr
    from services.parecer_pdf_graos import gerar_pdf_parecer_graos

    payload = {
        'ano_agricola': '2026/27',
        'culturas': [
            {
                'cultura': 'SOJA',
                'safra_tipo': '1_SAFRA',
                'area_ha': 1000,
                'produtividade_ha': 62,
                'preco_unitario': 144,
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
    analise = analisar_culturas_anuais(payload)
    barter = calcular_barter({
        'valor_insumos': 500_000,
        'praca': 'SOJA_RONDONOPOLIS_MT',
        'produtividade_esperada_ha': 62,
        'area_total_ha': 1000,
    })
    cpr = gerar_minuta_cpr({
        'barter': barter,
        'emitente': {'nome': 'Fazenda Modelo', 'cpf_cnpj': '000'},
        'credor': {'nome': 'Revenda Insumos', 'cnpj': '111'},
    })

    identificacao = {'fazenda': 'Fazenda Modelo', 'municipio': 'Rondonópolis / MT', 'proprietario': 'João da Silva'}
    branding = {'nome_consultoria': 'Orkavyn Agro Intelligence'}

    pdf_bytes = gerar_pdf_parecer_graos(analise, identificacao=identificacao, barter=barter, cpr=cpr, branding=branding)

    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes.startswith(b'%PDF')
    assert len(pdf_bytes) > 2000


def test_rota_pdf_parecer_graos_endpoint():
    """Valida a rota /api/agricola/graos/parecer/pdf devolvendo o arquivo PDF."""
    import database as db
    db.init_db()
    email = 'pdfgraos@example.com'
    usuario = db.buscar_usuario_email(email)
    if not usuario:
        db.criar_usuario(email, 'Produtor PDF', 'senha123')
        usuario = db.buscar_usuario_email(email)
    from app import app
    app.config['TESTING'] = True
    cliente = app.test_client()
    with cliente.session_transaction() as sessao:
        sessao['_user_id'] = str(usuario['id'])

    payload = {
        'culturas': [
            {
                'cultura': 'SOJA',
                'safra_tipo': '1_SAFRA',
                'area_ha': 500,
                'produtividade_ha': 60,
                'preco_unitario': 144,
                'coe_ha': 4000,
            }
        ],
        'credito': {'valor': 500_000, 'prazo_meses': 24, 'juros_aa': 0.115},
        'identificacao': {'fazenda': 'Fazenda Modelo', 'proprietario': 'Carlos'},
    }
    resp = cliente.post('/api/agricola/graos/parecer/pdf', json=payload)
    assert resp.status_code == 200
    assert resp.mimetype == 'application/pdf'
    assert resp.data.startswith(b'%PDF')






