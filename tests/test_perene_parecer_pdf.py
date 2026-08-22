"""PDF do parecer de lavoura perene.

O PDF pecuário tem 26 referências a rebanho, arroba, cabeça e matriz. Emitir
ele com números de café produziria um documento falando de desfrute num
cafezal — pior que não ter PDF. Este documento é outro: fala de talhão, idade
e estágio, e traz duas seções que só existem aqui.

A primeira é a curva de produtividade com a fonte de cada cultura: a projeção
inteira depende dela, e quem lê o parecer precisa saber se ela tem lastro
citável ou é declaração do analista.

A segunda é o ano crítico explicado — não basta o número, o documento diz por
que o aperto não cai no ano 1.
"""
import pdfplumber
import pytest

import database as db
from services.parecer_pdf_perene import gerar_pdf_parecer_perene
from services.perennial_engine import analisar_lavoura_perene

CREDITO = {
    'credito_valor': 1_500_000, 'prazo_meses': 72, 'juros_aa': 0.105,
    'carencia_meses': 24, 'sistema_amortizacao': 'sac', 'periodicidade_meses': 12,
}
IDENT = {'fazenda': 'Sítio Boa Esperança', 'municipio': 'Patrocínio / MG',
         'proprietario': 'Produtor Exemplo'}


def _analise(fonte='Embrapa Café — exemplo', **extra):
    payload = {
        'ano_base': 2026, 'anos': 6,
        'talhoes': [
            {'cultura': 'CAFE', 'area_ha': 40, 'ano_plantio': 2021,
             'identificacao': 'Talhão A', 'fase_bienal': 'alta'},
            {'cultura': 'CAFE', 'area_ha': 20, 'ano_plantio': 2025,
             'identificacao': 'Talhão B', 'fase_bienal': 'baixa'},
        ],
        'curvas': {'CAFE': {
            'produtividade_plena': 30, 'unidade': 'saca_60kg',
            'fatores': {'1': 0, '2': 0, '3': 0.4, '4': 0.8, '5': 1.0},
            'bienalidade': 0.15, 'fonte': fonte}},
        'precos': {'CAFE': 1400},
        'custos': {'CAFE': {'formacao': 14000, 'producao': 9000, 'por_unidade': 120}},
        'credito': CREDITO,
    }
    payload.update(extra)
    return analisar_lavoura_perene(payload)


def _texto(pdf_bytes) -> str:
    import io
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        return '\n'.join(pagina.extract_text() or '' for pagina in pdf.pages)


def _login():
    db.init_db()
    email = 'pdfperene@example.com'
    usuario = db.buscar_usuario_email(email)
    if not usuario:
        db.criar_usuario(email, 'PDF Perene', 'senha123')
        usuario = db.buscar_usuario_email(email)
    from app import app
    app.config['TESTING'] = True
    cliente = app.test_client()
    with cliente.session_transaction() as sessao:
        sessao['_user_id'] = str(usuario['id'])
    return cliente


# ── O documento é agrícola ──────────────────────────────────────────────────

def test_o_parecer_fala_de_talhao_e_nao_de_rebanho():
    texto = _texto(gerar_pdf_parecer_perene(_analise(), IDENT))

    assert 'Parecer de Crédito Agrícola' in texto
    assert 'Composição da lavoura' in texto
    assert 'Talhão A' in texto
    for palavra in ('rebanho', 'arroba', 'desfrute', 'matriz'):
        assert palavra not in texto.lower()


def test_a_composicao_traz_idade_e_estagio_de_cada_talhao():
    texto = _texto(gerar_pdf_parecer_perene(_analise(), IDENT))

    assert 'Produção' in texto and 'Formação' in texto
    assert '60,00 ha' in texto          # área total
    assert '40,00 ha' in texto          # em produção no ano 1
    assert '20,00 ha' in texto          # em formação


# ── A curva e a origem do dado ──────────────────────────────────────────────

def test_a_fonte_da_curva_aparece_no_parecer():
    texto = _texto(gerar_pdf_parecer_perene(_analise(), IDENT))

    assert 'Curva de produtividade e origem do dado' in texto
    assert 'Embrapa Café' in texto


def test_curva_sem_fonte_vira_ressalva_explicita():
    """Toda a projeção depende da curva. Sem lastro, o documento diz."""
    texto = _texto(gerar_pdf_parecer_perene(_analise(fonte=''), IDENT))

    assert 'Declarada pelo analista' in texto
    assert 'não tem fonte declarada' in texto


# ── O ano crítico ───────────────────────────────────────────────────────────

def test_o_documento_explica_por_que_o_ano_critico_nao_e_o_primeiro():
    analise = _analise()
    texto = _texto(gerar_pdf_parecer_perene(analise, IDENT))
    ano = analise['credito']['analysis']['pior_periodo']['ano']

    assert 'Capacidade de pagamento' in texto
    assert f'ano mais apertado do contrato é o {ano}' in texto
    assert 'carga alta e baixa' in texto


def test_os_cenarios_saem_com_dscr_calculado():
    """Sem o serviço da dívida ano a ano, todo cenário saía com DSCR vazio."""
    analise = _analise()
    texto = _texto(gerar_pdf_parecer_perene(analise, IDENT))

    assert 'Cenários de estresse' in texto
    assert 'Quebra safra' in texto
    for cenario in analise['stress']['scenarios']:
        assert cenario['dscr_minimo'] is not None


# ── Análise incompleta ──────────────────────────────────────────────────────

def test_analise_incompleta_sai_marcada_no_documento():
    analise = _analise()
    analise['valido'] = False
    texto = _texto(gerar_pdf_parecer_perene(analise, IDENT))

    assert 'Análise incompleta' in texto


def test_o_pdf_sai_mesmo_sem_identificacao():
    """Falta de cadastro não pode impedir o analista de ver o documento."""
    pdf = gerar_pdf_parecer_perene(_analise())

    assert pdf[:5] == b'%PDF-'


# ── A rota ──────────────────────────────────────────────────────────────────

def test_a_rota_devolve_o_pdf_a_partir_do_payload():
    payload = {
        'ano_base': 2026, 'anos': 6,
        'talhoes': [{'cultura': 'CAFE', 'area_ha': 40, 'ano_plantio': 2021,
                     'identificacao': 'A', 'fase_bienal': 'alta'}],
        'curvas': {'CAFE': {'produtividade_plena': 30, 'unidade': 'saca_60kg',
                            'fatores': {'1': 0, '2': 0, '3': 0.4, '4': 0.8, '5': 1.0},
                            'bienalidade': 0.15, 'fonte': 'F'}},
        'precos': {'CAFE': 1400},
        'custos': {'CAFE': {'formacao': 14000, 'producao': 9000}},
        'credito': CREDITO,
        'identificacao': IDENT,
    }

    resposta = _login().post('/api/perene/parecer/pdf', json=payload)

    assert resposta.status_code == 200
    assert resposta.mimetype == 'application/pdf'
    assert resposta.data[:5] == b'%PDF-'


def test_a_rota_recusa_pedido_vazio():
    resposta = _login().post('/api/perene/parecer/pdf', json={})

    assert resposta.status_code == 400
