"""Tela de Resultado refatorada: resumo executivo + 4 sub-abas, confiança em
escala correta, nenhum card de crédito vazio sem crédito ativo, e o modelo
intocado.

A parte de navegador (Playwright via Node, 1440x900 e 390x844) é pulada onde
não há Node/Playwright.
"""
import json
import re
import shutil
import subprocess
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
INDEX = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
JS = (ROOT / "static" / "orkavyn-dashboard.js").read_text(encoding="utf-8")
CSS = (ROOT / "static" / "orkavyn-dashboard.css").read_text(encoding="utf-8")

CORPO_VALORES = [10, 10, 8, 8, 6, 6, 30, 2, 40, 3]
SEM_CREDITO = {"valores": CORPO_VALORES, "preco": 320, "custo_arroba": 57}
COM_CREDITO = {**SEM_CREDITO, "credito_valor": 100000, "prazo_meses": 24, "juros_aa": 0.10}


def _cliente():
    import database as db
    from app import app
    db.init_db()
    email = f"res_{uuid.uuid4().hex[:10]}@example.com"
    db.criar_usuario(email, "Res", "senha123")
    uid = db.buscar_usuario_email(email)["id"]
    c = app.test_client()
    with c.session_transaction() as s:
        s["_user_id"] = str(uid)
    return c


def _classificar(c, payload):
    r = c.post("/api/classificar", json=payload)
    assert r.status_code == 200, r.status_code
    return r.get_json()


def _corpo(texto, inicio, fim):
    ini = texto.index(inicio)
    return texto[ini:texto.index(fim, ini)]


# ── estrutura da tela ────────────────────────────────────────────────────────

def test_resultado_tem_quatro_subabas_e_resumo_executivo():
    corpo = _corpo(INDEX, "function corpoResultado", "function renderResult(")
    for rotulo in ("Checklist", "Financeiro", "Rebanho &amp; Zootecnia", "Risco &amp; Auditoria"):
        assert rotulo in corpo, rotulo
    assert "renderResultTabs(abas" in corpo and "renderDecisionSummary(data)" in corpo
    # acessibilidade das abas
    tabs = _corpo(INDEX, "function renderResultTabs", "function rtAtivar")
    assert 'role="tablist"' in tabs and 'role="tab"' in tabs and 'role="tabpanel"' in tabs
    assert "aria-selected" in tabs and "ArrowRight" in INDEX
    # impressão mostra todas as abas
    assert ".rt-panel[hidden] { display: block !important; }" in CSS


def test_resumo_executivo_traz_identidade_selo_badges_alerta_e_kpis():
    corpo = _corpo(INDEX, "function renderDecisionSummary", "// ── Sub-abas do Resultado")
    for trecho in ("Sistema identificado", "cabeças", "badge('Rating'", "badge('Completude'",
                   "badge('Confiança'", 'role="alert"', "Preencher campos pendentes",
                   "Resultado operacional", "Crédito máx. (garantia)", "Desfrute anual", "COE calculado"):
        assert trecho in corpo, trecho
    assert "repeat(2, minmax(0, 1fr))" in CSS  # grid 2x2


def test_checklist_destaca_impeditivos_e_recolhe_pendentes_e_ok():
    corpo = _corpo(INDEX, "function renderDadosImpeditivos", "// ================== RETENÇÃO")
    assert "rt-imps" in corpo and "irParaCampo(" in corpo
    assert "dobravel(`${titulo} (${lista.length})`" in corpo
    assert "grupo('Pendentes'" in corpo and "grupo('OK'" in corpo
    assert 'ork-fold" open' not in corpo


def test_redundancias_do_rebanho_e_dos_ciclos_foram_removidas():
    # tira de 6 números do rebanho (repetia indicadores, distribuição e pirâmide)
    assert 'class="sstrip"' not in INDEX
    assert "Total Rebanho</div><div class=\"sc2-v" not in INDEX
    # seis cartões descrevendo todos os ciclos; agora só o identificado, uma vez
    assert "tipoCards" not in INDEX and 'class="tc-grid"' not in INDEX and 'class="tc"' not in INDEX
    assert INDEX.count("TD[") == 1
    # hero antigo repetia o tipo identificado
    assert 'class="rhero"' not in INDEX


def test_memoria_de_calculo_e_parametros_em_gaveta():
    gaveta = _corpo(INDEX, "function renderMemoriaGaveta", "function abrirMemoria")
    assert "<dialog" in gaveta and "memoriaPassos(" in gaveta and "Origem dos parâmetros e fontes" in gaveta
    assert "showModal" in INDEX and ".rt-drawer" in CSS


def test_justificativa_do_aprovado_continua_na_tela_e_impressao_leva_a_gaveta():
    # o hero esconde a justificativa quando a recomendação é "aprovar"
    assert 'c.recomendacao !== "aprovar"' in JS
    assert "c.recomendacao==='aprovar' && c.justificativa" in INDEX
    assert ".rt-drawer:not([open]) { display: block !important;" in CSS


def test_dock_e_padding_inferior_preservados():
    # layout da dock intocado: o mesmo bloco, a mesma folga no workspace
    assert "calc(96px + env(safe-area-inset-bottom))" in CSS
    assert "calc(128px + env(safe-area-inset-bottom))" in CSS


