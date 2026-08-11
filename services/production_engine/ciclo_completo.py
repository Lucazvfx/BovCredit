from __future__ import annotations

from typing import Any

from services.engine.contracts import HerdState
from services.pesos_rebanho import arrobas_categorias
from services.parametros_zootecnicos import (
    PESO_BEZERRA_ARR,
    PESO_BOI_ARR,
    PESO_GARROTE_ARR,
    PESO_JOVEM_F_ARR,
    PESO_JOVEM_M_ARR,
    PESO_VACA_ARR,
)

from .projector import _coerce_float, _coerce_int, finalize_projection


def _ano(
    *,
    prestes_matrizes: float,
    matrizes: float,
    femeas_024: float,
    machos_024: float,
    bois: float,
    nat_pct: float,
    desc_mat_pct: float,
    prop_boi: float,
    renov_boi_pct: float,
    venda_bez_pct: float,
    mort_pct: float,
    preco_arroba: float,
    custo_cria: float,
    custo_recria: float,
    custo_engorda: float,
    peso_boi: float,
    peso_vaca: float,
    peso_bezerra: float,
    peso_garrote: float,
    preco_boi_arr: float | None,
    preco_vaca_arr: float | None,
    preco_bezerra_cab: float | None,
    preco_bezerro_cab: float | None,
    custo_arroba: float,
) -> dict[str, Any]:
    bezerros = matrizes * nat_pct
    bois_nec = max(round(matrizes / max(prop_boi, 1.0)), 1)
    renovacao = round(bois_nec * renov_boi_pct)

    graduados = machos_024 * 0.5
    bois_disp = bois + graduados
    bois_vendidos = max(bois_disp - bois_nec, 0)
    machos_024_vend = 0.0
    desc_mat = round(matrizes * desc_mat_pct)
    bez_vend = round(femeas_024 * venda_bez_pct)
    fem_repor = femeas_024 - bez_vend
    aumento = fem_repor - desc_mat + float(prestes_matrizes or 0.0)
    vendidos = bois_vendidos + desc_mat + bez_vend + machos_024_vend

    def _mortes(n: float, taxa: float) -> int:
        if n <= 0 or taxa <= 0:
            return 0
        return max(1, round(n * taxa))

    mortes_mat = _mortes(matrizes, mort_pct)
    mortes_bois_tot = _mortes(bois, mort_pct)
    mortes_jovens = _mortes(femeas_024 + machos_024, mort_pct)
    mortes_bezerros = _mortes(bezerros, min(mort_pct * 3.5, 0.25))
    mortes = mortes_mat + mortes_bois_tot + mortes_jovens + mortes_bezerros

    mat_prox = max(matrizes + aumento - mortes_mat, 0)
    bois_prox = max(bois_nec, 1)
    femeas_024_prx = round(bezerros * 0.5 * (1 - min(mort_pct * 3.5, 0.25)))
    machos_024_prx = round(
        max(machos_024 - graduados - machos_024_vend, 0) * (1 - mort_pct)
        + bezerros * 0.5 * (1 - min(mort_pct * 3.5, 0.25))
    )
    total_prox = mat_prox + femeas_024_prx + machos_024_prx + bois_prox

    p_boi = preco_boi_arr if preco_boi_arr is not None else preco_arroba
    p_vaca = preco_vaca_arr if preco_vaca_arr is not None else preco_arroba
    receita = bois_vendidos * peso_boi * p_boi + desc_mat * peso_vaca * p_vaca
    receita += (bez_vend * preco_bezerra_cab if preco_bezerra_cab is not None else bez_vend * peso_bezerra * preco_arroba)
    receita += (machos_024_vend * preco_bezerro_cab if preco_bezerro_cab is not None else machos_024_vend * peso_garrote * preco_arroba)
    arrobas_rebanho = arrobas_categorias(
        matrizes=mat_prox,
        bois=bois_prox,
        jovens_f=femeas_024_prx,
        jovens_m=machos_024_prx,
        peso_vaca=peso_vaca,
        peso_boi=peso_boi,
        peso_bezerra=peso_bezerra,
        peso_garrote=peso_garrote,
    )
    custo_tot = arrobas_rebanho * custo_arroba
    resultado = receita - custo_tot

    return {
        "bezerros_produzidos": int(bezerros),
        "bois_necessarios": bois_nec,
        "bois_excedentes": int(max(bois_disp - bois_nec, 0)),
        "machos_graduados": int(graduados),
        "renovacao_bois": renovacao,
        "bois_vendidos": int(bois_vendidos),
        "descarte_matrizes": desc_mat,
        "bezerras_vendidas": bez_vend,
        "machos_024_vendidos": int(machos_024_vend),
        "total_vendido": int(vendidos),
        "aumento_matrizes": int(aumento),
        "mortes": mortes,
        "matrizes_prox": int(mat_prox),
        "bois_prox": bois_prox,
        "femeas_024_prox": int(femeas_024_prx),
        "machos_024_prox": int(machos_024_prx),
        "total_prox": int(total_prox),
        "receita": round(receita, 2),
        "custo": round(custo_tot, 2),
        "resultado": round(resultado, 2),
    }


