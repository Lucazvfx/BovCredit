"""Desfecho do parecer: o que aconteceu depois que a recomendação saiu.

O sistema emitia parecer e nunca perguntava. Sem isso o rating é indicativo
por construção — está escrito em services/rating_credito.py — e o classificador
segue treinado em dado sintético.

A regra que estes testes existem para travar: **"não sei" é resposta, e é
diferente de ninguém ter respondido**. Juntar as duas coisas esconde a taxa de
resposta, e taxa de resposta é o número que diz se o conjunto presta. Mesma
distinção que validacao_zootecnica faz entre checagem que falhou e checagem que
não rodou.
"""
import pytest

import database as db
from services import auditoria as aud
from services import desfecho as d
from services import lgpd


@pytest.fixture
def parecer():
    db.init_db()
    fazenda_id = db.criar_fazenda('Fazenda Desfecho', 'Produtor', 'Patrocínio',
                                  'MG', criado_por=1)
    return db.salvar_parecer(1, fazenda_id, {'credito_valor': 1_500_000},
                             {'conclusao': {'recomendacao': 'aprovar', 'dscr': 2.3}})


def _login(email='desfecho@example.com'):
    db.init_db()
    usuario = db.buscar_usuario_email(email)
    if not usuario:
        db.criar_usuario(email, 'Desfecho', 'senha123')
        usuario = db.buscar_usuario_email(email)
    from app import app
    app.config['TESTING'] = True
    cliente = app.test_client()
    with cliente.session_transaction() as sessao:
        sessao['_user_id'] = str(usuario['id'])
    cliente.empresa_id = db.empresas_do_usuario(usuario['id'])[0]['id']
    return cliente


def _parecer_da_empresa(empresa_id):
    fazenda_id = db.criar_fazenda('Fazenda Rota', empresa_id=empresa_id, criado_por=1)
    return db.salvar_parecer(1, fazenda_id, {'credito_valor': 1}, {'conclusao': {}})


# ── Um parecer, muitos desfechos ────────────────────────────────────────────

def test_o_parecer_acumula_desfechos_em_vez_de_sobrescrever(parecer):
    """A trajetória é o que ensina: trocar 'em dia' por 'atraso' perde o meio."""
    db.registrar_desfecho(parecer, d.CONTRATACAO, d.CONTRATADA, user_id=1)
    db.registrar_desfecho(parecer, d.ADIMPLENCIA, d.EM_DIA, user_id=1,
                          competencia='safra 2027')
    db.registrar_desfecho(parecer, d.ADIMPLENCIA, d.ATRASO_31_90, user_id=1,
                          competencia='safra 2028')

    registros = db.listar_desfechos(parecer_id=parecer)

    assert [r['situacao'] for r in registros] == [
        d.CONTRATADA, d.EM_DIA, d.ATRASO_31_90]
    assert db.desfecho_atual(parecer, d.ADIMPLENCIA)['situacao'] == d.ATRASO_31_90
    assert db.desfecho_atual(parecer, d.CONTRATACAO)['situacao'] == d.CONTRATADA


# ── A distinção que dá sentido ao conjunto ──────────────────────────────────

def test_nao_sei_e_ausencia_de_resposta_sao_estados_distintos(parecer):
    """O critério de verificação da fase 1."""
    assert db.desfecho_atual(parecer, d.CONTRATACAO) is None

    db.registrar_desfecho(parecer, d.CONTRATACAO, d.NAO_SEI, user_id=1)
    atual = db.desfecho_atual(parecer, d.CONTRATACAO)

    assert atual is not None
    assert atual['situacao'] == d.NAO_SEI


def test_a_cobertura_separa_os_tres_estados():
    """Painel que só mostra "% respondido" trata 'não sei' como resposta útil."""
    registros = [
        {'parecer_id': 1, 'situacao': d.CONTRATADA},
        {'parecer_id': 2, 'situacao': d.NAO_SEI},
        {'parecer_id': 3, 'situacao': d.RECUSADA},
    ]

    c = d.cobertura(10, registros)

    assert c == {'pareceres': 10, 'respondidos': 2, 'so_nao_sei': 1,
                 'sem_registro': 7, 'taxa_resposta_pct': 20.0,
                 'com_desfecho_desfavoravel': 1}


def test_desfecho_desfavoravel_e_contado_a_parte():
    """Se o ruim não for registrado na mesma proporção, o conjunto está torto."""
    bons = d.cobertura(4, [{'parecer_id': i, 'situacao': d.EM_DIA} for i in (1, 2)])
    com_ruim = d.cobertura(4, [{'parecer_id': 1, 'situacao': d.EM_DIA},
                               {'parecer_id': 2, 'situacao': d.ATRASO_MAIS_90}])

    assert bons['com_desfecho_desfavoravel'] == 0
    assert com_ruim['com_desfecho_desfavoravel'] == 1


# ── Vocabulário ─────────────────────────────────────────────────────────────

def test_situacao_de_uma_etapa_nao_vale_na_outra():
    with pytest.raises(d.DesfechoInvalido, match='não existe na etapa'):
        d.validar(d.CONTRATACAO, d.EM_DIA)
    with pytest.raises(d.DesfechoInvalido, match='não existe na etapa'):
        d.validar(d.ADIMPLENCIA, d.RECUSADA)


def test_nao_sei_vale_nas_duas_etapas():
    assert d.validar(d.CONTRATACAO, d.NAO_SEI)[1] == d.NAO_SEI
    assert d.validar(d.ADIMPLENCIA, d.NAO_SEI)[1] == d.NAO_SEI


