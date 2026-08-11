from __future__ import annotations

from copy import deepcopy
from typing import Any

from ml_engine import calcular_indicadores, classificar, simular_cenario

from services.analysis_engine import build_explanation  # compatibility helper
from services.benchmarks_nacionais import avaliar_nacional, avaliar_zootecnico
from services.cashflow_engine import project_cashflow
from services.checklist_credito import checklist_credito
from services.economic_engine import calculate_economic_result
from services.engine.contracts import HerdState
from services.engine.versions import engine_version
from services.explicacao_classificacao import montar_explicacao_classificacao
from services.fluxo_caixa_gep import calcular_fluxo_gep
from services.fluxo_mensal_credito import projetar_fluxo_mensal
from services.garantia import avaliar_garantia
from services.livestock_engine import analyze_herd, calculate_herd_indicators
from services.payment_capacity_engine import calculate_payment_capacity
from services.qualidade_dados import analisar_qualidade_dados
from services.stress_engine import run_stress_tests
from services.validacao_zootecnica import analisar_validacoes_zootecnicas


_BLOCK_NAMES = (
    "validation",
    "herd",
    "production",
    "economic",
    "cashflow",
    "debt",
    "stress",
    "quality",
    "explanation",
)


def _normalize_payload(payload: dict | None) -> dict:
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        raise ValueError("payload must be a dict")
    normalized = deepcopy(payload)
    if "preco_arroba" not in normalized and "preco" in normalized:
        normalized["preco_arroba"] = float(normalized["preco"])
    return normalized


def _normalize_context(context: dict | None) -> dict:
    if context is None:
        context = {}
    if not isinstance(context, dict):
        raise ValueError("context must be a dict")
    normalized = deepcopy(context)
    normalized.setdefault("organization_id", normalized.get("empresa_id"))
    normalized.setdefault("user_id", None)
    return normalized


def _analysis_version() -> dict:
    return engine_version()


def _build_herd_state(payload: dict) -> HerdState:
    values = payload.get("valores") or payload.get("values") or []
    metadata = {
        key: deepcopy(payload[key])
        for key in ("bois_vendidos", "bezerros_vendidos")
        if key in payload
    }
    return HerdState(
        values=list(values),
        source=str(payload.get("source") or "API"),
        farm_id=payload.get("fazenda_id"),
        metadata=metadata,
    )


def _block(name: str, output: Any) -> dict:
    version = _analysis_version()
    return {
        "name": name,
        "engine": name,
        "version": version,
        "output": deepcopy(output),
    }


def _build_validation_block(payload: dict, context: dict, state: dict) -> dict:
    values = payload.get("valores") or payload.get("values") or []
    validation = analisar_validacoes_zootecnicas(
        values,
        payload,
        projecao=(state.get("production") or {}).get("output", {}).get("projecao_anos"),
    )
    return _block("validation", validation)


def _build_herd_block(payload: dict, context: dict, state: dict) -> dict:
    values = payload.get("valores") or payload.get("values") or []
    classification_kwargs = {
        "bois_vendidos": payload.get("bois_vendidos"),
        "bezerros_vendidos": payload.get("bezerros_vendidos"),
    }
    taxa_natalidade = payload.get("taxa_natalidade")
    if taxa_natalidade is not None:
        classification_kwargs["taxa_natalidade"] = float(taxa_natalidade)
    classification = classificar(
        values,
        **classification_kwargs,
    )
    indicators = calcular_indicadores(values)
    explanation = montar_explicacao_classificacao(classification, indicators)
    herd_state = _build_herd_state(payload)
    evidence = analyze_herd(herd_state, ml_result=classification)
    return _block(
        "herd",
        {
            "classification": classification,
            "indicators": indicators,
            "explanation": explanation,
            "evidence": evidence,
        },
    )


