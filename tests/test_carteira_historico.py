"""Histórico em visão de carteira (revenda): resumo lido do parecer salvo,
endpoint isolado por empresa, registros antigos/parciais com '—' e layout.

Nenhuma regra de crédito é recalculada: o resumo só lê o JSON persistido.
"""
import json
import shutil
import subprocess
import uuid
from pathlib import Path

import pytest

import database as db
from app import app
from services.carteira import resumo_parecer

ROOT = Path(__file__).parents[1]
INDEX = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
CSS = (ROOT / "static" / "orkavyn-dashboard.css").read_text(encoding="utf-8")

PARECER_COMPLETO = {
    "conclusao": {"recomendacao": "ressalva", "dscr": 1.1, "dscr_minimo": 1.05,
                  "anos_avaliados": 5, "justificativa": "DSCR mínimo 1,05 no ano 3."},
    "rating": {"faixa": "B", "score": 72},
    "consistencia": {"resumo": {"erros": 1}},
    "estresse_pecuario": {
        "disponivel": True, "avisos": ["Aviso de estresse A"],
        "ponto_ruptura_arroba": {"ressalva": {
            "preco_minimo": 248.5, "preco_base": 300.0,
            "queda_maxima_suportada_pct": 17.2, "em_ruptura": False}}},
    "ciclo_pecuario": {"disponivel": True, "vale_caixa": -85000.0, "mes_vale": 10,
                       "meses_deficit": [9, 10, 11], "quebra_caixa_com_dscr_ok": True},
}
SOLIC = {"credito_valor": 900000, "prazo_meses": 60}


def test_resumo_completo():
    r = resumo_parecer(json.dumps(PARECER_COMPLETO), json.dumps(SOLIC))
    assert r["dscr_minimo"] == 1.05 and r["rating_faixa"] == "B" and r["rating_score"] == 72
    assert r["ruptura"] == {"preco_minimo": 248.5, "preco_base": 300.0,
                            "folga_pct": 17.2, "em_ruptura": False}
    assert r["vale_caixa"]["tem_vale"] is True and r["vale_caixa"]["valor"] == 85000.0
    assert r["vale_caixa"]["mes"] == "out" and r["vale_caixa"]["meses_deficit"] == 3
    assert r["prazo_meses"] == 60 and r["anos_avaliados"] == 5
    assert r["ressalvas_total"] == 2 and r["ressalvas"][0].startswith("DSCR mínimo")
    assert r["erros_consistencia"] == 1 and r["credito_valor"] == 900000


@pytest.mark.parametrize("bruto", [
    '{"conclusao": {"recomendacao": "aprovar", "dscr": 1.5}}',  # registro antigo
    "{}", "", None, "não é json", "[1,2]", '{"conclusao": "x", "rating": 5}',
    '{"estresse_pecuario": {"disponivel": false}, "ciclo_pecuario": {"disponivel": false}}',
])
def test_resumo_antigo_ou_malformado_nao_quebra_e_devolve_none(bruto):
    r = resumo_parecer(bruto, None)
    assert r["ruptura"] is None and r["vale_caixa"] is None
    assert r["rating_faixa"] is None and r["prazo_meses"] is None
    assert r["ressalvas_total"] == 0 and r["erros_consistencia"] is None


def test_resumo_sem_vale_e_em_ruptura_e_numeros_invalidos():
    p = {"estresse_pecuario": {"disponivel": True, "ponto_ruptura_arroba": {"ressalva": {
             "preco_minimo": 320, "preco_base": 300, "queda_maxima_suportada_pct": "x",
             "em_ruptura": True}}},
         "ciclo_pecuario": {"disponivel": True, "meses_deficit": [], "vale_caixa": float("nan"),
                            "mes_vale": 99}}
    r = resumo_parecer(p, {"prazo_meses": True})
    assert r["ruptura"]["em_ruptura"] is True and r["ruptura"]["folga_pct"] is None
    assert r["vale_caixa"] == {"tem_vale": False, "valor": None, "mes": None,
                               "meses_deficit": 0, "quebra_com_dscr_ok": False}
    assert r["prazo_meses"] is None


def _login(nome):
    db.init_db()
    email = f"{nome}-{uuid.uuid4().hex[:8]}@example.com"
    db.criar_usuario(email, nome, "senha123")
    u = db.buscar_usuario_email(email)
    c = app.test_client()
    with c.session_transaction() as s:
        s["_user_id"] = str(u["id"])
    return c, u, db.empresas_do_usuario(u["id"])[0]["id"]


