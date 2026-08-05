# Qualidade, explicação, validação e cenários da análise

## Objetivo

Melhorar a transparência do BovCredit quando a ficha não contém todos os dados necessários. A aplicação continuará capaz de gerar uma simulação usando parâmetros padrão, mas distinguirá claramente fatos extraídos do documento, dados informados pelo analista, estimativas e dados ausentes.

## Escopo

1. Classificar a origem e a qualidade dos principais dados usados no parecer.
2. Explicar os fatores que sustentam a classificação do ciclo produtivo.
3. Detectar incoerências zootécnicas e apresentar alertas acionáveis.
4. Comparar cenários base, conservador, provável e otimista.

Ficam fora deste ciclo: retreinamento do modelo, alteração das regras de crédito, integração com novas fontes externas e bloqueio do parecer por dado ausente.

## Modelo de dados

Cada indicador relevante poderá carregar:

- `valor`: número efetivamente usado;
- `origem`: `documento`, `usuario`, `estimativa` ou `ausente`;
- `informado`: se o documento ou analista forneceu o valor;
- `confianca`: quando houver classificação automática;
- `observacao`: explicação curta e legível.

Dados ausentes usarão parâmetros padrão somente na simulação. O parecer deverá marcar o resultado financeiro como estimado quando houver dependência relevante de valores ausentes.

## Explicação da classificação

O resultado deverá preservar o contrato atual de `tipo`, mas expor um bloco estruturado com:

- ciclo final e ciclo sugerido pelo modelo;
- probabilidades por classe;
- regras determinísticas aplicadas;
- composição que sustentou a decisão;
- dados faltantes relacionados à decisão;
- necessidade de confirmação humana.

As explicações devem distinguir modelo, regra e estimativa, sem apresentar uma regra como se fosse probabilidade do modelo.

## Validações zootécnicas

As validações serão avisos, não rejeições automáticas. O serviço deverá verificar, quando houver dados suficientes:

- nascimentos incompatíveis com a quantidade de matrizes e a taxa de natalidade;
- vendas acima do estoque disponível ou do volume projetado;
- mortalidade, natalidade e reposição fora das faixas configuradas;
- reposição incompatível com a manutenção da base reprodutiva;
- variação de estoque projetada que não fecha com entradas, nascimentos, vendas e mortalidade.

Cada alerta terá severidade, título, evidência numérica, impacto provável e ação sugerida. Quando não houver dados para verificar uma regra, ela será marcada como não avaliada, sem inventar um problema.

## Comparação de cenários

O endpoint de análise fornecerá uma comparação comum para:

- base estimada;
- conservador;
- provável;
- otimista.

Cada cenário usará o mesmo rebanho inicial e informará preço, custo, produção, geração de caixa, resultado, DSCR, ano crítico e capacidade de pagamento. A tabela também exibirá as premissas que mudaram e evitará comparar cenários com volumes de rebanho diferentes.

## Interface

O resultado terá três áreas visíveis:

1. **Qualidade dos dados**: encontrados, informados, estimados e ausentes.
2. **Por que o sistema chegou a este ciclo**: fatores, regras e confiança.
3. **Riscos e cenários**: alertas zootécnicos e comparação financeira.

Valores dinâmicos serão escapados no frontend. A ausência de dado deverá aparecer como “não informado”, e não como zero.

## API e compatibilidade

Os campos atuais de `/api/classificar` e o uso de `result['tipo']` serão preservados. Os novos blocos serão aditivos e opcionais para consumidores antigos. O simulador continuará recebendo o ciclo final, mas receberá metadados indicando quando suas premissas são estimadas.

## Testes de aceitação

- Uma ficha INDEA sem vendas mostra `bois_vendidos` como ausente, não como zero, e mantém o ciclo inferido.
- Uma ficha sem mortalidade gera simulação com estimativa explicitamente marcada.
- Uma venda acima do estoque gera alerta de incoerência com evidência numérica.
- A explicação identifica corretamente modelo, regra e origem dos dados.
- Os quatro cenários usam o mesmo vetor inicial e retornam métricas comparáveis.
- Os casos de 400, 5.837 e 4.789 cabeças permanecem independentes.
