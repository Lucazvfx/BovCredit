# Orkavyn Agro Intelligence — Dashboard Executivo Natural

## Objetivo

Refinar o dashboard e os resultados da análise para transmitir maior clareza, confiança e profissionalismo. A nova composição mantém a identidade rural da Orkavyn, mas reduz efeitos visuais, contrastes excessivos e movimentos que desviam a atenção dos indicadores econômico-produtivos.

Esta mudança é exclusivamente visual. Cálculos, endpoints, IDs, seletores, autenticação, classificação, fluxo de caixa e geração de relatórios permanecem inalterados.

## Direção aprovada

O dashboard seguirá a direção **Executivo Natural**:

- verde-escuro como cor principal dos textos e da navegação;
- fotografia rural discretamente visível no fundo;
- superfícies claras e quase opacas sobre a fotografia;
- hierarquia mais limpa, com menos sombras e divisões;
- ausência de movimentos ou revelações ao passar o mouse;
- cores de alerta reservadas a estados com significado real.

## Hierarquia visual

O foco inicial da tela será a leitura da decisão e de seus indicadores principais. A ordem visual será:

1. contexto da análise e propriedade ativa;
2. capacidade estimada, DSCR, resultado operacional, risco e qualidade dos dados;
3. explicação e faixa de evidências;
4. composição do rebanho e projeções;
5. detalhes financeiros, premissas e ações secundárias.

Títulos, valores e rótulos devem ser distinguidos principalmente por peso, tamanho e espaçamento, evitando depender de várias cores.

## Cores e tipografia

- Títulos, valores e textos principais usarão `--ork-forest` ou um verde-escuro derivado com contraste adequado.
- Textos secundários usarão um verde acinzentado, evitando cinza frio e preto puro.
- O marrom-terra ficará restrito a contexto, proveniência e pequenos marcadores de domínio.
- Âmbar e vermelho serão usados somente para atenção e risco.
- Valores numéricos manterão algarismos tabulares.
- A hierarquia atual de Barlow Condensed, Barlow e DM Mono será preservada, mas com menos variações simultâneas de cor e peso.

## Fundo rural

A fotografia existente do rebanho será reutilizada como fundo ambiental do workspace do dashboard.

- Presença visual aproximada: 10% a 15%.
- A imagem não ficará diretamente atrás de tabelas, textos longos ou gráficos sem uma superfície intermediária.
- O enquadramento deve funcionar em desktop e mobile sem criar áreas de alto contraste atrás do conteúdo.
- O fundo permanece fixo ou estático; não haverá paralaxe.
- Em dispositivos com economia de dados ou quando a imagem não carregar, a superfície areia continuará garantindo a leitura.

## Superfícies e profundidade

- Painéis principais usarão marfim claro com opacidade suficiente para leitura, aproximadamente 94% a 98% conforme o contexto.
- Sombras serão reduzidas a uma elevação curta e suave.
- Bordas existirão apenas para separar grupos, entradas e estados.
- Raios atuais serão preservados, evitando aumentar o aspecto arredondado.
- Seções relacionadas poderão compartilhar uma superfície maior em vez de parecer uma coleção de cartões independentes.

## Interações

Serão removidos do dashboard:

- deslocamento vertical de cartões ou botões no hover;
- aumento de escala;
- conteúdo revelado apenas ao passar o mouse;
- mudanças fortes de sombra;
- transições aplicadas indiscriminadamente.

Permanecerão:

- mudança discreta de cor em links, botões e itens de navegação;
- estado ativo claramente visível;
- foco de teclado com contraste adequado;
- feedback de pressionamento curto, sem deslocar o layout;
- estados de carregamento, sucesso, parcial, alerta, erro e vazio.

Informação necessária à análise nunca dependerá de hover, inclusive em desktop.

## Componentes afetados

- shell e workspace do dashboard;
- cabeçalho de contexto;
- cards de indicadores principais;
- resumo de decisão;
- faixa de evidências;
- painéis de rebanho, produção, financeiro e risco;
- tabelas e blocos de histórico mostrados dentro do dashboard;
- botões e navegação lateral presentes nessas vistas;
- adaptação correspondente da navegação e dos painéis em mobile.

Landing page, autenticação, administração, páginas legais e demonstração não fazem parte desta rodada, salvo ajustes em tokens compartilhados indispensáveis para impedir regressão no dashboard.

## Responsividade

- Em desktop, a fotografia permanece ambiental e os painéis formam uma grade executiva legível.
- Em tablet, os indicadores se reorganizam sem reduzir valores críticos a tamanhos ilegíveis.
- Em mobile, os painéis ficam em uma coluna e o fundo recebe cobertura mais forte para evitar ruído.
- Nenhum conteúdo crítico ficará oculto por hover, tooltips ou largura de viewport.
- A navegação inferior continuará respeitando `safe-area-inset-bottom`.

## Acessibilidade

- Contraste mínimo será verificado sobre cada superfície translúcida.
- O texto não será colocado diretamente sobre trechos detalhados da fotografia.
- Controles manterão alvo mínimo de 44 px.
- Foco por teclado permanecerá visível.
- `prefers-reduced-motion` continuará eliminando movimento não essencial.
- Alertas usarão texto e ícone além da cor.

## Preservação funcional

- IDs e classes consumidos pelo JavaScript serão preservados.
- Renderizadores atuais continuarão recebendo os mesmos dados.
- Nenhuma regra de negócio será movida para CSS ou JavaScript visual.
- Upload, classificação, cenários, histórico, análise e PDF continuarão com os mesmos contratos.
- Conteúdo inexistente não será substituído por números fictícios.

## Verificação

### Automatizada

- executar os testes de contrato visual existentes;
- adicionar testes para impedir retorno de `translateY`, `scale` e conteúdo crítico dependente de hover no dashboard;
- conferir preservação dos seletores e estados principais;
- executar a suíte relevante de frontend e regressão.

### Visual

Validar dashboard e resultados em:

- 1440 × 900;
- 1280 × 800;
- 768 × 1024;
- 390 × 844;
- 320 × 720.

Conferir:

- legibilidade sobre o fundo;
- verde-escuro consistente nos textos;
- fotografia presente sem competir com dados;
- ausência de movimentos no hover;
- foco visível;
- ausência de overflow e sobreposição;
- leitura clara da decisão e das evidências.

## Critérios de aceite

- O dashboard parece mais limpo e profissional que a versão anterior.
- A fotografia do campo é percebida, mas não reduz a leitura.
- Textos principais são predominantemente verde-escuro.
- Nenhum dado aparece ou desaparece apenas por hover.
- Cards não sobem, aumentam ou mudam de profundidade ao passar o mouse.
- A decisão, os indicadores e a faixa de evidências formam a hierarquia dominante.
- O fluxo funcional existente permanece íntegro.
