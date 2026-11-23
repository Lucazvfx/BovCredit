"""Papéis por empresa e regra de quem pode decidir uma proposta.

Camada de autorização comercial: não toca em pontuação, classificação nem
DSCR. O papel mora no vínculo (`empresa_membros.papel`), então a mesma pessoa
pode ser admin de uma empresa e analista de outra.
"""
from __future__ import annotations

import re

PAPEL_ADMIN = 'admin'
PAPEL_APROVADOR = 'aprovador'
PAPEL_ANALISTA = 'analista'

PAPEIS = (PAPEL_ADMIN, PAPEL_APROVADOR, PAPEL_ANALISTA)
PAPEL_PADRAO = PAPEL_ANALISTA   # menor privilégio: vínculo sem papel = analista

PAPEIS_ROTULO = {
    PAPEL_ADMIN: 'Administrador',
    PAPEL_APROVADOR: 'Aprovador',
    PAPEL_ANALISTA: 'Analista',
}

# Estados da proposta e decisões possíveis (em_analise é o estado inicial).
STATUS_EM_ANALISE = 'em_analise'
DECISOES = ('aprovado', 'aprovado_com_ressalva', 'reprovado')
STATUS_PROPOSTA = (STATUS_EM_ANALISE,) + DECISOES

# Classificações de alçada que exigem papel autorizado para decidir.
ALCADA_EXIGE_AUTORIZADO = ('requer_comite', 'fora_alcada')
PAPEIS_AUTORIZADOS = (PAPEL_ADMIN, PAPEL_APROVADOR)

PARECER_MAX = 2000
REFERENCIA_MAX = 120


def normalizar_papel(papel) -> str:
    """Papel válido; vazio ou desconhecido cai no padrão (menor privilégio)."""
    return papel if papel in PAPEIS else PAPEL_PADRAO


def pode_decidir(papel, status_alcada: str) -> bool:
    """Analista só decide o que está explicitamente dentro da alçada.

    Status desconhecido (linha corrompida, valor novo) é tratado como restrito.
    """
    if status_alcada == 'dentro_alcada':
        return True
    return normalizar_papel(papel) in PAPEIS_AUTORIZADOS


def validar_proposta(dados) -> tuple[str | None, str | None]:
    """Valida a identificação livre da proposta. Devolve (referencia, erro).

    A referência é um rótulo interno (ex.: número do contrato); não deve
    conter dado pessoal do produtor — o limite de tamanho e o aviso na UI são
    a barreira, a simulação em si não carrega CPF/CNPJ.
    """
    if not isinstance(dados, dict):
        return None, 'Corpo inválido.'
    ref = dados.get('referencia', '')
    if not isinstance(ref, str):
        return None, 'referencia deve ser texto.'
    ref = ref.strip()
    if not 1 <= len(ref) <= REFERENCIA_MAX:
        return None, f'referencia deve ter de 1 a {REFERENCIA_MAX} caracteres.'
    # Barreira mínima de LGPD: CPF (11 dígitos) ou CNPJ (14) na referência.
    if re.search(r'\d{11}', re.sub(r'[.\-/\s]', '', ref)):
        return None, 'referencia não deve conter CPF ou CNPJ; use um código interno.'
    return ref, None


def validar_decisao(dados) -> tuple[dict | None, str | None]:
    if not isinstance(dados, dict):
        return None, 'Corpo inválido.'
    decisao = dados.get('decisao')
    if decisao not in DECISOES:
        return None, 'decisao inválida.'
    parecer = dados.get('parecer', '')
    if not isinstance(parecer, str):
        return None, 'parecer deve ser texto.'
    parecer = parecer.strip()
    if not 1 <= len(parecer) <= PARECER_MAX:
        return None, f'parecer deve ter de 1 a {PARECER_MAX} caracteres.'
    return {'decisao': decisao, 'parecer': parecer}, None
