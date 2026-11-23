"""
LGPD como código: inventário, anonimização, portabilidade e retenção.

A TENSÃO QUE ESTES TESTES GUARDAM

A trilha de auditoria é append-only por decisão explícita — uma trilha que se
edita não é trilha. Mas o Art. 18 dá ao titular direito à eliminação, e a
trilha guarda e-mail e IP.

Os dois não se atendem apagando linhas. A resolução é anonimizar: o evento
permanece (quem auditou continua sabendo que às 14h32 alguém consultou o
parecer 412), a pessoa deixa de ser identificável.

O pseudônimo é ESTÁVEL de propósito. Trocar por NULL destruiria a capacidade de
reconstruir uma sessão — "o mesmo usuário fez 40 consultas em 3 minutos" é
exatamente o que uma investigação de vazamento precisa ver.

O QUE ESTE MÓDULO NÃO COBRE

Base legal de cada tratamento, encarregado (DPO), política de privacidade e
contrato de operador. São decisão da empresa, não do sistema.
"""
import pytest

import database as db
from app import app
from services import lgpd


@pytest.fixture
def titular():
    """Um usuário novo a cada teste — anonimização é irreversível."""
    import uuid
    db.init_db()
    email = f'lgpd_{uuid.uuid4().hex[:10]}@example.com'
    db.criar_usuario(email, 'Titular de Teste', 'senha123')
    u = db.buscar_usuario_email(email)
    db.registrar_acesso('parecer_gerado', user_id=u['id'], user_email=email,
                        recurso='fazenda', recurso_id=7, ip='203.0.113.7')
    return u


# ── Pseudônimo ──────────────────────────────────────────────────────────────
def test_pseudonimo_e_estavel():
    """
    O mesmo e-mail sempre gera o mesmo pseudônimo — sem isso a trilha
    anonimizada viraria ruído e a investigação de incidente morreria junto.
    """
    assert lgpd.pseudonimo('a@b.com') == lgpd.pseudonimo('a@b.com')


def test_pseudonimos_diferentes_para_titulares_diferentes():
    assert lgpd.pseudonimo('a@b.com') != lgpd.pseudonimo('c@d.com')


def test_pseudonimo_nao_contem_o_original():
    p = lgpd.pseudonimo('joao.silva@fazenda.com.br')
    assert 'joao' not in p and 'fazenda' not in p


def test_pseudonimo_de_vazio_nao_quebra():
    assert lgpd.e_anonimo(lgpd.pseudonimo(''))


# ── Anonimização ────────────────────────────────────────────────────────────
def test_anonimizar_remove_a_identificacao_da_conta(titular):
    db.anonimizar_usuario(titular['id'])
    u = db.buscar_usuario_id(titular['id'])
    assert titular['email'] not in u['email']
    assert u['nome'] != 'Titular de Teste'
    assert lgpd.e_anonimo(u['nome'])


def test_a_conta_fica_inutilizavel(titular):
    """
    Anonimizar sem invalidar a senha deixaria uma conta acessível sem dono
    identificado — pior que não anonimizar.
    """
    db.anonimizar_usuario(titular['id'])
    assert db.verificar_senha(titular['email'], 'senha123') is None


def test_o_evento_da_trilha_sobrevive_a_anonimizacao(titular):
    """
    O ponto do desenho: append-only e direito de eliminação convivendo. O
    registro fica, a pessoa sai.
    """
    antes = len(db.listar_acessos(user_id=titular['id'], limit=100))
    db.anonimizar_usuario(titular['id'])
    depois = db.listar_acessos(user_id=titular['id'], limit=100)
    assert len(depois) >= antes, 'a trilha perdeu eventos'
    assert any(e['evento'] == 'parecer_gerado' for e in depois)


def test_a_trilha_perde_email_e_ip(titular):
    db.anonimizar_usuario(titular['id'])
    for e in db.listar_acessos(user_id=titular['id'], limit=100):
        assert e['user_email'] != titular['email']
        assert lgpd.e_anonimo(e['user_email'])
        assert e['ip'] is None, 'IP é dado pessoal e precisa sair'


