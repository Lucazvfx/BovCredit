"""Rating explicável para pré-análise de crédito pecuário."""
from __future__ import annotations


def calcular_rating(*, dscr=None, ltv=None, consistencia=0,
                    confianca='media-baixa', documentos_pendentes=0,
                    comprometimento_pct=None) -> dict:
    """Calcula nota 0–100 e faixa A–E.

    É uma política inicial explicável. Não representa PD estatística até que
    exista histórico real de operações pagas e inadimplentes.
    """
    pontos = {}
    try: dscr = float(dscr) if dscr is not None else None
    except (TypeError, ValueError): dscr = None
    try: ltv = float(ltv) if ltv is not None else None
    except (TypeError, ValueError): ltv = None
    try: consistencia = float(consistencia or 0)
    except (TypeError, ValueError): consistencia = 0.0
    try: comprometimento_pct = float(comprometimento_pct) if comprometimento_pct is not None else None
    except (TypeError, ValueError): comprometimento_pct = None

    pontos['capacidade_pagamento'] = 30 if dscr is not None and dscr >= 1.30 else 20 if dscr is not None and dscr >= 1.00 else 5 if dscr is not None and dscr > 0 else 0
    pontos['garantia'] = 25 if ltv is not None and ltv <= 60 else 15 if ltv is not None and ltv <= 80 else 0
    pontos['consistencia'] = 20 if consistencia >= 80 else 10 if consistencia >= 50 else 0
    pontos['qualidade_dados'] = 15 if confianca == 'alta' else 10 if confianca == 'media' else 5
    pontos['documentacao'] = 10 if not documentos_pendentes else 4
    pontos['endividamento'] = (10 if comprometimento_pct is not None and comprometimento_pct <= 50
                               else 5 if comprometimento_pct is not None and comprometimento_pct <= 70
                               else 0 if comprometimento_pct is not None else 5)
    score = sum(pontos.values())
    faixa_base = 'A' if score >= 85 else 'B' if score >= 70 else 'C' if score >= 50 else 'D' if score >= 30 else 'E'
    # Sem capacidade calculada ou com documentação obrigatória pendente, o
    # rating não pode ser tratado como baixo risco mesmo que a composição do
    # rebanho seja consistente.
    faixa = faixa_base
    if dscr is None and faixa in ('A', 'B'):
        faixa = 'C'
    if documentos_pendentes and faixa in ('A', 'B'):
        faixa = 'C'
    rotulos = {'A': 'baixo risco', 'B': 'risco moderado', 'C': 'risco elevado',
               'D': 'alto risco', 'E': 'não recomendado'}
    return {
        'score': score,
        'faixa': faixa,
        'faixa_base': faixa_base,
        'rotulo': rotulos[faixa],
        'metodo': 'politica_explicavel_v1',
        'pontos': pontos,
        'observacao': 'Rating indicativo. Deve ser calibrado com histórico real de operações pagas e inadimplentes.',
    }

