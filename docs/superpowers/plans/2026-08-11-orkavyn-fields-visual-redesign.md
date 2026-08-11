# Orkavyn Fields Visual Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild every Orkavyn Agro Intelligence page with the approved Fields Executivo visual system while preserving all existing behavior, selectors, routes, calculations, document imports and accessibility contracts.

**Architecture:** Add one shared Fields stylesheet and a small shell controller, then migrate templates incrementally rather than rewriting the Flask application. Preserve the large `index.html` JavaScript contract by keeping critical IDs and functions unchanged, introducing Jinja partials only for repeated navigation. Complete and review the already-uncommitted report/demo work before the visual migration so later tasks start from a clean, testable baseline.

**Tech Stack:** Python 3.11, Flask/Jinja2, semantic HTML, CSS custom properties, vanilla JavaScript, ReportLab, pytest, existing Flask test client, local browser verification.

## Global Constraints

- Preserve every existing endpoint and API response contract.
- Preserve JavaScript-critical IDs, event handlers and upload/classification behavior.
- Use the Organic anchor only: forest, moss, sage, sand, oat, clay and soil tokens; no pure-white dashboard surfaces, cold-gray system or decorative gradients.
- Desktop uses a fixed 240–272 px sidebar; mobile uses bottom navigation and 44 px minimum touch targets.
- Keep one dominant action per screen and attach the evidence ribbon to headline decisions.
- Never present fictitious demonstration data as real customer data.
- Keep motion below 300 ms and honor `prefers-reduced-motion`.
- Do not add a frontend framework or new icon dependency.
- Existing uncommitted changes in `app.py`, `services/parecer_pdf.py` and `templates/index.html` belong to Task 1 and must not be discarded.

---

### Task 1: Finish and isolate the pending B2B report/demo baseline

**Files:**
- Create: `templates/demo.html`
- Create: `tests/test_report_v1.py`
- Modify: `app.py:920-1046`
- Modify: `services/parecer_pdf.py:66-243`
- Modify: `templates/index.html:20-440`

**Interfaces:**
- Consumes: `database.load_analysis_snapshot(analysis_id, organization_id)` and `gerar_pdf_parecer(parecer, branding=None)`.
- Produces: authenticated `GET /api/analysis/<id>`, authenticated `GET /api/report/<id>`, public `GET /demo`, and B2B PDF sections without changing the legacy PDF endpoint.

- [ ] **Step 1: Write characterization tests for the current uncommitted routes and PDF sections**

```python
def test_demo_is_visibly_fictitious(client):
    response = client.get('/demo')
    assert response.status_code == 200
    assert b'DEMONSTRA' in response.data.upper()
    assert b'FICT' in response.data.upper()

def test_report_snapshot_requires_login(client):
    response = client.get('/api/report/1')
    assert response.status_code in (302, 401)

def test_pdf_contains_b2b_section_titles(sample_parecer):
    pdf = gerar_pdf_parecer(sample_parecer)
    assert pdf.startswith(b'%PDF')
    for label in ('Resumo executivo', 'Qualidade dos dados', 'Limitações'):
        assert label in _extract_pdf_text(pdf)
```

- [ ] **Step 2: Run the tests and confirm the missing demo template or incomplete integration fails**

Run: `pytest -q tests/test_report_v1.py tests/test_parecer_pdf.py tests/test_parecer_pdf_endpoint.py`

Expected: at least the demo/template assertion fails before `templates/demo.html` exists.

- [ ] **Step 3: Implement the minimal demo template and remove unsafe PDF syntax**

Create `templates/demo.html` with a visible `MODO DEMONSTRAÇÃO — DADOS FICTÍCIOS` banner and render only `demo_report` values passed by Flask. In `services/parecer_pdf.py`, replace the assignment expression inside the formatted string with a normal local variable so the PDF code remains compatible and readable:

