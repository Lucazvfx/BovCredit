"""
Canal WhatsApp — Meta Cloud API.

A URL de um webhook é pública por necessidade: qualquer um pode postar nela.
O que separa a Meta de um impostor é a assinatura HMAC, e é por isso que a
maior parte destes testes é sobre ela. Sem essa verificação, qualquer um
injeta mensagens em nome de qualquer telefone e o bot devolve dados de
crédito de um cliente real.
"""
import hashlib
import hmac
import json

import pytest

from services import whatsapp as wa


@pytest.fixture
def configurado(monkeypatch):
    monkeypatch.setattr(wa, '_TOKEN', 'tok-teste')
    monkeypatch.setattr(wa, '_PHONE_ID', '123456')
    monkeypatch.setattr(wa, '_VERIFY_TOKEN', 'verify-secreto')
    monkeypatch.setattr(wa, '_APP_SECRET', 'app-secreto')


def _assinar(corpo: bytes, segredo: str = 'app-secreto') -> str:
    return 'sha256=' + hmac.new(segredo.encode(), corpo, hashlib.sha256).hexdigest()


# ── Feature flag ────────────────────────────────────────────────────────────
def test_inativo_sem_credenciais(monkeypatch):
    monkeypatch.setattr(wa, '_TOKEN', '')
    monkeypatch.setattr(wa, '_PHONE_ID', '')
    assert wa._feature_ativa() is False


def test_ativo_com_credenciais(configurado):
    assert wa._feature_ativa() is True


# ── Assinatura: a fronteira de segurança ────────────────────────────────────
def test_assinatura_valida_passa(configurado):
    corpo = b'{"entry":[]}'
    assert wa.validar_assinatura(corpo, _assinar(corpo)) is True


def test_assinatura_de_outro_segredo_e_recusada(configurado):
    """Um impostor com o payload certo e o segredo errado."""
    corpo = b'{"entry":[]}'
    assert wa.validar_assinatura(corpo, _assinar(corpo, 'segredo-do-atacante')) is False


def test_corpo_adulterado_e_recusado(configurado):
    """Assinatura legítima de OUTRO corpo — o ataque que a HMAC existe para pegar."""
    assinatura = _assinar(b'{"entry":[]}')
    assert wa.validar_assinatura(b'{"entry":[{"malicioso":1}]}', assinatura) is False


@pytest.mark.parametrize('header', [None, '', 'lixo', 'sha1=abc', 'sha256=', 'sha256=zz'])
def test_headers_malformados_sao_recusados(configurado, header):
    assert wa.validar_assinatura(b'{}', header) is False


def test_sem_app_secret_falha_fechado(monkeypatch):
    """
    O erro mais perigoso possível aqui seria tratar segredo ausente como
    "aceita tudo". Configuração incompleta tem que recusar, não liberar.
    """
    monkeypatch.setattr(wa, '_APP_SECRET', '')
    corpo = b'{"entry":[]}'
    assert wa.validar_assinatura(corpo, _assinar(corpo, '')) is False


# ── Handshake de verificação ────────────────────────────────────────────────
def test_handshake_devolve_o_challenge(configurado):
    assert wa.verificar_webhook({
        'hub.mode': 'subscribe', 'hub.verify_token': 'verify-secreto',
        'hub.challenge': 'abc123'}) == 'abc123'


def test_handshake_com_token_errado_recusa(configurado):
    assert wa.verificar_webhook({
        'hub.mode': 'subscribe', 'hub.verify_token': 'errado',
        'hub.challenge': 'abc123'}) is None


def test_handshake_sem_verify_token_configurado_recusa(monkeypatch):
    monkeypatch.setattr(wa, '_VERIFY_TOKEN', '')
    assert wa.verificar_webhook({
        'hub.mode': 'subscribe', 'hub.verify_token': '', 'hub.challenge': 'x'}) is None


# ── Leitura do payload ──────────────────────────────────────────────────────
def _payload_texto(texto='Qual o DSCR?', telefone='5511987654321'):
    return {'entry': [{'changes': [{'value': {
        'contacts': [{'wa_id': telefone, 'profile': {'name': 'João'}}],
        'messages': [{'from': telefone, 'id': 'wamid.X', 'type': 'text',
                      'text': {'body': texto}}],
    }}]}]}


def test_extrai_mensagem_de_texto():
    msgs = wa.extrair_mensagens(_payload_texto())
    assert len(msgs) == 1
    assert msgs[0]['texto'] == 'Qual o DSCR?'
    assert msgs[0]['telefone'] == '5511987654321'
    assert msgs[0]['nome'] == 'João'


