"""
Cifragem dos segredos que ficam guardados no banco.

O caso a proteger é um só: alguém lê a base. Backup mal guardado, dump
acidental, credencial do Supabase vazada, ex-funcionário com acesso. Nesse
cenário, um segredo TOTP em claro deixa de ser segundo fator — quem leu a
tabela gera os códigos de todo mundo, para sempre, e a vítima não tem como
perceber. Ao contrário de uma senha, o segredo não expira e não é trocado.

Por isso a chave mora FORA do banco: qualquer chave que não esteja na base
já derrota o ataque.

## De onde vem a chave

`TOTP_CHAVE` se estiver definida (chave Fernet, 32 bytes em base64 urlsafe —
gere com `Fernet.generate_key()`). Sem ela, deriva de `SECRET_KEY`, que em
produção é obrigatória e estável.

Derivar da SECRET_KEY foi escolha deliberada: evita coordenar uma variável
nova num deploy que já roda. O preço está registrado abaixo.

## O que acontece se a chave mudar

Trocar `SECRET_KEY` sem definir `TOTP_CHAVE` torna os segredos ilegíveis.
Isso NÃO tranca ninguém fora e NÃO burla o 2FA: `decifrar` devolve None,
`totp.verificar` recusa qualquer código, e a entrada passa a ser pelos
códigos de backup — que são hash próprio, alheios a esta chave. O usuário
reativa o 2FA depois.

Ainda assim é um transtorno para toda a base ao mesmo tempo. Quem for
rotacionar `SECRET_KEY` deve antes fixar `TOTP_CHAVE`, que desacopla as duas.

## Migração

Segredos gravados antes desta versão estão em claro. `decifrar` os reconhece
e devolve como estão; `precisa_recifrar` avisa quem os lê para regravá-los
cifrados. A base se corrige sozinha conforme cada usuário usa o 2FA.
"""
from __future__ import annotations

import base64
import hashlib
import logging
import os

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)

# Todo token Fernet começa com o byte de versão 0x80, que em base64 urlsafe
# vira este prefixo. Serve para separar cifrado de legado em claro sem
# depender de tentativa e erro — um segredo TOTP é base32 (A-Z2-7) e nunca
# se parece com isto.
_PREFIXO_FERNET = 'gAAAAA'


def _chave() -> bytes:
    bruta = os.environ.get('TOTP_CHAVE')
    if bruta:
        return bruta.encode()
    semente = os.environ.get('SECRET_KEY') or 'orkavyn-dev-secret-local'
    derivada = hashlib.sha256(f'totp:{semente}'.encode()).digest()
    return base64.urlsafe_b64encode(derivada)


def cifrar(texto: str) -> str:
    return Fernet(_chave()).encrypt((texto or '').encode()).decode()


def parece_cifrado(valor: str) -> bool:
    return bool(valor) and valor.startswith(_PREFIXO_FERNET)


def precisa_recifrar(valor: str) -> bool:
    """True para o que está gravado em claro — legado a regravar."""
    return bool(valor) and not parece_cifrado(valor)


def decifrar(valor: str) -> str | None:
    """Devolve o texto em claro, ou None se a chave não abrir o valor.

    None é o caminho de degradação, não um erro a engolir: quem chama trata
    como "sem segredo", o que recusa os códigos TOTP e joga o usuário para os
    códigos de backup. Silenciar seria burlar o 2FA; estourar trancaria a
    conta inteira, backup incluído.
    """
    if not valor:
        return None
    if not parece_cifrado(valor):
        return valor          # legado em claro, de antes da cifragem
    try:
        return Fernet(_chave()).decrypt(valor.encode()).decode()
    except InvalidToken:
        logger.error(
            '[cripto] segredo TOTP não abriu com a chave atual. '
            'SECRET_KEY foi trocada sem TOTP_CHAVE definida? '
            'O usuário entra pelos códigos de backup e reativa o 2FA.'
        )
        return None
