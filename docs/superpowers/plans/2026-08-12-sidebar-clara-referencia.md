# Light Reference Sidebar Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transformar a barra lateral desktop do Orkavyn Agro Intelligence em uma navegação clara inspirada na referência aprovada, preservando destinos, comportamento e navegação móvel.

**Architecture:** O partial `fields_sidebar.html` continua sendo a única fonte da navegação desktop e recebe marcação semântica, ícones SVG locais e o bloco de conta. `orkavyn-fields.css` concentra aparência e responsividade, enquanto `index.html` deixa de duplicar a ação de saída no cabeçalho. Os contratos estáticos em `test_ui_fields_contract.py` protegem estrutura, rotas e tokens visuais sem carregar o aplicativo ou o modelo ML.

**Tech Stack:** Flask/Jinja2, HTML5, CSS3, SVG inline e pytest.

## Global Constraints

- Aplicar a mudança somente à barra lateral desktop, acima de `900px`.
- Manter a navegação móvel inferior existente e os destinos Nova análise, Resultado, Cenários, Histórico e Ajuda.
- Usar largura desktop de `280px`, superfície clara, item ativo verde-floresta e padding lateral de `24px`.
- Hover altera somente cor, fundo e borda; nunca deslocamento, escala, sombra ou revelação.
- Usar ícones SVG lineares embutidos, sem dependência externa e sem emojis.
- Exibir nome do usuário com e-mail como fallback e link explícito para `/logout` no rodapé.
- Não alterar regras de classificação, PDF, fluxo de caixa, autenticação ou banco de dados.

---

### Task 1: Estrutura semântica, destinos e conta

**Files:**
- Modify: `tests/test_ui_fields_contract.py`
- Modify: `templates/partials/fields_sidebar.html`
- Modify: `templates/index.html`

**Interfaces:**
- Consumes: variáveis Jinja `usuario.nome` e `usuario.email`; função JavaScript existente `showTab(tab, element)`; rota Flask existente `/logout`.
- Produces: classes `.ork-brand__mark`, `.ork-nav__icon`, `.ork-sidebar__account`, `.ork-sidebar__user` e `.ork-sidebar__logout` usadas pela Task 2.

- [ ] **Step 1: Write the failing structural test**

Adicionar a `tests/test_ui_fields_contract.py`:

```python
def test_light_sidebar_preserves_destinations_and_moves_account_to_footer():
    sidebar = (ROOT / "templates" / "partials" / "fields_sidebar.html").read_text(encoding="utf-8")
    html = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")

    assert "Análise econômico-produtiva" in sidebar
    for destination in ("entrada", "resultado", "cenarios", "historico", "ajuda"):
        assert f'data-ork-nav="{destination}"' in sidebar
        assert f"showTab('{destination}', this)" in sidebar
    assert sidebar.count("<svg") == 5
    assert 'class="ork-sidebar__account"' in sidebar
    assert "usuario.nome" in sidebar
    assert "usuario.email" in sidebar
    assert 'href="/logout"' in sidebar
    assert 'onclick="logout()"' not in html
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```powershell
& 'C:\Users\Lucas\Documents\lucas\.bovcredit-venv\Scripts\python.exe' -m pytest tests/test_ui_fields_contract.py::test_light_sidebar_preserves_destinations_and_moves_account_to_footer -q --basetemp .pytest-local-sidebar-structure
```

Expected: FAIL porque a barra ainda usa números, não possui conta e o cabeçalho ainda contém `onclick="logout()"`.

- [ ] **Step 3: Implement the semantic sidebar**

Em `templates/partials/fields_sidebar.html`:

- manter os cinco botões, `data-ork-nav` e chamadas `showTab` atuais;
- trocar os números por cinco SVGs lineares com `viewBox="0 0 24 24"`, `fill="none"`, `stroke="currentColor"`, `stroke-width="1.8"` e `aria-hidden="true"`;
- usar o rótulo `Análise econômico-produtiva`;
- criar o rodapé:

```html
<div class="ork-sidebar__account">
  <span class="ork-sidebar__user">{{ usuario.nome or usuario.email }}</span>
  <a class="ork-sidebar__logout" href="/logout">Sair da conta</a>
