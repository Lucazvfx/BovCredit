"""Política de alçada comercial e simulação de proposta.

Camada complementar: não altera pontuação, classificação nem DSCR. A
capacidade vem de `payment_capacity_engine.dscr` (única fórmula); aqui só se
compara o pedido com essa capacidade e com a alçada que a empresa definiu.

Os valores padrão são premissa de política (origem `politica`), não
benchmark: cada empresa os substitui pelos seus.
"""
from __future__ import annotations

import math

from services.payment_capacity_engine.dscr import (
    avaliar_capacidade_pagamento,
    credito_maximo,
)
from services.proveniencia import politica as _politica

FONTE_PADRAO = 'Premissa de política comercial (padrão Orkavyn)'

_PADRAO = {
    'alcada_analista': _politica(
        500_000.0, FONTE_PADRAO, rotulo='Alçada do analista (R$)',
        nota='Até este valor o analista decide sem comitê.'),
    'alcada_comite': _politica(
        3_000_000.0, FONTE_PADRAO, rotulo='Alçada do comitê (R$)',
        nota='Acima deste valor a proposta está fora da alçada da empresa.'),
    'prazo_max_meses': _politica(
        60, FONTE_PADRAO, rotulo='Prazo máximo (meses)'),
    'margem_capacidade_pct': _politica(
        100.0, FONTE_PADRAO, rotulo='Uso máximo da capacidade (%)',
        nota='Fração da capacidade máxima de endividamento que o pedido pode usar.'),
}
COMITE_SE_REVISAO_PADRAO = True

MOTIVOS_REVISAO_VALIDOS = ('dados_incompletos', 'muito_atipico')
NIVEIS_ATIPICIDADE = ('tipico', 'atipico', 'muito_atipico')

VALOR_MAX = 1e11
PRAZO_MAX_MESES = 360

_ROTULOS_STATUS = {
    'dentro_alcada': 'Dentro da alçada',
    'requer_comite': 'Requer comitê',
    'fora_alcada': 'Fora da alçada',
}
ROTULOS_STATUS = _ROTULOS_STATUS
_TEXTO_MOTIVO = {
    'acima_alcada_comite': 'Valor acima da alçada do comitê.',
    'acima_alcada_analista': 'Valor acima da alçada do analista.',
    'prazo_acima_politica': 'Prazo acima do máximo da política.',
    'acima_capacidade': 'Valor acima da capacidade de pagamento permitida.',
    'sem_capacidade': 'Sem capacidade de pagamento no prazo informado.',
    'revisao_humana': 'Classificação exige revisão humana.',
}


def politica_padrao() -> dict:
    return {
        'alcada_analista': float(_PADRAO['alcada_analista']),
        'alcada_comite': float(_PADRAO['alcada_comite']),
        'prazo_max_meses': int(_PADRAO['prazo_max_meses']),
        'margem_capacidade_pct': float(_PADRAO['margem_capacidade_pct']),
        'comite_se_revisao_humana': COMITE_SE_REVISAO_PADRAO,
    }


def _numero(valor):
    """float finito ou None; bool e texto não numérico são rejeitados."""
    if isinstance(valor, bool) or valor is None:
        return None
    try:
        n = float(valor)
    except (TypeError, ValueError, OverflowError):
        return None
    return n if math.isfinite(n) else None


def validar_politica(dados, base: dict | None = None) -> tuple[dict | None, str | None]:
    """Valida um payload de política. Campos ausentes herdam `base`.

    `base` é a política vigente da empresa (padrão se omitida), de modo que um
    PUT parcial não apaga o que já foi configurado.
    Devolve (politica, None) ou (None, mensagem de erro).
    """
    if not isinstance(dados, dict):
        return None, 'Corpo inválido.'
    atual = politica_padrao()
    if base:
        atual.update({k: base[k] for k in atual if k in base})
    for campo in ('alcada_analista', 'alcada_comite'):
        if campo in dados:
            n = _numero(dados[campo])
            if n is None or not 0 < n <= VALOR_MAX:
                return None, f'{campo} deve ser um valor positivo.'
            atual[campo] = round(n, 2)
    if 'prazo_max_meses' in dados:
        n = _numero(dados['prazo_max_meses'])
        if n is None or n != int(n) or not 1 <= n <= PRAZO_MAX_MESES:
            return None, f'prazo_max_meses deve ser inteiro de 1 a {PRAZO_MAX_MESES}.'
        atual['prazo_max_meses'] = int(n)
    if 'margem_capacidade_pct' in dados:
        n = _numero(dados['margem_capacidade_pct'])
        if n is None or not 10 <= n <= 100:
            return None, 'margem_capacidade_pct deve estar entre 10 e 100.'
        atual['margem_capacidade_pct'] = round(n, 2)
    if 'comite_se_revisao_humana' in dados:
        if not isinstance(dados['comite_se_revisao_humana'], bool):
            return None, 'comite_se_revisao_humana deve ser verdadeiro ou falso.'
        atual['comite_se_revisao_humana'] = dados['comite_se_revisao_humana']
    if atual['alcada_analista'] > atual['alcada_comite']:
        return None, 'A alçada do analista não pode exceder a do comitê.'
    return atual, None


