# Transparência de custos de produção e reposição

## Objetivo

Explicar por que cria e recria podem apresentar caixa negativo sem alterar a regra financeira vigente. A análise deve mostrar manutenção, reposição, resultado antes da reposição, resultado operacional de caixa e resultado econômico.

## Decisão

Manter a reposição dentro do resultado operacional e do caixa. A reposição é desembolso real quando o produtor compra animais para manter o fluxo produtivo. A mudança será de decomposição e comunicação, não de premissa.

## Desenho

O motor já calcula `custo_manutencao` e `custo_reposicao` por ano. A camada da aplicação agregará esses valores no `fluxo_gep` do primeiro ano, preservando `custo_operacional` como soma das duas parcelas. Serão adicionados:

- `custo_manutencao`;
- `custo_reposicao`;
- `resultado_antes_reposicao`;
- `resultado_operacional` continuará sendo o resultado após reposição;
- `resultado_economico` continuará incluindo a variação de estoque.

O painel exibirá as duas parcelas e um subtotal antes da reposição. O PDF repetirá a mesma estrutura. Nenhum valor usado pelo DSCR será redefinido.

## Critérios de aceite

1. Para recria, a API informa manutenção e reposição separadamente e a soma é igual ao custo operacional.
2. O resultado antes da reposição é receita menos manutenção.
3. O resultado operacional permanece receita menos manutenção menos reposição.
4. O painel e o PDF exibem a decomposição sem esconder o caixa final.
5. Os testes de cria, recria e regressão existentes continuam passando.