</div>
```

Em `templates/index.html`, remover apenas o botão com `onclick="logout()"` do cabeçalho. Manter cotações, acesso administrativo, empresa ativa e marca.

- [ ] **Step 4: Run the structural tests**

Run:

```powershell
& 'C:\Users\Lucas\Documents\lucas\.bovcredit-venv\Scripts\python.exe' -m pytest tests/test_ui_fields_contract.py::test_light_sidebar_preserves_destinations_and_moves_account_to_footer tests/test_ui_fields_contract.py::test_shell_has_mobile_and_desktop_navigation tests/test_ui_fields_contract.py::test_index_shell_preserves_critical_controls -q --basetemp .pytest-local-sidebar-structure-green
```

Expected: 3 passed.

- [ ] **Step 5: Commit the semantic structure**

```powershell
git add tests/test_ui_fields_contract.py templates/partials/fields_sidebar.html templates/index.html
git commit -m "feat: structure light desktop sidebar"
```

---

### Task 2: Superfície clara e estados visuais estáveis

**Files:**
- Modify: `tests/test_ui_fields_contract.py`
- Modify: `static/orkavyn-fields.css`
- Modify: `.interface-design/system.md`

**Interfaces:**
- Consumes: classes produzidas pela Task 1 e tokens `--ork-forest`, `--ork-sand`, `--ork-soil`, `--ork-surface-raised` e `--ork-line`.
- Produces: contrato visual desktop de `280px`; em `max-width: 900px`, a regra responsiva existente continua escondendo a lateral e zerando a margem do workspace.

- [ ] **Step 1: Write the failing visual contract test**

Adicionar a `tests/test_ui_fields_contract.py`:

```python
def test_light_sidebar_uses_reference_surface_and_static_hover():
    css = (ROOT / "static" / "orkavyn-fields.css").read_text(encoding="utf-8")

    root = _css_rule(css, ":root")
    sidebar = _css_rule(css, ".ork-sidebar")
    active = _css_rule(css, ".ork-nav__item.is-active")
    hover = _css_rule(css, ".ork-nav__item:hover")

    assert "--ork-sidebar-width: 280px" in root
    assert "padding: 28px 24px" in sidebar
    assert "var(--ork-sand)" in sidebar or "rgba(251, 247, 239" in sidebar
    assert "var(--ork-forest)" in active
    assert "translate" not in hover
    assert "scale(" not in hover
    assert "box-shadow" not in hover
```

Se os seletores ativos estiverem agrupados, desagrupar `.ork-nav__item:hover` e `.ork-nav__item.is-active` para permitir contratos distintos: hover claro e ativo verde-floresta.

- [ ] **Step 2: Run the visual test to verify it fails**

Run:

```powershell
& 'C:\Users\Lucas\Documents\lucas\.bovcredit-venv\Scripts\python.exe' -m pytest tests/test_ui_fields_contract.py::test_light_sidebar_uses_reference_surface_and_static_hover -q --basetemp .pytest-local-sidebar-visual
```

Expected: FAIL porque a largura é `256px`, o fundo é verde e os estados hover/ativo estão agrupados.

- [ ] **Step 3: Implement the approved visual system**

Em `static/orkavyn-fields.css`:

```css
:root { --ork-sidebar-width: 280px; }

.ork-sidebar {
  padding: 28px 24px 24px;
  color: var(--ork-forest);
  background: rgba(251, 247, 239, 0.96);
  border-right: 1px solid var(--ork-line);
}

.ork-nav__item:hover {
  color: var(--ork-forest);
  background: rgba(23, 58, 42, 0.06);
  border-color: rgba(23, 58, 42, 0.08);
}

.ork-nav__item.is-active {
  color: var(--ork-surface-raised);
  background: var(--ork-forest);
  border-color: var(--ork-forest);
}

.ork-nav__item[aria-current="page"] {
  color: var(--ork-surface-raised);
  background: var(--ork-forest);
  border-color: var(--ork-forest);
}
```

Completar as regras da marca, ícones SVG e conta usando os mesmos tokens, sem sombra no hover e com alvos mínimos de `44px`. Manter inalterado o bloco responsivo `@media (max-width: 900px)` que esconde `.ork-sidebar` e exibe `.ork-mobile-nav`.

Em `.interface-design/system.md`, atualizar a largura para `280px` e registrar: superfície clara, ativo verde-floresta, ícones SVG lineares, conta no rodapé e hover sem movimento.

- [ ] **Step 4: Run visual and template regressions**

Run:

```powershell
& 'C:\Users\Lucas\Documents\lucas\.bovcredit-venv\Scripts\python.exe' -m pytest tests/test_ui_fields_contract.py tests/test_frontend_pdf_upload.py::test_upload_pdf_fica_visivel_na_area_de_entrada tests/test_frontend_pdf_upload.py::test_preview_pdf_e_botao_classificacao_ficam_disponiveis_na_entrada tests/test_frontend_pdf_upload.py::test_frontend_exibe_fluxo_de_analise_e_estados_acessiveis tests/test_frontend_pdf_upload.py::test_primary_import_control_keeps_multiple_pdf_contract tests/test_frontend_pdf_upload.py::test_import_status_is_accessible_and_actionable -q --basetemp .pytest-local-sidebar-final
```

Expected: todos os testes selecionados passam.

Run:

```powershell
& 'C:\Users\Lucas\Documents\lucas\.bovcredit-venv\Scripts\python.exe' -m compileall -q app.py services
git diff --check
```

Expected: saída vazia e exit code `0`.

- [ ] **Step 5: Inspect responsive behavior**

Quando o navegador local estiver acessível, verificar `1280×800` e `390×844`: no desktop, barra clara de `280px` com conta no rodapé; no móvel, lateral oculta e barra inferior existente. Se o navegador local estiver bloqueado pelo ambiente, registrar essa limitação sem substituir a inspeção por uma alegação visual.

- [ ] **Step 6: Commit the visual system**

```powershell
git add tests/test_ui_fields_contract.py static/orkavyn-fields.css .interface-design/system.md
git commit -m "feat: style light reference sidebar"
```