def _production_parameters(payload: dict) -> dict[str, Any]:
    allowed = {
        "preco_arroba",
        "custo_arroba",
        "custo_arroba_cria",
        "custo_arroba_recria",
        "custo_arroba_engorda",
        "preco_boi_arr",
        "preco_vaca_arr",
        "preco_bezerra_cab",
        "preco_bezerro_cab",
        "peso_boi",
        "peso_vaca",
        "peso_bezerra",
        "peso_garrote",
        "nat_pct",
        "mort_pct",
        "desc_mat_pct",
        "venda_bez_pct",
        "prop_boi",
        "renov_boi_pct",
        "ganho_peso_kg_dia",
        "meses_recria",
        "dias_engorda",
    }
    return {key: deepcopy(value) for key, value in payload.items() if key in allowed}


def _build_production_block(payload: dict, context: dict, state: dict) -> dict:
    herd = state["herd"]["output"]
    values = payload.get("valores") or payload.get("values") or []
    cycle = herd["classification"]["tipo"]
    years = int(payload.get("anos") or 5)
    simulation = simular_cenario(
        values,
        cenario=str(payload.get("cenario") or "conservador"),
        ciclo=cycle,
        anos=years,
        **_production_parameters(payload),
    )
    return _block(
        "production",
        {
            "simulation": simulation,
            "classification": herd["classification"],
            "indicators": herd["indicators"],
        },
    )


def _build_economic_block(payload: dict, context: dict, state: dict) -> dict:
    production = state["production"]["output"]["simulation"]
    ano1 = dict((production.get("anos") or [{}])[0] or {})
    revenues = {"receita_total": ano1.get("receita", 0.0)}
    costs = {
        "custo_operacional": ano1.get("custo", 0.0),
        "custo_manutencao": ano1.get("custo_manutencao", 0.0),
        "custo_reposicao": ano1.get("custo_reposicao", 0.0),
        "reposicao_reprodutores": payload.get("reposicao_reprodutores", 0.0),
        "custo_investimento": payload.get("custo_investimento", 0.0),
        "cabecas": ano1.get("total", 0.0),
        "arrobas_vendidas": ano1.get("arrobas_vendidas", 0.0),
        "valor_rebanho_ini": payload.get("valor_rebanho_ini", 0.0),
        "valor_rebanho_fim": payload.get("valor_rebanho_fim", 0.0),
    }
    inventory_change = float((payload.get("valor_rebanho_fim") or 0.0) - (payload.get("valor_rebanho_ini") or 0.0))
    economic = calculate_economic_result(revenues, costs, inventory_change=inventory_change)
    legacy = calcular_fluxo_gep(
        receita_caixa=economic["receita_vendas"],
        custo_caixa=economic["custo_operacional"],
        valor_rebanho_ini=economic["valor_rebanho_ini"],
        valor_rebanho_fim=economic["valor_rebanho_fim"],
        servico_divida_anual=economic.get("servico_divida_anual", 0.0),
        reposicao_reprodutores=economic.get("reposicao_reprodutores", 0.0),
    )
    economic.update(legacy)
    return _block("economic", economic)


def _build_cashflow_block(payload: dict, context: dict, state: dict) -> dict:
    production = state["production"]["output"]["simulation"]
    year_rows = list(production.get("anos") or [])
    cashflow = projetar_fluxo_mensal(year_rows)
    cashflow["projecao_anos"] = year_rows
    return _block("cashflow", cashflow)


