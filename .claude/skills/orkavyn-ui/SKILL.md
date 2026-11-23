---
name: orkavyn-ui
description: Use ao criar ou alterar a UI do dashboard Orkavyn (templates/index.html e estilos/JS associados) para seguir o layout institucional minimalista (sem sidebar, topbar enxuta, dock flutuante), os Design Tokens agro-fintech verde-floresta, light/dark mode carvão, tipografia e regras de segurança do frontend.
---

# Orkavyn UI — Design Tokens e regras

Paleta verde-floresta agro-fintech. Light em `:root`, dark carvão em `[data-theme="dark"]` (superfícies neutras quase pretas, bordas finas translúcidas). Tokens vivem em `static/orkavyn-dashboard.css`.

## Tokens

| Token | Light | Dark |
|---|---|---|
| `--brand-primary` | `#166534` | `#22C55E` |
| `--brand-primary-hover` | `#14532D` | `#16A34A` |
| `--brand-hero-start` | `#14532D` | `#0F2E1D` |
| `--brand-hero-end` | `#166534` | `#14532D` |
| `--brand-tint` | `#ECFDF5` | `rgba(34, 197, 94, 0.12)` |
| `--bg-canvas` | `#F6F8F7` | `#0A0C0B` |
| `--bg-surface` | `#FFFFFF` | `#121513` |
| `--bg-subtle` | `#F0F4F2` | `#181C1A` |
| `--border-subtle` | `#E2E8E5` | `rgba(255, 255, 255, 0.08)` |
| `--border-strong` | `#CBD5D0` | `rgba(255, 255, 255, 0.14)` |
| `--text-primary` | `#111827` | `#F3F4F6` |
| `--text-secondary` | `#4B5563` | `#D1D5DB` |
| `--text-muted` | `#6B7280` | `#9CA3AF` |
| `--text-on-brand` | `#FFFFFF` | `#FFFFFF` |
| `--status-approve-fg` | `#15803D` | `#4ADE80` |
| `--status-approve-bg` | `#DCFCE7` | `rgba(34, 197, 94, 0.16)` |
| `--status-warn-fg` | `#B45309` | `#FBBF24` |
| `--status-warn-bg` | `#FEF3C7` | `rgba(245, 158, 11, 0.16)` |
| `--status-reject-fg` | `#B91C1C` | `#F87171` |
| `--status-reject-bg` | `#FEE2E2` | `rgba(239, 68, 68, 0.16)` |

## Layout (shell)

- **Sem sidebar.** Conteúdo centralizado em `max-width: 1120px` (`.ork-main`), com `padding-bottom: calc(96px + env(safe-area-inset-bottom))` para o dock nunca cobrir botões ou cards.
- **Topbar** (`.od-topbar`, 60px, linha única, sticky): logo à esquerda; à direita pílulas `Boi`/`Vaca` (`#hdr-boi`, `#hdr-vaca`), botão de tema (`Claro`/`Escuro`) e menu do usuário (`#od-user-menu`: empresa ativa, Acessos [admin], Marca da consultoria, Sair). O ticker de notícias fica oculto (`#news-ticker { display: none }`).
- **Dock flutuante** (`templates/partials/dashboard_dock.html`, `.od-dock`): pílula fixa e centralizada em `bottom: max(16px, env(safe-area-inset-bottom))`, fundo translúcido com `backdrop-filter: blur(12px)`, borda `--border-strong`, sombra suave. Itens: `Nova análise`, `Resultado`, `Cenários`, `Histórico` e `Mais` (popover com `Grãos & Safra`, `Lavoura perene`, `Ajuda`, `Sair`). Desktop e mobile usam o mesmo dock.
- **Menus popover** (`.od-menu`, abertos por `[data-od-menu]`): fecham com clique fora, `Esc` ou ao escolher um item. Montados em `orkavyn-dashboard.js` sem `innerHTML`.
- **Nova análise:** capa atmosférica `.od-cover` (~220px, gradiente carvão/verde-floresta, saudação + subtítulo) e card central elevado `#od-upload` (mantém as classes `analysis-flow ork-panel ork-import-panel`, de que o arrastar-e-soltar depende) sobrepondo a borda inferior da capa, com `Ler PDF` (CTA primário) e `Ler planilha`. Sem faixa de cotações no rodapé do formulário: elas vivem só na topbar.
- **Resultado:** sem capa decorativa. Abre direto no Hero verde-floresta + banner de exceção + abas (`Resumo / Base`, `Ciclo 12m`, `Estresse do Boi`). O card legado de `Resumo / Base` é compacto: *Sistema identificado*, *Resultado operacional* e o aviso de análise preliminar — nunca repetir o veredito do Hero.
- `--brand-primary` só em: CTA principal, item ativo do dock e Hero do parecer.

## Regras

- Fonte **Inter**.
- `font-variant-numeric: tabular-nums` em todos os números e tabelas; colunas numéricas alinhadas à direita.
- Raios: **8px** (inputs, chips), **14px** (cards), **20px** (hero).
- Cores só via tokens; status sempre pelos pares `--status-*-fg/bg` (nunca só cor: acompanhar de texto/rótulo).
- Logos: `static/img/logo-light.svg` no tema claro, `logo-dark.svg` no escuro.
- Anti-poluição: um card por bloco, um CTA primário por tela, exceções primeiro (banner antes de detalhes), detalhes em abas.
- **Segurança:** zero `innerHTML` com dado vindo da API ou do usuário; usar `textContent` / `createElement`.
- **Payload:** novos campos numéricos convertidos com `Number()`; campos vazios são omitidos do JSON (nunca string numérica, nunca envio parcial de grupos que exigem preenchimento conjunto).
