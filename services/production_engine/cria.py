from __future__ import annotations

from typing import Any

from services.engine.contracts import HerdState
from services.parametros_zootecnicos import (
    PESO_BEZERRA_ARR,
    PESO_BOI_ARR,
    PESO_JOVEM_F_ARR,
    PESO_VACA_ARR,
    taxa_desmama_efetiva,
)

from .projector import _coerce_bool, _coerce_float, _coerce_int, finalize_projection


def project_cria(state: HerdState, parameters: dict, years: int = 5) -> dict[str, Any]:
    va = [float(value) for value in state.values]
    total_ini = float(sum(va))
    years_value = _coerce_int(years, default=5)
    params = parameters or {}

    nat_pct = _coerce_float(params.get("nat_pct"), default=70.0)
    mort_pct = _coerce_float(params.get("mort_pct"), default=3.0)
    desmama_pct = params.get("desmama_pct")
    if desmama_pct is not None:
        desmama_pct = _coerce_float(desmama_pct, default=82.0)
    venda_bez_pct = _coerce_float(params.get("venda_bez_pct"), default=75.0)
    preco_arroba_bezerro = _coerce_float(params.get("preco_arroba_bezerro"), default=320.0)
    custo_arroba = _coerce_float(
        params.get("custo_arroba_cria", params.get("custo_arroba")),
        default=57.0,
    )
    peso_matriz = _coerce_float(params.get("peso_matriz"), default=PESO_VACA_ARR)
    peso_bezerra = _coerce_float(params.get("peso_bezerra"), default=PESO_BEZERRA_ARR)
    preco_vaca_arr = params.get("preco_vaca_arr")
    if preco_vaca_arr is not None:
        preco_vaca_arr = _coerce_float(preco_vaca_arr, default=preco_arroba_bezerro)
    desc_mat_pct = _coerce_float(params.get("desc_mat_pct"), default=10.0)
    repoe_compra_desmama = _coerce_bool(params.get("repoe_compra_desmama"), default=False)
    reposicao_precificada = _coerce_bool(params.get("reposicao_precificada"), default=True)

    nat = min((nat_pct / 100.0), 0.95)
    mort = mort_pct / 100.0
    mort_bez = min(mort * 3.5, 0.25)
    taxa_desmama = taxa_desmama_efetiva(
        natalidade_pct=nat * 100.0,
        mortalidade_bezerro_pct=mort_bez * 100.0,
        desmama_declarada_pct=desmama_pct,
    )
    venda_bz = venda_bez_pct / 100.0
    preco_bz = preco_arroba_bezerro * peso_bezerra
    preco_vaca_cab = ((preco_vaca_arr if preco_vaca_arr is not None else preco_arroba_bezerro) * peso_matriz)

    bez_F = float(va[0] + va[2])
    bez_M = float(va[1] + va[3])
    mac_R = float(va[5] + va[7])
    matrizes = float(va[8])
    nov_F = float(va[4])
    prestes_F = float(va[6])
    bois = float(va[9])

    anos_proj: list[dict[str, Any]] = []
    for yr in range(1, years_value + 1):
        nascidos = matrizes * nat
        desmamados = matrizes * taxa_desmama

        _desm_M = desmamados * 0.5
        _desm_F = desmamados * 0.5
        disp_M = max(bez_M, _desm_M)
        disp_F = max(bez_F, _desm_F)
        _antecip_M = max(disp_M - bez_M, 0.0)
        _antecip_F = max(disp_F - bez_F, 0.0)

        vende_bez_M = disp_M
        vende_bez_F = disp_F * venda_bz
        retem_bez_F = disp_F - vende_bez_F
        descarte_mat = round(matrizes * (desc_mat_pct / 100.0))
        _baixas_mat = float(descarte_mat) + matrizes * mort
        _falta = max(_baixas_mat - prestes_F, 0.0)
        promovidas = prestes_F + min(nov_F, _falta)
        vende_nov_F = max(nov_F - min(nov_F, _falta), 0.0)
        vende_mac_R = mac_R

        machos_vend = vende_bez_M + vende_mac_R
        femeas_vend = vende_bez_F
        femeas_exced = vende_nov_F
        vez_vendidos = machos_vend + femeas_vend + femeas_exced

        preco_novilha_cab = ((preco_vaca_arr if preco_vaca_arr is not None else preco_arroba_bezerro) * PESO_JOVEM_F_ARR)
        # The legacy engine values the male young surplus at a garrote price
        # derived from the bezerro arroba reference, not from carcass boi.
        preco_garrote_cab = preco_arroba_bezerro * 10.67
        receita = (
            (vende_bez_M + vende_bez_F) * preco_bz
            + vende_mac_R * preco_garrote_cab
            + femeas_exced * preco_novilha_cab
            + descarte_mat * preco_vaca_cab
        )

        touros = bois if bois > 0 else (max(round(matrizes / 30.0), 1) if matrizes > 0 else 0)
        custo_manutencao = (
            matrizes * peso_matriz
            + (bez_F + bez_M) * peso_bezerra
            + (nov_F + prestes_F + mac_R) * PESO_JOVEM_F_ARR
            + touros * PESO_BOI_ARR
        ) * custo_arroba

        compra_desmama = max((bez_F + bez_M) - nascidos, 0.0)
        custo_compra_desmama = compra_desmama * preco_bz if (repoe_compra_desmama and reposicao_precificada) else 0.0
        custo = custo_manutencao + custo_compra_desmama
        resultado = receita - custo

        mortes = round((matrizes + nov_F + prestes_F + mac_R + bois) * mort + (nascidos - desmamados))
        matrizes_prox = max(matrizes * (1 - mort) + promovidas - descarte_mat, matrizes * 0.7)
        nov_F_prox = max(retem_bez_F - retem_bez_F * mort, 0.0)
        prestes_prox = 0.0
        bois_prox = max(bois - bois * mort, 0.0)
        bez_F_prox = max(_desm_F - _antecip_F, 0.0)
        bez_M_prox = max(_desm_M - _antecip_M, 0.0)
        if repoe_compra_desmama and compra_desmama > 0:
            frac_f_jov = (bez_F / (bez_F + bez_M)) if (bez_F + bez_M) > 0 else 0.5
            bez_F_prox += compra_desmama * frac_f_jov
            bez_M_prox += compra_desmama * (1 - frac_f_jov)
        mac_R_prox = 0.0
        total_fim = int(
            matrizes_prox
            + nov_F_prox
            + prestes_prox
            + bois_prox
            + bez_F_prox
            + bez_M_prox
            + mac_R_prox
        )

        anos_proj.append(
            {
                "ano": yr,
                "total": total_fim,
                "matrizes": int(matrizes_prox),
                "bezerros": int(nascidos),
                "vendidos": int(vez_vendidos),
                "bois_vendidos": int(machos_vend),
                "matrizes_descartadas": int(round(descarte_mat)),
                "bezerras_vendidas": int(femeas_vend),
                "machos_vendidos": int(machos_vend),
                "femeas_excedentes": int(femeas_exced),
                "aumento_matrizes": int(promovidas - descarte_mat),
                "receita": round(receita, 2),
                "custo": round(custo, 2),
                "custo_manutencao": round(custo_manutencao, 2),
                "custo_compra_desmama": round(custo_compra_desmama, 2),
                "compra_desmama_estimada": int(round(compra_desmama)),
                "repoe_compra_desmama": repoe_compra_desmama,
                "resultado": round(resultado, 2),
                "bois_fim": int(bois_prox),
                "jovens_f_fim": int(nov_F_prox + prestes_prox + bez_F_prox),
                "jovens_m_fim": int(bez_M_prox + mac_R_prox),
                "compras": 0,
                "mortes": int(mortes),
            }
        )

        matrizes = float(matrizes_prox)
        nov_F = float(nov_F_prox)
        prestes_F = float(prestes_prox)
        bois = float(bois_prox)
        bez_F = float(bez_F_prox)
        bez_M = float(bez_M_prox)
        mac_R = float(mac_R_prox)

    ano1 = anos_proj[0]
    result = finalize_projection(
        "CRIA",
        anos_proj,
        total_ini,
        extra={
            "preco_breakeven": round(ano1["custo"] / max(float(ano1["vendidos"]), 1.0), 2),
            "preco_breakeven_unidade": "R$/cabeça",
            "preco_usado": preco_bz,
            "slider_units": float(ano1["vendidos"]),
            "slider_custo_ano1": ano1["custo"],
            "margem_atual_pct": round(ano1["resultado"] / max(ano1["custo"], 1) * 100, 1),
            "margem_atual_rs": round(ano1["resultado"], 2),
        },
    )
    return result