def _debt_request(payload: dict, state: dict) -> tuple[dict, dict]:
    production = state["production"]["output"]["simulation"]
    ano1 = dict((production.get("anos") or [{}])[0] or {})
    cashflow = {
        "geracao_caixa_anual": float(ano1.get("resultado", payload.get("geracao_caixa_anual", 0.0)) or 0.0),
        "projecao_anos": [
            {
                "ano": row.get("ano"),
                "resultado": row.get("resultado", 0.0),
                "receita": row.get("receita", 0.0),
                "custo": row.get("custo", 0.0),
                "servico_divida_anual": row.get("servico_divida_anual", 0.0),
                "dscr": row.get("dscr"),
                "viavel": row.get("viavel", True),
            }
            for row in production.get("anos") or []
        ],
    }
    debt_request = {
        "credito_valor": payload.get("credito_valor", 0.0),
        "prazo_meses": payload.get("prazo_meses", 0),
        "juros_aa": payload.get("juros_aa", 0.0),
        "carencia_meses": payload.get("carencia_meses", 0),
    }
    return cashflow, debt_request


def _build_debt_block(payload: dict, context: dict, state: dict) -> dict:
    cashflow, debt_request = _debt_request(payload, state)
    existing_debt = {
        "parcela_existente_mensal": float(payload.get("parcela_existente_mensal", 0.0) or 0.0),
    }
    debt = calculate_payment_capacity(cashflow, debt_request, existing_debt)
    return _block("debt", debt)


def _build_stress_block(payload: dict, context: dict, state: dict) -> dict:
    debt = state["debt"]["output"]
    production = state["production"]["output"]["simulation"]
    analysis = {
        "projecao_anos": list(production.get("anos") or []),
        "conclusao": debt.get("analysis", {}).get("conclusao", {}),
        "servico_divida_anual": debt.get("analysis", {}).get("servico_divida_anual", 0.0),
        "geracao_caixa_anual": debt.get("analysis", {}).get("geracao_caixa_anual", 0.0),
    }
    stress = run_stress_tests(analysis, payload.get("stress_scenarios"))
    return _block("stress", stress)


def _build_quality_block(payload: dict, context: dict, state: dict) -> dict:
    values = payload.get("valores") or payload.get("values") or []
    quality = analisar_qualidade_dados(values, payload)
    quality["checklist"] = checklist_credito(payload, quality)
    quality["benchmark_nacional"] = avaliar_nacional(
        state["herd"]["output"]["classification"]["tipo"],
        {
            "prenhez": payload.get("taxa_prenhez_pct"),
            "natalidade": payload.get("taxa_natalidade_pct"),
            "desfrute": payload.get("desfrute_pct"),
            "desembolso": payload.get("desembolso_cab_mes"),
        },
    )
    quality["benchmark_zootecnico"] = avaliar_zootecnico(
        state["herd"]["output"]["classification"]["tipo"],
        {
            "natalidade_pct": payload.get("taxa_natalidade_pct"),
            "desfrute_pct": payload.get("desfrute_pct"),
            "mortalidade_bezerros_pct": payload.get("mortalidade_pct"),
            "lotacao_ua_ha": payload.get("lotacao_ua_ha"),
            "gmd_g_dia": payload.get("gmd_g_dia"),
        },
    )
    return _block("quality", quality)


def _build_explanation_block(payload: dict, context: dict, state: dict) -> dict:
    herd = state["herd"]["output"]
    explanation = {
        "classification": herd["explanation"],
        "data_quality": state["quality"]["output"],
        "stress": state["stress"]["output"],
    }
    explanation.update(
        build_explanation(
            {
                "status": state["quality"]["output"].get("status"),
                "confidence_score": state["quality"]["output"].get("confidence_score"),
                "data_confidence_score": state["quality"]["output"].get("data_confidence_score"),
                "reasons": state["quality"]["output"].get("reasons"),
                "positive_factors": state["quality"]["output"].get("positive_factors"),
                "points_of_attention": state["quality"]["output"].get("points_of_attention"),
                "assumptions": state["quality"]["output"].get("assumptions"),
                "provenance": state["quality"]["output"].get("provenance"),
                "limitations": state["quality"]["output"].get("limitations"),
            }
        )
    )
    return _block("explanation", explanation)


def _collect_analysis_map(blocks: list[dict]) -> dict[str, Any]:
    return {block["name"]: deepcopy(block["output"]) for block in blocks}


