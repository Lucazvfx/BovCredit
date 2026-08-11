# Orkavyn Agro Intelligence — Redesign visual Fields Executivo

## Objetivo

Unificar toda a interface da Orkavyn Agro Intelligence em um sistema visual limpo, profissional e ligado ao campo, inspirado nas referências do Orkavyn Fields fornecidas pelo usuário. O redesign deve melhorar hierarquia, legibilidade e consistência sem alterar cálculos, endpoints, IDs, seletores, autenticação, leitura de documentos ou fluxo de análise existentes.

## Escopo

O novo sistema visual será aplicado a:

- landing page;
- login, cadastro, recuperação de senha e autenticação em duas etapas;
- tela principal de análise;
- importação de PDF e planilha;
- composição e classificação do rebanho;
- resultados, cenários, histórico e ajuda;
- administração;
- termos e privacidade;
- modo demonstração e relatório B2B previstos na evolução do produto.

## Direção escolhida

### Anchor visual

Organic, com composição executiva. A interface deve parecer parte do universo rural, mas adequada a analistas de crédito e consultores. O resultado não deve parecer rústico, artesanal ou decorativo.

### Domínio

- estrutura do rebanho;
- ciclos de cria, recria e engorda;
- pastagem e sazonalidade;
- arrobas, produção e comercialização;
- evidências documentais;
- capacidade de pagamento;
- risco e confiança dos dados.

### Mundo de cores

- verde-floresta para navegação e ações principais;
- musgo para evidências e estados positivos;
- sálvia para superfícies ambientais;
- areia e aveia para cartões e áreas de trabalho;
- argila e marrom-terra para rótulos e destaques do domínio;
- vermelho e âmbar dessaturados apenas para risco e atenção.

Os tokens devem utilizar nomes do produto, como `--forest`, `--pasture`, `--sand`, `--oat`, `--clay`, `--soil`, `--ink` e tokens semânticos derivados.

### Assinatura do produto

A “faixa de evidências” acompanha as principais conclusões. Capacidade estimada, DSCR, risco e sistema produtivo devem poder exibir, no mesmo contexto visual, qualidade dos dados, premissas, fontes e alertas relevantes.

Essa faixa é o elemento que diferencia a Orkavyn de um dashboard genérico: a decisão permanece ligada à sua explicação.

## Hierarquia e composição

### Desktop

- menu lateral fixo, em verde-floresta, com largura aproximada de 240 a 272 px;
- área principal clara e responsiva;
- cabeçalho local por tela, sem duplicar toda a navegação;
- conteúdo com largura confortável e seções claramente agrupadas;
- uma ação principal dominante em cada tela;
- navegação da análise organizada por etapas e áreas: entrada, rebanho, produção, financeiro, capacidade, stress, premissas e relatório.

### Mobile

- composição inspirada diretamente nas referências Fields;
- navegação inferior para as áreas principais;
- ação central destacada somente quando existir uma ação global real;
- cartões em uma coluna, com alvos de toque de pelo menos 44 px;
- menus administrativos ou secundários acessíveis por painel, sem lotar a barra inferior.

### Densidade

- base de espaçamento de 4 px;
- controles e formulários com densidade média;
- áreas de decisão mais abertas que as áreas de entrada;
- cartões não devem ter todos a mesma dimensão ou importância;
- números usam algarismos tabulares.

## Tipografia

Usar uma família geométrica e humanista disponível de forma confiável no projeto. Epilogue é a preferência para títulos e interface caso possa ser carregada com fallback seguro; caso contrário, usar uma pilha sans-serif humanista compatível.

Hierarquia prevista:

- rótulos de domínio pequenos, com caixa alta e espaçamento moderado;
- títulos fortes, compactos e alinhados à esquerda;
- texto de apoio em cor secundária;
- dados financeiros e zootécnicos com peso e números tabulares;
- no máximo quatro níveis de cor textual: principal, secundário, terciário e desabilitado.

## Superfícies e profundidade

- fundo rural dessaturado pode aparecer em landing, login e áreas de entrada, sempre com camada que garanta contraste;
- superfícies principais usam areia ou aveia, não branco puro;
- cartões usam raios entre 16 e 24 px;
- controles usam raios menores e coerentes;
- profundidade por sombras suaves e mudanças discretas de superfície;
- bordas são baixas em contraste e usadas apenas quando ajudam a estrutura;
- não usar gradientes decorativos, vidro excessivo ou sombras dramáticas.

## Componentes principais

### Navegação lateral

Contém marca, áreas do produto, empresa ativa e ações de conta. O item atual recebe superfície sutil e contraste claro. Administração aparece apenas quando autorizada.

