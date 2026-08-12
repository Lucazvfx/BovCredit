# Dashboard Executivo Natural Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tornar o dashboard da Orkavyn mais limpo e profissional, com textos em verde-escuro, fotografia rural estática e discretamente aparente, superfícies claras e nenhuma informação ou elevação dependente de hover.

**Architecture:** O refinamento permanece na camada de apresentação. `templates/index.html` deixa de controlar o fundo pelo cursor e remove animações legadas do dashboard; `static/orkavyn-fields.css` concentra os tokens, superfícies e estados visuais finais. Os contratos funcionais, IDs e renderizadores permanecem intactos, com regressões protegidas por `tests/test_ui_fields_contract.py`.

**Tech Stack:** Flask/Jinja2, HTML5, CSS responsivo, JavaScript sem framework, pytest.

## Global Constraints

- Não alterar cálculos, endpoints, contratos da API, autenticação, classificação, fluxo de caixa ou relatórios.
- Preservar todos os IDs e funções JavaScript consumidos pelo fluxo atual.
- Usar `--ork-forest` como cor principal de títulos, valores e texto de alta prioridade.
- Manter a fotografia com presença visual aproximada de 10% a 15%, sempre sob uma superfície legível.
- Não usar paralaxe, spotlight, conteúdo revelado por hover, `translateY` ou `scale` em cards e botões do dashboard.
- Manter foco visível, alvos de toque de 44 px e suporte a `prefers-reduced-motion`.
- Não apresentar dados fictícios como reais.

---

## File Structure

- Modify: `templates/index.html` — remove o spotlight controlado pelo mouse e movimentos legados do dashboard, preservando estrutura e comportamento dos dados.
- Modify: `static/orkavyn-fields.css` — aplica o fundo ambiental, tipografia verde-escuro, superfícies translúcidas e estados de interação estáticos.
- Modify: `tests/test_ui_fields_contract.py` — protege os contratos visuais e os seletores funcionais.
- Modify: `.interface-design/system.md` — registra os padrões aprovados para futuras alterações.

---

### Task 1: Proteger o contrato do fundo estático e das interações

**Files:**
- Modify: `tests/test_ui_fields_contract.py`
- Test: `tests/test_ui_fields_contract.py`

**Interfaces:**
- Consumes: `templates/index.html` e `static/orkavyn-fields.css` como artefatos renderizados pelo navegador.
- Produces: contratos que falham se o spotlight ou movimentos de hover retornarem ao dashboard.

- [ ] **Step 1: Escrever os testes que falham com o dashboard atual**

Adicionar ao final de `tests/test_ui_fields_contract.py`:

```python
import re


def _css_rule(source: str, selector: str) -> str:
    match = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", source, re.S)
    assert match, f"regra ausente: {selector}"
    return match.group(1)


def test_dashboard_uses_static_ambient_herd_background():
    html = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
    css = (ROOT / "static" / "orkavyn-fields.css").read_text(encoding="utf-8")

    assert 'class="ork-surface ork-dashboard-surface"' in html
    assert 'id="bg-rebanho"' in html
    assert "document.addEventListener('mousemove'" not in html
    assert "maskImage = mask" not in html

    background = _css_rule(css, ".ork-dashboard-surface #bg-rebanho")
    assert "rebanho-bg.jpg" in background
    assert re.search(r"opacity:\s*0\.1[0-5]", background)


def test_dashboard_hover_does_not_move_controls_or_cards():
    html = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
    css = (ROOT / "static" / "orkavyn-fields.css").read_text(encoding="utf-8")
    dashboard_sources = html + "\n" + css

    for selector in (".ork-action:hover", ".btn-p:hover", ".sc-card:hover"):
        rule = _css_rule(dashboard_sources, selector)
        assert "translate" not in rule
        assert "scale(" not in rule
```

- [ ] **Step 2: Executar os testes e confirmar a falha correta**

Run:

```powershell
python -m pytest tests/test_ui_fields_contract.py::test_dashboard_uses_static_ambient_herd_background tests/test_ui_fields_contract.py::test_dashboard_hover_does_not_move_controls_or_cards -q
```

Expected: FAIL porque o body não possui `ork-dashboard-surface`, o HTML ainda registra `mousemove` e os hovers ainda usam `translateY`.

- [ ] **Step 3: Confirmar que os testes preservam comportamento e não apenas texto ornamental**

Mutação manual temporária: remover uma das asserções contra `mousemove` e confirmar que o teste deixaria o spotlight retornar sem proteção. Restaurar a asserção antes do commit.

