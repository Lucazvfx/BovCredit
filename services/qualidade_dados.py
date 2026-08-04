"""Qualidade e origem dos dados usados na análise rural.

Uma ficha sanitária normalmente informa contagens por sexo/faixa etária,
mas não informa peso, GMD ou índices reprodutivos. Este módulo evita que
estimativas sejam apresentadas como medições.
"""
from __future__ import annotations


_CAMPOS_ZOOTECNICOS = {
    'peso_medio_kg': 'peso médio por categoria',
    'peso_desmama_kg': 'peso à desmama',
    'ganho_peso_kg_dia': 'ganho médio diário',
    'taxa_prenhez_pct': 'taxa de prenhez',
    'natalidade_pct': 'taxa de natalidade',
    'desmama_pct': 'taxa de desmama',
    'mortalidade_pct': 'mortalidade',
    'area_pasto_ha': 'área de pastagem',
}


def analisar_qualidade_dados(valores: list, dados: dict | None = None) -> dict:
    """Classifica a evidência disponível sem inventar índices produtivos."""
    dados = dados or {}
    campos_informados = []
    campos_ausentes = []
    for campo, rotulo in _CAMPOS_ZOOTECNICOS.items():
        valor = dados.get(campo)
        if valor not in (None, ''):
            try:
                if float(valor) >= 0:
                    campos_informados.append({'campo': campo, 'descricao': rotulo})
                    continue
            except (TypeError, ValueError):
                pass
        campos_ausentes.append({'campo': campo, 'descricao': rotulo})

    total = sum(float(x or 0) for x in (valores or []))
    # A ficha fornece estrutura do rebanho; índices produtivos continuam
    # estimados enquanto não houver medições ou histórico operacional.
    observados = ['contagem por sexo e faixa etária'] if total > 0 else []
    estimaveis = [x['descricao'] for x in campos_ausentes]
    n = len(campos_informados)
    if n >= 5:
        confianca = 'alta'
    elif n >= 2:
        confianca = 'media'
    else:
        confianca = 'media-baixa'

    avisos = []
    if not campos_informados:
        avisos.append('A ficha contém apenas a composição do rebanho; os índices produtivos serão estimados.')
    if 'peso_medio_kg' in {x['campo'] for x in campos_ausentes}:
        avisos.append('Sem peso informado, valor da garantia e arrobas são estimados por categoria.')
    if any(x['campo'] in {y['campo'] for y in campos_ausentes}
           for x in ({'campo': 'taxa_prenhez_pct'}, {'campo': 'natalidade_pct'}, {'campo': 'desmama_pct'})):
        avisos.append('Sem histórico reprodutivo, natalidade e desmama não são índices medidos da fazenda.')

    return {
        'nivel_confianca': confianca,
        'origem_principal': 'ficha_sanitaria' if total > 0 else 'incompleta',
        'observados': observados,
        'informados': campos_informados,
        'estimados': estimaveis,
        'ausentes': campos_ausentes,
        'avisos': avisos,
        'pode_calcular_indices_estruturais': bool(total > 0),
        'pode_calcular_indices_produtivos_reais': n >= 5,
    }

