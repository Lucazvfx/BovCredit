# Classificação automática por ficha sem vendas confirmadas

## Objetivo

Permitir que o BovCredit leia uma ficha de saldo e infira automaticamente o
ciclo produtivo pela composição do rebanho, mesmo quando a fonte não informa
vendas de bois. A ausência de vendas deve reduzir a qualidade/proveniência da
conclusão, mas não ser tratada como venda zero nem impedir a simulação.

## Comportamento aprovado

Para uma ficha sem `bois_vendidos`:

1. O modelo e a composição do rebanho continuam determinando o ciclo inferido.
2. O ciclo inferido alimenta os cálculos de projeção e fluxo de caixa.
3. A resposta declara que a classificação é automática e limitada pela
   ausência de vendas confirmadas.
4. O frontend mostra o ciclo inferido, a confiança, os dados ausentes e a
   necessidade de revisão humana.
5. O resultado financeiro permanece uma estimativa baseada nas premissas
   disponíveis; não deve ser apresentado como dado observado da fazenda.

## Regras de dados

- `bois_vendidos=None` significa desconhecido.
- `bois_vendidos=0` significa que o analista informou explicitamente zero.
- Regras que exigem venda confirmada só podem usar o segundo caso.
- Dados ausentes devem aparecer em `dados_faltantes` e na proveniência da
  decisão.

## Contrato de saída

O resultado de classificação deve preservar `tipo` como o ciclo inferido usado
pelos consumidores atuais e incluir:

- `tipo_modelo`: classe de maior probabilidade do modelo;
- `classificacao_limitada`: verdadeiro quando faltarem dados relevantes;
- `dados_faltantes`: lista dos campos ausentes;
- `revisao_humana`: verdadeiro quando a conclusão exigir confirmação.

No caso INDEA de 4.789 cabeças, a composição atualmente produz maior
probabilidade para `CICLO_COMPLETO`; esse ciclo deve ser usado na projeção,
com `bois_vendidos` listado como ausente.

## Impacto no fluxo

`api_classificar` continuará usando `result['tipo']` para benchmarks,
simulação, parecer e sensibilidade. Como `tipo` passará a representar a
inferência automática da composição quando as vendas forem desconhecidas, o
fluxo será coerente com a leitura automática da ficha.

As ressalvas de qualidade devem acompanhar o parecer para evitar que a
estimativa seja confundida com confirmação documental.

## Testes de aceitação

- O vetor INDEA `[300, 280, 563, 187, 1105, 1344, 298, 80, 593, 39]` continua
  sendo extraído como total 4.789.
- Sem `bois_vendidos`, a classificação usa a classe inferida pelo modelo e
  retorna `bois_vendidos` em `dados_faltantes`.
- A simulação recebe o ciclo inferido, não um ciclo substituto por ausência de
  vendas.
- Com `bois_vendidos=0` explicitamente informado, as regras conservadoras de
  ausência de venda continuam disponíveis.
- A interface mostra a ressalva de classificação limitada.

## Fora do escopo

- Inventar vendas, pesos, custos ou mortalidade.
- Transformar a inferência automática em aprovação de crédito.
- Alterar o modelo ML ou recalibrar suas probabilidades.
- Misturar os casos de 400, 5.837 e 4.789 cabeças.
