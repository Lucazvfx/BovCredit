"""
Acervo de documentos — o ativo que o sistema jogava fora.

`/api/ler-pdf` fazia o parse e apagava o arquivo. Cada ficha real que passou
por este projeto achou uma classe de defeito que os testes sintéticos não
achavam (ver o cabeçalho de services/documentos.py), e o documento que a
revelou vivia trinta segundos em disco.

O que estes testes prendem:

  1. a comparação parser × analista classifica certo — é ela que separa
     "afinou" de "o parser errou", e só a segunda vira fixture
  2. o acervo deduplica reenvio, mas NÃO entre empresas
  3. guardar documento nunca derruba a leitura
  4. o acervo está declarado no inventário da LGPD — é documento de cliente
     com CPF dentro, e entrar sem declarar é o que a ANPD procura
"""
import pytest

import database as db
from services.documentos import (
    comparar, impressao, vale_revisao,
    CONFERE, AJUSTE, DIVERGENCIA, PARSER_VAZIO, SEM_PARSE,
)


# ── A comparação: onde o parser tropeçou ────────────────────────────────────
def test_analista_aceitou_o_parse():
    c = comparar([10] * 10, [10] * 10)
    assert c['situacao'] == CONFERE
    assert c['faixas_alteradas'] == []
    assert not vale_revisao(c)


def test_ajuste_pequeno_nao_e_erro_de_leitura():
    """Mexer uma cabeça em 1.000 é afinação, não falha do parser."""
    lido = [100] * 10
    usado = [100] * 9 + [101]
    c = comparar(lido, usado)
    assert c['situacao'] == AJUSTE
    assert not vale_revisao(c)


def test_divergencia_grande_vira_fila_de_revisao():
    c = comparar([100] * 10, [100] * 9 + [500])
    assert c['situacao'] == DIVERGENCIA
    assert c['faixas_alteradas'] == ['fac_M']
    assert vale_revisao(c)


def test_parser_vazio_e_o_caso_mais_valioso():
    """
    O ADAPEC-TO devolvia rebanho zerado num PDF que o OCR leu bem. É o
    defeito que menos aparece e mais engana: nada falha, o número é zero.
    """
    c = comparar([0] * 10, [219, 22, 234, 105, 16, 45, 0, 59, 0, 0])
    assert c['situacao'] == PARSER_VAZIO
    assert c['total_usado'] == 700
    assert vale_revisao(c)


def test_sem_documento_nao_inventa_divergencia():
    assert comparar(None, None)['situacao'] == SEM_PARSE
    assert comparar([0] * 10, [0] * 10)['situacao'] == SEM_PARSE


def test_troca_entre_faixas_e_detectada_mesmo_com_total_igual():
    """
    O erro que o OCR comete: engole um zero e desloca a coluna. O total
    continua batendo e a composição fica errada — 59 matrizes viram 59 bois.
    Medir divergência pela diferença dos TOTAIS não pegaria isso.
    """
    lido  = [0, 0, 0, 0, 0, 0, 0, 59, 0, 0]
    usado = [0, 0, 0, 0, 0, 0, 0, 0, 59, 0]
    c = comparar(lido, usado)
    assert c['total_lido'] == c['total_usado'] == 59
    assert c['situacao'] == DIVERGENCIA, 'troca de faixa com total igual passou batido'
    assert set(c['faixas_alteradas']) == {'f25_M', 'fac_F'}


# ── A impressão digital ─────────────────────────────────────────────────────
def test_mesmo_arquivo_mesma_impressao():
    assert impressao(b'%PDF-1.4 x') == impressao(b'%PDF-1.4 x')
    assert impressao(b'%PDF-1.4 x') != impressao(b'%PDF-1.4 y')


# ── A persistência ──────────────────────────────────────────────────────────
@pytest.fixture
def acervo():
    db.init_db()
    db._ensure_documentos_table()
    return db


def test_reenvio_da_mesma_ficha_nao_duplica(acervo):
    """O produtor reenvia a mesma ficha várias vezes numa análise."""
    kw = dict(empresa_id=901, user_id=1, nome_arquivo='ficha.pdf',
              conteudo=b'%PDF dedup', sha256=impressao(b'%PDF dedup'),
              origem='INDEA', parse={}, valores_lidos=[1] * 10)
    a = acervo.registrar_documento(**kw)
    b = acervo.registrar_documento(**kw)
    assert a == b


def test_empresas_diferentes_nao_compartilham_documento(acervo):
    """
    Deduplicar entre consultorias economizaria bytes e quebraria o
    isolamento: uma poderia apagar o documento da outra, e o id passaria a
    apontar para ficha de cliente alheio.
    """
    conteudo = b'%PDF isolamento'
    kw = dict(user_id=1, nome_arquivo='f.pdf', conteudo=conteudo,
              sha256=impressao(conteudo), origem='INDEA', parse={},
              valores_lidos=[2] * 10)
    a = acervo.registrar_documento(empresa_id=911, **kw)
    b = acervo.registrar_documento(empresa_id=912, **kw)
    assert a != b


