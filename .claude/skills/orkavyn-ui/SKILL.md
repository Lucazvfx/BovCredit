---
name: orkavyn-ui
description: Design System institucional agro-fintech do Orkavyn Agro Intelligence (BovCredit). Use sempre que criar ou editar telas autenticadas (`templates/index.html`, `admin.html`, `login.html`, `cadastro.html`, `login_2fa.html`) ou estilos/JS do dashboard. Não aplicar na `landing.html` sem pedido explícito.
---

# Orkavyn UI — Design System Agro-Fintech

Identidade visual institucional para análise de crédito pecuário. Combina a calma e clareza de fintechs B2B (Mercury, Stripe, Brex) com paleta verde-floresta sóbria e leitura rápida de risco.

## 1. Stack e Restrições Técnicas

- **Sem build step:** HTML semântico (Jinja2/Flask), CSS puro com Custom Properties (`:root`) e JavaScript vanilla. Não introduzir React, Tailwind CLI ou bundlers.
- **Light + Dark mode obrigatórios:** Usar sempre as variáveis CSS abaixo e alternar `static/img/logo-light.svg` / `static/img/logo-dark.svg` conforme o tema.
- **Segurança (XSS):** Nunca usar `innerHTML` com dados vindos da API ou do usuário. Preferir `textContent`, `document.createElement` ou função de escape rigorosa.
- **Tipagem de API:** Endpoints como `/api/classificar` rejeitam strings numéricas nos campos novos (`preco_arroba_base`, `custo_reposicao_anual`, `custo_suplementacao_anual`, `capital_giro_inicial`). Sempre converter inputs com `Number()` e omitir campos vazios antes de enviar o JSON.
- **Preservar `templates/landing.html`:** Não alterar a landing page em tarefas de dashboard.

## 2. Design Tokens (CSS Variables)

```css
:root {
  /* Marca & Ação (Verde-Floresta Agro-Fintech) */
  --brand-primary: #166534;
  --brand-primary-hover: #14532D;
  --brand-hero-start: #14532D;
  --brand-hero-end: #166534;
  --brand-tint: #ECFDF5;

  /* Superfícies */
  --bg-canvas: #F6F8F7;
  --bg-surface: #FFFFFF;
  --bg-subtle: #F0F4F2;
  --border-subtle: #E2E8E5;
  --border-strong: #CBD5D0;

  /* Tipografia */
  --text-primary: #111827;
  --text-secondary: #4B5563;
  --text-muted: #6B7280;
  --text-on-brand: #FFFFFF;

  /* Semântica de Crédito (usar APENAS para status/risco) */
  --status-approve-fg: #15803D;
  --status-approve-bg: #DCFCE7;
  --status-warn-fg: #B45309;
  --status-warn-bg: #FEF3C7;
  --status-reject-fg: #B91C1C;
  --status-reject-bg: #FEE2E2;

  /* Raios, Espaçamento e Elevação */
  --radius-sm: 8px;
  --radius-md: 14px;
  --radius-lg: 20px;
  --shadow-card: 0 1px 2px rgba(17, 24, 39, 0.04), 0 4px 12px rgba(17, 24, 39, 0.03);
}

[data-theme="dark"] {
  --brand-primary: #22C55E;
  --brand-primary-hover: #16A34A;
  --brand-hero-start: #0F2E1D;
  --brand-hero-end: #14532D;
  --brand-tint: rgba(34, 197, 94, 0.12);

  --bg-canvas: #0B110E;
  --bg-surface: #111915;
  --bg-subtle: #18231D;
  --border-subtle: #23322A;
  --border-strong: #32473B;

  --text-primary: #F3F4F6;
  --text-secondary: #D1D5DB;
  --text-muted: #9CA3AF;
  --text-on-brand: #FFFFFF;

  --status-approve-fg: #4ADE80;
  --status-approve-bg: rgba(34, 197, 94, 0.16);
  --status-warn-fg: #FBBF24;
  --status-warn-bg: rgba(245, 158, 11, 0.16);
  --status-reject-fg: #F87171;
  --status-reject-bg: rgba(239, 68, 68, 0.16);
}
```
