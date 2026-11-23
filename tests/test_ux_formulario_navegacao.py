"""UX do formulário e da navegação: menu "Mais opções", blocos opcionais
recolhíveis, feedback do trio do estresse, cards da faixa etária no mobile,
folga do dock e saudação sem identificador bruto.

Checagens estáticas + renderização do template + uma verificação em navegador
(Playwright via Node) em 1440x900 e 390x844, temas claro e escuro, sem overflow
horizontal. A parte de navegador é pulada onde não há Node/Playwright.
"""
import re
import subprocess
from pathlib import Path

import pytest

from tests.test_parecer_hierarquia_ui import _logado_html, _node_playwright

ROOT = Path(__file__).parents[1]
INDEX = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
CSS = (ROOT / "static" / "orkavyn-dashboard.css").read_text(encoding="utf-8")
JS = (ROOT / "static" / "orkavyn-dashboard.js").read_text(encoding="utf-8")


def test_acoes_secundarias_da_faixa_etaria_ficam_no_menu_mais_opcoes():
    menu = INDEX[INDEX.index('<details class="od-more"'):INDEX.index("</details>", INDEX.index('<details class="od-more"'))]
    assert "Mais opções ▾" in menu
    for secundaria in ("/api/template/download", "/api/ficha/download", "/api/ficha/instrucoes", "toggleGuiaFicha"):
        assert secundaria in menu, secundaria
    barra = INDEX[INDEX.index('<div class="od-actions">'):INDEX.index('<details class="od-more"')]
    for primaria in ("lerPlanilha", "pdf-inp-main", "insr-ficha-inp", "clearAll"):
        assert primaria in barra, primaria
    # O seletor de UF do PDF e os handlers de importação continuam intactos.
    assert re.search(r'<select id="insr-uf-ficha"', INDEX)


def test_nav_legada_usa_os_mesmos_rotulos_do_dock():
    for rotulo in ("Nova análise", "Cenários", "Lavoura perene"):
        assert f">{rotulo}</button>" in INDEX
    assert ">Inserir Dados</button>" not in INDEX and ">Simular Cenários</button>" not in INDEX


def test_aviso_gep_mantem_o_texto_e_some_com_desembolso_informado():
    assert 'id="aviso-gep-padrao"' in INDEX
    assert "Usa o desembolso padrão (GEP médio) se você não informar o do produtor" in INDEX
    assert 'getElementById("c-desemb")' in JS and 'getElementById("aviso-gep-padrao")' in JS


def test_blocos_opcionais_recolhiveis_com_aria_e_sem_innerhtml():
    for n in (2, 3):
        assert f'id="od-b{n}-body"' in INDEX and f'id="od-b{n}"' in INDEX
    assert "aria-controls" in JS and "aria-expanded" in JS
    novo = JS[JS.index("function iniciarMaisOpcoes"):JS.index("// ── payload")]
    assert "innerHTML" not in novo
    assert '"aria-describedby"' in novo  # nome acessível do botão: título do bloco
    assert '"aria-live"' not in novo  # só #od-estresse-status é região ao vivo
    # Erro de validação num bloco recolhido o reabre antes de focar o campo.
    assert "OrkavynDash.revelarCampo(_novos.campo)" in INDEX


def test_estresse_parcial_tem_feedback_e_trio_continua_exigido():
    assert re.search(r'<p[^>]*id="od-estresse-status"[^>]*role="status"[^>]*aria-live="polite"', INDEX)
    assert ".od-field--missing" in CSS and ".od-field--ok" in CSS
    # Regra do payload preservada: envio parcial continua barrado no cliente.
    assert "preencha os três campos juntos" in JS


def test_dock_nao_cobre_conteudo_no_mobile_e_tabela_vira_cards():
    assert re.search(r"@media \(max-width: 600px\) \{\s*\.ork-dashboard-surface \.ork-workspace \{ padding-bottom: calc\(128px", CSS)
    assert "content: attr(data-label)" in CSS
    for rotulo in ("Fêmeas", "Machos", "Total faixa", "% Rebanho"):
        assert f'data-label="{rotulo}"' in INDEX


def _saudacao(usuario):
    """Renderiza só o <h1> da capa com o mesmo trecho Jinja do template (o
    client de teste da suíte injeta um usuário próprio, então não dá para
    depender do /app para controlar o nome)."""
    from jinja2 import Environment
    h1 = re.search(r'<h1 class="od-cover__title".*?</h1>', INDEX, re.S).group(0)
    from app import primeiro_nome_exibicao
    primeiro = primeiro_nome_exibicao(usuario.get("nome"), usuario.get("email"))
    return Environment(autoescape=True).from_string(h1).render(usuario=usuario, primeiro_nome=primeiro)


def test_saudacao_usa_primeiro_nome_e_nunca_o_email():
    s = _saudacao({"nome": "Maria Souza", "email": "maria.souza@example.com"})
    assert "Maria" in s and "Souza" not in s and "@" not in s and "maria.souza" not in s
    for sem_nome in ({"nome": "", "email": "joao123@example.com"}, {"nome": None, "email": "joao123@example.com"}):
        s2 = _saudacao(sem_nome)
        assert "joao123" not in s2 and "@" not in s2 and s2.strip().endswith(".</h1>")
    assert "<script>" not in _saudacao({"nome": "<script>x</script>", "email": "a@b.c"})
    # Nome digitado como e-mail no cadastro também não aparece.
    s3 = _saudacao({"nome": "joao@x.com", "email": "joao@x.com"})
    assert "@" not in s3 and "joao" not in s3


def test_formulario_em_navegador_sem_overflow_nos_dois_viewports(tmp_path):
    node = _node_playwright()
    if not node:
        pytest.skip("Node/Playwright indisponível")
    site, shots = tmp_path / "site", tmp_path / "shots"
    site.mkdir(), shots.mkdir()
    _logado_html(site)
    r = subprocess.run([node, str(ROOT / "tests" / "browser" / "formulario_layout.js"), str(site), str(shots)],
                       capture_output=True, text=True, timeout=180)
    assert r.returncode == 0, r.stdout + r.stderr
    assert len([l for l in r.stdout.splitlines() if " OK " in l]) == 4, r.stdout
