"""Identidade institucional (white-label leve) no PDF do parecer."""
import uuid
import zlib
import re

import pytest

import app as app_module
import database as db
from services import identidade_institucional as ident
from services.parecer_pdf import gerar_pdf_parecer
from tests.test_parecer_pdf import PARECER_COMPLETO

CNPJ = '11.222.333/0001-81'  # dígitos verificadores válidos


def _usuario(nome='Ident'):
    db.init_db()
    email = f'{nome}-{uuid.uuid4().hex[:8]}@example.com'
    uid = db.criar_usuario(email, nome, 'senha123')
    return uid, db.empresas_do_usuario(uid)[0]['id'], email


def _cliente(uid):
    c = app_module.app.test_client()
    with c.session_transaction() as s:
        s['_user_id'] = str(uid)
    return c


def _analista(empresa_id):
    uid, _, _ = _usuario('Analista')
    db._exec(f'UPDATE empresa_membros SET empresa_id={db._PH}, papel={db._PH} '
             f'WHERE user_id={db._PH}', (empresa_id, 'analista', uid), commit=True)
    return uid


def _texto_pdf(pdf: bytes) -> str:
    """Texto dos streams do PDF (reportlab comprime em Flate+ASCII85 por padrão)."""
    import base64
    out = []
    for m in re.finditer(rb'stream\r?\n(.*?)endstream', pdf, re.S):
        bruto = m.group(1).strip()
        try:
            bruto = base64.a85decode(bruto, adobe=True) if bruto.endswith(b'~>') else bruto
            out.append(zlib.decompress(bruto).decode('latin-1'))
        except Exception:
            continue
    return '\n'.join(out)


DADOS = {'nome_exibicao': 'Agro Alfa Ltda', 'cnpj': CNPJ,
         'responsavel_nome': 'Maria Souza', 'responsavel_registro': 'CRMV-MT 1234'}


# ── validação / sanitização ─────────────────────────────────────────────────

def test_validar_normaliza_cnpj_para_digitos():
    d, msg = ident.validar_identidade(DADOS)
    assert msg is None and d['cnpj'] == '11222333000181'
    assert ident.formatar_cnpj(d['cnpj']) == CNPJ


@pytest.mark.parametrize('payload', [
    {'cnpj': '11.222.333/0001-82'},          # DV errado
    {'cnpj': '11111111111111'},              # repetido
    {'cnpj': '123.456.789-09'},              # CPF não é aceito
    {'cnpj': 123},                           # tipo errado
    {'nome_exibicao': 'x' * 121},
    {'nome_exibicao': '<b>Agro</b>'},
    {'responsavel_nome': ['a']},
    {'responsavel_registro': 'CRMV;DROP'},
    'texto',
])
def test_validar_rejeita_entradas_invalidas(payload):
    d, msg = ident.validar_identidade(payload)
    assert d is None and msg


def test_validar_remove_controle_e_normaliza_espacos():
    d, _ = ident.validar_identidade({'nome_exibicao': 'Agro\x00 \n  Alfa‮'})
    assert d['nome_exibicao'] == 'Agro Alfa'


def test_vazio_limpa_campos():
    d, msg = ident.validar_identidade({})
    assert msg is None and d == ident.identidade_vazia()


# ── persistência e isolamento ───────────────────────────────────────────────

def test_persistencia_e_isolamento_entre_empresas():
    uid_a, eid_a, _ = _usuario('A')
    uid_b, eid_b, _ = _usuario('B')
    a, b = _cliente(uid_a), _cliente(uid_b)
    r = a.put('/api/empresa/identidade', json=DADOS)
    assert r.status_code == 200
    got = a.get('/api/empresa/identidade').get_json()
    assert got['identidade']['cnpj_formatado'] == CNPJ and got['pode_editar'] is True
    outra = b.get('/api/empresa/identidade').get_json()['identidade']
    assert outra['cnpj'] == '' and outra['nome_exibicao'] == ''
    assert db.obter_identidade_empresa(eid_b)['cnpj'] == ''
    # segunda gravação atualiza (upsert), não duplica
    a.put('/api/empresa/identidade', json={**DADOS, 'responsavel_nome': 'João'})
    n = db._exec(f'SELECT COUNT(*) AS n FROM empresa_identidade WHERE empresa_id={db._PH}',
                 (eid_a,), fetch='one')['n']
    assert n == 1


def test_empresa_ativa_do_corpo_e_ignorada():
    uid_a, _, _ = _usuario('A2')
    _, eid_b, _ = _usuario('B2')
    a = _cliente(uid_a)
    a.put('/api/empresa/identidade', json={**DADOS, 'empresa_id': eid_b})
    assert db.obter_identidade_empresa(eid_b)['cnpj'] == ''


# ── permissões ──────────────────────────────────────────────────────────────

def test_analista_le_mas_nao_altera():
    uid, eid, _ = _usuario('Adm')
    _cliente(uid).put('/api/empresa/identidade', json=DADOS)
    c = _cliente(_analista(eid))
    got = c.get('/api/empresa/identidade').get_json()
    assert got['pode_editar'] is False and got['identidade']['cnpj'] == '11222333000181'
    r = c.put('/api/empresa/identidade', json={'nome_exibicao': 'Invasor'})
    assert r.status_code == 403
    assert db.obter_identidade_empresa(eid)['nome_exibicao'] == 'Agro Alfa Ltda'


def test_sem_login_e_recusado():
    c = app_module.app.test_client()
    assert c.get('/api/empresa/identidade').status_code in (302, 401)
    assert c.put('/api/empresa/identidade', json=DADOS).status_code in (302, 401)