def test_ignora_eventos_que_nao_sao_mensagem():
    """
    Recibo de entrega e leitura chegam pelo mesmo webhook. Responder a um
    recibo gera laço — a resposta gera outro recibo, e assim por diante.
    """
    status = {'entry': [{'changes': [{'value': {
        'statuses': [{'id': 'wamid.X', 'status': 'delivered'}]}}]}]}
    assert wa.extrair_mensagens(status) == []


def test_ignora_mensagem_que_nao_e_texto():
    audio = {'entry': [{'changes': [{'value': {'messages': [
        {'from': '5511999', 'id': 'w1', 'type': 'audio', 'audio': {'id': 'a'}}]}}]}]}
    assert wa.extrair_mensagens(audio) == []


@pytest.mark.parametrize('payload', [
    {}, None, {'entry': []}, {'entry': [{}]}, {'entry': [{'changes': []}]},
    {'entry': [{'changes': [{'value': {}}]}]},
    {'entry': [{'changes': [{'value': {'messages': [{}]}}]}]},
])
def test_payloads_incompletos_nao_quebram(payload):
    assert wa.extrair_mensagens(payload) == []


def test_varias_mensagens_no_mesmo_payload():
    p = {'entry': [{'changes': [{'value': {'messages': [
        {'from': '551199', 'id': 'a', 'type': 'text', 'text': {'body': 'um'}},
        {'from': '551188', 'id': 'b', 'type': 'text', 'text': {'body': 'dois'}},
    ]}}]}]}
    assert [m['texto'] for m in wa.extrair_mensagens(p)] == ['um', 'dois']


# ── Telefone brasileiro: a armadilha do nono dígito ─────────────────────────
def test_normaliza_removendo_formatacao():
    assert wa.normalizar_telefone('+55 (11) 98765-4321') == '5511987654321'


def test_variantes_cobrem_o_nono_digito():
    """
    A Meta entrega celulares brasileiros SEM o nono dígito, e o usuário digita
    COM. Comparar cru nunca casa, e o vínculo silenciosamente nunca funciona.
    """
    com_nono = wa.variantes_telefone('5511987654321')
    assert '5511987654321' in com_nono
    assert '551187654321' in com_nono

    sem_nono = wa.variantes_telefone('551187654321')
    assert '551187654321' in sem_nono
    assert '5511987654321' in sem_nono


def test_numero_estrangeiro_nao_ganha_variante_inventada():
    v = wa.variantes_telefone('14155552671')       # EUA
    assert v == ['14155552671']


def test_telefone_vazio():
    assert wa.variantes_telefone('') == []


# ── Envio ───────────────────────────────────────────────────────────────────
def test_envio_inativo_sem_credenciais(monkeypatch):
    monkeypatch.setattr(wa, '_TOKEN', '')
    monkeypatch.setattr(wa, '_PHONE_ID', '')
    assert wa.enviar_mensagem('5511999', 'oi') is False


def test_envio_monta_a_chamada_certa(configurado, monkeypatch):
    capturado = {}

    class _Resp:
        status_code = 200
        text = 'ok'

    def _post(url, **kw):
        capturado['url'] = url
        capturado['json'] = kw.get('json')
        capturado['headers'] = kw.get('headers')
        return _Resp()

    monkeypatch.setattr(wa.requests, 'post', _post)
    assert wa.enviar_mensagem('5511987654321', 'resposta') is True
    assert '123456/messages' in capturado['url']
    assert capturado['json']['to'] == '5511987654321'
    assert capturado['json']['text']['body'] == 'resposta'
    assert capturado['headers']['Authorization'] == 'Bearer tok-teste'


def test_texto_longo_e_truncado(configurado, monkeypatch):
    """O WhatsApp corta; cortamos antes para não perder o fim sem aviso."""
    enviado = {}

    class _Resp:
        status_code = 200
        text = 'ok'

    monkeypatch.setattr(wa.requests, 'post',
                        lambda url, **kw: (enviado.update(kw['json']), _Resp())[1])
    wa.enviar_mensagem('5511999', 'x' * 9000)
    assert len(enviado['text']['body']) <= wa.LIMITE_TEXTO
    assert enviado['text']['body'].endswith('...')


def test_erro_de_rede_nao_levanta(configurado, monkeypatch):
    """
    O chamador é um webhook: se levantasse, a Meta veria 500 e reenviaria a
    mesma mensagem em backoff — resposta duplicada para o usuário.
    """
    def _explode(*a, **k):
        raise ConnectionError('rede caiu')

    monkeypatch.setattr(wa.requests, 'post', _explode)
    assert wa.enviar_mensagem('5511999', 'oi') is False


def test_erro_http_devolve_false(configurado, monkeypatch):
    class _Resp:
        status_code = 401
        text = 'token expirado'

    monkeypatch.setattr(wa.requests, 'post', lambda url, **kw: _Resp())
    assert wa.enviar_mensagem('5511999', 'oi') is False