```python
arrobas_vendidas = fluxo_gep.get('arrobas_vendidas', '—')
story.append(Paragraph(
    f"Arrobas vendidas: <b>{arrobas_vendidas}</b> · "
    f"Produz/vende: <b>{_fmt_pct(fluxo_gep.get('producao_sobre_venda_pct'))}</b>",
    ss['Corpo'],
))
```

- [ ] **Step 4: Verify organization isolation and legacy PDF compatibility**

Run: `pytest -q tests/test_report_v1.py tests/test_analysis_pipeline.py tests/test_parecer_pdf.py tests/test_parecer_pdf_endpoint.py`

Expected: PASS.

- [ ] **Step 5: Commit only the pending baseline**

```powershell
git add app.py services/parecer_pdf.py templates/index.html templates/demo.html tests/test_report_v1.py
git commit -m "feat: complete b2b report and demo baseline"
```

---

### Task 2: Add the shared Fields design system and selector contract

**Files:**
- Create: `static/orkavyn-fields.css`
- Create: `static/orkavyn-shell.js`
- Create: `templates/partials/fields_sidebar.html`
- Create: `templates/partials/fields_mobile_nav.html`
- Create: `tests/test_ui_fields_contract.py`
- Create: `.interface-design/system.md`

**Interfaces:**
- Produces: `.ork-shell`, `.ork-sidebar`, `.ork-workspace`, `.ork-page-header`, `.ork-panel`, `.ork-field`, `.ork-action`, `.ork-evidence-ribbon`, `[data-ork-nav]`, `window.OrkavynShell.init()`.
- Preserves: native button/link/input semantics and the page-specific JavaScript functions named in existing templates.

- [ ] **Step 1: Write failing token and partial tests**

```python
from pathlib import Path

ROOT = Path(__file__).parents[1]

def test_fields_stylesheet_defines_domain_tokens():
    css = (ROOT / 'static' / 'orkavyn-fields.css').read_text(encoding='utf-8')
    for token in ('--ork-forest', '--ork-moss', '--ork-sage', '--ork-sand',
                  '--ork-oat', '--ork-clay', '--ork-soil', '--ork-ink'):
        assert token in css

def test_shell_has_mobile_and_desktop_navigation():
    sidebar = (ROOT / 'templates' / 'partials' / 'fields_sidebar.html').read_text(encoding='utf-8')
    mobile = (ROOT / 'templates' / 'partials' / 'fields_mobile_nav.html').read_text(encoding='utf-8')
    assert 'aria-label="Navegação principal"' in sidebar
    assert 'aria-label="Navegação móvel"' in mobile
```

- [ ] **Step 2: Run the new contract test and confirm missing files fail**

Run: `pytest -q tests/test_ui_fields_contract.py`

Expected: FAIL with `FileNotFoundError` for `static/orkavyn-fields.css`.

- [ ] **Step 3: Implement the approved Organic token foundation**

The stylesheet begins with these exact semantic primitives and derives all component colors from them:

```css
:root {
  --ork-forest: #173a2a;
  --ork-moss: #606c38;
  --ork-sage: #8b9d83;
  --ork-sand: #e8dcc7;
  --ork-oat: #d4b895;
  --ork-clay: #b08b6e;
  --ork-soil: #765038;
  --ork-ink: #203127;
  --ork-copy: #647067;
  --ork-danger: #9b4f42;
  --ork-warning: #a87631;
  --ork-space: 4px;
  --ork-radius-control: 10px;
  --ork-radius-panel: 20px;
  --ork-sidebar-width: 256px;
}
```

Add only shared geometry and states in this task: typography, focus rings, buttons, inputs, panels, shell, sidebar, mobile navigation, loading, empty, warning and error surfaces. Do not style page-specific result blocks yet.

- [ ] **Step 4: Implement the shell controller with no duplicated business logic**

```javascript
window.OrkavynShell = {
  init() {
    const toggle = document.querySelector('[data-sidebar-toggle]');
    const shell = document.querySelector('.ork-shell');
    if (!toggle || !shell) return;
    toggle.addEventListener('click', () => {
      const open = shell.classList.toggle('is-sidebar-open');
      toggle.setAttribute('aria-expanded', String(open));
    });
  }
};
document.addEventListener('DOMContentLoaded', () => window.OrkavynShell.init());
```

