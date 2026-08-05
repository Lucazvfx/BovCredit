from __future__ import annotations

from collections import defaultdict


def validar_registros(registros: list[dict], total_documento=None) -> dict:
    itens = [dict(item) for item in (registros or [])]
    erros = []
    avisos = []
    vistos = defaultdict(list)

    for index, item in enumerate(itens):
        status = item.get('status') or 'Revisão'
        try:
            quantidade = float(item.get('quantidade'))
            if quantidade.is_integer():
                quantidade = int(quantidade)
        except (TypeError, ValueError):
            quantidade = None
        item['quantidade'] = quantidade

        if quantidade is None:
            item['status'] = 'Revisão'
            item['motivo'] = 'Quantidade ausente ou não numérica.'
            erros.append(f'Registro {index + 1}: quantidade inválida.')
        elif quantidade < 0:
            item['status'] = 'Revisão'
            item['motivo'] = 'Quantidade negativa.'
            erros.append(f'Registro {index + 1}: quantidade negativa.')
        elif status != 'Distribuído':
            item['status'] = 'Revisão'
            erros.append(
                f'Registro {index + 1}: {item.get("motivo") or "não classificado"}.')

        chave_dup = (
            item.get('arquivo', ''),
            item.get('numero_ficha', ''),
            item.get('chave', ''),
        )
        vistos[chave_dup].append(index)

    for chave, indices in vistos.items():
        if chave[2] and len(indices) > 1:
            avisos.append(
                f'Registros potencialmente duplicados nas linhas '
                f'{", ".join(str(i + 1) for i in indices)}.')
            for index in indices:
                itens[index]['status'] = 'Revisão'
                itens[index]['motivo'] = 'Possível ficha/linha duplicada.'

    total_extraido = sum(
        item['quantidade'] for item in itens
        if isinstance(item.get('quantidade'), (int, float))
        and item.get('quantidade') >= 0
    )
    if total_documento is not None:
        try:
            total_informado = float(total_documento)
            if total_informado != total_extraido:
                avisos.append(
                    f'Total informado ({total_informado:g}) difere do '
                    f'total extraído ({total_extraido:g}).')
        except (TypeError, ValueError):
            avisos.append('Total informado no documento não é numérico.')

    return {
        'valido': not erros and not avisos,
        'registros': itens,
        'erros': erros,
        'avisos': avisos,
        'total_extraido': total_extraido,
    }
