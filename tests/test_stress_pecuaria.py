import math
from dataclasses import FrozenInstanceError, replace

import numpy as np
import pytest

from services.payment_capacity_engine import dscr as dscr_mod
from services.stress_engine import (
    CENARIOS_PECUARIOS,
    BasePecuaria,
    ChoquePecuario,
    aplicar_choque,
    ponto_ruptura_arroba,
    simular_cenarios_pecuarios,
    simular_choque,
)
from services.stress_engine import pecuaria


def _base(**kw):
    # receita 1.000.000 (5.000 @ x R$ 200), custo 700.000, serviço 150.000
    dados = dict(
        arrobas_vendidas=5000,
        preco_arroba=200.0,
        custo_reposicao=400_000.0,
        custo_suplementacao=150_000.0,
        custo_outros=150_000.0,
        servico_divida=150_000.0,
    )
    dados.update(kw)
    return BasePecuaria(**dados)


# ---------------- cenários ----------------

def test_base_dscr_is_resultado_over_servico():
    r = simular_cenarios_pecuarios(_base())["base"]
    assert r.resultado == pytest.approx(300_000)
    assert r.dscr == pytest.approx(2.0)
    assert r.margem_liquida == pytest.approx(0.30)
    assert r.classificacao == "aprovar"


def test_named_scenarios_present_and_immutable():
    assert {
        "queda_arroba", "alta_reposicao", "seca_severa",
        "tesoura_margem_moderada", "tesoura_margem_severa",
    } <= set(CENARIOS_PECUARIOS)
    with pytest.raises(TypeError):
        CENARIOS_PECUARIOS["x"] = ChoquePecuario("x")
    with pytest.raises(FrozenInstanceError):
        CENARIOS_PECUARIOS["queda_arroba"].arroba_pct = 0


def test_queda_arroba_only_hits_revenue():
    b = _base()
    r = simular_choque(b, CENARIOS_PECUARIOS["queda_arroba"])
    assert r.receita == pytest.approx(850_000)
    assert r.custo == pytest.approx(b.custo)
    assert r.dscr == pytest.approx((850_000 - 700_000) / 150_000)
    assert r.classificacao == "ressalva"


def test_alta_reposicao_only_hits_replacement_cost():
    r = simular_choque(_base(), CENARIOS_PECUARIOS["alta_reposicao"])
    assert r.receita == pytest.approx(1_000_000)
    assert r.custo == pytest.approx(700_000 + 80_000)
    assert r.dscr == pytest.approx(220_000 / 150_000)


def test_seca_severa_cuts_volume_and_raises_supplement_but_not_replacement():
    b = _base()
    s = aplicar_choque(b, CENARIOS_PECUARIOS["seca_severa"])
    assert s.arrobas_vendidas == pytest.approx(4250)
    assert s.custo_reposicao == b.custo_reposicao
    assert s.custo_suplementacao == pytest.approx(195_000)
    r = simular_choque(b, CENARIOS_PECUARIOS["seca_severa"])
    assert r.resultado == pytest.approx(850_000 - 745_000)
    assert r.classificacao == "negar"


def test_tesoura_compound_is_worse_than_each_isolated_shock():
    b = _base()
    mod = simular_choque(b, CENARIOS_PECUARIOS["tesoura_margem_moderada"])
    sev = simular_choque(b, CENARIOS_PECUARIOS["tesoura_margem_severa"])
    isolados = [simular_choque(b, CENARIOS_PECUARIOS[n]).dscr
                for n in ("queda_arroba", "alta_reposicao", "alta_suplementacao")]
    assert mod.dscr < min(isolados)
    assert sev.dscr < mod.dscr
    assert sev.margem_liquida < mod.margem_liquida
    # moderada: receita 900k, custo 400k*1.15 + 150k*1.2 + 150k = 790k
    assert mod.resultado == pytest.approx(110_000)
    assert mod.classificacao == "negar"


def test_scenarios_do_not_mutate_base_and_return_all():
    b = _base()
    out = simular_cenarios_pecuarios(b)
    assert set(out) == {"base", *CENARIOS_PECUARIOS}
    assert b == _base()