- [ ] **Step 5: Document the approved system**

Write `.interface-design/system.md` with Organic direction, subtle-shadow depth, 4 px spacing, type hierarchy, 256 px desktop sidebar, 44 px touch target, evidence ribbon pattern, and the exact tokens above.

- [ ] **Step 6: Run tests and commit**

Run: `pytest -q tests/test_ui_fields_contract.py tests/test_marca_orkavyn.py`

```powershell
git add static/orkavyn-fields.css static/orkavyn-shell.js templates/partials .interface-design/system.md tests/test_ui_fields_contract.py
git commit -m "feat: add Orkavyn Fields design system"
```

---

### Task 3: Build the desktop sidebar and responsive app shell

**Files:**
- Modify: `templates/index.html:1-520`
- Modify: `templates/admin.html`
- Modify: `static/orkavyn-fields.css`
- Modify: `tests/test_ui_fields_contract.py`

**Interfaces:**
- Consumes: Fields partials and `window.OrkavynShell.init()` from Task 2.
- Produces: responsive navigation that calls existing `showTab(name, button)` and retains `empresa-ativa-select`, admin access, branding and logout controls.

- [ ] **Step 1: Add failing assertions for critical selectors and navigation semantics**

```python
def test_index_shell_preserves_critical_controls():
    html = (ROOT / 'templates' / 'index.html').read_text(encoding='utf-8')
    for selector in ('id="empresa-ativa-select"', 'id="pdf-inp-main"',
                     'id="tab-res"', 'id="tab-cen"', 'id="loading-ov"'):
        assert selector in html
    assert "{% include 'partials/fields_sidebar.html' %}" in html
    assert "{% include 'partials/fields_mobile_nav.html' %}" in html
```

- [ ] **Step 2: Run the selector test before changing the shell**

Run: `pytest -q tests/test_ui_fields_contract.py tests/test_frontend_pdf_upload.py`

Expected: FAIL on missing includes while existing selector assertions remain green.

- [ ] **Step 3: Replace only the outer header/tab chrome**

Wrap the existing panels in:

```html
<div class="ork-shell">
  {% include 'partials/fields_sidebar.html' %}
  <div class="ork-workspace">
    <header class="ork-context-header">...</header>
    <main id="ork-main-content">existing panels unchanged</main>
  </div>
  {% include 'partials/fields_mobile_nav.html' %}
</div>
```

Sidebar links use `type="button" data-ork-nav="entrada" onclick="showTab('entrada', this)"` so they call the existing function. Keep the old `.tab-btn` elements in the DOM as a visually hidden compatibility tablist until result/cenario unlocking is migrated and tested.

- [ ] **Step 4: Add responsive shell rules**

At `min-width: 901px`, reserve `var(--ork-sidebar-width)` and hide bottom navigation. At `max-width: 900px`, make content one column, hide the fixed sidebar by default, show the 64 px bottom navigation and add safe bottom padding. At `max-width: 480px`, keep 16 px page gutters and prevent header controls from overflowing.

- [ ] **Step 5: Verify app and admin pages render**

Run: `pytest -q tests/test_ui_fields_contract.py tests/test_frontend_pdf_upload.py tests/test_admin_acesso.py tests/test_empresa_ativa.py`

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add templates/index.html templates/admin.html static/orkavyn-fields.css tests/test_ui_fields_contract.py
git commit -m "feat: add Fields application shell"
```

---

### Task 4: Redesign document import, herd entry and credit forms

**Files:**
- Modify: `templates/index.html:500-1000`
- Modify: `static/orkavyn-fields.css`
- Modify: `tests/test_frontend_pdf_upload.py`
- Modify: `tests/test_ui_fields_contract.py`

**Interfaces:**
- Preserves: `lerPDFs(files)`, `lerPlanilha(file)`, `fillEx(tipo)`, `_previaNivel()`, `addCredor()`, `novaFazendaPrompt()` and every input ID used by `/api/classificar` payload construction.
- Produces: primary document importer with manual and spreadsheet alternatives, visible import states and grouped advanced fields.

- [ ] **Step 1: Extend import tests before moving markup**

```python
def test_primary_import_control_keeps_multiple_pdf_contract():
    html = TEMPLATE.read_text(encoding='utf-8')
    assert 'id="pdf-inp-main"' in html
    assert 'accept=".pdf"' in html
    assert 'multiple' in html
    assert 'onchange="lerPDFs(this.files)' in html

