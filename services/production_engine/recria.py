from __future__ import annotations

import os
from typing import Any

from services.engine.contracts import HerdState
from services.parametros_zootecnicos import PESO_GARROTE_ARR, PESO_JOVEM_F_ARR, TROCA_ARROBAS_BEZERRO

from .projector import _coerce_bool, _coerce_float, _coerce_int, finalize_projection

_FRAC_VENDA_RECRIA_M = float(os.environ.get("FRAC_VENDA_RECRIA_M", "0.83"))


def project_recria(state: HerdState, parameters: dict, years: int = 5) -> dict[str, Any]:
    va = [float(value) for value in state.values]
    total_ini = float(sum(va))
    years_value = _coerce_int(years, default=5)
    params = parameters or {}

    mort_pct = _coerce_float(params.get("mort_pct"), default=3.0)
    preco_arroba = _coerce_float(params.get("preco_arroba"), default=320.0)
    peso_entrada_arr = _coerce_float(params.get("peso_entrada_arr"), default=6.5)
    peso_saida_arr = _coerce_float(params.get("peso_saida_arr"), default=13.5)
    meses_recria = _coerce_float(params.get("meses_recria"), default=12.0)
    custo_arroba = _coerce_float(
        params.get("custo_arroba_recria", params.get("custo_arroba")),
        default=57.0,
    )
    preco_reposicao_cab = params.get("preco_reposicao_cab")
    if preco_reposicao_cab is not None:
        preco_reposicao_cab = _coerce_float(preco_reposicao_cab, default=0.0)
    reposicao_precificada = _coerce_bool(params.get("reposicao_precificada"), default=True)

    mort = mort_pct / 100.0
    preco = preco_arroba
    ganho_arr = max(peso_saida_arr - peso_entrada_arr, 0.0)

    c0_f, c0_m = float(va[0] + va[2]), float(va[1] + va[3])
    c1_f, c1_m = float(va[4]), float(va[5])
    c2_f, c2_m = float(va[6]), float(va[7])
    c3_f, c3_m = float(va[8]), float(va[9])

    anos_proj: list[dict[str, Any]] = []
    for yr in range(1, years_value + 1):
        plantel_ini = c0_f + c0_m + c1_f + c1_m + c2_f + c2_m + c3_f + c3_m
        mortes = plantel_ini * mort

        s = 1.0 - mort
        c0_f, c0_m = c0_f * s, c0_m * s
        c1_f, c1_m = c1_f * s, c1_m * s
        c2_f, c2_m = c2_f * s, c2_m * s
        c3_f, c3_m = c3_f * s, c3_m * s

        vend_c1_m = c1_m * _FRAC_VENDA_RECRIA_M
        machos_sai = c3_m + c2_m + vend_c1_m
        femeas_sai = c3_f + c2_f
        animais_sai = machos_sai + femeas_sai

        receita = animais_sai * peso_saida_arr * preco
        peso_medio = (peso_entrada_arr + peso_saida_arr) / 2.0
        custo_manutencao = plantel_ini * peso_medio * custo_arroba * (meses_recria / 12.0)

        n3_f = n3_m = 0.0
        n2_f, n2_m = c1_f, c1_m - vend_c1_m
        n1_f, n1_m = c0_f, c0_m

        compras = animais_sai
        n0_f, n0_m = 0.0, compras

        _p_repo = (preco_reposicao_cab if preco_reposicao_cab is not None else TROCA_ARROBAS_BEZERRO * preco)
        custo_reposicao = compras * _p_repo if reposicao_precificada else 0.0
        custo = custo_manutencao + custo_reposicao
        resultado = receita - custo

        total_fim = n0_f + n0_m + n1_f + n1_m + n2_f + n2_m + n3_f + n3_m
        anos_proj.append(
            {
                "ano": yr,
                "total": int(round(total_fim)),
                "matrizes": int(round(n3_f + n2_f)),
                "bezerros": 0,
                "vendidos": int(round(animais_sai)),
                "bois_vendidos": int(round(animais_sai)),
                "matrizes_descartadas": 0,
                "bezerras_vendidas": 0,
                "machos_vendidos": int(round(machos_sai)),
                "femeas_vendidas": int(round(femeas_sai)),
                "aumento_matrizes": 0,
                "ganho_arrobas_por_animal": round(ganho_arr, 2),
                "receita": round(receita, 2),
                "custo": round(custo, 2),
                "custo_manutencao": round(custo_manutencao, 2),
                "custo_reposicao": round(custo_reposicao, 2),
                "resultado": round(resultado, 2),
                "bois_fim": int(round(n3_m + n2_m)),
                "jovens_f_fim": int(round(n0_f + n1_f)),
                "jovens_m_fim": int(round(n0_m + n1_m)),
                "compras": int(round(compras)),
                "mortes": int(round(mortes)),
            }
        )
        c0_f, c0_m = n0_f, n0_m
        c1_f, c1_m = n1_f, n1_m
        c2_f, c2_m = n2_f, n2_m
        c3_f, c3_m = n3_f, n3_m

    ano1 = anos_proj[0]
    result = finalize_projection(
        "RECRIA",
        anos_proj,
        total_ini,
        extra={
            "preco_breakeven": round(ano1["custo"] / max(float(ano1["vendidos"]) * peso_saida_arr, 1.0), 2),
            "preco_breakeven_unidade": "R$/arroba",
            "preco_usado": preco,
            "slider_units": round(float(ano1["vendidos"]) * peso_saida_arr, 2),
            "slider_custo_ano1": ano1["custo"],
            "margem_atual_pct": round(ano1["resultado"] / max(ano1["custo"], 1) * 100, 1),
            "margem_atual_rs": round(ano1["resultado"], 2),
        },
    )
    return result
