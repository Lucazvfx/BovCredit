"""Cálculos financeiros e atuariais de garantias agropecuárias, deságios e LTV.
"""
from __future__ import annotations

from typing import Any

from .models import (
    DESAGIOS_PADRAO_GARANTIA,
    ClassificacaoGarantia,
    ItemGarantia,
    MatrizGarantiasConsolidada,
    TipoGarantia,
    TipoGravame,
)


def calcular_item_garantia(
    tipo: TipoGarantia | str,
    gravame: TipoGravame | str,
    descricao: str,
    identificador_registro: str,
    valor_mercado_bruto: float,
    dividas_previas_averbadas: float = 0.0,
    area_ha: float = 0.0,
    desagio_customizado_pct: float | None = None,
    observacoes: str = "",
    id_garantia: str = "",
) -> ItemGarantia:
    """Calcula a liquidação forçada de um item individual de garantia."""
    if isinstance(tipo, str):
        tipo = TipoGarantia(tipo.upper())
    if isinstance(gravame, str):
        gravame = TipoGravame(gravame.upper())

    vm = max(0.0, float(valor_mercado_bruto or 0.0))
    div_prev = max(0.0, float(dividas_previas_averbadas or 0.0))

    # Base líquida antes do deságio (abate dívidas prioritárias já registradas na matrícula)
    base_disponivel = max(0.0, vm - div_prev)

    if desagio_customizado_pct is not None and desagio_customizado_pct >= 0:
        desagio = float(desagio_customizado_pct)
        if desagio > 1.0:
            desagio = desagio / 100.0
    else:
        desagio = DESAGIOS_PADRAO_GARANTIA.get(gravame, 0.25)

    valor_liquidacao = base_disponivel * (1.0 - desagio)

    return ItemGarantia(
        id_garantia=id_garantia or f"GAR-{tipo.value[:3]}-{int(vm)}",
        tipo=tipo,
        gravame=gravame,
        descricao=descricao or f"{tipo.value} - {gravame.value}",
        identificador_registro=identificador_registro or "Registro Não Informado",
        area_ha=round(float(area_ha or 0.0), 2),
        valor_mercado_bruto=round(vm, 2),
        dividas_previas_averbadas=round(div_prev, 2),
        desagio_aplicado_pct=round(desagio * 100.0, 2),
        valor_liquidacao_forcada=round(valor_liquidacao, 2),
        observacoes=observacoes,
    )


def consolidar_matriz_garantias(
    itens: list[ItemGarantia],
    credito_solicitado: float,
    cobertura_minima_exigida_pct: float = 130.0,
) -> MatrizGarantiasConsolidada:
    """Consolida todas as garantias ofertadas e afere o LTV e suficiência de cobertura."""
    cred = max(0.0, float(credito_solicitado or 0.0))
    vm_total = sum(i.valor_mercado_bruto for i in itens)
    vl_total = sum(i.valor_liquidacao_forcada for i in itens)

    if vl_total > 0:
        ltv = round((cred / vl_total) * 100.0, 4)
    else:
        ltv = 999.0 if cred > 0 else 0.0

    if cred > 0:
        icg = round((vl_total / cred) * 100.0, 4)
    else:
        icg = 999.0 if vl_total > 0 else 0.0

    garantia_minima_necessaria = cred * (cobertura_minima_exigida_pct / 100.0)
    sobra_ou_deficit = vl_total - garantia_minima_necessaria

    if ltv <= 55.0:
        classificacao = ClassificacaoGarantia.EXCELENTE
        suficiente = True
        rec = (
            f"PACOTE DE GARANTIAS EXCELENTE (LTV {ltv:.1f}% | Cobertura {icg:.0f}%). "
            "Garantias líquidas cobrem a operação com margem robusta contra oscilações de mercado e quebra de safra."
        )
    elif ltv <= 75.0:
        classificacao = ClassificacaoGarantia.ADEQUADA
        suficiente = True
        rec = (
            f"PACOTE DE GARANTIAS ADEQUADO (LTV {ltv:.1f}% | Cobertura {icg:.0f}%). "
            "Atende às diretrizes de crédito B2B. Recomenda-se registrar gravame em 1º grau no CRI ou B3/CERC."
        )
    elif ltv <= 90.0:
        classificacao = ClassificacaoGarantia.AJUSTADA
        suficiente = False
        rec = (
            f"GARANTIAS EM NÍVEL AJUSTADO (LTV {ltv:.1f}% | Cobertura {icg:.0f}%). "
            f"Abaixo da cobertura recomendada de {cobertura_minima_exigida_pct:.0f}%. Exige reforço de avalista ou contratação de seguro agrícola com apólice endossada."
        )
    else:
        classificacao = ClassificacaoGarantia.INSUFICIENTE
        suficiente = False
        rec = (
            f"GARANTIAS INSUFICIENTES (LTV {ltv:.1f}% | Cobertura {icg:.0f}%). "
            "Risco severo de perda em caso de inadimplência (LGD elevado). Operação não recomendada sem aporte adicional de bens imóveis ou penhor complementar."
        )

    return MatrizGarantiasConsolidada(
        itens=itens,
        credito_solicitado=cred,
        valor_mercado_total=vm_total,
        valor_liquidacao_total=vl_total,
        ltv_pct=ltv,
        indice_cobertura_pct=icg,
        sobra_ou_deficit_garantia=sobra_ou_deficit,
        classificacao_risco=classificacao,
        suficiente_para_aprovacao=suficiente,
        recomendacao_comite=rec,
    )