def test_import_status_is_accessible():
    html = TEMPLATE.read_text(encoding='utf-8')
    assert 'id="pdf-status-main"' in html
    assert 'aria-live="polite"' in html
```

- [ ] **Step 2: Run tests and confirm the missing live-region assertion fails**

Run: `pytest -q tests/test_frontend_pdf_upload.py tests/test_ui_fields_contract.py`

- [ ] **Step 3: Build the primary import panel without changing input contracts**

Use one `.ork-panel.ork-import-panel` with the existing hidden file inputs. The visible primary button triggers `pdf-inp-main`; secondary buttons trigger the spreadsheet and manual sections. Keep UF/model correction controls adjacent to import review, not in the headline action row.

- [ ] **Step 4: Group forms by decision sequence**

Order the existing blocks as property → document/import → herd composition → productive parameters → credit request → existing debt → guarantees. Mark advanced assumptions with native `<details>` and `<summary>` only when their current visibility is not required by JavaScript.

- [ ] **Step 5: Add explicit UI states**

Add classes and copy targets for `.is-loading`, `.is-success`, `.is-partial`, `.is-error`. Reuse `pdf-status-main`; do not invent a second status source. Error text must include the next action, such as reviewing the extracted lines or selecting the state/model.

- [ ] **Step 6: Run import and classification regressions**

Run: `pytest -q tests/test_frontend_pdf_upload.py tests/test_pdf_reais_indea.py tests/test_pdf_resumo_fazendas.py tests/test_classificar_parecer.py tests/test_regressao_bugs.py`

- [ ] **Step 7: Commit**

```powershell
git add templates/index.html static/orkavyn-fields.css tests/test_frontend_pdf_upload.py tests/test_ui_fields_contract.py
git commit -m "feat: redesign herd import and analysis inputs"
```

---

### Task 5: Redesign results, scenarios, history and evidence ribbon

**Files:**
- Modify: `templates/index.html:1000-4300`
- Modify: `static/orkavyn-fields.css`
- Modify: `tests/test_ui_fields_contract.py`
- Modify: `tests/test_classificar_parecer.py`

**Interfaces:**
- Consumes: the existing `/api/classificar` response keys and the existing renderer functions in `index.html`.
- Produces: `.ork-decision-summary`, `.ork-evidence-ribbon`, section navigation and responsive financial/zootechnical result layouts.

- [ ] **Step 1: Characterize the current result renderer contract**

```python
def test_result_renderer_still_reads_decision_blocks():
    html = (ROOT / 'templates' / 'index.html').read_text(encoding='utf-8')
    for key in ('parecer', 'qualidade_dados', 'fluxo_mensal',
                'comparacao_cenarios', 'explicacao_classificacao'):
        assert key in html
    for panel in ('panel-resultado', 'panel-cenarios', 'panel-historico', 'panel-ajuda'):
        assert f'id="{panel}"' in html