def test_o_vinculo_de_whatsapp_e_removido(titular):
    tel = '5511900001111'
    db.consumir_codigo_whatsapp(db.criar_codigo_whatsapp(titular['id']), tel)
    assert db.buscar_user_por_telefone([tel]) == titular['id']
    db.anonimizar_usuario(titular['id'])
    assert db.buscar_user_por_telefone([tel]) is None


def test_pareceres_nao_sao_apagados(titular):
    """
    O parecer é dado do CLIENTE da consultoria, com valor probatório e prazo
    próprio de guarda. Anonimizar o analista não pode destruí-lo.
    """
    db.salvar_parecer(titular['id'], None, {'tipo': 'CRIA'},
                      {'conclusao': {'recomendacao': 'aprovar'}})
    antes = db.ultimo_parecer_do_usuario(titular['id'])
    assert antes is not None
    db.anonimizar_usuario(titular['id'])
    assert db.ultimo_parecer_do_usuario(titular['id']) is not None


def test_anonimizar_e_idempotente(titular):
    """Rodar duas vezes não pode gerar pseudônimo de pseudônimo."""
    r1 = db.anonimizar_usuario(titular['id'])
    r2 = db.anonimizar_usuario(titular['id'])
    assert r1['ja_anonimo'] is False
    assert r2['ja_anonimo'] is True


def test_anonimizar_usuario_inexistente():
    r = db.anonimizar_usuario(99999999)
    assert r['ok'] is False


def test_a_propria_anonimizacao_fica_registrada(titular):
    """Quem exerceu o direito, e quando — a operação também é auditável."""
    db.anonimizar_usuario(titular['id'])
    assert db.listar_acessos(evento='lgpd_anonimizacao', limit=1)


# ── Portabilidade ───────────────────────────────────────────────────────────
def test_exportacao_traz_conta_empresas_fazendas_e_trilha(titular):
    d = db.exportar_dados_usuario(titular['id'])
    assert d['conta']['email'] == titular['email']
    assert 'empresas' in d and 'fazendas' in d
    assert d['auditoria'], 'a trilha é dado sobre o titular e precisa ir junto'


def test_exportacao_nao_vaza_hash_de_senha(titular):
    d = db.exportar_dados_usuario(titular['id'])
    assert 'senha_hash' not in d['conta']
    assert 'security_answer_hash' not in d['conta']


def test_exportacao_avisa_o_que_nao_esta_incluido(titular):
    """
    Portabilidade parcial sem aviso é pior que parcial com aviso — o titular
    precisa saber que o dado do cliente da consultoria não é dele.
    """
    assert 'clientes da consultoria' in db.exportar_dados_usuario(titular['id'])['aviso']


def test_exportacao_de_usuario_inexistente():
    assert db.exportar_dados_usuario(99999999) == {}


# ── Retenção ────────────────────────────────────────────────────────────────
def test_purga_remove_alem_do_prazo():
    from datetime import datetime, timedelta
    db.init_db()
    antigo = datetime.now() - timedelta(days=900)
    db._exec(f'''INSERT INTO auditoria_acessos
                 (user_id, user_email, evento, created_at)
                 VALUES ({db._PH},{db._PH},{db._PH},{db._PH})''',
             (7777, 'velho@x.com', 'login', antigo), commit=True)
    assert db.purgar_auditoria(dias=730) >= 1


def test_purga_preserva_o_que_esta_no_prazo():
    db.registrar_acesso('login', user_id=8888, user_email='recente@x.com')
    db.purgar_auditoria(dias=730)
    assert db.listar_acessos(user_id=8888, limit=1)


def test_purga_com_zero_dias_nao_apaga_tudo():
    """
    Guarda contra o pé na jaca: `dias=0` apagaria a trilha inteira. Um erro de
    digitação não pode destruir a auditoria.
    """
    db.registrar_acesso('login', user_id=9999, user_email='guarda@x.com')
    assert db.purgar_auditoria(dias=0) == 0
    assert db.listar_acessos(user_id=9999, limit=1)


def test_retencao_tem_padrao_e_e_configuravel():
    assert lgpd.RETENCAO_AUDITORIA_DIAS > 0
    assert 'RETENCAO_AUDITORIA_DIAS' in lgpd.INVENTARIO['auditoria_acessos']['retencao']