def test_etapa_e_situacao_sao_normalizadas():
    assert d.validar('CONTRATACAO', ' Contratada ') == (d.CONTRATACAO, d.CONTRATADA)


# ── Condições contratadas ───────────────────────────────────────────────────

def test_condicoes_contratadas_registram_a_divergencia_do_pedido():
    """O banco que corta o valor está dizendo o que achou da operação."""
    condicoes = d.validar_condicoes(d.CONTRATADA, {
        'valor_contratado': '900000', 'prazo_contratado': 72,
        'juros_contratado': 0.105, 'sistema_contratado': 'SAC'})

    assert condicoes == {'valor_contratado': 900000.0, 'prazo_contratado': 72.0,
                         'juros_contratado': 0.105, 'sistema_contratado': 'sac'}


def test_operacao_que_nao_saiu_nao_tem_condicao_contratada():
    with pytest.raises(d.DesfechoInvalido, match='só valem quando a operação'):
        d.validar_condicoes(d.RECUSADA, {'valor_contratado': 900_000})


def test_juros_contratado_segue_a_convencao_de_fracao():
    """10.5 no lugar de 0.105 já produziu serviço de dívida na casa dos bilhões."""
    with pytest.raises(d.DesfechoInvalido, match='fração ao ano'):
        d.validar_condicoes(d.CONTRATADA, {'juros_contratado': 10.5})


# ── Conformidade ────────────────────────────────────────────────────────────

def test_a_tabela_nova_entrou_no_inventario_da_lgpd():
    """O lgpd.py é explícito: tabela com dado pessoal fora daqui é buraco."""
    assert 'desfechos' in lgpd.INVENTARIO
    entrada = lgpd.INVENTARIO['desfechos']
    assert 'produtor' in entrada['titular']
    assert entrada['finalidade'] and entrada['retencao']


def test_o_uso_agregado_fica_marcado_como_pendente():
    """Se a resposta for "só dentro de quem coletou", o produto muda."""
    assert 'base legal' in lgpd.INVENTARIO['desfechos']['observacao'].lower()


def test_registrar_desfecho_tem_evento_de_auditoria():
    assert aud.DESFECHO_REGISTRADO in aud.EVENTOS


# ── As rotas ────────────────────────────────────────────────────────────────

def test_a_rota_registra_e_devolve_o_historico():
    cliente = _login()
    parecer = _parecer_da_empresa(cliente.empresa_id)

    criado = cliente.post(f'/api/pareceres/{parecer}/desfecho', json={
        'etapa': 'contratacao', 'situacao': 'contratada',
        'condicoes': {'valor_contratado': 900000, 'juros_contratado': 0.105},
        'observacao': 'banco aprovou 60% do pedido'})
    assert criado.status_code == 201

    corpo = cliente.get(f'/api/pareceres/{parecer}/desfecho').get_json()
    assert len(corpo['desfechos']) == 1
    assert corpo['atual']['contratacao']['situacao'] == 'contratada'
    assert corpo['atual']['adimplencia'] is None          # ninguém respondeu
    assert 'nao_sei' in corpo['vocabulario']['contratacao']


def test_a_rota_recusa_situacao_de_outra_etapa():
    cliente = _login()
    parecer = _parecer_da_empresa(cliente.empresa_id)
    resposta = cliente.post(f'/api/pareceres/{parecer}/desfecho',
                             json={'etapa': 'contratacao', 'situacao': 'em_dia'})

    assert resposta.status_code == 400
    assert 'não existe na etapa' in resposta.get_json()['erro']


def test_a_rota_de_cobertura_responde():
    corpo = _login().get('/api/desfechos/cobertura').get_json()

    assert {'pareceres', 'respondidos', 'so_nao_sei', 'sem_registro',
            'taxa_resposta_pct'} <= set(corpo)


# ── Isolamento multi-tenant ─────────────────────────────────────────────────

def test_parecer_de_outra_empresa_responde_404_na_leitura_e_na_escrita():
    dono = _login('dono-desfecho@example.com')
    intruso = _login('intruso-desfecho@example.com')
    parecer = _parecer_da_empresa(dono.empresa_id)

    assert intruso.get(f'/api/pareceres/{parecer}/desfecho').status_code == 404
    gravado = intruso.post(f'/api/pareceres/{parecer}/desfecho',
                           json={'etapa': 'contratacao', 'situacao': 'contratada'})
    assert gravado.status_code == 404
    assert db.listar_desfechos(parecer_id=parecer) == []


def test_parecer_inexistente_responde_404():
    assert _login().post('/api/pareceres/999999/desfecho',
                         json={'etapa': 'contratacao',
                               'situacao': 'contratada'}).status_code == 404


def test_snapshot_de_outra_organizacao_e_recusado():
    cliente = _login()
    parecer = _parecer_da_empresa(cliente.empresa_id)
    resposta = cliente.post(f'/api/pareceres/{parecer}/desfecho',
                            json={'etapa': 'contratacao', 'situacao': 'contratada',
                                  'snapshot_id': 999999})
    assert resposta.status_code == 400


def test_excluir_fazenda_leva_os_desfechos_junto():
    cliente = _login()
    fazenda_id = db.criar_fazenda('Fazenda Excluir', empresa_id=cliente.empresa_id,
                                  criado_por=1)
    parecer = db.salvar_parecer(1, fazenda_id, {'credito_valor': 1}, {'conclusao': {}})
    db.registrar_desfecho(parecer, d.CONTRATACAO, d.CONTRATADA, user_id=1)

    assert db.excluir_fazenda(fazenda_id, cliente.empresa_id)
    assert db.listar_desfechos(parecer_id=parecer) == []