def _legacy_response(state: dict) -> dict:
    herd = state["herd"]["output"] or {}
    validation = state["validation"]["output"] or {}
    production_block = state["production"]["output"]
    production = production_block.get("simulation") or production_block
    economic = state["economic"]["output"] or {}
    cashflow = state["cashflow"]["output"] or {}
    debt = state["debt"]["output"] or {}
    stress = state["stress"]["output"] or {}
    quality = state["quality"]["output"] or {}
    explanation = state["explanation"]["output"] or {}
    classification = herd.get("classification") or {}
    indicators = herd.get("indicators") or {}
    return {
        "validacoes_zootecnicas": deepcopy(validation),
        "qualidade_dados": deepcopy(quality),
        "explicacao_classificacao": deepcopy(herd.get("explanation") or {}),
        "comparacao_cenarios": deepcopy(stress),
        "fluxo_mensal": deepcopy(cashflow),
        "fluxo_gep": deepcopy(economic),
        "analises_credito": deepcopy(debt.get("analysis", {})),
        "projecao_anos": deepcopy((production or {}).get("anos") or []),
        "rating": deepcopy(debt.get("legacy", {})),
        "desfrute_projetado": deepcopy(
            {
                "valor": quality.get("benchmark_nacional", {}).get("desfrute"),
                "projetado": quality.get("benchmark_nacional", {}).get("desfrute"),
                "origem": "projetado",
                "vendidos": 0,
                "rebanho": indicators.get("total_animals"),
                "real": None,
                "afastamento": None,
                "liquidacao": None,
            }
        ),
        "narrativa_contexto": {
            "tipo": classification.get("tipo"),
            "recomendacao": debt.get("analysis", {}).get("conclusao", {}).get("recomendacao"),
            "total_rebanho": indicators.get("total_animals"),
            "geracao_caixa_anual": debt.get("analysis", {}).get("geracao_caixa_anual"),
        },
        "shap_pendente": True,
        "narrativa_pendente": False,
        "resumo_explicacao": deepcopy(explanation),
    }


def run_full_analysis(payload: dict | None, context: dict | None) -> dict:
    payload = _normalize_payload(payload)
    context = _normalize_context(context)

    state: dict[str, dict] = {"payload": payload, "context": context}
    blocks: list[dict] = []

    validation = _build_validation_block(payload, context, state)
    state["validation"] = validation
    blocks.append(validation)

    herd = _build_herd_block(payload, context, state)
    state["herd"] = herd
    blocks.append(herd)

    production = _build_production_block(payload, context, state)
    state["production"] = production
    blocks.append(production)

    economic = _build_economic_block(payload, context, state)
    state["economic"] = economic
    blocks.append(economic)

    cashflow = _build_cashflow_block(payload, context, state)
    state["cashflow"] = cashflow
    blocks.append(cashflow)

    debt = _build_debt_block(payload, context, state)
    state["debt"] = debt
    blocks.append(debt)

    stress = _build_stress_block(payload, context, state)
    state["stress"] = stress
    blocks.append(stress)

    quality = _build_quality_block(payload, context, state)
    state["quality"] = quality
    blocks.append(quality)

    explanation = _build_explanation_block(payload, context, state)
    state["explanation"] = explanation
    blocks.append(explanation)

    result_version = _analysis_version()
    analysis_map = _collect_analysis_map(blocks)
    legacy_response = _legacy_response(state)

    return {
        "version": result_version,
        "context": deepcopy(context),
        "payload": deepcopy(payload),
        "blocks": blocks,
        "analysis": analysis_map,
        "legacy_response": legacy_response,
        "block_order": [block["name"] for block in blocks],
        "warnings": {
            "validation": deepcopy(validation["output"].get("warnings", [])),
            "quality": deepcopy(quality["output"].get("points_of_attention", [])),
        },
    }
