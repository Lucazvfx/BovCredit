"""Transforma a decisão do classificador em evidência legível e estruturada."""
from __future__ import annotations


def montar_explicacao_classificacao(resultado: dict, indicadores: dict) -> dict:
    origem = resultado.get('origem_decisao')
    decisao = 'regra' if origem == 'regra' else 'modelo'
    fatores = []
    labels = {
        'total': 'total do rebanho',
        'matrizes': 'matrizes consideradas',
        'fem_adultas': 'fêmeas adultas',
        'pct_matrizes': 'participação de matrizes',
        'pct_cria': 'participação de animais de cria',
        'pct_recria': 'participação de animais de recria',
        'pct_adultos': 'participação de adultos',
    }
    for campo, rotulo in labels.items():
        if campo not in indicadores or indicadores[campo] is None:
            continue
        fatores.append({
            'campo': campo,
            'rotulo': rotulo,
            'valor': indicadores[campo],
            'evidencia': f'{rotulo}: {indicadores[campo]}',
        })

    return {
        'ciclo_final': resultado.get('tipo'),
        'ciclo_modelo': resultado.get('tipo_modelo', resultado.get('tipo')),
        'confianca': resultado.get('confianca'),
        'confianca_ml': resultado.get('confianca_ml'),
        'probabilidades': resultado.get('probabilidades', {}),
        'decisao': decisao,
        'origem_decisao': origem,
        'regra_aplicada': resultado.get('regra_aplicada'),
        'fatores': fatores,
        'explicacoes': list(resultado.get('explicacao') or []),
        'dados_faltantes': list(resultado.get('dados_faltantes') or []),
        'revisao_humana': bool(resultado.get('revisao_humana')),
    }