```

- [ ] **Step 2: Run the contract tests before changing result markup**

Run: `pytest -q tests/test_ui_fields_contract.py tests/test_classificar_parecer.py tests/test_analise_transparente.py`

- [ ] **Step 3: Add the decision-summary composition**

The first result viewport contains capacity estimate, minimum DSCR, operating result, risk and data quality. Use one dominant metric and four supporting metrics, not five identical cards. Values remain populated by existing renderer functions and IDs.

- [ ] **Step 4: Implement the evidence ribbon**

```html
<aside class="ork-evidence-ribbon" aria-label="Evidências da conclusão">
  <div><span>Qualidade dos dados</span><strong id="ev-quality">—</strong></div>
  <div><span>Premissas alteradas</span><strong id="ev-assumptions">—</strong></div>
  <div><span>Fontes</span><strong id="ev-sources">—</strong></div>
  <div><span>Limitações</span><strong id="ev-limitations">—</strong></div>
</aside>
```

Populate the four targets from fields already returned in `parecer`, `qualidade_dados` and provenance. Do not ask generative AI for these values.

- [ ] **Step 5: Restyle scenarios and history with semantic tables**

Use `.ork-table-wrap` only when columns cannot fit. Keep scenario base/moderate/severe labels stable, highlight DSCR below 1.0 with text plus color, and leave the existing scenario endpoint untouched.

- [ ] **Step 6: Run result, scenario and history tests**

Run: `pytest -q tests/test_classificar_parecer.py tests/test_comparacao_cenarios.py tests/test_fazenda_pareceres_endpoint.py tests/test_analise_transparente.py tests/test_explicacao_classificacao.py`

- [ ] **Step 7: Commit**

```powershell
git add templates/index.html static/orkavyn-fields.css tests/test_ui_fields_contract.py tests/test_classificar_parecer.py
git commit -m "feat: add Fields decision and evidence views"
```

---

### Task 6: Redesign authentication and legal pages

**Files:**
- Modify: `templates/login.html`
- Modify: `templates/login_2fa.html`
- Modify: `templates/register.html`
- Modify: `templates/cadastro.html`
- Modify: `templates/esqueci_senha.html`
- Modify: `templates/redefinir_senha.html`
- Modify: `templates/termos.html`
- Modify: `templates/privacidade.html`
- Modify: `tests/test_ui_fields_contract.py`
- Modify: `tests/test_seguranca_web.py`

**Interfaces:**
- Preserves: all form action URLs, CSRF/security behavior, input names and error variables.
- Produces: shared `.ork-auth-layout` and `.ork-reading-layout` using `orkavyn-fields.css`.

- [ ] **Step 1: Add route and form-contract tests**

```python
def test_auth_pages_load_fields_stylesheet(client):
    for route in ('/login', '/cadastro', '/esqueci-senha', '/termos', '/privacidade'):
        response = client.get(route)
        assert response.status_code == 200
        assert b'orkavyn-fields.css' in response.data

def test_login_preserves_field_names(client):
    html = client.get('/login').get_data(as_text=True)
    assert 'name="email"' in html
    assert 'name="senha"' in html
```

- [ ] **Step 2: Run tests and confirm stylesheet assertions fail**

Run: `pytest -q tests/test_ui_fields_contract.py tests/test_seguranca_web.py tests/test_2fa.py`

- [ ] **Step 3: Apply the Fields authentication layout**

Use a quiet rural image only in the non-form half or under a strong overlay. Keep the form surface opaque sand, headings left-aligned, one primary submit button and standard labels such as “Entrar” and “Continuar”.

- [ ] **Step 4: Apply the legal reading layout**

Terms and privacy use a solid sand/oat reading surface, maximum readable line length and no photographic image behind long text. Preserve all legal copy verbatim.

- [ ] **Step 5: Verify authentication and security flows**

Run: `pytest -q tests/test_seguranca_web.py tests/test_2fa.py tests/test_empresas_signup.py tests/test_lgpd.py tests/test_marca_orkavyn.py`

- [ ] **Step 6: Commit**

```powershell
git add templates/login.html templates/login_2fa.html templates/register.html templates/cadastro.html templates/esqueci_senha.html templates/redefinir_senha.html templates/termos.html templates/privacidade.html tests/test_ui_fields_contract.py tests/test_seguranca_web.py
git commit -m "feat: apply Fields identity to access pages"
```

---

### Task 7: Redesign landing page and administration

**Files:**
- Modify: `templates/landing.html`
- Modify: `templates/admin.html`
- Modify: `static/orkavyn-fields.css`
- Modify: `tests/test_ui_fields_contract.py`
- Modify: `tests/test_admin_acesso.py`

**Interfaces:**
- Preserves: landing CTAs, `/app`, `/login`, admin forms, admin-only visibility and API calls.
- Produces: Fields marketing composition and dense Fields admin tool.

- [ ] **Step 1: Add failing CTA/admin contract tests**

```python
def test_landing_keeps_real_primary_routes(client):
    html = client.get('/').get_data(as_text=True)
    assert 'href="/login"' in html or "url_for('login')" in html
    assert 'Orkavyn Agro Intelligence' in html

