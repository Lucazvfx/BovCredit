"""
Canal WhatsApp via Meta Cloud API — o parecer respondendo onde o analista está.

O analista de campo não abre o sistema no meio de uma visita; ele abre o
WhatsApp. Este módulo entrega o mesmo chat que já existe sobre o parecer
(services.groq_narrativa) por um canal que já está na mão dele.

Feature flag: ativo apenas com WHATSAPP_TOKEN e WHATSAPP_PHONE_ID no ambiente.
Sem eles, `_feature_ativa()` é False e as rotas devolvem 404 — o webhook não
existe para quem não configurou. Para reverter por completo: delete este
arquivo e remova as rotas correspondentes em app.py.

Módulo isolado: não importa Flask nem DB, para poder ser testado sem app.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
from typing import Optional

import requests

logger = logging.getLogger(__name__)

_TOKEN        = os.environ.get('WHATSAPP_TOKEN', '')
_PHONE_ID     = os.environ.get('WHATSAPP_PHONE_ID', '')
_VERIFY_TOKEN = os.environ.get('WHATSAPP_VERIFY_TOKEN', '')
_APP_SECRET   = os.environ.get('WHATSAPP_APP_SECRET', '')
_API_VERSION  = os.environ.get('WHATSAPP_API_VERSION', 'v21.0')
_TIMEOUT      = 15

# O WhatsApp corta mensagens acima disso; cortamos antes para não perder o fim.
LIMITE_TEXTO = 4000


def _feature_ativa() -> bool:
    return bool(_TOKEN and _PHONE_ID)


# ── Verificação do webhook (handshake GET da Meta) ──────────────────────────
def verificar_webhook(args: dict) -> Optional[str]:
    """
    Handshake que a Meta faz ao cadastrar a URL do webhook.

    Devolve o challenge quando o token confere, e None em qualquer outro caso —
    o chamador responde 403. Comparação em tempo constante: o verify token é um
    segredo, e comparar com `==` vaza informação pelo tempo de resposta.
    """
    if not _VERIFY_TOKEN:
        logger.warning('WHATSAPP_VERIFY_TOKEN não configurado — handshake recusado')
        return None
    modo      = args.get('hub.mode')
    token     = args.get('hub.verify_token') or ''
    challenge = args.get('hub.challenge')
    if modo == 'subscribe' and hmac.compare_digest(token, _VERIFY_TOKEN):
        return challenge
    return None


# ── Autenticidade da requisição ─────────────────────────────────────────────
def validar_assinatura(corpo: bytes, header_assinatura: str | None) -> bool:
    """
    Confere o X-Hub-Signature-256 que a Meta envia em cada POST.

    A URL do webhook é pública por necessidade: qualquer um pode postar nela.
    Sem esta verificação, qualquer um injeta mensagens em nome de qualquer
    telefone — e o bot responde dados de crédito de um cliente real.

    Sem WHATSAPP_APP_SECRET configurado devolve False, e não True: falhar
    fechado. Um segredo ausente não pode virar "aceita tudo".
    """
    if not _APP_SECRET:
        logger.error('WHATSAPP_APP_SECRET ausente — requisição recusada. '
                     'Sem ele não há como distinguir a Meta de um impostor.')
        return False
    if not header_assinatura or not header_assinatura.startswith('sha256='):
        return False
    esperado = hmac.new(_APP_SECRET.encode(), corpo, hashlib.sha256).hexdigest()
    return hmac.compare_digest(header_assinatura[7:], esperado)


# ── Leitura do payload ──────────────────────────────────────────────────────
def extrair_mensagens(payload: dict) -> list[dict]:
    """
    Extrai as mensagens de texto de um payload de webhook.

    A estrutura da Meta é profundamente aninhada e vem também para eventos que
    não são mensagem (status de entrega, leitura, reações). Devolve lista de
    {telefone, texto, message_id, nome} apenas para texto — o resto é ignorado
    em silêncio, que é o comportamento correto: responder a um recibo de
    leitura gera laço.
    """
    out = []
    for entrada in (payload or {}).get('entry', []) or []:
        for mudanca in entrada.get('changes', []) or []:
            valor = mudanca.get('value') or {}
            perfis = {c.get('wa_id'): (c.get('profile') or {}).get('name', '')
                      for c in valor.get('contacts', []) or []}
            for msg in valor.get('messages', []) or []:
                if msg.get('type') != 'text':
                    continue
                texto = ((msg.get('text') or {}).get('body') or '').strip()
                telefone = msg.get('from')
                if not texto or not telefone:
                    continue
                out.append({
                    'telefone':   telefone,
                    'texto':      texto,
                    'message_id': msg.get('id'),
                    'nome':       perfis.get(telefone, ''),
                })
    return out


# ── Envio ───────────────────────────────────────────────────────────────────
def enviar_mensagem(telefone: str, texto: str) -> bool:
    """
    Envia texto para um número. Devolve True/False e nunca levanta.

    O chamador é um webhook: se levantasse, a Meta veria erro 500 e reenviaria
    a mesma mensagem em backoff, gerando resposta duplicada.
    """
    if not _feature_ativa():
        return False
    if not telefone or not texto:
        return False
    if len(texto) > LIMITE_TEXTO:
        texto = texto[:LIMITE_TEXTO - 3] + '...'

    url = f'https://graph.facebook.com/{_API_VERSION}/{_PHONE_ID}/messages'
    try:
        r = requests.post(
            url,
            headers={'Authorization': f'Bearer {_TOKEN}',
                     'Content-Type': 'application/json'},
            json={'messaging_product': 'whatsapp', 'to': telefone,
                  'type': 'text', 'text': {'preview_url': False, 'body': texto}},
            timeout=_TIMEOUT,
        )
        if r.status_code >= 400:
            logger.warning('WhatsApp envio falhou %s: %s', r.status_code, r.text[:300])
            return False
        return True
    except Exception as e:
        logger.warning('WhatsApp envio falhou (não crítico): %s', e)
        return False


def normalizar_telefone(t: str) -> str:
    """
    Só dígitos.

    O Brasil tem uma armadilha aqui: a Meta entrega números de celular
    brasileiros SEM o nono dígito (5511987654321 chega como 551187654321),
    enquanto o usuário digita o número como o conhece, com ele. Comparar os
    dois cruamente nunca casa. `variantes_telefone` resolve a comparação; esta
    função só limpa a formatação.
    """
    return ''.join(c for c in (t or '') if c.isdigit())


def variantes_telefone(t: str) -> list[str]:
    """
    Formas equivalentes de um número brasileiro, para casar no banco.

    Devolve o número normalizado e, quando aplicável, a variante com e sem o
    nono dígito. Fora do padrão brasileiro devolve só o próprio número.
    """
    n = normalizar_telefone(t)
    if not n:
        return []
    saida = [n]
    # 55 + DDD(2) + 9 + 8 dígitos = 13  →  variante sem o nono
    if len(n) == 13 and n.startswith('55') and n[4] == '9':
        saida.append(n[:4] + n[5:])
    # 55 + DDD(2) + 8 dígitos = 12  →  variante com o nono
    elif len(n) == 12 and n.startswith('55'):
        saida.append(n[:4] + '9' + n[4:])
    return saida