# ── confiança (42%, nunca 4200%) ─────────────────────────────────────────────

def test_confianca_do_front_nao_multiplica_por_100_de_novo():
    assert "const fPct100=" in INDEX
    assert "confianca_classificacao*100" not in INDEX
    assert "fPct100(x.confianca_classificacao)" in INDEX
    assert "${data.confianca}%" not in INDEX


def test_contexto_da_narrativa_envia_fracao_para_o_formatador_percentual():
    """O formatador usa :.0% (espera fração). O servidor mandava 0–100 e a
    narrativa dizia 'confiança ML: 4200%'."""
    import app as app_module
    from services.groq_narrativa import _contexto_str

    assert "confiança ML: 42%" in _contexto_str({"tipo": "CRIA", "confianca": 0.42})

    capturado = {}

    def falso(**kw):
        capturado.update(kw)
        return None

    mp = pytest.MonkeyPatch()
    try:
        mp.setattr(app_module, "_NARRATIVA_INLINE", True)
        mp.setattr(app_module, "_gerar_narrativa_groq", falso)
        dados = _classificar(_cliente(), COM_CREDITO)
    finally:
        mp.undo()
    assert 0 <= capturado["confianca"] <= 1
    assert abs(capturado["confianca"] * 100 - dados["confianca"]) < 1e-9
    # 98,3% vira "98%", nunca "9830%"
    assert not re.search(r"\d{3,}%", _contexto_str(capturado))


# ── sem crédito ativo ────────────────────────────────────────────────────────

def test_hero_nao_mostra_cards_de_credito_sem_credito_ativo():
    hero = _corpo(JS, "function montarHero", "function montarBanners")
    assert "const creditoAtivo = !!c.recomendacao;" in hero
    assert "creditoAtivo ? el(\"div\", { cls: \"od-hero__figures\" }" in hero
    assert "const kpis = creditoAtivo ? [k1, k2, k4] : [];" in hero
    assert "kpis.length ? el(\"div\", { cls: \"od-kpis\" }, kpis) : null" in hero


def test_api_sem_credito_nao_tem_recomendacao():
    """Premissa do front: sem solicitação, recomendacao é nula."""
    sem = _classificar(_cliente(), SEM_CREDITO)["parecer"]["conclusao"]
    com = _classificar(_cliente(), COM_CREDITO)["parecer"]["conclusao"]
    assert not sem.get("recomendacao")
    assert com.get("recomendacao")


# ── modelo e isolamento ──────────────────────────────────────────────────────

def test_gestao_model_pkl_inalterado_em_relacao_ao_commit():
    git = shutil.which("git")
    if not git:
        pytest.skip("git indisponível")
    pkl = ROOT / "gestao_model.pkl"
    if not pkl.exists():
        pytest.skip("modelo ausente")
    # contra o HEAD, não contra o index: um pkl alterado e já em `git add` falharia
    versionado = subprocess.run([git, "rev-parse", "HEAD:gestao_model.pkl"], cwd=ROOT,
                                capture_output=True, text=True)
    if versionado.returncode != 0:
        pytest.skip("pkl não versionado neste checkout")
    atual = subprocess.run([git, "hash-object", "gestao_model.pkl"], cwd=ROOT,
                           capture_output=True, text=True).stdout.strip()
    assert atual == versionado.stdout.strip(), "gestao_model.pkl foi alterado (hash difere do HEAD)"


def test_refatoracao_nao_toca_casos_reais_nem_formulas():
    """A mudança é de apresentação: a tela só LÊ o payload da classificação."""
    corpo = _corpo(INDEX, "function corpoResultado", "function renderResult(")
    assert "casos_reais" not in corpo and "criar_caso_real" not in corpo
    assert "fetch(" not in corpo


# ── navegador: 1440x900 e 390x844 ────────────────────────────────────────────

def _node_playwright():
    node = shutil.which("node")
    if not node:
        return None
    ok = subprocess.run([node, "-e", "require('playwright')"], capture_output=True)
    return node if ok.returncode == 0 else None


def test_resultado_em_navegador_sem_overflow_nos_dois_viewports(tmp_path):
    node = _node_playwright()
    if not node:
        pytest.skip("Node/Playwright indisponível")
    c = _cliente()
    html = c.get("/app")
    assert html.status_code == 200
    site, shots = tmp_path / "site", tmp_path / "shots"
    site.mkdir(), shots.mkdir()
    (site / "index.html").write_bytes(html.data)
    shutil.copytree(ROOT / "static", site / "static")
    com, sem = tmp_path / "com.json", tmp_path / "sem.json"
    com.write_text(json.dumps(_classificar(c, COM_CREDITO)))
    sem.write_text(json.dumps(_classificar(c, SEM_CREDITO)))
    r = subprocess.run([node, str(ROOT / "tests" / "browser" / "resultado_layout.js"),
                        str(site), str(shots), str(com), str(sem)],
                       capture_output=True, text=True, timeout=180)
    assert r.returncode == 0, r.stdout + r.stderr
    assert len([ln for ln in r.stdout.splitlines() if " OK " in ln]) == 4, r.stdout
