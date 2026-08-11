from __future__ import annotations

from typing import Any

from services.engine.contracts import HerdState
from services.parametros_zootecnicos import PESO_BOI_ARR, TROCA_ARROBAS_BOI_MAGRO

from .projector import _coerce_bool, _coerce_float, _coerce_int, finalize_projection


def project_engorda(state: HerdState, parameters: dict, years: int = 5) -> dict[str, Any]:
    va = [float(value) for value in state.values]
    total_ini = float(sum(va))
    years_value = _coerce_int(years, default=5)
    params = parameters or {}

    mort_pct = _coerce_float(params.get("mort_pct"), default=3.0)
    preco_arroba = _coerce_float(params.get("preco_arroba"), default=320.0)
    peso_entrada_kg = _coerce_float(params.get("peso_entrada_kg"), default=405.0)
    peso_saida_kg = _coerce_float(params.get("peso_saida_kg"), default=520.0)
    rendimento_carcaca = _coerce_float(params.get("rendimento_carcaca"), default=52.0)
    custo_arroba = _coerce_float(
        params.get("custo_arroba_engorda", params.get("custo_arroba")),
        default=57.0,
    )
    dias_engorda = params.get("dias_engorda")
    ganho_peso_kg_dia = params.get("ganho_peso_kg_dia")
    nat_mod = _coerce_float(params.get("nat_mod"), default=1.0)
    reposicao_precificada = _coerce_bool(params.get("reposicao_precificada"), default=True)

    if dias_engorda is None:
        _gmd = max(_coerce_float(ganho_peso_kg_dia, default=0.85), 0.20)
        _ganho_kg = max(float(peso_saida_kg) - float(peso_entrada_kg), 1.0)
        dias_engorda = int(round(_ganho_kg / _gmd))
    else:
        dias_engorda = _coerce_int(dias_engorda, default=90)

    mort = mort_pct / 100.0
    preco = preco_arroba
    rend = rendimento_carcaca / 100.0

    arrobas_saida = (peso_saida_kg * rend) / 15.0
    ganho_arrobas = max(arrobas_saida - (peso_entrada_kg * rend) / 15.0, 0.0)

    bois = float(va[7] + va[9])
    outros_f = float(va[0] + va[2] + va[4] + va[6] + va[8])
    outros_m = float(va[1] + va[3] + va[5])

    lotes_ano = 365.0 / max(float(dias_engorda), 30.0)

    anos_proj: list[dict[str, Any]] = []
    for yr in range(1, years_value + 1):
        bois_no_ano = bois * lotes_ano
        mortes = bois_no_ano * mort
        bois_abatidos = bois_no_ano - mortes

        receita = bois_abatidos * arrobas_saida * preco
        arrobas_media = (arrobas_saida + (peso_entrada_kg * rend) / 15.0) / 2.0
        custo_manutencao = bois_no_ano * arrobas_media * custo_arroba * (dias_engorda / 365.0)

        bois_prox = bois * (1 + min(0.05, 0.04 * nat_mod))
        compras = max(bois_prox + bois_abatidos + mortes - bois, 0.0)
        outros_f_prox = max(outros_f - outros_f * mort, 0.0)
        outros_m_prox = max(outros_m - outros_m * mort, 0.0)
        custo_reposicao = compras * TROCA_ARROBAS_BOI_MAGRO * preco if reposicao_precificada else 0.0
        custo = custo_manutencao + custo_reposicao
        resultado = receita - custo

        anos_proj.append(
            {
                "ano": yr,
                "total": int(bois_prox + outros_f_prox + outros_m_prox),
                "compras": int(compras),
                "mortes": int(mortes + (outros_f + outros_m) * mort),
                "matrizes": 0,
                "bezerros": 0,
                "vendidos": int(bois_abatidos),
                "bois_vendidos": int(bois_abatidos),
                "matrizes_descartadas": 0,
                "bezerras_vendidas": 0,
                "machos_vendidos": int(bois_abatidos),
                "aumento_matrizes": 0,
                "arrobas_por_boi": round(arrobas_saida, 2),
                "arrobas_ganho_por_boi": round(ganho_arrobas, 2),
                "lotes_por_ano": round(lotes_ano, 2),
                "ganho_peso_kg": round(peso_saida_kg - peso_entrada_kg, 1),
                "receita": round(receita, 2),
                "custo": round(custo, 2),
                "custo_manutencao": round(custo_manutencao, 2),
                "custo_reposicao": round(custo_reposicao, 2),
                "resultado": round(resultado, 2),
                "bois_fim": int(bois_prox),
                "jovens_f_fim": int(outros_f_prox),
                "jovens_m_fim": int(outros_m_prox),
            }
        )
        bois = bois_prox
        outros_f = outros_f_prox
        outros_m = outros_m_prox

    ano1 = anos_proj[0]
    result = finalize_projection(
        "ENGORDA",
        anos_proj,
        total_ini,
        extra={
            "preco_breakeven": round(ano1["custo"] / max(float(ano1["vendidos"]) * arrobas_saida, 1.0), 2),
            "preco_breakeven_unidade": "R$/arroba",
            "preco_usado": preco,
            "slider_units": round(float(ano1["vendidos"]) * arrobas_saida, 2),
            "slider_custo_ano1": ano1["custo"],
            "margem_atual_pct": round(ano1["resultado"] / max(ano1["custo"], 1) * 100, 1),
            "margem_atual_rs": round(ano1["resultado"], 2),
        },
    )
    return result
