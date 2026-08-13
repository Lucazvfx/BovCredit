"""Motor de retenção bovina — os três limites.

Para cada animal retido há um custo de oportunidade (venda adiada) e um custo
de permanência. A decisão prudente usa o menor entre:

    1. Limite zootécnico  — reposição necessária de matrizes
    2. Limite de pastagem — UA ainda disponíveis na área informada
    3. Limite financeiro  — caixa livre depois do serviço da dívida × ICSD-alvo

Também calcula a retenção por fase (bezerras, machos, novilhas→engorda) e os
percentuais comparáveis com os benchmarks do documento de treinamento.
"""
from __future__ import annotations

_UA_KG = 450.0  # Embrapa: 1 UA = 450 kg de peso vivo


def _safe(v, default=0.0):
    try:
        return float(v or default)
    except (TypeError, ValueError):
        return default


# ── Limite zootécnico ────────────────────────────────────────────────────────

def limite_zootecnico(
    matrizes: float,
    taxa_descarte_pct: float = 15.0,
    aproveitamento_pct: float = 90.0,
    expansao_cabecas: float = 0.0,
) -> dict:
    """Quantidade mínima de bezerras a reter para repor e/ou expandir o plantel.

    Args:
        matrizes: Número de matrizes ativas.
        taxa_descarte_pct: % de matrizes descartadas/perdidas por ano.
        aproveitamento_pct: % de bezerras retidas que efetivamente entram como
            matriz (sobrevivência, aptidão reprodutiva, descarte pré-entrada).
        expansao_cabecas: Aumento desejado de matrizes no período.
    """
    matrizes = _safe(matrizes)
    descarte = _safe(taxa_descarte_pct) / 100
    aprov = max(_safe(aproveitamento_pct, 90.0) / 100, 0.01)
    expans = _safe(expansao_cabecas)

    reposicao_nec = matrizes * descarte
    bezerras_necessarias = (reposicao_nec + expans) / aprov

    return {
        'reposicao_necessaria': round(reposicao_nec),
        'bezerras_a_reter': round(bezerras_necessarias),
        'taxa_descarte_pct': round(descarte * 100, 1),
        'aproveitamento_pct': round(aprov * 100, 1),
        'expansao_cabecas': round(expans),
    }


# ── Limite de pastagem ───────────────────────────────────────────────────────

def limite_pastagem(
    area_ha: float,
    ua_atual: float,
    peso_medio_bezerra_kg: float = 170.0,
    lotacao_segura_ua_ha: float = 1.0,
) -> dict:
    """Quantidade máxima de animais que a pastagem ainda suporta.

    Args:
        area_ha: Área efetiva de pastagem (ha).
        ua_atual: UA do rebanho atual (antes da retenção).
        peso_medio_bezerra_kg: Peso médio dos animais a reter.
        lotacao_segura_ua_ha: Capacidade segura da pastagem em UA/ha.
    """
    area = _safe(area_ha)
    ua_at = _safe(ua_atual)
    peso = max(_safe(peso_medio_bezerra_kg, 170.0), 1.0)
    lot = max(_safe(lotacao_segura_ua_ha, 1.0), 0.01)

    if area <= 0:
        return {
            'area_ha': 0.0,
            'ua_atual': round(ua_at, 1),
            'ua_capacidade': None,
            'ua_disponivel': None,
            'animais_maximos': None,
            'imperativo': 'Área de pastagem não informada — limite de pastagem incalculável.',
        }

    ua_cap = area * lot
    ua_disp = max(ua_cap - ua_at, 0.0)
    ua_por_animal = peso / _UA_KG
    animais_max = int(ua_disp / ua_por_animal) if ua_por_animal > 0 else 0

    return {
        'area_ha': round(area, 1),
        'ua_atual': round(ua_at, 1),
        'ua_capacidade': round(ua_cap, 1),
        'ua_disponivel': round(ua_disp, 1),
        'animais_maximos': animais_max,
        'lotacao_segura_ua_ha': round(lot, 2),
        'imperativo': None,
    }


# ── Limite financeiro ────────────────────────────────────────────────────────

def limite_financeiro(
    fluxo_antes_retencao: float,
    servico_divida_anual: float,
    preco_venda_bezerra: float,
    custo_mensal_por_animal: float,
    meses_adicionais: float = 12.0,
    icsd_alvo: float = 1.50,
    reserva_minima: float = 0.0,
) -> dict:
    """Quantidade máxima de animais que o caixa suporta reter.

    Impacto de caixa por animal retido:
        receita adiada   = preco_venda_bezerra
        custo adicional  = custo_mensal × meses
        impacto total    = receita_adiada + custo_adicional

    Orçamento disponível para retenção:
        caixa_min        = servico_divida_anual × icsd_alvo
        orçamento        = fluxo − caixa_min − reserva
        animais_maximos  = orçamento ÷ impacto_por_animal
    """
    fluxo = _safe(fluxo_antes_retencao)
    servico = _safe(servico_divida_anual)
    preco = _safe(preco_venda_bezerra)
    custo_m = _safe(custo_mensal_por_animal)
    meses = max(_safe(meses_adicionais, 12.0), 0.0)
    icsd = max(_safe(icsd_alvo, 1.50), 1.0)
    reserva = _safe(reserva_minima)

    caixa_min = servico * icsd
    orcamento = fluxo - caixa_min - reserva
    impacto_por_animal = preco + custo_m * meses

    if impacto_por_animal <= 0:
        animais_max = None
        imperativo = 'Preço de venda e custo por animal não informados — limite financeiro incalculável.'
    elif orcamento <= 0:
        animais_max = 0
        imperativo = 'Sem espaço financeiro: fluxo de caixa insuficiente para cobrir dívida e ainda reter animais.'
    else:
        animais_max = int(orcamento / impacto_por_animal)
        imperativo = None

    return {
        'fluxo_antes_retencao': round(fluxo, 2),
        'caixa_minimo_divida': round(caixa_min, 2),
        'orcamento_retencao': round(orcamento, 2),
        'impacto_por_animal': round(impacto_por_animal, 2),
        'animais_maximos': animais_max,
        'icsd_alvo': icsd,
        'imperativo': imperativo,
    }


