"""Limites de entrada compartilhados pelas rotas de crédito.

`juros_aa` é FRAÇÃO ao ano (0,105 = 10,5% a.a.). Quem manda 10.5 querendo
10,5% gerava dívida absurda sem aviso, então o teto recusa a entrada.

- JUROS_AA_TETO = 1.0 (exclusivo, ou seja, 100% a.a.): já era o limite usado em
  /api/perene/analisar e /api/agricola/graos/analisar. Crédito rural fica
  muito abaixo disso; o teto só existe para pegar percentual digitado como
  fração, e qualquer valor >= 1 é isso.
- ANOS_MAX = 30: horizonte de projeção de lavoura perene. A vida útil das
  culturas perenes cobertas (café, citros etc.) fica em 25-30 anos, e o
  projetor percorre ano a ano, sem teto próprio.
"""
from __future__ import annotations

import math

JUROS_AA_TETO = 1.0
ANOS_MAX = 30

MSG_JUROS_TETO = (
    'juros_aa é fração ao ano: use 0.105 para 10,5% a.a. '
    'O valor deve ser menor que 1 (100% a.a.).'
)


def erro_juros_aa(valor) -> str | None:
    """Mensagem de erro (pt-BR) para um juros_aa inválido, ou None se ok/ausente."""
    if valor is None:
        return None
    if isinstance(valor, bool):
        return 'juros_aa inválido: informe um número.'
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return 'juros_aa inválido: informe um número.'
    if not math.isfinite(numero):
        return 'juros_aa inválido: informe um número finito.'
    if numero < 0:
        return 'juros_aa não pode ser negativo.'
    if numero >= JUROS_AA_TETO:
        return MSG_JUROS_TETO
    return None


def erro_anos(valor) -> str | None:
    """Mensagem de erro (pt-BR) para `anos` fora de 0..ANOS_MAX, ou None.

    Texto não numérico e 0 seguem para o default (6) do pipeline, como antes.
    """
    if valor is None:
        return None
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(numero):
        return 'anos inválido: informe um número finito.'
    if numero < 0:
        return 'anos não pode ser negativo.'
    if int(numero) > ANOS_MAX:
        return f'anos deve ser no máximo {ANOS_MAX}.'
    return None
