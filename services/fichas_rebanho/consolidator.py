from __future__ import annotations

from services.faixa_0_12 import dividir_0_12


_VALOR_POR_CLASSIFICACAO = {
    'bezerra': 0,
    'bezerro': 1,
    'bezerra desmama': 4,
    'bezerro desmama': 5,
    'novilha': 6,
    'garrote': 7,
    'vaca': 8,
    'boi gordo': 9,
}

# A classificação sozinha não distingue as duas posições jovens: tanto
# '00 A 04 MESES' quanto '05 A 12 MESES' são classificados como 'Bezerra' no
# MAPEAMENTO, e ambas caíam na posição 0 — a divisão feita pelo parser era
# descartada aqui. Fichas de quatro faixas trazem '0 A 12 MESES' inteiro e
# precisam da divisão neste ponto. A estratificação desempata.
_POSICAO_JOVEM = {
    ('bezerra', '00 A 04 MESES'): 0,
    ('bezerra', '05 A 12 MESES'): 2,
    ('bezerro', '00 A 04 MESES'): 1,
    ('bezerro', '05 A 12 MESES'): 3,
}
_FAIXA_UNIFICADA = {
    'bezerra': (0, 2),
    'bezerro': (1, 3),
}


def consolidar_registros(registros: list[dict]) -> list[dict]:
    grupos = {}
    for registro in registros or []:
        if registro.get('status') != 'Distribuído':
            continue
        fazenda = registro.get('fazenda') or registro.get('codigo_propriedade') or 'Sem nome'
        chave = (fazenda, registro.get('municipio', ''))
        grupo = grupos.setdefault(chave, {
            'fazenda': fazenda,
            'municipio': registro.get('municipio', ''),
            'estado': registro.get('estado', ''),
            'origem': registro.get('origem', ''),
            'modelo': registro.get('modelo', ''),
            'valores': [0] * 10,
            'registros': [],
        })
        classificacao = str(registro.get('classificacao', '')).strip().lower()
        estratificacao = str(registro.get('estratificacao', '')).strip().upper()
        quantidade = registro.get('quantidade') or 0
        posicao = _POSICAO_JOVEM.get((classificacao, estratificacao))
        if posicao is None and classificacao in _FAIXA_UNIFICADA:
            nova, velha = _FAIXA_UNIFICADA[classificacao]
            qtd_nova, qtd_velha = dividir_0_12(quantidade)
            grupo['valores'][nova] += qtd_nova
            grupo['valores'][velha] += qtd_velha
        else:
            if posicao is None:
                posicao = _VALOR_POR_CLASSIFICACAO.get(classificacao)
            if posicao is not None:
                grupo['valores'][posicao] += quantidade
        grupo['registros'].append(registro)

    for grupo in grupos.values():
        grupo['total'] = sum(grupo['valores'])
    return list(grupos.values())