def test_put_invalido_devolve_400_e_nao_grava():
    uid, eid, _ = _usuario('Inv')
    r = _cliente(uid).put('/api/empresa/identidade', json={'cnpj': '1234'})
    assert r.status_code == 400
    assert db.obter_identidade_empresa(eid)['cnpj'] == ''


def test_resposta_nao_vaza_email():
    uid, _, email = _usuario('Vaza')
    c = _cliente(uid)
    c.put('/api/empresa/identidade', json=DADOS)
    assert email not in c.get('/api/empresa/identidade').get_data(as_text=True)


# ── renderização no PDF ─────────────────────────────────────────────────────

def test_pdf_com_identidade_mostra_campos():
    d, _ = ident.validar_identidade(DADOS)
    pdf = gerar_pdf_parecer(PARECER_COMPLETO, branding={'nome_consultoria': 'Antigo', **d})
    assert pdf.startswith(b'%PDF')
    txt = _texto_pdf(pdf)
    assert 'Agro Alfa Ltda' in txt and CNPJ in txt
    assert 'Maria Souza' in txt and 'CRMV-MT 1234' in txt
    assert 'Antigo' not in txt


def test_pdf_sem_identidade_tem_fallback_limpo():
    txt = _texto_pdf(gerar_pdf_parecer(PARECER_COMPLETO, branding={'nome_consultoria': 'Consultoria X'}))
    assert 'Consultoria X' in txt and 'CNPJ' not in txt and 'Responsável técnico' not in txt
    txt2 = _texto_pdf(gerar_pdf_parecer(PARECER_COMPLETO, branding=None))
    assert 'Responsável técnico' not in txt2 and 'None' not in txt2


def test_pdf_escapa_markup_malicioso_vindo_do_banco():
    pdf = gerar_pdf_parecer(PARECER_COMPLETO, branding={
        'nome_exibicao': 'A & B <font size=500>X</font>',
        'responsavel_nome': '<b>Mal</b> & Cia', 'cnpj': 'abc', 'responsavel_registro': ''})
    assert pdf.startswith(b'%PDF')
    txt = _texto_pdf(gerar_pdf_parecer(PARECER_COMPLETO, branding={
        'nome_exibicao': 'A & B <font size=500>X</font>'}))
    assert '<font size=500>X</font>' in txt or 'font size=500' in txt
    assert 'A & B' in txt


def test_cnpj_alfanumerico_e_aceito_e_formatado():
    base = '12ABC34501DE'
    pesos1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    d1 = 11 - sum((ord(c) - 48) * p for c, p in zip(base, pesos1)) % 11
    d1 = 0 if d1 >= 10 else d1
    pesos2 = [6] + pesos1
    d2 = 11 - sum((ord(c) - 48) * p for c, p in zip(base + str(d1), pesos2)) % 11
    d2 = 0 if d2 >= 10 else d2
    cnpj = f'{base}{d1}{d2}'
    d, msg = ident.validar_identidade({'cnpj': cnpj.lower()})
    assert msg is None and d['cnpj'] == cnpj
    assert ident.formatar_cnpj(cnpj) == f'12.ABC.345/01DE-{d1}{d2}'
    d, msg = ident.validar_identidade({'cnpj': cnpj[:-1] + str((d2 + 1) % 10)})
    assert d is None


def test_quebra_de_linha_vira_espaco():
    d, _ = ident.validar_identidade({'nome_exibicao': 'Agro\nAlfa\tLtda'})
    assert d['nome_exibicao'] == 'Agro Alfa Ltda'


def test_texto_gigante_e_recusado_sem_varredura():
    d, msg = ident.validar_identidade({'nome_exibicao': 'x' * 100_000})
    assert d is None and msg


def test_endpoint_pdf_usa_identidade_da_empresa_ativa():
    uid_a, _, _ = _usuario('PA')
    uid_b, _, _ = _usuario('PB')
    a, b = _cliente(uid_a), _cliente(uid_b)
    a.put('/api/empresa/identidade', json=DADOS)
    ra = a.post('/api/parecer/pdf', json={'parecer': PARECER_COMPLETO})
    rb = b.post('/api/parecer/pdf', json={'parecer': PARECER_COMPLETO})
    assert ra.status_code == rb.status_code == 200
    assert CNPJ in _texto_pdf(ra.data)
    assert CNPJ not in _texto_pdf(rb.data) and 'Agro Alfa' not in _texto_pdf(rb.data)


# ── UI: painel sem overflow horizontal (1440x900 e 390x844) ─────────────────

def test_ui_painel_identidade_em_navegador_sem_overflow(tmp_path):
    import pathlib
    import shutil
    import subprocess
    root = pathlib.Path(__file__).resolve().parent.parent
    node = shutil.which('node')
    if not node or subprocess.run([node, '-e', "require('playwright')"],
                                  capture_output=True).returncode != 0:
        pytest.skip('Node/Playwright indisponível')
    site = tmp_path / 'site'
    site.mkdir()
    uid, _, _ = _usuario('UiIdent')
    r = _cliente(uid).get('/app')
    assert r.status_code == 200
    (site / 'index.html').write_bytes(r.data)
    shutil.copytree(root / 'static', site / 'static')
    out = subprocess.run([node, str(root / 'tests' / 'browser' / 'identidade_layout.js'),
                          str(site)], capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stdout + out.stderr
    assert len([ln for ln in out.stdout.splitlines() if ' OK ' in ln]) == 4, out.stdout
