"""Testes do motor de benchmarks nacionais (multi-fonte + financeiro).

Todos os números conferidos contra as fontes reais: PPTX "Análise Crédito
Pecuária" (Embrapa, Scot, CEPEA-USP, ABCZ, ASBIA) e XLSX GEP Araguaia /
Inttegra 2025 (desembolso R$/cab/mês).
"""
import pytest

from services.benchmarks_nacionais import (
    posicao_valor,
    avaliar_multifonte,
    avaliar_desfrute,
    avaliar_desembolso,
    avaliar_nacional,
    PRENHEZ_FONTES,
    NATALIDADE_FONTES,
)


def test_posicao_valor():
    assert posicao_valor(40, 55, 65) == "abaixo"
    assert posicao_valor(60, 55, 65) == "dentro"
    assert posicao_valor(70, 55, 65) == "acima"


def test_multifonte_natalidade_todas_as_fontes():
    r = avaliar_multifonte("natalidade", 62.0)
    fontes = {i["fonte"] for i in r}
    assert fontes == set(NATALIDADE_FONTES)
    # 62% está abaixo de Embrapa (65–80) e abaixo de ABCZ (65–75).
    emb = next(i for i in r if i["fonte"] == "Embrapa")
    abcz = next(i for i in r if i["fonte"] == "ABCZ")
    assert emb["posicao"] == "abaixo"
    assert abcz["posicao"] == "abaixo"


def test_multifonte_prenhez_conhece_asbia():
    r = avaliar_multifonte("prenhez", 65.0)
    assert set(i["fonte"] for i in r) == set(PRENHEZ_FONTES)


def test_multifonte_indicador_invalido():
    with pytest.raises(ValueError):
        avaliar_multifonte("desfrute", 50)


def test_desfrute_por_modalidade():
    r = avaliar_desfrute("CRIA", 24.0)
    assert r["faixa"] == (18.0, 30.0)
    assert r["posicao"] == "dentro"
    assert r["classe"] == "baixo"  # 18–30 na escala geral de desfrute


def test_desembolso_abaixo_do_top_e_excelente():
    # Cria: Média 90,88 / Top 69,63. Custo 60 < top -> excelente.
    r = avaliar_desembolso("CRIA", 60.0)
    assert r["media"] == 90.88
    assert r["top"] == 69.63
    assert r["nivel"] == "excelente"


def test_desembolso_acima_da_media_e_atencao():
    r = avaliar_desembolso("CRIA", 100.0)
    assert r["nivel"] == "atencao"


def test_desembolso_recria_e_engorda_sao_desagregados():
    # RECRIA e ENGORDA têm presets separados desde a safra 24/25 GEP Araguaia.
    a = avaliar_desembolso("RECRIA", 150.0)
    b = avaliar_desembolso("ENGORDA", 150.0)
    assert a["media"] == 100.50
    assert b["media"] == 182.60


def test_avaliar_nacional_orquestra_parcial():
    # Só informa natalidade e desfrute; desembolso ausente.
    res = avaliar_nacional("CRIA", {"natalidade": 62.0, "desfrute": 24.0})
    assert res["modalidade"] == "CRIA"
    assert len(res["multifonte"]) >= 1
    assert res["desfrute"] is not None
    assert res["desembolso"] is None
