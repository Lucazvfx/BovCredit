from pathlib import Path


TEMPLATE = Path(__file__).parents[1] / 'templates' / 'index.html'


def test_upload_pdf_fica_visivel_na_area_de_entrada():
    html = TEMPLATE.read_text(encoding='utf-8')
    entrada = html.split('<div class="panel active" id="panel-entrada">', 1)[1]
    entrada = entrada.split('<div class="panel" id="panel-pdf">', 1)[0]

    assert 'id="pdf-inp-main"' in entrada
    assert 'onchange="lerPDFs(this.files);this.value=\'\'"' in entrada
    assert 'Ler PDF' in entrada