def test_retencao_padrao_e_180_dias_como_na_politica_de_privacidade():
    """Roda em subprocesso: o ambiente de teste pode definir a variável."""
    import os
    import subprocess
    import sys
    env = {k: v for k, v in os.environ.items() if k != 'RETENCAO_AUDITORIA_DIAS'}
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out = subprocess.run(
        [sys.executable, '-c',
         'from services import lgpd; print(lgpd.RETENCAO_AUDITORIA_DIAS)'],
        env=env, cwd=raiz, capture_output=True, text=True, check=True)
    assert out.stdout.strip().splitlines()[-1] == '180'
    assert 'default 180' in lgpd.INVENTARIO['auditoria_acessos']['retencao']


def test_purga_sem_argumento_usa_a_retencao_padrao(monkeypatch):
    from datetime import datetime, timedelta
    db.init_db()
    monkeypatch.setattr(lgpd, 'RETENCAO_AUDITORIA_DIAS', 180)
    email = 'purga180@x.com'
    for dias, uid in ((200, 6001), (100, 6002)):
        db._exec(f'''INSERT INTO auditoria_acessos
                     (user_id, user_email, evento, created_at)
                     VALUES ({db._PH},{db._PH},{db._PH},{db._PH})''',
                 (uid, email, 'login', datetime.now() - timedelta(days=dias)),
                 commit=True)
    db.purgar_auditoria()
    assert not db.listar_acessos(user_id=6001, limit=1), 'além de 180 dias sai'
    assert db.listar_acessos(user_id=6002, limit=1), 'dentro de 180 dias fica'


# ── remover_usuario ─────────────────────────────────────────────────────────
def _novo_usuario():
    import uuid
    email = f'rm_{uuid.uuid4().hex[:10]}@example.com'
    db.criar_usuario(email, 'Usuário de Teste', 'senha123')
    return db.buscar_usuario_email(email)


def test_remover_usuario_revoga_api_keys_sem_tocar_as_de_outros():
    alvo, outro = _novo_usuario(), _novo_usuario()
    ka = db.issue_analysis_api_key(organization_id=1, user_id=alvo['id'], name='alvo')
    ko = db.issue_analysis_api_key(organization_id=1, user_id=outro['id'], name='outro')
    ka_raw, ko_raw = ka['raw_key'], ko['raw_key']
    assert db.load_analysis_api_key(ka_raw)

    db.remover_usuario(alvo['id'])

    assert db.load_analysis_api_key(ka_raw) is None, 'key do removido segue válida'
    assert db.load_analysis_api_key(ka_raw, include_revoked=True)['revoked_at']
    assert db.load_analysis_api_key(ko_raw), 'key de outro usuário foi afetada'


def test_anonimizar_revoga_api_keys_sem_tocar_as_de_outros():
    alvo, outro = _novo_usuario(), _novo_usuario()
    ka = db.issue_analysis_api_key(organization_id=1, user_id=alvo['id'], name='alvo')
    ko = db.issue_analysis_api_key(organization_id=1, user_id=outro['id'], name='outro')
    ka_raw, ko_raw = ka['raw_key'], ko['raw_key']
    assert db.load_analysis_api_key(ka_raw)

    db.anonimizar_usuario(alvo['id'])

    assert db.load_analysis_api_key(ka_raw) is None, 'key do anonimizado segue válida'
    # revogada, não apagada: a trilha de emissão permanece
    assert db.load_analysis_api_key(ka_raw, include_revoked=True)['revoked_at']
    assert db.load_analysis_api_key(ko_raw), 'key de outro usuário foi afetada'


def test_anonimizar_sem_api_keys_nao_quebra():
    r = db.anonimizar_usuario(_novo_usuario()['id'])
    assert r['ok'] and not r['ja_anonimo']


def test_anonimizar_de_novo_revoga_key_de_conta_ja_anonimizada():
    alvo = _novo_usuario()
    db.anonimizar_usuario(alvo['id'])
    k = db.issue_analysis_api_key(organization_id=1, user_id=alvo['id'], name='legada')

    r = db.anonimizar_usuario(alvo['id'])

    assert r['ja_anonimo']
    assert db.load_analysis_api_key(k['raw_key']) is None