def test_api_carteira_completa_antiga_e_sem_parecer():
    c, u, eid = _login("Carteira")
    f1 = db.criar_fazenda("Faz Completa", empresa_id=eid, criado_por=u["id"])
    f2 = db.criar_fazenda("Faz Antiga", empresa_id=eid, criado_por=u["id"])
    f3 = db.criar_fazenda("Faz Sem Parecer", empresa_id=eid, criado_por=u["id"])
    db.salvar_parecer(u["id"], f1, {"credito_valor": 1}, {"conclusao": {"recomendacao": "negar", "dscr": 0.5}})
    db.salvar_parecer(u["id"], f1, SOLIC, PARECER_COMPLETO)  # o último vale
    db.salvar_parecer(u["id"], f2, {}, {"conclusao": {"recomendacao": "aprovar", "dscr": 1.5}})
    r = c.get("/api/carteira")
    assert r.status_code == 200
    por_id = {x["fazenda_id"]: x for x in r.get_json()["carteira"]}
    assert set(por_id) == {f1, f2, f3}
    assert por_id[f1]["recomendacao"] == "ressalva"
    assert por_id[f1]["resumo"]["ruptura"]["folga_pct"] == 17.2
    assert por_id[f2]["recomendacao"] == "aprovar"
    assert por_id[f2]["resumo"]["ruptura"] is None and por_id[f2]["resumo"]["vale_caixa"] is None
    assert por_id[f3]["recomendacao"] is None and por_id[f3]["resumo"] is None


def test_api_carteira_isolada_por_empresa_e_exige_login():
    c1, u1, e1 = _login("EmpA")
    c2, u2, e2 = _login("EmpB")
    fa = db.criar_fazenda("Faz Da A", empresa_id=e1, criado_por=u1["id"])
    db.salvar_parecer(u1["id"], fa, SOLIC, PARECER_COMPLETO)
    ids_b = {x["fazenda_id"] for x in c2.get("/api/carteira").get_json()["carteira"]}
    assert fa not in ids_b
    assert app.test_client().get("/api/carteira").status_code in (401, 302)


def test_api_pareceres_traz_resumo_e_mantem_campos_antigos():
    c, u, eid = _login("ParecResumo")
    fid = db.criar_fazenda("Faz R", empresa_id=eid, criado_por=u["id"])
    db.salvar_parecer(u["id"], fid, SOLIC, PARECER_COMPLETO)
    db.salvar_parecer(u["id"], fid, {}, {"conclusao": {"recomendacao": "aprovar", "dscr": 1.5}})
    itens = c.get(f"/api/fazendas/{fid}/pareceres").get_json()["pareceres"]
    assert {"id", "solicitacao", "parecer", "recomendacao", "dscr", "created_at"} <= set(itens[0])
    assert itens[0]["resumo"]["vale_caixa"] is None            # antigo/parcial
    assert itens[1]["resumo"]["vale_caixa"]["mes"] == "out"    # completo


def test_frontend_carteira_escapa_saida_e_usa_traco_de_fallback():
    for ident in ('id="cart-busca"', 'id="cart-resumo"', 'id="cart-lista"',
                  'id="hist-fazenda-id"', 'id="hist-lista"', "carregarHistoricoPareceres",
                  "baixarPdfParecerHistorico", "carregarCarteira"):
        assert ident in INDEX
    assert "escapeHtml(c.nome||'—')" in INDEX
    assert "if(id==='historico'" in INDEX
    assert ".ork-cart-item" in CSS and "min-width: 0" in CSS


def _node_playwright():
    node = shutil.which("node")
    if not node:
        return None
    ok = subprocess.run([node, "-e", "require('playwright')"], capture_output=True)
    return node if ok.returncode == 0 else None


def test_carteira_em_navegador_sem_overflow_nos_dois_viewports(tmp_path):
    node = _node_playwright()
    if not node:
        pytest.skip("Node/Playwright indisponível")
    site, shots = tmp_path / "site", tmp_path / "shots"
    site.mkdir(), shots.mkdir()
    c, _, _ = _login("UiCart")
    r = c.get("/app")
    assert r.status_code == 200
    (site / "index.html").write_bytes(r.data)
    shutil.copytree(ROOT / "static", site / "static")
    out = subprocess.run([node, str(ROOT / "tests" / "browser" / "carteira_layout.js"), str(site), str(shots)],
                         capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stdout + out.stderr
    assert len([l for l in out.stdout.splitlines() if " OK " in l]) == 4, out.stdout
