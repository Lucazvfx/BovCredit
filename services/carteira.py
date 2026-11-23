"""Resumo de carteira (revenda) a partir dos pareceres já salvos.

Somente LEITURA do JSON persistido: nenhuma regra de crédito é recalculada aqui.
Pareceres antigos não têm `ciclo_pecuario`, `estresse_pecuario` ou `rating`; cada
campo ausente ou malformado vira `None` (a interface mostra '—').
"""
import json

MESES = ("jan", "fev", "mar", "abr", "mai", "jun",
         "jul", "ago", "set", "out", "nov", "dez")
_MAX_RESSALVAS = 3


def _dict(v):
    return v if isinstance(v, dict) else {}


def _num(v):
    if isinstance(v, bool) or v is None:
        return None
    try:
        n = float(v)
    except (TypeError, ValueError):
        return None
    return n if n == n and abs(n) != float('inf') else None


def _json(txt):
    if isinstance(txt, dict):
        return txt
    try:
        return _dict(json.loads(txt or '{}'))
    except (TypeError, ValueError):
        return {}


def _ressalvas(parecer):
    c = _dict(parecer.get('conclusao'))
    itens = []
    if c.get('justificativa') and c.get('recomendacao') != 'aprovar':
        itens.append(str(c['justificativa']))
    est = _dict(parecer.get('estresse_pecuario'))
    if est.get('disponivel') and isinstance(est.get('avisos'), list):
        itens.extend(str(a) for a in est['avisos'])
    return itens


def resumo_parecer(parecer_json, solicitacao_json=None) -> dict:
    """Campos de leitura rápida de um parecer salvo; `None` quando não existe."""
    p = _json(parecer_json)
    sol = _json(solicitacao_json)
    c = _dict(p.get('conclusao'))
    rating = _dict(p.get('rating'))

    est = _dict(p.get('estresse_pecuario'))
    rup = (_dict(_dict(est.get('ponto_ruptura_arroba')).get('ressalva'))
           if est.get('disponivel') else {})
    ruptura = None
    if rup and _num(rup.get('preco_minimo')) is not None:
        ruptura = {'preco_minimo': _num(rup.get('preco_minimo')),
                   'preco_base': _num(rup.get('preco_base')),
                   'folga_pct': _num(rup.get('queda_maxima_suportada_pct')),
                   'em_ruptura': rup.get('em_ruptura') is True}

    ciclo = _dict(p.get('ciclo_pecuario'))
    vale = None
    if ciclo.get('disponivel'):
        deficit = ciclo.get('meses_deficit')
        n_def = len(deficit) if isinstance(deficit, list) else None
        mes = ciclo.get('mes_vale')
        vale = {'tem_vale': bool(n_def) if n_def is not None else None,
                'valor': (abs(_num(ciclo.get('vale_caixa')))
                          if _num(ciclo.get('vale_caixa')) is not None else None),
                'mes': (MESES[mes - 1]
                        if isinstance(mes, int) and not isinstance(mes, bool)
                        and 1 <= mes <= 12 else None),
                'meses_deficit': n_def,
                'quebra_com_dscr_ok': ciclo.get('quebra_caixa_com_dscr_ok') is True}

    ress = _ressalvas(p)
    erros = _num(_dict(_dict(p.get('consistencia')).get('resumo')).get('erros'))
    return {
        'dscr_minimo': _num(c.get('dscr_minimo')),
        'rating_faixa': str(rating['faixa']) if rating.get('faixa') else None,
        'rating_score': _num(rating.get('score')),
        'prazo_meses': _num(sol.get('prazo_meses')),
        'anos_avaliados': _num(c.get('anos_avaliados')),
        'credito_valor': _num(sol.get('credito_valor')),
        'ruptura': ruptura,
        'vale_caixa': vale,
        'ressalvas_total': len(ress),
        'ressalvas': ress[:_MAX_RESSALVAS],
        'erros_consistencia': int(erros) if erros is not None else None,
    }
