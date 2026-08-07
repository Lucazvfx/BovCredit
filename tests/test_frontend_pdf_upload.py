from pathlib import Path
import io

from services.fichas_rebanho.base_reader import registros_do_parse


TEMPLATE = Path(__file__).parents[1] / 'templates' / 'index.html'


def test_upload_pdf_fica_visivel_na_area_de_entrada():
    html = TEMPLATE.read_text(encoding='utf-8')
    entrada = html.split('<div class="panel active" id="panel-entrada">', 1)[1]
    entrada = entrada.split('<div class="panel" id="panel-pdf">', 1)[0]

    assert 'id="pdf-inp-main"' in entrada
    assert 'onchange="lerPDFs(this.files);this.value=\'\'"' in entrada
    assert 'Ler PDF' in entrada


def test_preview_pdf_e_botao_classificacao_ficam_disponiveis_na_entrada():
    html = TEMPLATE.read_text(encoding='utf-8')

    assert 'id="pdf-status-main"' in html
    assert 'Classificar com Machine Learning' in html
    assert 'document.getElementById(\'pdf-status-main\')' in html


def test_frontend_exibe_fluxo_de_analise_e_estados_acessiveis():
    html = TEMPLATE.read_text(encoding='utf-8')

    assert 'class="analysis-flow"' in html
    assert 'aria-controls="panel-entrada"' in html
    assert 'aria-selected="true"' in html
    assert '--surface-2:var(--c2)' in html
    assert 'button:focus-visible' in html
    assert 'prefers-reduced-motion:reduce' in html


def test_endpoint_importacao_entrega_valores_prontos_para_classificar(monkeypatch):
    import database as db
    import app as app_module
    from app import app

    db.init_db()
    email = 'pdf-flow-test@example.com'
    usuario = db.buscar_usuario_email(email)
    if not usuario:
        db.criar_usuario(email, 'PDF Flow', 'senha123')
        usuario = db.buscar_usuario_email(email)
    client = app.test_client()
    with client.session_transaction() as sess:
        sess['_user_id'] = str(usuario['id'])

    animais = {
        'f00_F': 10, 'f05_F': 5, 'f13_F': 10, 'f25_F': 5, 'fac_F': 20,
        'f00_M': 8, 'f05_M': 4, 'f13_M': 8, 'f25_M': 4, 'fac_M': 12,
    }
    dados = {'fazenda': 'Fazenda Teste', 'municipio': 'Palmas', 'animais': animais}
    registros = registros_do_parse(dados, 'TO_DECLARACAO', modelo='TO_DECLARACAO')
    monkeypatch.setattr(
        app_module,
        'read_ficha_pdf',
        lambda *args, **kwargs: {'sucesso': True, 'registros': registros,
                                 'avisos': [], 'erros': [], 'dados_brutos': dados,
                                 'origem': 'ADAPEC_TO', 'modelo': 'TO_DECLARACAO'},
    )

    resposta = client.post(
        '/api/fichas/importar',
        data={'pdf': (io.BytesIO(b'%PDF-falso'), 'teste.pdf')},
        content_type='multipart/form-data',
    )

    assert resposta.status_code == 200
    corpo = resposta.get_json()
    assert corpo['total'] == 86
    assert len(corpo['valores']) == 10
    assert corpo['fazendas']
    assert corpo['fazendas'][0]['origem'] == 'ADAPEC_TO'
    assert corpo['fazendas'][0]['modelo'] == 'TO_DECLARACAO'

    classificacao = client.post('/api/classificar', json={'valores': corpo['valores']})
    assert classificacao.status_code == 200
    assert classificacao.get_json().get('tipo')
