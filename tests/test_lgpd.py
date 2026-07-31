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