def test_classification_uses_engine_thresholds(monkeypatch):
    # limites vêm do motor (dscr.py), não de literais locais
    assert pecuaria.DSCR_APROVAR is dscr_mod.DSCR_APROVAR
    assert pecuaria.DSCR_RESSALVA is dscr_mod.DSCR_RESSALVA
    b = _base(servico_divida=300_000)  # DSCR 1.0 exato
    assert simular_choque(b, ChoquePecuario("n")).classificacao == "ressalva"
    monkeypatch.setattr(pecuaria, "DSCR_RESSALVA", 1.1)
    assert simular_choque(b, ChoquePecuario("n")).classificacao == "negar"


def test_no_debt_has_no_dscr():
    r = simular_choque(_base(servico_divida=0), ChoquePecuario("n", arroba_pct=-50))
    assert r.dscr is None and r.classificacao == "sem_divida"


def test_zero_revenue_margin_is_none_without_division_error():
    r = simular_choque(_base(arrobas_vendidas=0), ChoquePecuario("n"))
    assert r.receita == 0 and r.margem_liquida is None
    assert r.dscr == pytest.approx(-700_000 / 150_000)
    assert r.classificacao == "negar"


def test_total_price_loss_allowed_at_minus_100():
    r = simular_choque(_base(), ChoquePecuario("n", arroba_pct=-100))
    assert r.receita == 0


# ---------------- ponto de ruptura ----------------

@pytest.mark.parametrize("kw", [
    {}, {"servico_divida": 40_000}, {"custo_outros": 0}, {"arrobas_vendidas": 123.456},
])
def test_breakeven_inverse_proof_hits_target_exactly(kw):
    b = _base(**kw)
    pr = ponto_ruptura_arroba(b)
    for rup, alvo in ((pr.ressalva, 1.00), (pr.aprovar, 1.30)):
        assert rup.dscr_alvo == alvo
        sub = replace(b, preco_arroba=rup.preco_minimo)
        dscr = (sub.receita - sub.custo) / sub.servico_divida
        assert dscr == pytest.approx(alvo, abs=1e-9)


def test_breakeven_known_values_and_margin():
    pr = ponto_ruptura_arroba(_base())
    # P* = (700k + T*150k)/5000
    assert pr.ressalva.preco_minimo == pytest.approx(170.0)
    assert pr.aprovar.preco_minimo == pytest.approx(179.0)
    assert pr.ressalva.margem_seguranca_pct == pytest.approx(15.0)
    assert pr.aprovar.margem_seguranca_pct == pytest.approx(10.5)
    assert pr.ressalva.status == "folga" and not pr.ressalva.em_ruptura
    # aprovar exige preço maior que ressalva
    assert pr.aprovar.preco_minimo > pr.ressalva.preco_minimo


def test_breakeven_matches_scenario_classification_boundary():
    b = _base()
    pr = ponto_ruptura_arroba(b)
    acima = replace(b, preco_arroba=pr.aprovar.preco_minimo * 1.001)
    abaixo = replace(b, preco_arroba=pr.aprovar.preco_minimo * 0.999)
    n = ChoquePecuario("n")
    assert simular_choque(acima, n).classificacao == "aprovar"
    assert simular_choque(abaixo, n).classificacao == "ressalva"


def test_breakeven_no_debt():
    pr = ponto_ruptura_arroba(_base(servico_divida=0))
    for rup in (pr.ressalva, pr.aprovar):
        assert rup.status == "sem_divida"
        assert rup.preco_minimo is None and rup.margem_seguranca_pct is None
        assert rup.em_ruptura is False


def test_breakeven_already_in_rupture_has_negative_margin():
    b = _base(custo_outros=450_000)  # custo 1.000k = receita; DSCR base 0
    pr = ponto_ruptura_arroba(b)
    assert pr.ressalva.status == "ja_em_ruptura" and pr.ressalva.em_ruptura
    assert pr.ressalva.margem_seguranca_pct < 0
    assert pr.ressalva.preco_minimo > b.preco_arroba
    assert pr.aprovar.margem_seguranca_pct < pr.ressalva.margem_seguranca_pct


def test_breakeven_exactly_at_limit_is_zero_margin_rupture():
    # P* ressalva = 170 → base com preço 170
    pr = ponto_ruptura_arroba(_base(preco_arroba=170.0))
    assert pr.ressalva.margem_seguranca_pct == 0.0
    assert pr.ressalva.em_ruptura is True
    assert pr.aprovar.status == "ja_em_ruptura"


def test_breakeven_zero_volume_no_division_by_zero():
    pr = ponto_ruptura_arroba(_base(arrobas_vendidas=0))
    assert pr.ressalva.status == "sem_volume"
    assert pr.ressalva.preco_minimo is None and pr.ressalva.em_ruptura


