"""Receita e custo da lavoura perene, ano a ano.

Reaproveita `calculate_economic_result` do motor econômico sem alterá-lo: ele
lê chaves genéricas (`receita_total`, `custo_operacional`…) e não sabe se o
que produziu o número foi boi ou café.

O QUE MUDA EM RELAÇÃO À PECUÁRIA é o custo. Rebanho custa por cabeça; lavoura
perene custa POR HECTARE E POR ESTÁGIO — e o estágio que decide o crédito é a
formação, que consome caixa por anos sem devolver uma saca. É esse buraco que
o financiamento de formação de lavoura existe para cobrir, e um custo médio
por hectare o esconderia.

Preço e custo ausentes NÃO são estimados, pela mesma razão da curva: número
inventado aqui sai do outro lado como capacidade de pagamento.
"""
from __future__ import annotations

from typing import Any, Mapping

from services.economic_engine.margins import calculate_economic_result

from .projector import FORMACAO, PRODUCAO, REFORMA


def _float(valor) -> float | None:
    if valor is None or isinstance(valor, bool):
        return None
    try:
        return float(valor)
    except (TypeError, ValueError):
        return None


def _normalizar(mapa: Mapping[str, Any] | None) -> dict[str, Any]:
    return {str(k).strip().upper(): v for k, v in (mapa or {}).items()}


def calcular_receita(linha_do_ano: dict, precos: Mapping[str, Any]) -> dict[str, Any]:
    """Receita do ano: produção de cada cultura pelo preço declarado dela.

    `precos` é R$ por unidade da curva — saca de 60 kg no café, tonelada na
    cana. A unidade vem da curva, não daqui.
    """
    precos = _normalizar(precos)
    avisos: list[str] = []
    receita_por_cultura: dict[str, float] = {}
    sem_preco: list[str] = []
    total = 0.0

    for cultura, producao in (linha_do_ano.get('producao_por_cultura') or {}).items():
        chave = str(cultura).strip().upper()
        preco = _float(precos.get(chave))
        if preco is None:
            if float(producao or 0) > 0:
                sem_preco.append(chave)
            continue
        receita = float(producao or 0) * preco
        receita_por_cultura[chave] = round(receita, 2)
        total += receita

    if sem_preco:
        avisos.append(
            'Sem preço declarado para: ' + ', '.join(sorted(set(sem_preco)))
            + '. A produção destas culturas não virou receita.')

    return {
        'valid': not sem_preco,
        'receita_total': round(total, 2),
        'receita_por_cultura': receita_por_cultura,
        'sem_preco': tuple(sorted(set(sem_preco))),
        'warnings': avisos,
    }


def calcular_custo(linha_do_ano: dict, custos: Mapping[str, Any]) -> dict[str, Any]:
    """Custo do ano, hectare a hectare, pelo estágio de cada talhão.

    `custos` por cultura aceita:
        {'formacao': R$/ha, 'producao': R$/ha, 'reforma': R$/ha,
         'por_unidade': R$/saca ou R$/tonelada colhida}

    `por_unidade` é opcional e existe porque colheita de perene é custo que
    acompanha a produção, não a área: um cafezal de carga baixa colhe menos e
    gasta menos para colher.
    """
    custos = _normalizar(custos)
    avisos: list[str] = []
    sem_custo: list[str] = []
    por_estagio = {FORMACAO: 0.0, PRODUCAO: 0.0, REFORMA: 0.0}
    custo_colheita = 0.0

    for talhao in linha_do_ano.get('talhoes') or []:
        estagio = talhao.get('estagio')
        if estagio not in por_estagio:
            continue
        cultura = str(talhao.get('cultura', '')).strip().upper()
        tabela = _normalizar(custos.get(cultura))
        custo_ha = _float(tabela.get(estagio.upper()))
        if custo_ha is None:
            sem_custo.append(f'{cultura}/{estagio}')
            continue
        por_estagio[estagio] += float(talhao.get('area_ha') or 0) * custo_ha

        por_unidade = _float(tabela.get('POR_UNIDADE'))
        if por_unidade is not None:
            custo_colheita += float(talhao.get('producao') or 0) * por_unidade

    if sem_custo:
        avisos.append(
            'Sem custo por hectare declarado para: '
            + ', '.join(sorted(set(sem_custo)))
            + '. Estes talhões entraram com custo zero.')

    custo_operacional = sum(por_estagio.values()) + custo_colheita
    return {
        'valid': not sem_custo,
        # Formação não é manutenção da lavoura em produção: é o investimento
        # que ainda não devolve nada. Separado para o parecer poder dizer isso.
        'custo_manutencao': round(por_estagio[PRODUCAO] + custo_colheita, 2),
        'custo_investimento': round(por_estagio[FORMACAO] + por_estagio[REFORMA], 2),
        'custo_reposicao': 0.0,
        'custo_operacional': round(custo_operacional, 2),
        'custo_por_estagio': {k: round(v, 2) for k, v in por_estagio.items()},
        'custo_colheita': round(custo_colheita, 2),
        'sem_custo': tuple(sorted(set(sem_custo))),
        'warnings': avisos,
    }


def resultado_economico(
    projecao: dict,
    precos: Mapping[str, Any],
    custos: Mapping[str, Any],
) -> dict[str, Any]:
    """Encadeia produção → receita → custo → resultado, ano a ano.

    Devolve `anos` com receita/custo/resultado — a mesma forma que a projeção
    pecuária entrega — para que fluxo mensal, DSCR e stress consumam sem saber
    de que lavoura vieram.
    """
    anos: list[dict[str, Any]] = []
    avisos = list(projecao.get('avisos') or [])
    valido = bool(projecao.get('valido'))

    for linha in projecao.get('anos') or []:
        receita = calcular_receita(linha, precos)
        custo = calcular_custo(linha, custos)
        economico = calculate_economic_result(receita, custo)
        valido = valido and receita['valid'] and custo['valid']

        anos.append({
            'ano': linha['ano'],
            'ano_calendario': linha['ano_calendario'],
            'producao_total': linha['producao_total'],
            'producao_por_cultura': linha['producao_por_cultura'],
            'area_produtiva_ha': linha['area_produtiva_ha'],
            'area_em_formacao_ha': linha['area_em_formacao_ha'],
            'receita': receita['receita_total'],
            'receita_por_cultura': receita['receita_por_cultura'],
            'custo': custo['custo_operacional'],
            'custo_por_estagio': custo['custo_por_estagio'],
            'resultado': round(
                float(economico.get('resultado_operacional') or 0.0), 2),
            'avisos': receita['warnings'] + custo['warnings'],
        })

    negativos = [a['ano'] for a in anos if a['resultado'] < 0]
    if negativos:
        avisos.append(
            'Resultado operacional negativo no(s) ano(s) '
            + ', '.join(str(n) for n in negativos)
            + '. Em lavoura perene isso é esperado durante a formação — e é '
            'exatamente o período que precisa de carência.')

    pior = min(anos, key=lambda a: a['resultado']) if anos else None
    return {
        'valido': valido,
        'anos': anos,
        'acumulado': {
            'receita': round(sum(a['receita'] for a in anos), 2),
            'custo': round(sum(a['custo'] for a in anos), 2),
            'resultado': round(sum(a['resultado'] for a in anos), 2),
        },
        'ano_pior_resultado': pior['ano'] if pior else None,
        'anos_negativos': tuple(negativos),
        'avisos': avisos,
    }
