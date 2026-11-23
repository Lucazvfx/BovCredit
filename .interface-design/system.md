# Orkavyn Fields — sistema de interface

## Direção

O sistema visual combina uma âncora orgânica com composição executiva. Verde floresta identifica navegação e ações principais; areia, aveia e argila estruturam superfícies; marrom-terra identifica contexto e evidências. A interface deve parecer ligada ao campo sem perder a objetividade necessária a uma decisão econômico-financeira B2B.

## Profundidade e geometria

- Escala de espaçamento: múltiplos de `4px`.
- Controles: raio de `10px`, altura mínima de toque de `44px`.
- Painéis: raio de `20px`, borda quente e sombra sutil.
- Navegação do dashboard: dock flutuante (`templates/partials/dashboard_dock.html`), respeitando `safe-area-inset-bottom` no celular.
- Movimento: transições de até `180ms`; o modo de movimento reduzido elimina animações perceptíveis.

## Hierarquia tipográfica

- Títulos: Barlow Condensed, alto peso, espaçamento compacto.
- Texto e controles: Barlow ou fonte de sistema equivalente.
- Dados técnicos curtos: DM Mono.
- Kicker: caixa alta, marrom-terra, corpo pequeno e espaçamento aberto.

## Tokens

```css
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
--ork-sidebar-width: 280px;
```

## Padrões centrais

### Dashboard Executivo Natural

- Texto principal: `--ork-forest`; evitar preto puro no workspace analítico.
- Fundo: `rebanho-bg.jpg` estático, opacidade `0.12` no desktop e `0.10` até `480px`.
- Painéis analíticos: `rgba(251, 247, 239, 0.96)` e `--ork-shadow-dashboard`.
- Hover: somente cor e borda; nunca deslocamento, escala, revelação ou mudança de profundidade.
- Exceções de movimento: skip link, toast, drawer e feedback de estado, sempre respeitando movimento reduzido.
- Informação crítica nunca depende de hover.

### Dock de navegação

- Barra flutuante com ícones SVG lineares (`currentColor`), sem bibliotecas externas.
- Item ativo em verde floresta; itens inativos e hover permanecem claros.
- Hover altera somente cor, fundo e borda, sem deslocamento, escala ou mudança de profundidade.

### Texto da interface

Interface B2B sóbria: sem emojis em rótulos, botões, estados ou mensagens. Ícones são SVG lineares; o significado vem do texto, nunca de um símbolo isolado.

### Ação dominante

Cada tela possui uma ação primária. Alternativas são secundárias e visualmente mais silenciosas. Ações destrutivas usam texto explícito e o token de perigo.

### Faixa de evidências

Uma conclusão de crédito nunca aparece isolada. A faixa de evidências liga a decisão a quatro dimensões: qualidade dos dados, premissas alteradas, fontes e limitações. Os valores vêm dos motores determinísticos ou da proveniência armazenada; IA generativa não os calcula.

### Estados

Carregando, sucesso, parcial, alerta, erro e vazio possuem texto além da cor. Estados de erro sempre indicam a próxima ação disponível.

## Acessibilidade

Controles nativos são preservados, o foco é visível, as navegações possuem rótulo, o alvo mínimo é de `44px` e `prefers-reduced-motion` é respeitado. Fundo fotográfico nunca fica atrás de texto longo ou dados críticos.

## Entradas de manutenção

- `static/orkavyn-fields.css`: fonte única dos tokens e componentes compartilhados.
- `static/orkavyn-shell.js`: somente comportamento de navegação; não contém regra de negócio.
- `static/orkavyn-dashboard.css` e `static/orkavyn-dashboard.js`: estilo e comportamento do dashboard.
- `templates/partials/dashboard_dock.html`: dock de navegação do dashboard.
- `templates/index.html`: preserva os IDs e renderizadores do fluxo de análise.

## Breakpoints

- `> 900px`: dock flutuante no dashboard.
- `≤ 900px`: dock adaptada ao celular, com espaço inferior seguro.
- `≤ 760px`: grids de importação, decisão, landing e demo são empilhados.
- `≤ 480px`: painéis usam gutters de `16px` e métricas ficam em uma coluna.

## Roteiro de QA visual

Verificar landing, login, aplicação, administração, demonstração e páginas legais em `1440×900`, `1280×800`, `768×1024`, `390×844` e `320×720`. Exercitar documento → revisão → classificação → cenários → histórico → PDF. Conferir foco, loading anunciado, ausência de overflow horizontal, ação dominante e faixa de evidências. As capturas devem ser atualizadas somente após inspeção em navegador real.
