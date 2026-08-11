# Orkavyn Fields — sistema de interface

## Direção

O sistema visual combina uma âncora orgânica com composição executiva. Verde floresta identifica navegação e ações principais; areia, aveia e argila estruturam superfícies; marrom-terra identifica contexto e evidências. A interface deve parecer ligada ao campo sem perder a objetividade necessária a uma decisão econômico-financeira B2B.

## Profundidade e geometria

- Escala de espaçamento: múltiplos de `4px`.
- Controles: raio de `10px`, altura mínima de toque de `44px`.
- Painéis: raio de `20px`, borda quente e sombra sutil.
- Barra lateral no desktop: `256px`, fixa e verde floresta.
- Navegação móvel: barra inferior flutuante, respeitando `safe-area-inset-bottom`.
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
--ork-sidebar-width: 256px;
```

## Padrões centrais

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
- `templates/partials/fields_sidebar.html`: navegação lateral da aplicação.
- `templates/partials/fields_mobile_nav.html`: navegação inferior móvel.
- `templates/index.html`: preserva os IDs e renderizadores do fluxo de análise.

## Breakpoints

- `> 900px`: sidebar fixa de `256px` e workspace deslocado.
- `≤ 900px`: sidebar recolhível, bottom navigation e espaço inferior seguro.
- `≤ 760px`: grids de importação, decisão, landing e demo são empilhados.
- `≤ 480px`: painéis usam gutters de `16px` e métricas ficam em uma coluna.

## Roteiro de QA visual

Verificar landing, login, aplicação, administração, demonstração e páginas legais em `1440×900`, `1280×800`, `768×1024`, `390×844` e `320×720`. Exercitar documento → revisão → classificação → cenários → histórico → PDF. Conferir foco, loading anunciado, ausência de overflow horizontal, ação dominante e faixa de evidências. As capturas devem ser atualizadas somente após inspeção em navegador real.
