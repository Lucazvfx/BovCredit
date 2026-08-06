from __future__ import annotations


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
            'valores': [0] * 10,
            'registros': [],
        })
        posicao = _VALOR_POR_CLASSIFICACAO.get(
            str(registro.get('classificacao', '')).strip().lower())
        if posicao is not None:
            grupo['valores'][posicao] += registro.get('quantidade') or 0
        grupo['registros'].append(registro)

    for grupo in grupos.values():
        grupo['total'] = sum(grupo['valores'])
    return list(grupos.values())
