"""Projeção plurianual da lavoura perene: soma dos talhões, ano a ano.

O que este módulo entrega é QUANTIDADE — sacas, toneladas — por ano. Preço e
custo entram na fase seguinte, no motor econômico que já existe.

A saída carrega `ano_menor_producao` porque é ele que decide o parecer. Numa
perene o aperto raramente cai no ano 1: o café alterna carga e a soqueira da
cana decai a cada corte. O motor de crédito já avalia todos os anos do prazo
(`avaliar_capacidade_no_prazo`); esta projeção é o que alimenta esses anos.
"""
from __future__ import annotations

from typing import Any, Mapping

from .models import ALTA, BAIXA, CurvaProdutividade, PerennialState, Talhao

FORMACAO = 'formacao'
PRODUCAO = 'producao'
REFORMA = 'reforma'
NAO_PLANTADO = 'nao_plantado'


def _idade_no_ciclo(talhao: Talhao, ano_calendario: int,
                    curva: CurvaProdutividade) -> tuple[int, int]:
    """Idade dentro do ciclo atual, e quantas reformas já ocorreram.

    Sem `ciclo_anos` o talhão envelhece indefinidamente. Com ele, passado o
    ciclo, o talhão volta à idade 1 — canavial reformado, cafezal recepado — e
    recomeça a curva.
    """
    idade = talhao.idade_em(ano_calendario)
    if idade <= 0 or not curva.ciclo_anos:
        return idade, 0
    ciclo = int(curva.ciclo_anos)
    reformas = (idade - 1) // ciclo
    return ((idade - 1) % ciclo) + 1, reformas


def _fase_bienal(talhao: Talhao, ano_calendario: int, ano_base: int) -> str | None:
    """Alterna a carga a cada ano a partir da fase declarada na safra base."""
    if not talhao.fase_bienal:
        return None
    distancia = ano_calendario - int(ano_base)
    if distancia % 2 == 0:
        return talhao.fase_bienal
    return BAIXA if talhao.fase_bienal == ALTA else ALTA


def _estagio(idade: int, fator: float, reformou_neste_ano: bool) -> str:
    if idade <= 0:
        return NAO_PLANTADO
    if reformou_neste_ano:
        return REFORMA
    return PRODUCAO if fator > 0 else FORMACAO


def _producao_do_talhao(talhao: Talhao, ano_calendario: int, ano_base: int,
                        curva: CurvaProdutividade) -> dict[str, Any]:
    idade, reformas = _idade_no_ciclo(talhao, ano_calendario, curva)
    idade_anterior, reformas_anteriores = _idade_no_ciclo(
        talhao, ano_calendario - 1, curva)
    fator = curva.fator(idade)

    fase = _fase_bienal(talhao, ano_calendario, ano_base)
    fator_bienal = 1.0
    if fase and curva.bienalidade:
        fator_bienal = 1 + curva.bienalidade if fase == ALTA else 1 - curva.bienalidade

    producao = float(talhao.area_ha) * float(curva.produtividade_plena) * fator * fator_bienal
    return {
        'talhao': talhao.identificacao or talhao.cultura,
        'cultura': talhao.cultura,
        'area_ha': round(float(talhao.area_ha), 4),
        'idade': idade,
        'estagio': _estagio(idade, fator, reformas > reformas_anteriores),
        'fase_bienal': fase,
        'fator_idade': round(fator, 6),
        'fator_bienal': round(fator_bienal, 6),
        'producao': round(producao, 4),
    }


def project_perennial_production(
    state: PerennialState,
    curvas: Mapping[str, CurvaProdutividade],
    years: int = 6,
) -> dict[str, Any]:
    """Projeta a produção da lavoura por `years` anos a partir da safra base.

    Cultura sem curva declarada NÃO é estimada: os talhões dela ficam de fora
    da produção, entram em `sem_curva` e a projeção volta com `valido=False`.
    Chutar a curva aqui produziria um número com cara de cálculo.
    """
    if not isinstance(state, PerennialState):
        raise TypeError('state deve ser um PerennialState')
    anos = int(years)
    if anos <= 0:
        raise ValueError('years deve ser positivo')

    curvas = {str(k).strip().upper(): v for k, v in (curvas or {}).items()}
    sem_curva = tuple(sorted({
        t.cultura for t in state.talhoes
        if str(t.cultura).strip().upper() not in curvas
    }))
    projetaveis = [t for t in state.talhoes
                   if str(t.cultura).strip().upper() in curvas]

    linhas = []
    for indice in range(anos):
        ano_calendario = int(state.ano_base) + indice
        talhoes = [
            _producao_do_talhao(t, ano_calendario, state.ano_base,
                                curvas[str(t.cultura).strip().upper()])
            for t in projetaveis
        ]
        por_cultura: dict[str, float] = {}
        for item in talhoes:
            por_cultura[item['cultura']] = round(
                por_cultura.get(item['cultura'], 0.0) + item['producao'], 4)

        linhas.append({
            'ano': indice + 1,
            'ano_calendario': ano_calendario,
            'producao_total': round(sum(i['producao'] for i in talhoes), 4),
            'producao_por_cultura': por_cultura,
            'area_produtiva_ha': round(
                sum(i['area_ha'] for i in talhoes if i['estagio'] == PRODUCAO), 4),
            'area_em_formacao_ha': round(
                sum(i['area_ha'] for i in talhoes
                    if i['estagio'] in (FORMACAO, REFORMA)), 4),
            'talhoes': talhoes,
        })

    avisos = []
    if sem_curva:
        avisos.append(
            'Sem curva de produtividade declarada para: '
            f'{", ".join(sem_curva)}. Estes talhões ficaram fora da projeção.')
    if state.fases_alinhadas() and any(c.bienalidade for c in curvas.values()):
        avisos.append(
            'Todos os talhões estão na mesma fase de carga: a lavoura inteira '
            'oscila junto, e o ano de carga baixa aperta o caixa de uma vez.')

    # O ano de reforma entra na conta. Ele é o PIOR ano do contrato — a lavoura
    # não produz —, e escondê-lo devolveria um ano crítico confortável para uma
    # operação que não tem caixa naquele ano.
    menor = min(linhas, key=lambda l: l['producao_total'])
    if menor['producao_total'] <= 0:
        avisos.append(
            f'No ano {menor["ano"]} ({menor["ano_calendario"]}) a lavoura não '
            'produz: os talhões estão em formação ou reforma. Operação com '
            'prazo que atravessa esse ano precisa de caixa de outra fonte.')

    return {
        'valido': not sem_curva,
        'ano_base': int(state.ano_base),
        'culturas': state.culturas,
        'area_total_ha': state.area_total_ha,
        'unidades': {c: curvas[c].unidade for c in curvas},
        'anos': linhas,
        'producao_acumulada': round(sum(l['producao_total'] for l in linhas), 4),
        'ano_menor_producao': menor['ano'],
        'producao_no_ano_menor': menor['producao_total'],
        'sem_curva': sem_curva,
        'avisos': avisos,
    }