def test_admin_keeps_access_management_controls(admin_client):
    html = admin_client.get('/admin').get_data(as_text=True)
    for marker in ('empresas', 'auditoria', 'LGPD'):
        assert marker.lower() in html.lower()
```

- [ ] **Step 2: Run tests before modifying the pages**

Run: `pytest -q tests/test_ui_fields_contract.py tests/test_admin_acesso.py tests/test_admin_empresas.py`

- [ ] **Step 3: Recompose the landing page with real product content**

Keep the existing value proposition, ML classification, cashflow, DSCR and PDF claims that are already supported. Use one hero, one workflow section, one evidence/report preview and one final CTA. Remove ticker-like decoration and invented telemetry if present.

- [ ] **Step 4: Recompose administration as an operational tool**

Reuse the sidebar shell, compact tables and native forms. Do not wrap every row in a card. Keep destructive actions text-labeled and require the existing confirmation behavior.

- [ ] **Step 5: Run landing/admin/brand tests**

Run: `pytest -q tests/test_admin_acesso.py tests/test_admin_empresas.py tests/test_lgpd.py tests/test_marca_orkavyn.py tests/test_auditoria_acesso.py`

- [ ] **Step 6: Commit**

```powershell
git add templates/landing.html templates/admin.html static/orkavyn-fields.css tests/test_ui_fields_contract.py tests/test_admin_acesso.py
git commit -m "feat: redesign Orkavyn landing and administration"
```

---

### Task 8: Finish the demonstration and PDF visual system

**Files:**
- Modify: `templates/demo.html`
- Modify: `services/parecer_pdf.py`
- Modify: `tests/test_report_v1.py`
- Modify: `tests/test_parecer_pdf.py`

**Interfaces:**
- Preserves: `GET /demo`, `gerar_pdf_parecer(parecer, branding=None)` and branding overrides.
- Produces: visually coherent demonstration and professional report sections with explicit assumptions and limitations.

- [ ] **Step 1: Add report ordering and disclaimer tests**

```python
def test_pdf_section_order(sample_parecer):
    text = _extract_pdf_text(gerar_pdf_parecer(sample_parecer))
    sections = ['Resumo executivo', 'Rebanho', 'Produção', 'Receitas', 'Custos',
                'Fluxo de caixa', 'Dívida', 'DSCR', 'Stress', 'Risco',
                'Qualidade dos dados', 'Premissas', 'Fontes', 'Limitações']
    positions = [text.index(section) for section in sections]
    assert positions == sorted(positions)

def test_demo_does_not_persist_analysis(client, monkeypatch):
    called = False
    monkeypatch.setattr('database.save_analysis_snapshot', lambda *a, **k: (_ for _ in ()).throw(AssertionError()))
    assert client.get('/demo').status_code == 200
