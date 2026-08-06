"""
TOTP (RFC 6238) — segundo fator, sem dependência externa.

São ~60 linhas de HMAC sobre a biblioteca padrão. Trazer um pacote para isso
adicionaria superfície de supply chain no caminho de autenticação, que é o
último lugar onde se quer dependência de terceiro.

O que costuma sair errado numa implementação caseira, e está resolvido aqui:

**Reuso de código.** Um TOTP vale 30 segundos. Sem registrar o contador já
usado, quem interceptar o código (ombro, phishing, log) o reusa dentro da
janela. `verificar` devolve o contador aceito justamente para o chamador
persistir e recusar o mesmo de novo — ver `USO_UNICO`.

**Comparação não constante.** `==` em string vaza o prefixo correto pelo tempo
de resposta. Usa `hmac.compare_digest`.

**Janela larga.** Aceitar ±5 passos "para o relógio do celular" multiplica por
dez a chance de acerto por força bruta. O default é ±1 (30s para cada lado),
que cobre desvio real de relógio.

**Força bruta.** Seis dígitos são um milhão de combinações — muito para chutar
uma vez, pouco para tentativas ilimitadas. O limite de tentativas fica com o
chamador; este módulo só não atrapalha.

Módulo puro — sem I/O, sem estado.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import struct
import time
from urllib.parse import quote

PASSO_SEGUNDOS = 30
DIGITOS = 6
JANELA_PADRAO = 1          # ±1 passo = ±30s de tolerância de relógio
_ALFABETO_B32 = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567'


def gerar_segredo(bytes_entropia: int = 20) -> str:
    """
    Segredo em base32 sem padding — 160 bits, o tamanho recomendado pela
    RFC 4226. Base32 porque é o que os aplicativos autenticadores leem.
    """
    bruto = secrets.token_bytes(bytes_entropia)
    return base64.b32encode(bruto).decode('ascii').rstrip('=')


def _decodificar_segredo(segredo: str) -> bytes:
    s = (segredo or '').strip().replace(' ', '').upper()
    if not s or any(c not in _ALFABETO_B32 for c in s):
        raise ValueError('segredo TOTP inválido')
    return base64.b32decode(s + '=' * (-len(s) % 8))


def _codigo(segredo_bytes: bytes, contador: int, digitos: int,
            algoritmo=hashlib.sha1) -> str:
    """HOTP (RFC 4226): truncamento dinâmico do HMAC do contador."""
    mac = hmac.new(segredo_bytes, struct.pack('>Q', contador), algoritmo).digest()
    desloc = mac[-1] & 0x0F
    trecho = struct.unpack('>I', mac[desloc:desloc + 4])[0] & 0x7FFFFFFF
    return str(trecho % (10 ** digitos)).zfill(digitos)


def contador_atual(agora: float | None = None) -> int:
    return int((time.time() if agora is None else agora) // PASSO_SEGUNDOS)


def gerar(segredo: str, agora: float | None = None, digitos: int = DIGITOS) -> str:
    return _codigo(_decodificar_segredo(segredo), contador_atual(agora), digitos)


def verificar(segredo: str, codigo: str, *, agora: float | None = None,
              janela: int = JANELA_PADRAO, digitos: int = DIGITOS,
              contador_minimo: int | None = None):
    """
    Confere um código. Devolve o CONTADOR aceito, ou None.

    O contador volta de propósito: o chamador precisa persistir para recusar o
    mesmo código de novo dentro da janela. Sem isso, um código interceptado é
    reutilizável por até 90 segundos.

    `contador_minimo` recusa contadores já usados — passe o último aceito + 1.
    """
    limpo = ''.join(c for c in str(codigo or '') if c.isdigit())
    if len(limpo) != digitos:
        return None
    try:
        chave = _decodificar_segredo(segredo)
    except ValueError:
        return None

    atual = contador_atual(agora)
    for delta in range(-janela, janela + 1):
        c = atual + delta
        if c < 0:
            continue
        if contador_minimo is not None and c < contador_minimo:
            continue   # já usado — não vale de novo
        if hmac.compare_digest(_codigo(chave, c, digitos), limpo):
            return c
    return None


def uri_provisionamento(segredo: str, conta: str, emissor: str = 'Orkavyn Agro Intelligence') -> str:
    """
    URI `otpauth://` para o QR code do aplicativo autenticador.

    O emissor aparece duas vezes por convenção do Google Authenticator: no
    rótulo e no parâmetro. Sem o do rótulo, apps antigos mostram só o e-mail e
    o usuário não sabe de qual sistema é a entrada.
    """
    rotulo = quote(f'{emissor}:{conta}', safe='')
    return (f'otpauth://totp/{rotulo}?secret={segredo}'
            f'&issuer={quote(emissor, safe="")}'
            f'&algorithm=SHA1&digits={DIGITOS}&period={PASSO_SEGUNDOS}')


# ── Códigos de recuperação ──────────────────────────────────────────────────
# Perder o celular não pode significar perder a conta. São de uso único e
# guardados em hash — quem lê o banco não consegue entrar.
QTD_BACKUP = 10


def gerar_codigos_backup(qtd: int = QTD_BACKUP) -> list[str]:
    """Formato xxxx-xxxx: legível para anotar, ~1 bilhão de combinações."""
    def _um():
        b = secrets.token_hex(4)
        return f'{b[:4]}-{b[4:]}'
    return [_um() for _ in range(qtd)]


def hash_codigo_backup(codigo: str, sal: str = '') -> str:
    limpo = ''.join(c for c in str(codigo or '').lower() if c.isalnum())
    sal = sal or os.environ.get('SECRET_KEY') or 'orkavyn-agro-intelligence'
    return hashlib.sha256((sal + limpo).encode()).hexdigest()


def conferir_codigo_backup(codigo: str, hashes: list, sal: str = ''):
    """
    Devolve o hash consumido, ou None. Comparação em tempo constante contra
    todos os hashes — sair no primeiro acerto vazaria a posição pelo tempo.
    """
    if not codigo or not hashes:
        return None
    alvo = hash_codigo_backup(codigo, sal)
    achado = None
    for h in hashes:
        if hmac.compare_digest(str(h), alvo):
            achado = h
    return achado
