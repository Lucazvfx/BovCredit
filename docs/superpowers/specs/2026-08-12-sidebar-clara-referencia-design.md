# Barra lateral clara — desenho aprovado

## Objetivo

Aproximar a barra lateral desktop do Orkavyn Agro Intelligence da referência visual enviada pelo usuário: navegação clara, organizada e corporativa, com item ativo em verde-escuro e conta no rodapé. A mudança é exclusivamente de apresentação e composição; os destinos e o comportamento atual da aplicação permanecem intactos.

## Escopo

- Aplicar a mudança somente à barra lateral desktop, acima de `900px`.
- Manter a navegação móvel inferior existente.
- Preservar os destinos atuais: Nova análise, Resultado, Cenários, Histórico e Ajuda.
- Exibir a marca Orkavyn Agro Intelligence no topo.
- Exibir o usuário autenticado e o link “Sair da conta” no rodapé.
- Remover o botão “Sair” do cabeçalho desktop para evitar ação duplicada.
- Preservar no cabeçalho as cotações, empresa ativa, marca e acesso administrativo.

## Composição visual

### Estrutura

- Largura desktop: `280px`.
- Fundo: areia clara e levemente translúcida, coerente com o dashboard Executivo Natural.
- Borda direita: fina e quente, sem sombra forte.
- Padding lateral: `24px`.
- A barra ocupa toda a altura e usa três regiões: marca, navegação e conta.

### Marca

- Usar o ativo oficial existente, sem criar ou alterar logotipo.
- Nome “Orkavyn” com descritor “Agro Intelligence”.
- A marca fica alinhada à esquerda e possui área de respiro maior que os itens de navegação.

### Navegação

- Rótulo de seção: “Análise econômico-produtiva”, em caixa alta, marrom-terra e tipografia pequena.
- Itens inativos: texto e ícone verde-floresta sobre fundo transparente.
- Item ativo: bloco verde-floresta, texto claro, raio entre `12px` e `14px`.
- Ícones: SVG lineares embutidos e acessíveis, sem dependência externa e sem emojis.
- Hover: apenas alteração de cor de fundo e borda; sem deslocamento, escala, sombra ou revelação.
- Foco por teclado: contorno visível e contrastante.

### Rodapé da conta

- Fica preso ao final da barra usando `margin-top: auto`.
- Mostra o nome do usuário quando disponível; usa o e-mail como fallback.
- “Sair da conta” é um link explícito para `/logout`.
- Nenhum dado sensível além do nome/e-mail já disponível na sessão é exibido.

## Responsividade

- Acima de `900px`, o workspace se desloca pela nova largura de `280px`.
- Em `900px` ou menos, a barra lateral continua recolhida e a navegação inferior existente permanece como mecanismo principal.
- A mudança não pode criar rolagem horizontal em `1280px`, `1024px` ou nos breakpoints móveis existentes.

## Compatibilidade funcional

- Os atributos `data-ork-nav`, os valores passados a `showTab` e os estados `is-active`/`aria-current` serão mantidos.
- O controle atual de abas continuará sendo realizado por `static/orkavyn-shell.js` e pelo JavaScript existente.
- Nenhuma regra de classificação, PDF, fluxo de caixa, autenticação ou banco de dados será alterada.

## Arquivos previstos

- `templates/partials/fields_sidebar.html`: marca, ícones, menu e conta.
- `static/orkavyn-fields.css`: composição, cores e estados da barra.
- `templates/index.html`: remoção da ação duplicada de saída no cabeçalho.
- `tests/test_ui_fields_contract.py`: contrato estrutural, conta, saída e preservação dos destinos.
- `.interface-design/system.md`: atualização do padrão visual da barra lateral.

## Validação

- Testes estáticos devem comprovar os cinco destinos existentes e seus contratos de navegação.
- Testes devem comprovar que a conta e `/logout` existem na barra e que o cabeçalho não duplica a saída.
- Testes devem comprovar largura de `280px`, superfície clara, item ativo escuro e ausência de movimento no hover.
- Executar os testes de contrato visual e os testes estáticos do upload/classificação que dependem do template.
- Fazer inspeção visual desktop e móvel quando o navegador local estiver acessível.

## Fora do escopo

- Criar páginas ou destinos novos.
- Alterar a barra inferior móvel.
- Copiar menus do Orkavyn Fields que não existem no Agro Intelligence.
- Alterar autenticação, permissões ou encerramento de sessão.