def validar_simulacao(dados) -> tuple[dict | None, str | None]:
    """Valida o payload da simulação. `juros_aa` é fração (0,105 = 10,5%)."""
    if not isinstance(dados, dict):
        return None, 'Corpo inválido.'
    valor = _numero(dados.get('valor_pretendido'))
    if valor is None or not 0 < valor <= VALOR_MAX:
        return None, 'valor_pretendido deve ser um valor positivo.'
    prazo = _numero(dados.get('prazo_meses'))
    if prazo is None or prazo != int(prazo) or not 1 <= prazo <= PRAZO_MAX_MESES:
        return None, f'prazo_meses deve ser inteiro de 1 a {PRAZO_MAX_MESES}.'
    caixa = _numero(dados.get('geracao_caixa_anual'))
    if caixa is None or abs(caixa) > VALOR_MAX:
        return None, 'geracao_caixa_anual deve ser um número.'
    juros = _numero(dados.get('juros_aa'))
    if juros is None or not 0 < juros < 1:
        return None, 'juros_aa deve ser fração entre 0 e 1 (0,105 = 10,5% a.a.).'
    carencia = _numero(dados.get('carencia_meses', 0))
    if carencia is None or carencia != int(carencia) or not 0 <= carencia < prazo:
        return None, 'carencia_meses deve ser inteiro menor que o prazo.'
    dividas = _numero(dados.get('dividas_mensais', 0))
    if dividas is None or not 0 <= dividas <= VALOR_MAX:
        return None, 'dividas_mensais deve ser um valor não negativo.'

    revisao = dados.get('revisao_humana', False)
    if not isinstance(revisao, bool):
        return None, 'revisao_humana deve ser verdadeiro ou falso.'
    motivos = dados.get('motivos_revisao') or []
    if (not isinstance(motivos, list)
            or any(m not in MOTIVOS_REVISAO_VALIDOS for m in motivos)):
        return None, 'motivos_revisao contém valor inválido.'
    nivel = dados.get('atipicidade_nivel')
    if nivel is not None and nivel not in NIVEIS_ATIPICIDADE:
        return None, 'atipicidade_nivel inválido.'

    return {
        'valor_pretendido': valor,
        'prazo_meses': int(prazo),
        'geracao_caixa_anual': caixa,
        'juros_aa': juros,
        'carencia_meses': int(carencia),
        'dividas_mensais': dividas,
        'revisao_humana': revisao,
        'motivos_revisao': list(dict.fromkeys(motivos)),
        'atipicidade_nivel': nivel,
    }, None


def simular_proposta(politica: dict, *, valor_pretendido: float, prazo_meses: int,
                     geracao_caixa_anual: float, juros_aa: float,
                     carencia_meses: int = 0, dividas_mensais: float = 0.0,
                     revisao_humana: bool = False, motivos_revisao=(),
                     atipicidade_nivel: str | None = None) -> dict:
    """Compara o pedido com a capacidade e com a alçada da empresa.

    Entradas já validadas (ver `validar_simulacao`). Não grava nada.
    """
    # O teto de capacidade usa o DSCR de aprovação (1,30) do motor: uma proposta
    # na faixa de "ressalva" do parecer é, por política, tratada como acima da
    # capacidade — a alçada comercial é mais conservadora que a recomendação.
    capacidade_max = credito_maximo(
        geracao_caixa_anual, juros_aa, prazo_meses, carencia_meses,
        dividas_mensais)
    capacidade_permitida = round(
        capacidade_max * politica['margem_capacidade_pct'] / 100.0, 2)
    avaliacao = avaliar_capacidade_pagamento(
        geracao_caixa_anual, valor_pretendido, prazo_meses, juros_aa,
        carencia_meses, dividas_mensais)

    bloqueios, avisos = [], []
    nivel = 'analista'
    if valor_pretendido > politica['alcada_comite']:
        bloqueios.append('acima_alcada_comite')
        nivel = 'fora_alcada'
    elif valor_pretendido > politica['alcada_analista']:
        avisos.append('acima_alcada_analista')
        nivel = 'comite'
    if prazo_meses > politica['prazo_max_meses']:
        bloqueios.append('prazo_acima_politica')
    if capacidade_max <= 0:
        bloqueios.append('sem_capacidade')
    elif valor_pretendido > capacidade_permitida:
        bloqueios.append('acima_capacidade')

    revisao = bool(revisao_humana) or bool(motivos_revisao) \
        or atipicidade_nivel == 'muito_atipico'
    if revisao:
        avisos.append('revisao_humana')

    if bloqueios:
        status = 'fora_alcada'
    elif nivel == 'comite' or (
            revisao and politica['comite_se_revisao_humana']):
        status = 'requer_comite'
    else:
        status = 'dentro_alcada'

    motivos = bloqueios + avisos
    return {
        'status': status,
        'status_rotulo': _ROTULOS_STATUS[status],
        'nivel_decisor': 'fora_alcada' if bloqueios else (
            'comite' if status == 'requer_comite' else 'analista'),
        'motivos': motivos,
        'motivos_texto': [_TEXTO_MOTIVO[m] for m in motivos],
        'valor_pretendido': round(valor_pretendido, 2),
        'prazo_meses': prazo_meses,
        'capacidade_maxima': capacidade_max,
        'capacidade_permitida': capacidade_permitida,
        'uso_da_capacidade_pct': (
            round(valor_pretendido / capacidade_permitida * 100, 1)
            if capacidade_permitida > 0 else None),
        'dscr': avaliacao.get('dscr'),
        'recomendacao_capacidade': avaliacao.get('recomendacao'),
        'revisao_humana': revisao,
        'motivos_revisao': list(motivos_revisao),
        'atipicidade_nivel': atipicidade_nivel,
        'politica': dict(politica),
    }