```

- [ ] **Step 2: Run tests and confirm ordering/visual gaps**

Run: `pytest -q tests/test_report_v1.py tests/test_parecer_pdf.py`

- [ ] **Step 3: Apply Fields PDF colors and hierarchy**

Use forest headings, soil labels, sand table headers and low-contrast dividers. Preserve custom consultancy branding. Keep PDF typography to ReportLab built-ins unless the repository already embeds a licensed font.

- [ ] **Step 4: Apply the dashboard shell to the demo**

The demo uses only the explicitly labeled fictitious dataset already supplied by `app.py`. It shows the process and representative result states but does not call persistence endpoints.

- [ ] **Step 5: Run report and endpoint tests**

Run: `pytest -q tests/test_report_v1.py tests/test_parecer_pdf.py tests/test_parecer_pdf_endpoint.py tests/test_analysis_pipeline.py`

- [ ] **Step 6: Commit**

```powershell
git add templates/demo.html services/parecer_pdf.py tests/test_report_v1.py tests/test_parecer_pdf.py
git commit -m "feat: style Fields demonstration and report"
```

---

### Task 9: Perform browser verification, accessibility checks and final regression

**Files:**
- Modify: `static/orkavyn-fields.css`
- Modify: `static/orkavyn-shell.js`
- Modify: `tests/test_ui_fields_contract.py`
- Modify: `.interface-design/system.md`
- Modify: `README.md`

**Interfaces:**
- Consumes: all redesigned pages from Tasks 1–8.
- Produces: verified desktop/mobile interface and documented maintenance rules.

- [ ] **Step 1: Add final static accessibility assertions**

```python
def test_motion_and_focus_contracts_exist():
    css = (ROOT / 'static' / 'orkavyn-fields.css').read_text(encoding='utf-8')
    assert ':focus-visible' in css
    assert '@media (prefers-reduced-motion: reduce)' in css

def test_loading_overlay_is_announced():
    html = (ROOT / 'templates' / 'index.html').read_text(encoding='utf-8')
    assert 'id="loading-ov"' in html
    assert 'role="status"' in html
    assert 'aria-live="polite"' in html
```

- [ ] **Step 2: Start the Flask app locally**

Run: `$env:SECRET_KEY='visual-qa'; python app.py`

Expected: app starts on the configured local port without template exceptions.

- [ ] **Step 3: Verify desktop widths in a browser**

Inspect 1440×900 and 1280×800 for `/`, `/login`, `/app`, `/admin` and `/demo`. Confirm the 256 px sidebar, one dominant action, no clipped forms, no horizontal page scroll, visible focus and readable tables.

- [ ] **Step 4: Verify tablet and mobile widths**

Inspect 768×1024, 390×844 and 320×720. Confirm bottom navigation, 44 px targets, no overlapping browser-safe content, stacked cards, accessible importer and readable result evidence.

- [ ] **Step 5: Exercise the real critical flow**

Run login → select company → import a real supported PDF → review extracted rows → classify → open scenarios → open history → download PDF. Confirm existing IDs/functions remain operational and every loading/error state is visible.

- [ ] **Step 6: Run the focused UI suite and full regression suite**

Run:

```powershell
pytest -q tests/test_ui_fields_contract.py tests/test_frontend_pdf_upload.py tests/test_report_v1.py tests/test_marca_orkavyn.py tests/test_admin_acesso.py tests/test_seguranca_web.py
pytest -q
git diff --check
```

Expected: all tests pass; `git diff --check` has no whitespace errors.

- [ ] **Step 7: Update maintenance documentation and commit**

Add the stylesheet/script entry points, responsive breakpoints and visual QA commands to `README.md`. Confirm `.interface-design/system.md` matches the shipped tokens and components.

```powershell
git add static/orkavyn-fields.css static/orkavyn-shell.js tests/test_ui_fields_contract.py .interface-design/system.md README.md
git commit -m "test: verify Orkavyn Fields interface"
```

---

## Completion criteria

- All nine tasks are independently reviewed and committed.
- The complete pytest suite passes.
- Landing, authentication, application, administration, legal, demo and PDF surfaces share the approved Fields Executivo identity.
- Desktop uses the fixed sidebar and mobile uses the bottom navigation.
- Upload, classification, scenarios, history and PDF generation work with their original contracts.
- The evidence ribbon visibly connects headline decisions to quality, assumptions, sources and limitations.
- Visual verification passes at 1440, 1280, 768, 390 and 320 px widths.