### Cabeçalho de contexto

Mostra título da área, fazenda/empresa ativa e ações locais. Cotações podem permanecer como informação contextual, sem competir com a tarefa principal.

### Entrada de documentos

Importação de PDF deve ser o foco inicial da análise. Planilha e preenchimento manual permanecem disponíveis como alternativas. O componente deve mostrar estados de arquivo selecionado, processando, concluído, parcial e erro.

### Formulários

Os grupos atuais serão reorganizados visualmente sem mudar IDs ou contratos. Campos críticos recebem mensagens de validação próximas. Seções avançadas podem ser recolhíveis, mantendo controles nativos e acessíveis.

### Resultados

O primeiro nível mostra capacidade estimada, DSCR, resultado operacional, risco e qualidade dos dados. A composição do rebanho e projeções aparecem como evidências abaixo. A faixa de evidências explica cada conclusão relevante.

### Tabelas e histórico

Tabelas permanecem sem grades verticais pesadas. Cabeçalhos, valores numéricos e estados devem ser legíveis em desktop; em mobile, tabelas extensas usam contêiner horizontal ou representação em linhas quando necessário.

### Modais e feedback

Modais usam foco gerenciado, retorno de foco e fechamento por Escape quando já suportado. Toasts, erros e carregamento usam os mesmos tokens semânticos. Movimento fica abaixo de 300 ms e respeita `prefers-reduced-motion`.

## Páginas institucionais e autenticação

Landing, login e cadastro compartilham a identidade Fields, mas não repetem o dashboard. A landing deve explicar o valor do produto com conteúdo real. Autenticação prioriza clareza, confiança e contraste. Termos e privacidade usam uma área de leitura simples, sem fundo fotográfico atrás do texto longo.

## Administração

A área administrativa mantém maior densidade, mas usa os mesmos tokens, navegação e componentes. Usuários, empresas, API keys, auditoria e configurações devem ter hierarquia de ferramenta operacional, sem cartões decorativos.

## Preservação funcional

- nenhum endpoint existente será removido ou renomeado;
- IDs usados pelo JavaScript serão preservados;
- funções JavaScript atuais continuarão sendo chamadas pelos mesmos controles;
- upload, parser de PDF/XLSM, classificação, cenários, histórico e exportação continuarão funcionando;
- mudanças estruturais no HTML serão graduais e acompanhadas por testes de seletores;
- alterações parciais já presentes no worktree serão revisadas antes de serem aproveitadas ou descartadas.

## Estados e tratamento de erro

Cada fluxo relevante deve contemplar:

- carregamento;
- vazio;
- sucesso;
- aviso ou leitura parcial;
- erro recuperável;
- erro de validação;
- indisponibilidade de integração.

Erros não devem desaparecer em modais genéricos ou depender apenas de cor. O usuário deve entender o que aconteceu e qual ação pode tomar.

## Responsividade e acessibilidade

- suporte principal a desktop e mobile;
- navegação utilizável por teclado;
- foco visível;
- semântica nativa para botões, links, inputs, selects e diálogos;
- contraste legível sobre imagens e superfícies coloridas;
- alvos de toque mínimos de 44 px;
- ausência de texto ou controles sobrepostos em 320 px;
- suporte a `prefers-reduced-motion`.

## Estratégia de implementação

1. inventariar seletores e estados atuais;
2. criar tokens e componentes visuais compartilhados;
3. implementar shell desktop e navegação mobile;
4. migrar a tela principal por áreas, preservando comportamento;
5. migrar autenticação, landing, administração e páginas legais;
6. concluir demo e relatório B2B;
7. executar testes funcionais e validação visual em desktop e mobile;
8. registrar o sistema aprovado em `.interface-design/system.md`.

## Verificação

- testes automatizados existentes devem permanecer verdes;
- novos testes verificam seletores críticos, páginas, estados e acessibilidade básica;
- fluxo manual: login → importar PDF → conferir dados → classificar → cenários → relatório;
- validação visual em desktop largo, notebook, tablet e mobile;
- comparação final com as referências Fields para confirmar paleta, leveza, proporções e hierarquia;
- nenhuma informação fictícia será apresentada como dado real.

## Fora do escopo

- alterar fórmulas econômicas ou zootécnicas;
- mudar contratos da API;
- criar novos módulos de manejo, mapa, tarefas ou operação de campo mostrados nas referências;
- copiar funcionalidades do Orkavyn Fields que não existem na Orkavyn Agro Intelligence;
- adicionar animações ornamentais ou dependências visuais desnecessárias.
