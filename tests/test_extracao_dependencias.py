"""
A cascata de extração de PDF depende de binários que o pip não instala.

`extrair_texto_pdf` tem três estágios: `pdftotext` (poppler), pdfplumber e OCR
(Tesseract). Dois deles são binários de sistema — chamados por subprocess ou
via ctypes — e não aparecem no requirements.txt. Ou seja: a imagem podia subir,
os testes podiam passar e a suíte podia ficar verde com dois dos três estágios
simplesmente ausentes em produção. Foi o que aconteceu; o sistema não lia PDF
escaneado e nada acusava.

Estes testes leem o Dockerfile como texto. Não provam que a imagem funciona —
só que ninguém removeu a instalação sem também remover o uso. É o que dá para
verificar sem um daemon de Docker, e cobre exatamente a regressão observada.

O contrário também vale: se um estágio for retirado do código, o teste
correspondente falha e obriga a limpar o Dockerfile junto.
"""
import os
import re
import shutil

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _ler(nome):
    with open(os.path.join(RAIZ, nome), encoding='utf-8') as f:
        return f.read()


@pytest.fixture(scope='module')
def dockerfile():
    return _ler('Dockerfile')


@pytest.fixture(scope='module')
def requirements():
    return _ler('requirements.txt')


@pytest.fixture(scope='module')
def parsers():
    return _ler('pdf_parsers.py')


def _apt(texto):
    """Pacotes do apt-get install, ignorando flags e continuações de linha."""
    bloco = re.search(r'apt-get install(.*?)(?:&&|\n\n)', texto, re.S)
    assert bloco, 'Dockerfile não instala nada com apt-get'
    return set(re.findall(r'[a-z0-9][a-z0-9.+-]*', bloco.group(1).replace('\\', ' ')))


# ── Estágio 1: pdftotext ────────────────────────────────────────────────────
def test_codigo_chama_pdftotext(parsers):
    assert "'pdftotext'" in parsers


def test_imagem_instala_poppler(dockerfile):
    """
    `pdftotext` vem do poppler-utils. Sem ele o subprocess levanta
    FileNotFoundError e a cascata cai no pdfplumber — que perde o layout em
    coluna das fichas de IDARON e INDEA, exatamente o que os parsers usam para
    separar as faixas etárias.
    """
    assert 'poppler-utils' in _apt(dockerfile)


# ── Estágio 3: OCR ──────────────────────────────────────────────────────────
def test_codigo_chama_pytesseract(parsers):
    assert 'import pytesseract' in parsers


def test_requirements_traz_o_wrapper(requirements):
    """
    pytesseract é só a ponte. Precisa estar pinado como todo o resto — ver o
    cabeçalho do requirements.txt sobre por que faixas `>=` não servem aqui.
    """
    linha = [l for l in requirements.splitlines() if l.strip().startswith('pytesseract')]
    assert linha, 'pytesseract ausente do requirements.txt'
    assert '==' in linha[0], f'pytesseract sem versão fixa: {linha[0]!r}'


def test_imagem_instala_tesseract(dockerfile):
    """O wrapper sem o binário falha em tempo de execução, não de import."""
    assert 'tesseract-ocr' in _apt(dockerfile)


def test_imagem_traz_o_modelo_de_portugues(dockerfile):
    """
    O código pede `lang='por+eng'`. Sem o pacote -por essa chamada levanta e o
    fallback usa só inglês, que erra acentuação e os rótulos das categorias —
    'Fêmeas', 'Bezerros', 'até 12 meses'. O OCR "funciona" e devolve lixo.
    """
    assert "lang='por+eng'" in _ler('pdf_parsers.py')
    assert 'tesseract-ocr-por' in _apt(dockerfile)


# ── Estágio 1 (continuação): o que já estava lá ─────────────────────────────
def test_libgomp_continua_instalado(dockerfile):
    """Regressão do boot: LightGBM/XGBoost carregam libgomp por ctypes."""
    assert 'libgomp1' in _apt(dockerfile)


# ── Ponta a ponta, quando os binários existem ───────────────────────────────
# Pulam onde o ambiente não os tem (a imagem de produção tem — é o que os
# testes acima garantem). Onde rodam, provam a cascata inteira sobre um PDF
# escaneado de verdade: sem camada de texto, só pixels.
falta_binario = pytest.mark.skipif(
    not (shutil.which('pdftotext') and shutil.which('tesseract')),
    reason='requer poppler-utils e tesseract-ocr instalados')


@pytest.fixture(scope='module')
def pdf_escaneado(tmp_path_factory):
    """
    Rasteriza a ficha real do INDEA e a regrava como PDF de imagem pura —
    o que chega de cartório e de fazenda que fotografa o papel.
    """
    import io

    import pdfplumber
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas

    pasta = tmp_path_factory.mktemp('ocr')
    origem = str(pasta / 'origem_sintetica.pdf')
    destino = str(pasta / 'escaneado.pdf')

    fonte = canvas.Canvas(origem, pagesize=A4)
    for y, linha in enumerate((
        'INDEA MT - SALDO ATUAL DA EXPLORACAO',
        'PROPRIEDADE: 00000000000 - FAZENDA SINTETICA',
        'MUNICIPIO: MUNICIPIO TESTE - MT',
        'BOVINO 5 A 12 MESES MACHO 120',
        'BOVINO 13 A 24 MESES MACHO 483',
    )):
        fonte.drawString(55, 780 - y * 35, linha)
    fonte.save()

    c = canvas.Canvas(destino, pagesize=A4)
    with pdfplumber.open(origem) as pdf:
        for page in pdf.pages:
            buf = io.BytesIO()
            page.to_image(resolution=200).original.save(buf, format='PNG')
            buf.seek(0)
            c.drawImage(ImageReader(buf), 0, 0, width=A4[0], height=A4[1])
            c.showPage()
    c.save()
    return destino


@falta_binario
def test_o_fixture_nao_tem_camada_de_texto(pdf_escaneado):
    """Se este teste falhar, os dois seguintes não estariam provando o OCR."""
    import subprocess

    import pdfplumber

    r = subprocess.run(['pdftotext', '-layout', pdf_escaneado, '-'],
                       capture_output=True, text=True, timeout=30)
    assert not r.stdout.strip(), 'pdftotext achou texto — o PDF não é escaneado'
    with pdfplumber.open(pdf_escaneado) as pdf:
        achado = ''.join((p.extract_text() or '') for p in pdf.pages)
    assert not achado.strip(), 'pdfplumber achou texto — o PDF não é escaneado'


@falta_binario
def test_ocr_le_pdf_escaneado(pdf_escaneado):
    from pdf_parsers import detectar_origem, extrair_texto_pdf

    texto = extrair_texto_pdf(pdf_escaneado)
    assert texto.strip(), 'cascata devolveu vazio num PDF que só o OCR lê'
    assert detectar_origem(texto) == 'INDEA'


@falta_binario
def test_ocr_recupera_o_rebanho_e_nao_so_o_cabecalho(pdf_escaneado):
    """
    O número que importa. Com o `--psm` no padrão o Tesseract descarta a
    coluna QUANTIDADE: o cabeçalho sai certo e o rebanho sai zerado — um
    parecer construído sobre rebanho zero, sem nenhum erro visível. Confere
    contra o total do documento sintético: 603 = 120 + 483.
    """
    from pdf_parsers import extrair_texto_pdf, parsear_indea

    dados = parsear_indea(extrair_texto_pdf(pdf_escaneado))
    assert dados['animais']['f05_M'] == 120
    assert dados['animais']['f13_M'] == 483
    assert sum(dados['animais'].values()) == 603