# ── Motor consolidado ────────────────────────────────────────────────────────

def calcular_retencao(
    *,
    # Rebanho
    matrizes: float = 0.0,
    bezerras_desmamadas: float = 0.0,
    machos_desmamados: float = 0.0,
    # Zootécnico
    taxa_descarte_pct: float = 15.0,
    aproveitamento_pct: float = 90.0,
    expansao_cabecas: float = 0.0,
    # Pastagem
    area_ha: float = 0.0,
    ua_atual: float = 0.0,
    peso_medio_bezerra_kg: float = 170.0,
    lotacao_segura_ua_ha: float = 1.0,
    # Financeiro
    fluxo_antes_retencao: float = 0.0,
    servico_divida_anual: float = 0.0,
    preco_venda_bezerra: float = 0.0,
    custo_mensal_por_animal: float = 0.0,
    meses_adicionais: float = 12.0,
    icsd_alvo: float = 1.50,
    reserva_minima: float = 0.0,
    # Retenção informada (para calcular percentuais)
    bezerras_retidas: float = 0.0,
    machos_retidos: float = 0.0,
) -> dict:
    """Motor consolidado: calcula os 3 limites e a recomendação final."""

    zoo = limite_zootecnico(matrizes, taxa_descarte_pct, aproveitamento_pct, expansao_cabecas)
    past = limite_pastagem(area_ha, ua_atual, peso_medio_bezerra_kg, lotacao_segura_ua_ha)
    fin = limite_financeiro(
        fluxo_antes_retencao, servico_divida_anual,
        preco_venda_bezerra, custo_mensal_por_animal,
        meses_adicionais, icsd_alvo, reserva_minima,
    )

    # Limite prudente = menor entre os calculáveis
    candidatos = {
        'zootecnico': zoo['bezerras_a_reter'],
        'pastagem': past['animais_maximos'],
        'financeiro': fin['animais_maximos'],
    }
    calculaveis = {k: v for k, v in candidatos.items() if v is not None}
    if calculaveis:
        fator_limitante = min(calculaveis, key=calculaveis.get)
        retencao_prudente = calculaveis[fator_limitante]
    else:
        fator_limitante = None
        retencao_prudente = None

    # Percentuais da retenção informada vs referências
    total_desm = _safe(bezerras_desmamadas) + _safe(machos_desmamados)
    ret_total = _safe(bezerras_retidas) + _safe(machos_retidos)

    fases = {}
    if _safe(bezerras_desmamadas) > 0:
        fases['retencao_bezerras_pct'] = round(_safe(bezerras_retidas) / _safe(bezerras_desmamadas) * 100, 1)
    if total_desm > 0:
        fases['retencao_total_desmama_pct'] = round(ret_total / total_desm * 100, 1)
    if _safe(matrizes) > 0:
        fases['reposicao_equivalente_matrizes_pct'] = round(_safe(bezerras_retidas) / _safe(matrizes) * 100, 1)

    return {
        'limite_zootecnico': zoo,
        'limite_pastagem': past,
        'limite_financeiro': fin,
        'retencao_prudente': retencao_prudente,
        'fator_limitante': fator_limitante,
        'fases': fases,
        'alertas': _alertas(zoo, past, fin, bezerras_retidas, retencao_prudente, area_ha),
    }


def _alertas(zoo, past, fin, bezerras_retidas, retencao_prudente, area_ha):
    out = []
    if _safe(area_ha) == 0:
        out.append({
            'nivel': 'impeditivo',
            'codigo': 'area_zerada',
            'mensagem': 'Área de pastagem = 0 ha. Impossível verificar se o rebanho atual e a retenção planejada cabem na propriedade.',
        })
    if retencao_prudente is not None and _safe(bezerras_retidas) > retencao_prudente:
        out.append({
            'nivel': 'alerta',
            'codigo': 'retencao_acima_do_limite',
            'mensagem': f'Retenção informada ({_safe(bezerras_retidas):.0f}) excede o limite prudente ({retencao_prudente:.0f}). Revisar pastagem ou caixa.',
        })
    if fin['animais_maximos'] == 0 and fin['orcamento_retencao'] < 0:
        out.append({
            'nivel': 'impeditivo',
            'codigo': 'sem_caixa_retencao',
            'mensagem': 'Fluxo de caixa insuficiente para reter animais sem comprometer o serviço da dívida.',
        })
    return out