def test_conteudo_so_sai_para_a_empresa_dona(acervo):
    conteudo = b'%PDF sigilo'
    did = acervo.registrar_documento(
        empresa_id=921, user_id=1, nome_arquivo='s.pdf', conteudo=conteudo,
        sha256=impressao(conteudo), origem='INDEA', parse={},
        valores_lidos=[0] * 10)
    assert acervo.documento_conteudo(did, 921)[1] == conteudo
    assert acervo.documento_conteudo(did, 922) is None, (
        'documento de uma consultoria saiu para outra'
    )


def test_correcao_fecha_o_par_e_entra_na_fila(acervo):
    conteudo = b'%PDF par'
    did = acervo.registrar_documento(
        empresa_id=931, user_id=1, nome_arquivo='p.pdf', conteudo=conteudo,
        sha256=impressao(conteudo), origem='ADAPEC_TO', parse={},
        valores_lidos=[0] * 10)
    usados = [219, 22, 234, 105, 16, 45, 0, 59, 0, 0]
    acervo.registrar_correcao(did, usados, comparar([0] * 10, usados))
    assert did in [d['id'] for d in acervo.documentos_para_revisao()]


def test_parse_volta_restrito_a_empresa(acervo):
    conteudo = b'%PDF parse'
    did = acervo.registrar_documento(
        empresa_id=941, user_id=1, nome_arquivo='x.pdf', conteudo=conteudo,
        sha256=impressao(conteudo), origem='INDEA', parse={},
        valores_lidos=[7] * 10)
    assert acervo.documento_parse(did, 941) == [7] * 10
    assert acervo.documento_parse(did, 942) is None


# ── LGPD ────────────────────────────────────────────────────────────────────
def test_acervo_esta_declarado_no_inventario():
    """
    O acervo guarda a ficha do órgão estadual — nome, CPF e propriedade do
    produtor. É o registro mais sensível do sistema. Guardar dado pessoal
    novo sem declarar no Art. 37 é exatamente o achado que trava auditoria.
    """
    from services.lgpd import INVENTARIO
    assert 'documentos' in INVENTARIO
    entrada = INVENTARIO['documentos']
    assert 'produtor' in entrada['titular']
    assert entrada['retencao'], 'retenção precisa estar declarada'


def test_inventario_declara_a_finalidade_secundaria():
    """
    Guardar para melhorar o parser é interesse legítimo do controlador, não
    do titular. Finalidade secundária que não aparece escrita é o que a ANPD
    procura — declarar as duas é o que torna o uso defensável.
    """
    from services.lgpd import INVENTARIO
    finalidade = INVENTARIO['documentos']['finalidade'].lower()
    assert 'parecer' in finalidade or 'rebanho' in finalidade
    assert 'leitor' in finalidade or 'leitura' in finalidade


# ── Ponta a ponta pelas rotas ───────────────────────────────────────────────
# Documento SINTÉTICO de propósito. A ficha real que motivou este acervo traz
# nome, CPF e telefone de um produtor identificável; versioná-la no git seria
# irreversível — e no mesmo commit que declara o acervo no inventário da LGPD.
# O acervo existe justamente para esse dado ficar no banco da consultoria, com
# retenção declarada, e não no repositório.

def _login():
    db.init_db()
    email = 'acervo@example.com'
    u = db.buscar_usuario_email(email)
    if not u:
        db.criar_usuario(email, 'Acervo', 'senha123')
        u = db.buscar_usuario_email(email)
    from app import app
    app.config['TESTING'] = True
    c = app.test_client()
    with c.session_transaction() as s:
        s['_user_id'] = str(u['id'])
    return c, u


def _pdf_sintetico(texto):
    """PDF nativo mínimo, com camada de texto — não precisa de OCR."""
    import io
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    y = 800
    for linha in texto.splitlines():
        c.drawString(40, y, linha)
        y -= 14
    c.save()
    buf.seek(0)
    return buf


def test_leitura_guarda_o_documento_e_devolve_o_id():
    cli, _ = _login()
    pdf = _pdf_sintetico('SALDO ATUAL DA EXPLORACAO\nFAZENDA TESTE SINTETICA\n')
    r = cli.post('/api/ler-pdf', data={'pdf': (pdf, 'ficha.pdf')},
                 content_type='multipart/form-data')
    assert r.status_code == 200, r.get_data(as_text=True)[:200]
    assert r.get_json().get('documento_id'), (
        'a leitura não guardou o documento — o acervo não está recebendo nada'
    )


def test_falha_do_acervo_nao_derruba_a_leitura(monkeypatch):
    """
    Mesma regra da trilha de auditoria: o analista precisa do parse mesmo que
    o acervo esteja fora do ar. Um sistema que falha assim acaba com o acervo
    desligado na primeira sexta-feira ruim.
    """
    cli, _ = _login()

    def _explode(**kw):
        raise RuntimeError('banco indisponível')

    monkeypatch.setattr(db, 'registrar_documento', _explode)
    pdf = _pdf_sintetico('SALDO ATUAL DA EXPLORACAO\nFAZENDA X\n')
    r = cli.post('/api/ler-pdf', data={'pdf': (pdf, 'f.pdf')},
                 content_type='multipart/form-data')
    assert r.status_code == 200, 'a leitura caiu junto com o acervo'
    assert r.get_json().get('documento_id') is None
