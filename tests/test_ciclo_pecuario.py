import math

import pytest

from services.payment_capacity_engine import PERFIS, projetar_fluxo_ciclo
from services.payment_capacity_engine.ciclo_pecuario import (
    SISTEMAS,
    VALOR_MAXIMO,
    distribuir_centavos,
)

RECEITA = 1_000_000.0
CUSTO = 600_000.0
PARCELA_MENSAL = 25_000.0  # serviço anual 300k → DSCR 400k/300k = 1,33


def _fluxo(sistema="cria", **kw):
    args = dict(sistema=sistema, receita_anual=RECEITA,
                custo_operacional_anual=CUSTO, parcela_divida=PARCELA_MENSAL)
    args.update(kw)
    return projetar_fluxo_ciclo(**args)


def _soma_centavos(meses, campo):
    return sum(round(m[campo] * 100) for m in meses)


# ── pesos sazonais ──────────────────────────────────────────────────

@pytest.mark.parametrize("sistema", SISTEMAS)
def test_pesos_fecham_em_100_por_cento(sistema):
    p = PERFIS[sistema]
    assert len(p.entradas_permil) == 12 and len(p.saidas_permil) == 12
    assert sum(p.entradas_permil) == 1000
    assert sum(p.saidas_permil) == 1000
    assert math.fsum(p.pesos_entradas) == pytest.approx(1.0, abs=1e-12)
    assert math.fsum(p.pesos_saidas) == pytest.approx(1.0, abs=1e-12)


def test_perfis_coerentes_com_o_ciclo():
    # cria vende desmama no pico de abr–jun; engorda vende gordo jul–out
    cria = PERFIS["cria"].entradas_permil
    assert max(range(12), key=lambda i: cria[i]) + 1 == 5
    assert sum(cria[3:6]) > 500
    engorda = PERFIS["engorda"].entradas_permil
    assert sum(engorda[6:10]) > 500
    # engorda compra o magro antes de vender (saída pesa mais no 1º semestre)
    assert sum(PERFIS["engorda"].saidas_permil[:6]) > 500
    # suplementação na seca: cria gasta mais em jun–out que em jan–abr
    s = PERFIS["cria"].saidas_permil
    assert sum(s[5:10]) / 5 > sum(s[0:4]) / 4


def test_perfis_tem_proveniencia_referencia():
    r = projetar_fluxo_ciclo(sistema="cria", receita_anual=1, custo_operacional_anual=1,
                             parcela_divida=0)
    assert r["proveniencia"]["origem"] == "referencia"


# ── fechamento matemático ───────────────────────────────────────────

@pytest.mark.parametrize("sistema", SISTEMAS)
@pytest.mark.parametrize("freq", ["mensal", "semestral", "anual"])
def test_fechamento_anual_sem_perder_centavos(sistema, freq):
    # valores propositalmente "feios" para forçar resto na repartição
    r = projetar_fluxo_ciclo(sistema=sistema, receita_anual=987_654.33,
                             custo_operacional_anual=543_210.17,
                             parcela_divida=12_345.67 if freq == "mensal" else 77_777.77,
                             frequencia=freq, capital_giro_inicial=1_000.01)
    m = r["meses"]
    assert _soma_centavos(m, "entradas") == 98_765_433
    assert _soma_centavos(m, "saidas_operacionais") == 54_321_017
    n = {"mensal": 12, "semestral": 2, "anual": 1}[freq]
    parcela = 1_234_567 if freq == "mensal" else 7_777_777
    assert _soma_centavos(m, "servico_divida") == parcela * n
    saldo_final = 100_001 + 98_765_433 - 54_321_017 - parcela * n
    assert round(m[-1]["saldo_acumulado"] * 100) == saldo_final
    assert round(r["totais"]["saldo_final"] * 100) == saldo_final