def test_breakeven_zero_base_price_has_no_percentage():
    pr = ponto_ruptura_arroba(_base(preco_arroba=0))
    assert pr.ressalva.preco_minimo == pytest.approx(170.0)
    assert pr.ressalva.margem_seguranca_pct is None
    assert pr.ressalva.em_ruptura


def test_breakeven_costs_exceed_revenue_and_zero_everything():
    pr = ponto_ruptura_arroba(_base(custo_outros=5_000_000))
    assert pr.ressalva.em_ruptura and pr.ressalva.margem_seguranca_pct < 0
    z = ponto_ruptura_arroba(BasePecuaria(0, 0, 0, 0, 0, 0))
    assert z.ressalva.status == "sem_divida"


def test_breakeven_under_stress_via_composition():
    b = _base()
    so_custos = ChoquePecuario("c", reposicao_pct=25, suplementacao_pct=20)
    base_est = aplicar_choque(b, so_custos)
    pr = ponto_ruptura_arroba(base_est)
    assert pr.ressalva.preco_minimo > ponto_ruptura_arroba(b).ressalva.preco_minimo


# ---------------- validação ----------------

@pytest.mark.parametrize("campo", [
    "arrobas_vendidas", "preco_arroba", "custo_reposicao",
    "custo_suplementacao", "custo_outros", "servico_divida",
])
@pytest.mark.parametrize("ruim", [float("nan"), float("inf"), -float("inf"), -1.0, "10", None, True])
def test_base_rejects_invalid(campo, ruim):
    with pytest.raises(ValueError):
        _base(**{campo: ruim})


@pytest.mark.parametrize("campo", ["arroba_pct", "reposicao_pct", "suplementacao_pct", "volume_pct"])
@pytest.mark.parametrize("ruim", [float("nan"), float("inf"), -100.01, -150, "5", None])
def test_choque_rejects_invalid(campo, ruim):
    with pytest.raises(ValueError):
        ChoquePecuario("n", **{campo: ruim})


def test_wrong_types_rejected():
    with pytest.raises(ValueError):
        simular_choque({"x": 1}, ChoquePecuario("n"))
    with pytest.raises(ValueError):
        simular_choque(_base(), {"arroba_pct": -10})
    with pytest.raises(ValueError):
        ponto_ruptura_arroba({"x": 1})


def test_numpy_scalars_accepted():
    b = BasePecuaria(
        np.int64(5000), np.float64(200.0), np.float32(400_000),
        np.float64(150_000), np.int32(150_000), np.float64(150_000),
    )
    r = simular_choque(b, ChoquePecuario("n", arroba_pct=np.float64(-10)))
    assert math.isfinite(r.dscr)
    assert ponto_ruptura_arroba(b).ressalva.preco_minimo == pytest.approx(170.0)


# ---------------- revisão: proveniência, tetos, chaves ----------------

def test_default_shocks_keep_policy_provenance():
    from services.proveniencia import e_parametro
    c = CENARIOS_PECUARIOS["tesoura_margem_severa"]
    assert e_parametro(c.arroba_pct) and c.arroba_pct == -20
    assert e_parametro(c.reposicao_pct) and e_parametro(c.volume_pct)


def test_caps_reject_overflow_and_tiny_divisors():
    with pytest.raises(ValueError):
        _base(preco_arroba=1e308, arrobas_vendidas=1e308)
    with pytest.raises(ValueError):
        _base(servico_divida=1e-320)
    with pytest.raises(ValueError):
        _base(arrobas_vendidas=1e-300)
    with pytest.raises(ValueError):
        ChoquePecuario("n", arroba_pct=1e6)


def test_scenario_key_rules():
    b = _base()
    with pytest.raises(ValueError):
        simular_cenarios_pecuarios(b, {"base": ChoquePecuario("base", arroba_pct=-50)})
    with pytest.raises(ValueError):
        simular_cenarios_pecuarios(b, {"x": ChoquePecuario("y")})


@pytest.mark.parametrize("nome", [None, "", "  ", 3])
def test_choque_name_validated(nome):
    with pytest.raises(ValueError):
        ChoquePecuario(nome)


def test_decimal_accepted():
    from decimal import Decimal
    b = _base(preco_arroba=Decimal("200.00"))
    assert b.preco_arroba == 200.0
    with pytest.raises(ValueError):
        _base(preco_arroba=Decimal("NaN"))