- [ ] **Step 4: Commitar somente os testes vermelhos**

```powershell
git add tests/test_ui_fields_contract.py
git commit -m "test: define natural dashboard interaction contract"
```

---

### Task 2: Substituir o spotlight por fundo ambiental estático

**Files:**
- Modify: `templates/index.html:35-55`
- Modify: `templates/index.html:435-440`
- Modify: `templates/index.html:1410-1430`
- Modify: `static/orkavyn-fields.css:27-75`
- Test: `tests/test_ui_fields_contract.py`

**Interfaces:**
- Consumes: imagem existente `/static/img/rebanho-bg.jpg` e o elemento `#bg-rebanho`.
- Produces: classe de escopo `.ork-dashboard-surface` e fundo estático com opacidade entre `0.10` e `0.15`.

- [ ] **Step 1: Marcar exclusivamente a aplicação principal como dashboard**

Em `templates/index.html`, alterar:

```html
<body class="ork-surface">
```

para:

```html
<body class="ork-surface ork-dashboard-surface">
```

- [ ] **Step 2: Remover o CSS legado do spotlight do template**

Excluir de `templates/index.html` a regra completa `#bg-rebanho` que começa com `opacity:0`, inclui `transition:opacity` e usa `mask-image`. Manter apenas o elemento HTML `<div id="bg-rebanho"></div>`.

- [ ] **Step 3: Remover o controlador de cursor**

Excluir do callback `DOMContentLoaded` em `templates/index.html` o bloco que começa em:

```javascript
// Fundo rebanho — spotlight segue o cursor
```

e termina após o listener `mouseleave`. Não substituir por JavaScript: o fundo será puramente CSS.

- [ ] **Step 4: Implementar o fundo estático na folha compartilhada**

Adicionar a `static/orkavyn-fields.css`, logo após `.ork-surface`:

```css
.ork-dashboard-surface {
  position: relative;
  min-height: 100vh;
  background: var(--ork-sand);
}

.ork-dashboard-surface #bg-rebanho {
  position: fixed;
  inset: 0;
  z-index: 0;
  pointer-events: none;
  background: url('/static/img/rebanho-bg.jpg') center / cover no-repeat;
  opacity: 0.12;
}

.ork-dashboard-surface .ork-shell,
.ork-dashboard-surface .ork-workspace {
  position: relative;
  background: transparent;
}

.ork-dashboard-surface .ork-shell { z-index: 1; }
```

- [ ] **Step 5: Reduzir a presença da foto no mobile sem escondê-la**

No breakpoint `@media (max-width: 480px)`, adicionar:

```css
.ork-dashboard-surface #bg-rebanho { opacity: 0.1; }
```

- [ ] **Step 6: Executar o teste do fundo**

Run:

```powershell
python -m pytest tests/test_ui_fields_contract.py::test_dashboard_uses_static_ambient_herd_background -q
```

Expected: PASS.

- [ ] **Step 7: Commitar o fundo ambiental**

```powershell
git add templates/index.html static/orkavyn-fields.css tests/test_ui_fields_contract.py
git commit -m "feat: make herd background quietly visible"
```

---

### Task 3: Limpar tipografia, superfícies e profundidade do dashboard

**Files:**
- Modify: `static/orkavyn-fields.css:1-530`
- Modify: `templates/index.html:55-370`
- Test: `tests/test_ui_fields_contract.py`

**Interfaces:**
- Consumes: tokens `--ork-forest`, `--ork-ink`, `--ork-copy`, `--ork-surface-raised`, `--ork-line` e classes legadas já usadas pelos renderizadores.
- Produces: textos predominantemente verde-escuro, painéis claros translúcidos e hierarquia executiva sem alteração de IDs.

- [ ] **Step 1: Escrever o teste de cores e superfícies antes da implementação**

Adicionar a `tests/test_ui_fields_contract.py`:

```python
def test_dashboard_uses_forest_text_and_readable_translucent_surfaces():
    css = (ROOT / "static" / "orkavyn-fields.css").read_text(encoding="utf-8")

    surface = _css_rule(css, ".ork-dashboard-surface")
    panels = _css_rule(css, ".ork-dashboard-surface .ork-result-view .card")
    headings = _css_rule(css, ".ork-dashboard-surface .ork-result-view .ct")

    assert "var(--ork-sand)" in surface
    assert "rgba(251, 247, 239" in panels
    assert "var(--ork-forest)" in headings
```

