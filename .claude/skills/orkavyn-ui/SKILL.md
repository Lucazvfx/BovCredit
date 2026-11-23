---
name: orkavyn-ui
description: Use ao criar ou alterar a UI do dashboard Orkavyn (templates/index.html e estilos/JS associados) para seguir os Design Tokens agro-fintech verde-floresta, light/dark mode, tipografia e regras de segurança do frontend.
---

# Orkavyn UI — Design Tokens e regras

Paleta verde-floresta agro-fintech. Light em `:root`, dark em `[data-theme="dark"]`.

## Tokens

| Token | Light | Dark |
|---|---|---|
| `--brand-primary` | `#166534` | `#22C55E` |
| `--brand-primary-hover` | `#14532D` | `#16A34A` |
| `--brand-hero-start` | `#14532D` | `#0F2E1D` |
| `--brand-hero-end` | `#166534` | `#14532D` |
| `--brand-tint` | `#ECFDF5` | `rgba(34, 197, 94, 0.12)` |
| `--bg-canvas` | `#F6F8F7` | `#0B110E` |
| `--bg-surface` | `#FFFFFF` | `#111915` |
| `--bg-subtle` | `#F0F4F2` | `#18231D` |
| `--border-subtle` | `#E2E8E5` | `#23322A` |
| `--border-strong` | `#CBD5D0` | `#32473B` |
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

## Regras

- Fonte **Inter**.
- `font-variant-numeric: tabular-nums` em todos os números e tabelas; colunas numéricas alinhadas à direita.
- Raios: **8px** (inputs, chips), **14px** (cards), **20px** (hero).
- Cores só via tokens; status sempre pelos pares `--status-*-fg/bg` (nunca só cor: acompanhar de texto/rótulo).
- Logos: `static/img/logo-light.svg` no tema claro, `logo-dark.svg` no escuro.
- Anti-poluição: um card por bloco, um CTA primário por tela, exceções primeiro (banner antes de detalhes), detalhes em abas.
- **Segurança:** zero `innerHTML` com dado vindo da API ou do usuário; usar `textContent` / `createElement`.
- **Payload:** novos campos numéricos convertidos com `Number()`; campos vazios são omitidos do JSON (nunca string numérica, nunca envio parcial de grupos que exigem preenchimento conjunto).