def test_remover_usuario_apaga_reset_tokens_e_invalida_o_link():
    alvo, outro = _novo_usuario(), _novo_usuario()
    t_alvo = db.criar_token_reset(alvo['email'])
    t_outro = db.criar_token_reset(outro['email'])
    assert db.validar_token_reset(t_alvo) == alvo['email'].lower()

    db.remover_usuario(alvo['id'])

    assert db.validar_token_reset(t_alvo) is None
    assert db.validar_token_reset(t_outro) == outro['email'].lower()


def test_remover_usuario_sem_credenciais_nao_quebra():
    alvo = _novo_usuario()
    db.remover_usuario(alvo['id'])
    assert db.buscar_usuario_email(alvo['email']) is None


def test_remover_usuario_inexistente_nao_quebra():
    db.remover_usuario(999999991)


def test_remover_usuario_limpa_vinculo_e_codigos_de_whatsapp_sem_tocar_outros():
    import uuid
    db.init_db()
    alvo, outro = _novo_usuario(), _novo_usuario()
    tel_alvo = '55119' + uuid.uuid4().hex[:8].translate(str.maketrans('abcdef', '123456'))
    tel_outro = '55118' + uuid.uuid4().hex[:8].translate(str.maketrans('abcdef', '123456'))
    db.consumir_codigo_whatsapp(db.criar_codigo_whatsapp(alvo['id']), tel_alvo)
    db.consumir_codigo_whatsapp(db.criar_codigo_whatsapp(outro['id']), tel_outro)
    cod_alvo = db.criar_codigo_whatsapp(alvo['id'])     # pendente, não usado
    cod_outro = db.criar_codigo_whatsapp(outro['id'])

    db.remover_usuario(alvo['id'])

    assert db.buscar_user_por_telefone([tel_alvo]) is None
    assert db.buscar_user_por_telefone([tel_outro]) == outro['id']
    assert db.consumir_codigo_whatsapp(cod_alvo, '5511977770000') is None
    assert db.consumir_codigo_whatsapp(cod_outro, '5511977771111') == outro['id']
    assert db.buscar_usuario_email(alvo['email']) is None


# ── Inventário (Art. 37) ────────────────────────────────────────────────────
def test_toda_tabela_com_dado_pessoal_declara_finalidade_e_retencao():
    for tabela, d in lgpd.INVENTARIO.items():
        assert d['campos'], f'{tabela} sem campos'
        assert d['titular'], f'{tabela} sem titular'
        assert d['finalidade'], f'{tabela} sem finalidade'
        assert d['retencao'], f'{tabela} sem prazo de retenção'


def test_o_inventario_separa_usuario_do_sistema_e_cliente():
    """
    Confundir os dois é o erro de fundo: anonimizar um analista não pode apagar
    o parecer de um produtor.
    """
    titulares = {d['titular'] for d in lgpd.INVENTARIO.values()}
    assert any('analista' in t for t in titulares)
    assert any('produtor' in t for t in titulares)


def test_as_tabelas_com_dado_pessoal_existem_no_banco():
    """Inventário que aponta para tabela inexistente é papel, não conformidade."""
    db.init_db()
    # Estas tabelas nascem sob demanda, não em init_db(); sem criá-las aqui o
    # resultado dependeria de outro teste já ter rodado no mesmo gestao.db.
    db._ensure_auditoria_table()
    db._ensure_whatsapp_tables()
    db._ensure_documentos_table()
    reais = {r['name'] for r in db._exec(
        "SELECT name FROM sqlite_master WHERE type='table'", fetch='all') or []}
    if reais:   # só roda no SQLite local
        for t in lgpd.tabelas_com_dado_pessoal():
            assert t in reais, f'{t} está no inventário mas não existe'


# ── Rotas ───────────────────────────────────────────────────────────────────
def test_rotas_lgpd_exigem_administrador():
    c = app.test_client()
    for metodo, rota in (('get', '/api/admin/lgpd/inventario'),
                         ('get', '/api/admin/lgpd/exportar/1'),
                         ('post', '/api/admin/lgpd/anonimizar/1'),
                         ('post', '/api/admin/lgpd/purgar-auditoria')):
        r = getattr(c, metodo)(rota)
        assert r.status_code in (302, 401, 403), f'{rota} aberta'
