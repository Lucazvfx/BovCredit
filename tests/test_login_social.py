"""Entrar com Google: quem entra, quem não entra, e o que não muda.

O risco desta funcionalidade não é técnico, é de autorização. Hoje o cadastro
público é 403 de propósito — só admin cria conta. Login social ingênuo desfaz
isso em silêncio: qualquer pessoa com conta Google entraria numa ferramenta de
análise de crédito.

A regra vive em services/login_social.py, pura, para ser testável sem rede e
sem provedor no ar. O Google prova quem é; quem decide se entra é o sistema.
"""
import database as db
import pytest

from services import login_social as ls

DOMINIOS = ('orkavyn.tech', 'consultoria.com.br')


def _decidir(**kw):
    base = dict(email='fulano@orkavyn.tech', email_verificado=True,
                hosted_domain=None, dominios_permitidos=DOMINIOS,
                ja_vinculado=False, ja_cadastrado=False)
    base.update(kw)
    return ls.decidir(**base)


# ── Quem não entra ───────────────────────────────────────────────────────────

def test_conta_de_fora_do_dominio_nao_entra():
    """O caso que a funcionalidade poderia abrir sem querer."""
    d = _decidir(email='estranho@gmail.com')
    assert not d.permitido
    assert d.motivo == ls.FORA_DO_DOMINIO


def test_sem_lista_de_dominios_ninguem_e_criado():
    """Variável de ambiente vazia tem de fechar, não abrir."""
    d = _decidir(dominios_permitidos=())
    assert not d.permitido
    assert d.motivo == ls.FORA_DO_DOMINIO


def test_email_nao_verificado_nao_entra():
    """Sem essa checagem, afirmar um e-mail bastaria para entrar pelo domínio."""
    d = _decidir(email_verificado=False)
    assert not d.permitido
    assert d.motivo == ls.NAO_VERIFICADO


def test_conta_sem_email_nao_entra():
    assert _decidir(email='').motivo == ls.SEM_EMAIL
    assert _decidir(email='sem-arroba').motivo == ls.SEM_EMAIL


def test_hosted_domain_de_outra_empresa_vence_o_sufixo_do_email():
    """`hd` é a afirmação forte do Workspace: se ele diz outra empresa, é ela.

    Protege contra um e-mail que *parece* do domínio numa conta que pertence
    a outro tenant.
    """
    d = _decidir(email='fulano@orkavyn.tech', hosted_domain='outra.com')
    assert not d.permitido
    assert d.motivo == ls.FORA_DO_DOMINIO


# ── Quem entra ───────────────────────────────────────────────────────────────

def test_quem_ja_vinculou_entra():
    assert _decidir(ja_vinculado=True).acao == ls.ENTRAR


def test_vinculo_sobrevive_a_saida_do_dominio_da_lista():
    """Tirar alguém de dentro é ato de administração.

    Se o domínio sair do .env, quem já usava não pode ser expulso por efeito
    colateral — o admin remove a conta quando quiser remover o acesso.
    """
    d = _decidir(ja_vinculado=True, dominios_permitidos=(), email='x@gmail.com')
    assert d.acao == ls.ENTRAR


def test_email_ja_cadastrado_pelo_admin_entra_mesmo_fora_do_dominio():
    """É o caminho de quem já usava senha e passou a usar o botão."""
    d = _decidir(email='convidado@gmail.com', ja_cadastrado=True)
    assert d.acao == ls.VINCULAR


def test_dominio_liberado_cria_a_conta():
    assert _decidir().acao == ls.CRIAR
    assert _decidir(email='outro@consultoria.com.br').acao == ls.CRIAR


def test_workspace_do_dominio_certo_cria():
    d = _decidir(email='fulano@orkavyn.tech', hosted_domain='orkavyn.tech')
    assert d.acao == ls.CRIAR


# ── Leitura da variável de ambiente ──────────────────────────────────────────

@pytest.mark.parametrize('bruto,esperado', [
    ('a.com', ('a.com',)),
    ('a.com, b.com', ('a.com', 'b.com')),
    ('@a.com,@b.com', ('a.com', 'b.com')),
    ('  A.COM  ', ('a.com',)),
    ('', ()),
    (None, ()),
])
def test_normalizacao_de_dominios(bruto, esperado):
    assert ls.normalizar_dominios(bruto) == esperado


def test_todo_motivo_de_recusa_tem_mensagem_para_a_tela():
    """"Acesso negado" não diz o que fazer; cada recusa tem instrução."""
    for motivo in (ls.SEM_EMAIL, ls.NAO_VERIFICADO, ls.FORA_DO_DOMINIO):
        assert motivo in ls.MENSAGENS
        assert len(ls.MENSAGENS[motivo]) > 20


# ── Banco: o vínculo não mexe na identidade ──────────────────────────────────

def test_vincular_nao_troca_o_id_do_usuario():
    """O `id` é chave estrangeira em dez tabelas. Ele não pode mudar.

    É esta propriedade que permite trocar de provedor amanhã sem migrar o
    histórico de pareceres.
    """
    db.init_db()
    email = 'social-vinculo@example.com'
    if not db.buscar_usuario_email(email):
        db.criar_usuario(email, 'Social', 'senha123')
    antes = db.buscar_usuario_email(email)

    db.vincular_provedor(antes['id'], 'google', '1234567890')
    depois = db.buscar_usuario_email(email)

    assert depois['id'] == antes['id']
    assert db.buscar_usuario_por_provedor('google', '1234567890')['id'] == antes['id']


def test_conta_criada_por_provedor_nao_tem_senha_utilizavel():
    """Senha vazia passaria por hash de string vazia e viraria porta."""
    db.init_db()
    email = 'social-novo@example.com'
    if not db.buscar_usuario_email(email):
        db.criar_usuario_do_provedor(
            email=email, nome='Novo', provedor='google',
            provedor_id='sub-novo-1', empresa_id=None)
    assert db.verificar_senha(email, '') is None
    assert db.verificar_senha(email, 'senha123') is None
    assert db.buscar_usuario_por_provedor('google', 'sub-novo-1') is not None


def test_dominio_ambiguo_nao_escolhe_empresa_sozinho():
    """Com duas empresas no mesmo domínio, quem decide é o admin.

    Adivinhar aqui colocaria um analista na carteira da firma errada.
    """
    db.init_db()
    dominio = 'ambiguo-teste.com.br'
    for i in (1, 2):
        e = f'socio{i}@{dominio}'
        if not db.buscar_usuario_email(e):
            db.criar_usuario(e, f'Socio {i}', 'senha123')  # cria 1 empresa cada
    assert db.empresa_unica_do_dominio(dominio) is None


def test_dominio_com_uma_empresa_so_agrupa_os_novos():
    """Sem isso, cada analista virava uma consultoria de uma pessoa."""
    db.init_db()
    dominio = 'unico-teste.com.br'
    email = f'primeiro@{dominio}'
    if not db.buscar_usuario_email(email):
        db.criar_usuario(email, 'Primeiro', 'senha123')
    eid = db.empresa_unica_do_dominio(dominio)
    assert eid is not None

    # SQLite do teste persiste entre execuções: só cria se ainda não existe.
    novo = db.buscar_usuario_email(f'segundo@{dominio}')
    uid = novo['id'] if novo else db.criar_usuario_do_provedor(
        email=f'segundo@{dominio}', nome='Segundo', provedor='google',
        provedor_id='sub-unico-1', empresa_id=eid)
    assert [e['id'] for e in db.empresas_do_usuario(uid)] == [eid]