def project_full_cycle(state: HerdState, parameters: dict, years: int = 5) -> dict[str, Any]:
    va = [float(value) for value in state.values]
    total_ini = float(sum(va))
    years_value = _coerce_int(years, default=5)
    params = parameters or {}

    nat_pct = _coerce_float(params.get("nat_pct"), default=70.0)
    mort_pct = _coerce_float(params.get("mort_pct"), default=3.0)
    desc_mat_pct = _coerce_float(params.get("desc_mat_pct"), default=10.0)
    prop_boi = _coerce_float(params.get("prop_boi"), default=30.0)
    renov_boi_pct = _coerce_float(params.get("renov_boi_pct"), default=20.0) / 100.0
    venda_bez_pct = _coerce_float(params.get("venda_bez_pct"), default=75.0) / 100.0
    preco_arroba = _coerce_float(params.get("preco_arroba"), default=320.0)
    custo_arroba_cria = _coerce_float(params.get("custo_arroba_cria", params.get("custo_arroba")), default=57.0)
    custo_arroba_recria = _coerce_float(params.get("custo_arroba_recria", params.get("custo_arroba")), default=57.0)
    custo_arroba_engorda = _coerce_float(params.get("custo_arroba_engorda", params.get("custo_arroba")), default=57.0)
    peso_boi = _coerce_float(params.get("peso_boi"), default=PESO_BOI_ARR)
    peso_vaca = _coerce_float(params.get("peso_vaca"), default=PESO_VACA_ARR)
    peso_bezerra = _coerce_float(params.get("peso_bezerra"), default=PESO_BEZERRA_ARR)
    peso_garrote = _coerce_float(params.get("peso_garrote"), default=PESO_GARROTE_ARR)
    preco_boi_arr = params.get("preco_boi_arr")
    if preco_boi_arr is not None:
        preco_boi_arr = _coerce_float(preco_boi_arr, default=preco_arroba)
    preco_vaca_arr = params.get("preco_vaca_arr")
    if preco_vaca_arr is not None:
        preco_vaca_arr = _coerce_float(preco_vaca_arr, default=preco_arroba)
    preco_bezerra_cab = params.get("preco_bezerra_cab")
    if preco_bezerra_cab is not None:
        preco_bezerra_cab = _coerce_float(preco_bezerra_cab, default=0.0)
    preco_bezerro_cab = params.get("preco_bezerro_cab")
    if preco_bezerro_cab is not None:
        preco_bezerro_cab = _coerce_float(preco_bezerro_cab, default=0.0)

    femeas_024 = float(va[0] + va[2] + va[4])
    machos_024 = float(va[1] + va[3] + va[5])
    matrizes = float(va[8])
    prestes_F = float(va[6])
    bois = float(va[7] + va[9])

    _n_cria = matrizes + femeas_024
    _n_recria = machos_024
    _n_engorda = bois
    _fases = [
        (custo_arroba_cria, _n_cria),
        (custo_arroba_recria, _n_recria),
        (custo_arroba_engorda, _n_engorda),
    ]
    _fases_w = [(c, n) for c, n in _fases if n > 0]
    _custo_completo = sum(c * n for c, n in _fases_w) / sum(n for _, n in _fases_w) if _fases_w else custo_arroba_cria

    anos_proj: list[dict[str, Any]] = []
    nat = nat_pct / 100.0
    mort = mort_pct / 100.0
    desc = desc_mat_pct / 100.0

    for yr in range(1, years_value + 1):
        r = _ano(
            prestes_matrizes=prestes_F,
            matrizes=matrizes,
            femeas_024=femeas_024,
            machos_024=machos_024,
            bois=bois,
            nat_pct=nat,
            desc_mat_pct=desc,
            prop_boi=prop_boi,
            renov_boi_pct=renov_boi_pct,
            venda_bez_pct=venda_bez_pct,
            mort_pct=mort,
            preco_arroba=preco_arroba,
            custo_cria=custo_arroba_cria,
            custo_recria=custo_arroba_recria,
            custo_engorda=custo_arroba_engorda,
            peso_boi=peso_boi,
            peso_vaca=peso_vaca,
            peso_bezerra=peso_bezerra,
            peso_garrote=peso_garrote,
            preco_boi_arr=preco_boi_arr,
            preco_vaca_arr=preco_vaca_arr,
            preco_bezerra_cab=preco_bezerra_cab,
            preco_bezerro_cab=preco_bezerro_cab,
            custo_arroba=_custo_completo,
        )
        anos_proj.append(
            {
                "ano": yr,
                "total": r["total_prox"],
                "matrizes": r["matrizes_prox"],
                "bezerros": r["bezerros_produzidos"],
                "vendidos": r["total_vendido"],
                "bois_vendidos": r["bois_vendidos"],
                "matrizes_descartadas": r["descarte_matrizes"],
                "bezerras_vendidas": r["bezerras_vendidas"],
                "machos_vendidos": r["machos_024_vendidos"],
                "aumento_matrizes": r["aumento_matrizes"],
                "receita": r["receita"],
                "custo": r["custo"],
                "resultado": r["resultado"],
                "bois_fim": r["bois_prox"],
                "jovens_f_fim": r["femeas_024_prox"],
                "jovens_m_fim": r["machos_024_prox"],
            }
        )
        matrizes = float(r["matrizes_prox"])
        prestes_F = 0.0
        bois = float(r["bois_prox"])
        femeas_024 = float(r["femeas_024_prox"])
        machos_024 = float(r["machos_024_prox"])

    ano1 = anos_proj[0]
    preco_adj = preco_arroba
    bv = float(ano1.get("bois_vendidos", 0))
    dv = float(ano1.get("matrizes_descartadas", 0))
    bezv = float(ano1.get("bezerras_vendidas", 0))
    garv = float(ano1.get("machos_vendidos", 0))
    peso_medio = (
        bv * peso_boi
        + dv * peso_vaca
        + bezv * peso_bezerra
        + garv * peso_garrote
    ) / max(ano1["vendidos"], 1)
    units = float(max(ano1["vendidos"], 1)) * peso_medio
    return finalize_projection(
        "CICLO_COMPLETO",
        anos_proj,
        total_ini,
        extra={
            "preco_breakeven": round(ano1["custo"] / max(units, 1), 2),
            "preco_breakeven_unidade": "R$/arroba",
            "preco_usado": preco_adj,
            "slider_units": round(units, 2),
            "slider_custo_ano1": ano1["custo"],
            "margem_atual_pct": round(ano1["resultado"] / max(ano1["custo"], 1) * 100, 1),
            "margem_atual_rs": round(ano1["resultado"], 2),
        },
    )