def test_distribuir_centavos_exato():
    for total in (0, 1, 7, 999, 1_000_001):
        for sistema in SISTEMAS:
            for pesos in (PERFIS[sistema].entradas_permil, PERFIS[sistema].saidas_permil):
                d = distribuir_centavos(total, pesos)
                assert sum(d) == total and min(d) >= 0


# ── DSCR aprovado, mas quebra de caixa ──────────────────────────────

@pytest.mark.parametrize("sistema", ["cria", "engorda"])
def test_dscr_aprovado_mas_caixa_quebra_no_mensal(sistema):
    r = _fluxo(sistema)
    assert r["dscr_anual"] == pytest.approx(1.3333, abs=1e-4)
    assert r["dscr_anual_suficiente"] is True
    assert r["quebra_caixa_com_dscr_ok"] is True
    assert r["vale_caixa"] < 0
    assert r["meses_deficit"] and 1 in r["meses_deficit"]
    assert any("quebra de caixa" in j for j in r["justificativa"])
    # o ano fecha positivo: o problema é calendário, não capacidade
    assert r["totais"]["saldo_final"] == pytest.approx(RECEITA - CUSTO - 300_000.0)


def test_sem_quebra_quando_dscr_insuficiente_nao_marca_descasamento():
    r = _fluxo("cria", parcela_divida=40_000.0)  # DSCR 0,83
    assert r["dscr_anual_suficiente"] is False
    assert r["quebra_caixa_com_dscr_ok"] is False


# ── recomendação de cronograma ──────────────────────────────────────

@pytest.mark.parametrize("sistema", SISTEMAS)
def test_recomendacao_reduz_o_vale(sistema):
    r = _fluxo(sistema)
    rec = r["recomendacao"]
    assert rec is not None and rec["melhora_vale"] is True
    assert rec["estrutura_recomendada"] in ("semestral", "anual")
    escolhida = next(a for a in rec["alternativas"]
                     if a["frequencia"] == rec["estrutura_recomendada"])
    assert escolhida["vale_caixa"] > r["vale_caixa"]
    assert rec["reducao_vale"] == pytest.approx(escolhida["vale_caixa"] - r["vale_caixa"])
    # a recomendada é a melhor das alternativas simuladas
    assert escolhida["vale_caixa"] == max(a["vale_caixa"] for a in rec["alternativas"])


def test_recomendacao_chega_ao_piso_operacional_na_cria():
    r = _fluxo("cria")
    # sem capital de giro o vale que sobra é o operacional (custo antes da venda)
    assert r["recomendacao"]["alternativas"][0]["vale_caixa"] == pytest.approx(r["vale_operacional"])


@pytest.mark.parametrize("sistema", ["cria", "engorda"])
def test_recomendacao_elimina_vale_com_giro_cobrindo_o_vale_operacional(sistema):
    base = _fluxo(sistema)
    giro = -base["vale_operacional"] + 10_000.0
    r = _fluxo(sistema, capital_giro_inicial=giro)
    if r["meses_deficit"]:  # mensal ainda quebra com esse giro
        rec = r["recomendacao"]
        assert rec["melhora_vale"] is True
        assert rec["elimina_vale"] is True
        escolhida = next(a for a in rec["alternativas"]
                         if a["frequencia"] == rec["estrutura_recomendada"])
        assert escolhida["meses_deficit"] == []
    else:
        pytest.fail("cenário deveria quebrar no mensal mesmo com giro operacional")


def test_anual_pode_piorar_e_a_recomendacao_nao_o_escolhe_as_cegas():
    # ciclo_completo: 300k de uma vez em maio aprofunda o vale vs. mensal
    r = _fluxo("ciclo_completo")
    alt = {a["frequencia"]: a for a in r["recomendacao"]["alternativas"]}
    assert alt["anual"]["vale_caixa"] < r["vale_caixa"]
    assert r["recomendacao"]["estrutura_recomendada"] == "semestral"