- [ ] **Step 2: Executar o teste e confirmar falha por regras ausentes**

```powershell
python -m pytest tests/test_ui_fields_contract.py::test_dashboard_uses_forest_text_and_readable_translucent_surfaces -q
```

Expected: FAIL em `.ork-dashboard-surface .ork-result-view .card` ausente.

- [ ] **Step 3: Reduzir as sombras no escopo do dashboard**

Adicionar um token específico em `:root`:

```css
--ork-shadow-dashboard: 0 2px 10px rgba(23, 58, 42, 0.055);
```

Aplicar esse token a `.ork-panel`, `.card`, `.rhero`, `.ork-decision-summary` e navegação móvel somente dentro de `.ork-dashboard-surface`. Não alterar as telas de login, landing, administração ou demonstração.

- [ ] **Step 4: Aplicar superfícies claras quase opacas**

Adicionar regras agrupadas:

```css
.ork-dashboard-surface .ork-panel,
.ork-dashboard-surface .ork-result-view .card,
.ork-dashboard-surface .ork-scenario-view .card,
.ork-dashboard-surface .ork-history-view .card,
.ork-dashboard-surface .ork-result-view .rhero {
  color: var(--ork-forest);
  background: rgba(251, 247, 239, 0.96) !important;
  border-color: rgba(190, 169, 142, 0.72) !important;
  box-shadow: var(--ork-shadow-dashboard);
}
```

Manter `.ork-import-panel` e `.ork-decision-summary__primary` em verde-floresta porque são ações/conclusões dominantes, sem aplicar a elas a superfície clara.

- [ ] **Step 5: Tornar títulos e valores verde-escuro**

Adicionar regras de escopo para `.ptitle`, `.ct`, `.sc2-v`, `.pjc-v`, `.mv`, `.tsc-v`, `.ork-panel__title`, `.ork-decision-summary__metrics strong` e cabeçalhos de tabelas. Usar `color: var(--ork-forest)` para valores neutros, mantendo `.is-critical`, `.cr`, `.r`, `.ca` e estados semânticos nas cores de risco/atenção existentes.

- [ ] **Step 6: Simplificar cabeçalhos e agrupamentos**

No escopo `.ork-dashboard-surface`:

```css
.ork-page-header,
.ork-context-header {
  color: var(--ork-forest);
  background: rgba(246, 240, 230, 0.94);
  box-shadow: none;
}

.ork-dashboard-surface .ch {
  background: rgba(232, 220, 199, 0.72);
  border-color: rgba(190, 169, 142, 0.58);
}
```

Não remover títulos, rótulos, fontes, alertas ou limitações.

- [ ] **Step 7: Executar os testes de estilo e seletores**

```powershell
python -m pytest tests/test_ui_fields_contract.py::test_dashboard_uses_forest_text_and_readable_translucent_surfaces tests/test_ui_fields_contract.py::test_index_shell_preserves_critical_controls tests/test_ui_fields_contract.py::test_result_renderer_keeps_decision_contract_and_evidence_targets -q
```

Expected: 3 PASS.

- [ ] **Step 8: Commitar a hierarquia executiva**

```powershell
git add static/orkavyn-fields.css templates/index.html tests/test_ui_fields_contract.py
git commit -m "feat: simplify executive dashboard surfaces"
```

---

### Task 4: Remover movimentos e revelações de hover do dashboard

**Files:**
- Modify: `templates/index.html:60-370`
- Modify: `static/orkavyn-fields.css:130-410`
- Test: `tests/test_ui_fields_contract.py`

**Interfaces:**
- Consumes: seletores existentes `.ork-action`, `.btn-p`, `.sc-card`, `.upzone`, `.tab-btn`, `.itbl`, `.ytbl` e `.panel`.
- Produces: estados hover estáticos, informação sempre disponível e feedback limitado a cor/borda.

- [ ] **Step 1: Remover movimento de botões compartilhados**

Em `static/orkavyn-fields.css`, alterar:

```css
.ork-action {
  transition: color 160ms ease, background-color 160ms ease, border-color 160ms ease;
}

.ork-action:hover {
  transform: none;
  background: #214d38;
}
```

- [ ] **Step 2: Remover movimento dos controles legados**

Em `templates/index.html`:

- remover `transform:translateY(-2px)` e a sombra forte de `.btn-p:hover`;
- remover `transform:translateY(-2px)` de `.sc-card:hover`;
- substituir `transition:all` por propriedades específicas em `.tab-btn`, `.upzone`, `.btn-p`, `.btn-sm`, `.sc-card`, `.toast` e controles equivalentes;
- manter mudança discreta de cor e borda;
- manter `transform` de toast, skip link e sidebar, pois eles representam estado de entrada/saída e não hover de conteúdo.

