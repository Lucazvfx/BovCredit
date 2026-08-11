"""Qualidade e origem dos dados usados na analise rural."""
from __future__ import annotations

from services.analysis_engine.data_quality import assess_data_quality


_CAMPOS_ZOOTECNICOS = {
    "peso_medio_kg": "peso medio por categoria",
    "peso_desmama_kg": "peso a desmama",
    "ganho_peso_kg_dia": "ganho medio diario",
    "taxa_prenhez_pct": "taxa de prenhez",
    "taxa_natalidade_pct": "taxa de natalidade",
    "natalidade_pct": "taxa de natalidade",
    "desmama_pct": "taxa de desmama",
    "mortalidade_pct": "mortalidade",
    "area_pasto_ha": "area de pastagem",
}

_CAMPOS_OPERACIONAIS = {
    "bois_vendidos": "vendas de bois",
    "bezerros_vendidos": "vendas de bezerros",
    "vendas_anuais": "vendas anuais totais",
    "compras_reposicao": "compras/reposicao",
    "preco_boi": "preco do boi",
    "preco_vaca": "preco da vaca",
    "custo_arroba": "custo por arroba",
    "credito_valor": "valor do credito",
    "prazo_meses": "prazo do credito",
}

_CAMPOS_COM_ESTIMATIVA_SEGURA = {"peso_medio_kg"}


def _normalizar_aliases_para_analise(dados: dict | None) -> dict:
    normalizados = dict(dados or {})
    if normalizados.get("taxa_natalidade_pct") in (None, "") and normalizados.get("natalidade_pct") not in (None, ""):
        normalizados["taxa_natalidade_pct"] = normalizados["natalidade_pct"]
    if normalizados.get("taxa_mortalidade_pct") in (None, "") and normalizados.get("mortalidade_pct") not in (None, ""):
        normalizados["taxa_mortalidade_pct"] = normalizados["mortalidade_pct"]
    return normalizados


def analisar_qualidade_dados(valores: list, dados: dict | None = None) -> dict:
    """Classifica a evidencia disponivel sem inventar indices produtivos."""
    dados = dados or {}
    total = sum(float(x or 0) for x in (valores or []))
    campos_informados = []
    campos_ausentes = []
    campos = {}
    tabela_campos = {**_CAMPOS_ZOOTECNICOS, **_CAMPOS_OPERACIONAIS}
    for campo, rotulo in tabela_campos.items():
        valor = dados.get(campo)
        if valor not in (None, ""):
            try:
                if float(valor) >= 0:
                    item = {
                        "valor": float(valor),
                        "origem": "usuario",
                        "informado": True,
                        "confianca": "declarado",
                        "observacao": "Valor informado na analise.",
                    }
                    campos[campo] = item
                    campos_informados.append({"campo": campo, "descricao": rotulo})
                    continue
            except (TypeError, ValueError):
                pass
        origem = "estimativa" if campo in _CAMPOS_COM_ESTIMATIVA_SEGURA else "ausente"
        campos[campo] = {
            "valor": None,
            "origem": origem,
            "informado": False,
            "confianca": "referencia" if origem == "estimativa" else None,
            "observacao": (
                "Sera derivado por parametro de referencia na simulacao."
                if origem == "estimativa"
                else "Nao informado na ficha ou na analise."
            ),
        }
        campos_ausentes.append({"campo": campo, "descricao": rotulo})

    if total > 0:
        campos["composicao_rebanho"] = {
            "valor": total,
            "origem": "documento",
            "informado": True,
            "confianca": "estrutural",
            "observacao": "Contagem por sexo e faixa etaria extraida da ficha.",
        }
    observados = ["contagem por sexo e faixa etaria"] if total > 0 else []
    estimaveis = [x["descricao"] for x in campos_ausentes]
    n = len(campos_informados)
    if n >= 5:
        confianca = "alta"
    elif n >= 2:
        confianca = "media"
    else:
        confianca = "media-baixa"

    avisos = []
    if not campos_informados:
        avisos.append(
            "A ficha contem apenas a composicao do rebanho; os indices produtivos serao estimados."
        )
    if "peso_medio_kg" in {x["campo"] for x in campos_ausentes}:
        avisos.append("Sem peso informado, valor da garantia e arrobas sao estimados por categoria.")
    if any(
        x["campo"] in {y["campo"] for y in campos_ausentes}
        for x in ({"campo": "taxa_prenhez_pct"}, {"campo": "natalidade_pct"}, {"campo": "desmama_pct"})
    ):
        avisos.append(
            "Sem historico reprodutivo, natalidade e desmama nao sao indices medidos da fazenda."
        )

    dados_para_analise = _normalizar_aliases_para_analise(dados)
    qualidade_consolidada = assess_data_quality(
        dados_para_analise,
        {"values": list(valores or [])},
        None,
    )

    return {
        "campos": campos,
        "nivel_confianca": confianca,
        "origem_principal": "ficha_sanitaria" if total > 0 else "incompleta",
        "observados": observados,
        "informados": campos_informados,
        "estimados": estimaveis,
        "ausentes": campos_ausentes,
        "avisos": avisos,
        "resultado_financeiro_estimado": any(
            campos[c]["origem"] in ("estimativa", "ausente")
            for c in (*_CAMPOS_OPERACIONAIS, "peso_medio_kg", "mortalidade_pct", "natalidade_pct")
        ),
        "pode_calcular_indices_estruturais": bool(total > 0),
        "pode_calcular_indices_produtivos_reais": n >= 5,
        "status": qualidade_consolidada["status"],
        "confidence_score": qualidade_consolidada["confidence_score"],
        "data_confidence_score": qualidade_consolidada["data_confidence_score"],
        "missing_fields": qualidade_consolidada["missing_fields"],
        "inconsistent_fields": qualidade_consolidada["inconsistent_fields"],
        "impossible_fields": qualidade_consolidada["impossible_fields"],
        "conflicting_fields": qualidade_consolidada["conflicting_fields"],
        "assumed_fields": qualidade_consolidada["assumed_fields"],
        "extra_fields": qualidade_consolidada["extra_fields"],
        "reasons": qualidade_consolidada["reasons"],
        "positive_factors": qualidade_consolidada["positive_factors"],
        "points_of_attention": qualidade_consolidada["points_of_attention"],
        "assumptions": qualidade_consolidada["assumptions"],
        "provenance": qualidade_consolidada["provenance"],
        "limitations": qualidade_consolidada["limitations"],
    }