def test_sem_estrutura_melhor_mantem_mensal():
    # sem receita o pior ponto é dezembro, quando todo o serviço já foi pago
    # em qualquer calendário: reescalonar não muda o vale
    r = _fluxo("cria", receita_anual=0.0)
    assert r["recomendacao"]["melhora_vale"] is False
    assert r["recomendacao"]["estrutura_recomendada"] == "mensal"
    assert r["recomendacao"]["reducao_vale"] == 0.0


def test_pagamentos_alinhados_ao_pico_de_entrada():
    r = _fluxo("cria")
    sem = {a["frequencia"]: a for a in r["recomendacao"]["alternativas"]}
    assert sem["anual"]["meses_pagamento"] == [5]          # maio: pico da desmama
    assert sem["semestral"]["meses_pagamento"] == [5, 7]    # pico de cada semestre
    e = _fluxo("engorda")
    sem = {a["frequencia"]: a for a in e["recomendacao"]["alternativas"]}
    assert sem["anual"]["meses_pagamento"] == [8]          # agosto: pico do gordo


def test_sem_recomendacao_quando_nao_ha_vale_ou_nao_e_mensal():
    sem_vale = _fluxo("cria", capital_giro_inicial=400_000.0)
    assert sem_vale["meses_deficit"] == [] and sem_vale["recomendacao"] is None
    anual = _fluxo("cria", frequencia="anual", parcela_divida=300_000.0)
    assert anual["recomendacao"] is None
    assert anual["meses_pagamento"] == [5]


# ── bordas ──────────────────────────────────────────────────────────

def test_divida_zero_nao_divide_por_zero():
    r = _fluxo("cria", parcela_divida=0.0)
    assert r["dscr_anual"] is None
    assert r["dscr_anual_suficiente"] is True
    assert r["quebra_caixa_com_dscr_ok"] is False
    assert r["recomendacao"] is None
    assert r["totais"]["servico_divida"] == 0.0


def test_receita_zero():
    r = _fluxo("engorda", receita_anual=0.0)
    assert r["totais"]["entradas"] == 0.0
    assert r["dscr_anual"] < 0 and r["dscr_anual_suficiente"] is False
    assert r["vale_caixa"] == r["meses"][-1]["saldo_acumulado"]  # só afunda


def test_tudo_zero():
    r = _fluxo("recria", receita_anual=0, custo_operacional_anual=0, parcela_divida=0)
    assert r["vale_caixa"] == 0.0 and r["meses_deficit"] == []
    assert r["dscr_anual"] is None


def test_capital_de_giro_cobrindo_o_vale():
    base = _fluxo("cria")
    r = _fluxo("cria", capital_giro_inicial=-base["vale_caixa"])
    assert r["meses_deficit"] == []          # vale exatamente zerado não é déficit
    assert r["vale_caixa"] == pytest.approx(0.0)
    assert r["quebra_caixa_com_dscr_ok"] is False


def test_entrada_aceita_caixa_alta_e_espacos():
    r = _fluxo(" CICLO_COMPLETO ", frequencia="Mensal")
    assert r["sistema"] == "ciclo_completo" and r["frequencia"] == "mensal"


# ── validação ───────────────────────────────────────────────────────

@pytest.mark.parametrize("kw", [
    dict(sistema="pecuaria_leiteira"),
    dict(sistema=None),
    dict(sistema=3),
    dict(frequencia="trimestral"),
    dict(frequencia=None),
    dict(receita_anual=-1.0),
    dict(custo_operacional_anual=-0.01),
    dict(parcela_divida=-5),
    dict(capital_giro_inicial=-1),
    dict(receita_anual=float("nan")),
    dict(custo_operacional_anual=float("inf")),
    dict(parcela_divida="25000"),
    dict(receita_anual=None),
    dict(receita_anual=True),
    dict(receita_anual=VALOR_MAXIMO * 10),
])
def test_entradas_invalidas_levantam_valueerror(kw):
    with pytest.raises(ValueError):
        _fluxo(**kw)