- [ ] **Step 3: Remover animação de subida na troca de painéis**

Alterar:

```css
.panel{display:none;animation:rise .35s cubic-bezier(.22,1,.36,1)}
```

para:

```css
.panel{display:none}
```

Alterar `.sc-spanel.act` para somente `display:block` e remover `@keyframes rise` se nenhuma outra regra o utilizar.

- [ ] **Step 4: Manter o hover informativo sem revelar conteúdo**

Conservar apenas:

```css
.tab-btn:hover,
.btn-sm:hover,
.sc-card:hover,
.upzone:hover {
  color: var(--ork-forest);
  border-color: var(--ork-sage);
}
```

Não adicionar `display`, `visibility`, `opacity`, `transform` ou mudanças de altura/largura em seletores `:hover`.

- [ ] **Step 5: Executar o contrato de interação**

```powershell
python -m pytest tests/test_ui_fields_contract.py::test_dashboard_hover_does_not_move_controls_or_cards tests/test_ui_fields_contract.py::test_motion_and_focus_contracts_exist -q
```

Expected: 2 PASS.

- [ ] **Step 6: Commitar as interações estáticas**

```powershell
git add templates/index.html static/orkavyn-fields.css tests/test_ui_fields_contract.py
git commit -m "feat: remove distracting dashboard hover motion"
```

---

### Task 5: Registrar o padrão e validar regressões

**Files:**
- Modify: `.interface-design/system.md`
- Test: `tests/test_ui_fields_contract.py`
- Test: `tests/test_frontend_pdf_upload.py`
- Test: `tests/test_regressao_bugs.py`

**Interfaces:**
- Consumes: dashboard final das Tasks 2–4.
- Produces: sistema visual documentado e evidência de que upload, resultados e responsividade permanecem íntegros.

- [ ] **Step 1: Atualizar o sistema visual**

Adicionar a `.interface-design/system.md` uma seção `Dashboard Executivo Natural` com estas decisões exatas:

```markdown
## Dashboard Executivo Natural

- Texto principal: `--ork-forest`; evitar preto puro no workspace analítico.
- Fundo: `rebanho-bg.jpg` estático, opacidade `0.12` no desktop e `0.10` até 480 px.
- Painéis analíticos: `rgba(251, 247, 239, 0.96)` e `--ork-shadow-dashboard`.
- Hover: somente cor e borda; nunca deslocamento, escala, revelação ou mudança de profundidade.
- Exceções de movimento: skip link, toast, drawer/sidebar e feedback de estado, sempre respeitando movimento reduzido.
- Informação crítica nunca depende de hover.
```

- [ ] **Step 2: Executar os testes de contrato visual e frontend**

```powershell
python -m pytest tests/test_ui_fields_contract.py tests/test_frontend_pdf_upload.py -q
```

Expected: PASS.

- [ ] **Step 3: Executar os testes de regressão funcional**

```powershell
python -m pytest tests/test_regressao_bugs.py -q
```

Expected: PASS.

- [ ] **Step 4: Executar a suíte completa**

```powershell
python -m pytest -q
```

Expected: todos os testes passam; skips e xfail previamente conhecidos permanecem documentados.

- [ ] **Step 5: Fazer QA visual em navegador real**

Iniciar o aplicativo:

```powershell
python app.py
```

Validar `/app` após login nas larguras 1440, 1280, 768, 390 e 320 px. Em cada largura, conferir:

- fotografia visível sem competir com os dados;
- textos principais em verde-escuro;
- ausência de movimento ao passar o mouse;
- nenhuma informação dependente de hover;
- foco visível por teclado;
- sem overflow horizontal;
- cards, decisão e evidências legíveis;
- navegação inferior sem cobrir conteúdo.

- [ ] **Step 6: Commitar documentação e ajustes finais de QA**

```powershell
git add .interface-design/system.md static/orkavyn-fields.css templates/index.html tests/test_ui_fields_contract.py
git commit -m "docs: record natural executive dashboard pattern"
```

- [ ] **Step 7: Confirmar que arquivos privados e auxiliares não entram no commit**

```powershell
git status --short
```

Expected: `out/`, `.claude/`, `.superpowers/brainstorm/` e diretórios locais de pytest permanecem não rastreados.
