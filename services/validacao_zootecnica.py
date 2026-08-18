"""Alertas zootécnicos derivados da ficha, sem bloquear a análise."""
from __future__ import annotations

from services.base_reprodutiva import base_reprodutiva


def _numero(dados: dict, *nomes):
    for nome in nomes:
        valor = dados.get(nome)
        if valor not in (None, ''):
            try:
                return float(valor)
            except (TypeError, ValueError):
                return None
    return None


def _alerta(codigo, severidade, titulo, evidencia, impacto, acao):
    return {
        'codigo': codigo,
        'severidade': severidade,
        'titulo': titulo,
        'evidencia': evidencia,
        'impacto': impacto,
        'acao': acao,
    }


def analisar_validacoes_zootecnicas(
    valores: list, dados: dict | None = None, projecao: list | None = None,
) -> dict:
    dados = dados or {}
    v = [float(x or 0) for x in (valores or [])]
    total = sum(v)
    alertas = []
    nao_avaliadas = []

    bois_vendidos = _numero(dados, 'bois_vendidos')
    bezerros_vendidos = _numero(dados, 'bezerros_vendidos')
    if bois_vendidos is not None or bezerros_vendidos is not None:
        vendas = (bois_vendidos or 0) + (bezerros_vendidos or 0)
        if vendas > total:
            alertas.append(_alerta(
                'vendas_acima_estoque', 'erro',
                'Vendas acima do estoque informado',
                f'{vendas:.0f} vendas declaradas para {total:.0f} animais no estoque',
                'A receita e o fluxo de caixa podem estar superestimados.',
                'Confirmar vendas, compras e período da ficha.',
            ))
    else:
        nao_avaliadas.append('vendas_ausentes')

    natalidade = _numero(dados, 'taxa_natalidade_pct', 'natalidade_pct', 'taxa_natalidade')
    nascimentos = _numero(dados, 'nascimentos', 'nascimentos_ano')
    # Só quem já pariu entra nos nascimentos esperados. Somar as 25–36m aqui
    # inflava o esperado em ~40%, e como o alerta só dispara acima de 1,15× o
    # esperado, ele parava de pegar exatamente a declaração exagerada que
    # existe para pegar — o erro corria a favor de aprovar.
    matrizes = base_reprodutiva(v).matrizes
    if natalidade is not None and not 40 <= natalidade <= 95:
        alertas.append(_alerta(
            'natalidade_fora_faixa', 'alerta', 'Natalidade fora da faixa de análise',
            f'taxa informada: {natalidade:.1f}%',
            'Pode distorcer nascimentos, reposição e geração de caixa.',
            'Confirmar histórico reprodutivo e período de medição.',
        ))
    if nascimentos is not None and natalidade is not None:
        esperado = matrizes * natalidade / 100
        if nascimentos > esperado * 1.15:
            alertas.append(_alerta(
                'nascimentos_incompativeis', 'alerta',
                'Nascimentos incompatíveis com a base reprodutiva',
                f'{nascimentos:.0f} nascimentos contra cerca de {esperado:.0f} esperados',
                'A produção de bezerros pode estar superestimada.',
                'Revisar matrizes, natalidade e período dos nascimentos.',
            ))
    else:
        nao_avaliadas.append('nascimentos_ou_natalidade_ausentes')

    mortalidade = _numero(dados, 'mortalidade_pct', 'mortalidade')
    if mortalidade is None:
        nao_avaliadas.append('mortalidade_ausente')
    elif not 0 <= mortalidade <= 20:
        alertas.append(_alerta(
            'mortalidade_fora_faixa', 'alerta', 'Mortalidade fora da faixa de análise',
            f'mortalidade informada: {mortalidade:.1f}%',
            'Pode alterar o estoque projetado e a capacidade de pagamento.',
            'Confirmar mortes e período de referência.',
        ))

    compras = _numero(dados, 'compras_reposicao', 'compras', 'reposicao')
    if compras is None:
        nao_avaliadas.append('reposicao_ausente')
    elif compras < 0:
        alertas.append(_alerta(
            'reposicao_invalida', 'erro', 'Reposição negativa',
            f'valor informado: {compras:.0f} animais',
            'A manutenção do rebanho não pode ser calculada.',
            'Corrigir a quantidade de compras/reposição.',
        ))

    if projecao:
        ultimo = projecao[-1] or {}
        total_final = ultimo.get('total', ultimo.get('total_prox'))
        if total_final is None:
            nao_avaliadas.append('reconciliacao_estoque_ausente')
        else:
            entradas = compras or 0
            mortes = total * (mortalidade or 0) / 100 if mortalidade is not None else None
            if mortes is None:
                nao_avaliadas.append('reconciliacao_mortalidade_ausente')
            else:
                esperado_final = total + (nascimentos or 0) + entradas - (vendas or 0) - mortes
                if abs(float(total_final) - esperado_final) > max(5, total * 0.05):
                    alertas.append(_alerta(
                        'estoque_projetado_nao_fecha', 'alerta',
                        'Estoque projetado não fecha com as entradas e saídas',
                        f'projetado: {float(total_final):.0f}; reconciliado: {esperado_final:.0f}',
                        'O fluxo de animais e as receitas podem não representar o mesmo período.',
                        'Revisar nascimentos, compras, vendas e mortalidade.',
                    ))
    else:
        nao_avaliadas.append('reconciliacao_estoque_ausente')

    erros = sum(a['severidade'] == 'erro' for a in alertas)
    avisos = sum(a['severidade'] == 'alerta' for a in alertas)
    return {
        'alertas': alertas,
        'nao_avaliadas': nao_avaliadas,
        'resumo': {
            'erros': erros,
            'alertas': avisos,
            'ok': max(0, 5 - len(alertas)),
        },
        'score': round(max(0.0, 100.0 - erros * 25.0 - avisos * 10.0), 1),
    }
