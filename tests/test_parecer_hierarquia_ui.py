"""Hierarquia e densidade do parecer na tela: resumo executivo no topo, blocos
densos recolhíveis e nulos como '—' (mesmo padrão do PDF).

Checagens estáticas + uma verificação em navegador (Playwright via Node) em
1440x900 e 390x844, temas claro e escuro, sem overflow horizontal e com o dock
flutuante dentro da viewport. A parte de navegador é pulada onde não há
Node/Playwright.
"""
import json
import shutil
import subprocess
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
INDEX = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
CSS = (ROOT / "static" / "orkavyn-dashboard.css").read_text(encoding="utf-8")
JS = (ROOT / "static" / "orkavyn-dashboard.js").read_text(encoding="utf-8")


def test_hero_traz_prazo_e_ressalvas_na_primeira_dobra():
    assert '"Prazo avaliado"' in JS and "anos_avaliados" in JS
    assert "ressalvasHero(parecer)" in JS and "Principais ressalvas" in JS
    # sem dado: '—', como o PDF
    assert 'kpi("Prazo avaliado", "—"' in JS
    assert 'el("div", { cls: "od-hero__notes-empty", text: "—" })' in JS


def test_blocos_densos_ficam_recolhidos_por_padrao():
    assert "const dobravel=" in INDEX
    # checklist: pendentes e OK recolhidos; projeção e sensibilidade viraram
    # conteúdo das sub-abas; a origem dos parâmetros mora na gaveta
    assert "dobravel(`${titulo} (${lista.length})`" in INDEX
    assert "Origem dos parâmetros e fontes" in INDEX and 'id="dlg-memoria"' in INDEX
    # SHAP assíncrono: o card final vira <details>, o placeholder segue com id
    assert 'class="ork-fold ork-fold--shap"' in INDEX
    assert 'id="card-shap"' in INDEX
    # nunca abre sozinho
    assert "<details class=\"ork-fold\" open" not in INDEX
    assert ".ork-fold > summary" in CSS and ".od-hero__notes" in CSS


def test_memoria_de_calculo_continua_recolhida():
    assert "Recolhido por padrão" in INDEX


def test_rotulos_de_nulo_alinhados_ao_pdf():
    assert "const fVazio=" in INDEX
    assert "fVazio(d.valor)" in INDEX
    assert "a.margem_pct != null ? a.margem_pct + '%' : '—'" in INDEX
    assert "'Não informadas'" not in INDEX and "'Nenhuma registrada'" not in INDEX


def _logado_html(tmp_path):
    import database as db
    from app import app
    db.init_db()
    email = f"ui_{uuid.uuid4().hex[:10]}@example.com"
    db.criar_usuario(email, "UI", "senha123")
    uid = db.buscar_usuario_email(email)["id"]
    c = app.test_client()
    with c.session_transaction() as s:
        s["_user_id"] = str(uid)
    r = c.get("/app")
    assert r.status_code == 200
    (tmp_path / "index.html").write_bytes(r.data)
    shutil.copytree(ROOT / "static", tmp_path / "static")


def _node_playwright():
    node = shutil.which("node")
    if not node:
        return None
    ok = subprocess.run([node, "-e", "require('playwright')"], capture_output=True)
    return node if ok.returncode == 0 else None


def test_parecer_em_navegador_sem_overflow_nos_dois_viewports(tmp_path):
    node = _node_playwright()
    if not node:
        pytest.skip("Node/Playwright indisponível")
    site, shots = tmp_path / "site", tmp_path / "shots"
    site.mkdir(), shots.mkdir()
    _logado_html(site)
    r = subprocess.run([node, str(ROOT / "tests" / "browser" / "parecer_layout.js"), str(site), str(shots)],
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stdout + r.stderr
    linhas = [l for l in r.stdout.splitlines() if " OK " in l]
    assert len(linhas) == 4, r.stdout


def test_formatadores_nao_fabricam_nan_nem_zero():
    assert "const fR=n=>_numOk(n)?" in INDEX and "const fN=n=>_numOk(n)?" in INDEX


def test_impressao_abre_os_blocos_recolhidos():
    assert 'addEventListener("beforeprint"' in JS and 'addEventListener("afterprint"' in JS
    assert "@media print" in CSS and "content: none" in CSS
