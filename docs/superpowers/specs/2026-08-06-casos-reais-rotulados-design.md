# Banco de Casos Reais Rotulados

## Objetivo

Criar uma base confiável de casos reais para medir e melhorar a classificação do rebanho. O sistema deve separar a previsão do modelo da decisão confirmada pelo analista e permitir retreinamento somente com rótulos humanos.

## Estado atual

A tabela `registros` já armazena composição, classificação do ML, confiança e `class_conf`. A função `exportar_treino()` já exporta registros confirmados. A nova estrutura complementará esse fluxo com origem, status, observação e rastreabilidade do documento.

## Modelo de dados

Criar a tabela `casos_reais` com:

- identificação da empresa, usuário e fazenda;
- arquivo de origem, tipo de origem e estado/modelo da ficha;
- vetor de dez valores do rebanho;
- classificação prevista e confiança;
- classificação humana, status e observação;
- timestamps de criação e confirmação;
- referência opcional ao registro original.

Status permitidos: `PENDENTE`, `CONFIRMADO` e `DESCARTADO`.

Origens permitidas: `PDF`, `EXCEL` e `MANUAL`.

## Fluxo

1. A classificação cria um caso `PENDENTE` sem entrar no treinamento.
2. O analista confirma ou corrige a classificação.
3. A confirmação muda o caso para `CONFIRMADO` e grava o rótulo humano.
4. O descarte mantém o caso para auditoria, mas não o usa no treino.
5. A exportação do treino consulta somente casos confirmados e válidos.

O fluxo legado de `registros.class_conf` continua funcionando para compatibilidade. Quando possível, a confirmação sincroniza os dois registros.

## API mínima

- `GET /api/casos-reais`: lista casos do usuário/empresa com filtros de status e ciclo.
- `POST /api/casos-reais/<id>/confirmar`: confirma ou corrige o rótulo humano.
- `POST /api/casos-reais/<id>/descartar`: descarta com motivo obrigatório.
- `GET /api/casos-reais/resumo`: totais por status, ciclo e origem.

As rotas exigem login e respeitam a empresa ativa. Nenhum documento bruto será duplicado no banco; será guardado somente o nome e a origem do arquivo.

## Validações

- vetor deve conter exatamente dez valores numéricos não negativos;
- classificação deve pertencer às modalidades suportadas;
- somente `CONFIRMADO` com rótulo humano entra no treino;
- confirmação repetida deve ser idempotente;
- casos de outras empresas não podem ser consultados ou alterados.

## Testes

Cobrir criação, listagem, confirmação, correção, descarte, filtros, isolamento por empresa e exportação exclusiva de casos confirmados. Também preservar os testes existentes de `registros` e `class_conf`.

