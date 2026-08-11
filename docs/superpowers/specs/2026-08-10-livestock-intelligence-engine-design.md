# Orkavyn Livestock Intelligence Engine

**Data:** 2026-08-10  
**Status:** Design aprovado para planejamento incremental  
**Escopo inicial:** separar o núcleo de análise sem interromper a aplicação web atual.

## Objetivo

Evoluir o Orkavyn de uma aplicação Flask de análise pecuária para uma plataforma B2B e um motor reutilizável de inteligência econômico-produtiva, preservando os endpoints, a autenticação, os parsers, o banco e a interface existentes.

O produto continuará funcionando como aplicação web e passará a oferecer uma API versionada para integrações autorizadas.

## Princípios

- Reutilizar cálculos e serviços existentes antes de criar novos.
- Manter `/api/classificar` e os demais endpoints atuais compatíveis.
- Implementar novos módulos como serviços Python independentes de Flask.
- Preferir regras zootécnicas determinísticas para cálculos e usar ML como apoio à classificação.
- Expor origem, premissa, fonte e incerteza de cada dado relevante.
- Não apresentar score experimental ou modelo treinado em dados sintéticos como validação de crédito.
- Fazer alterações aditivas no banco e preservar os dados existentes.
- Executar testes e registrar um commit separado ao final de cada fase.

## Estado atual resumido

O projeto já possui leitura de PDFs e XLSM, parsers por estado, classificação híbrida, simulação por coortes, custos por modalidade, fluxo de caixa, DSCR, garantia, endividamento, qualidade de dados, auditoria, multiempresa, geração de parecer PDF e uma interface web funcional.

As principais limitações são a concentração de responsabilidades em `app.py` e `ml_engine.py`, a projeção mensal linear, a ausência de um motor de stress independente, a falta de API B2B versionada e a ausência de snapshots completos de versão para reprodução de análises antigas.

## Arquitetura alvo

```text
Web Orkavyn / Clientes externos
             |
       Flask + API v1
             |
       Application pipeline
             |
  Orkavyn Intelligence Engine
   |       |        |        |
 rebanho produção econômico crédito
             |
       fluxo / stress / qualidade
             |
 Banco, parsers, preços e relatórios
```

As rotas Flask atuais funcionarão como camada de compatibilidade. A API v1 usará os mesmos serviços de domínio, sem duplicar fórmulas.

## Componentes

### Livestock Engine

Responsável por normalizar e analisar o vetor de dez categorias atual, calcular composição, sexo, faixas etárias, matrizes, touros, bois, animais comercializáveis, relação matriz/touro e explicações. Consumirá o classificador ML existente, mas manterá regras e validações independentes.

### Production Engine

Extrairá de `ml_engine.py` os cálculos de cria, recria, engorda e ciclo completo. O motor receberá um estado de rebanho e parâmetros versionados e devolverá coortes, entradas, saídas, mortalidade, ganho de peso, duração, giros e produção. Ciclo completo deverá evitar dupla contagem entre fases.

### Economic Engine

Separará receitas, custos fixos, custos variáveis, investimentos, reposição e serviço da dívida. Devolverá receita bruta, custo operacional, margens, resultado, break-even, custo por cabeça, custo por arroba e receita por cabeça.

### Cashflow Engine

Manterá a projeção anual existente e substituirá gradualmente a distribuição linear por uma projeção mensal com calendário e sazonalidade configuráveis. Quando o calendário não existir, o resultado continuará marcado como estimado.

### Payment Capacity Engine

Reutilizará `services/parecer_credito.py` para cronograma, carência, Price, DSCR, pior período, melhor período, DSCR médio e valor máximo suportável. A capacidade calculada será apresentada como estimativa, nunca como garantia de pagamento.

### Stress Engine

Aplicará choques individuais e combinados sobre preços, custos, natalidade, mortalidade, ganho de peso e prazo de comercialização. Cada cenário devolverá as alterações aplicadas, o DSCR resultante, o período crítico e os fatores que causaram a deterioração.

### Data Quality e Explainability

Serão mantidos `services/qualidade_dados.py`, `services/proveniencia.py`, `services/explicacao_classificacao.py` e `services/validacao_zootecnica.py`, reorganizados atrás de contratos comuns. A análise terá qualidade dos dados separada do risco econômico.

## API alvo

Adicionar, sem remover as rotas atuais:

```text
POST /api/v1/herd/analyze
POST /api/v1/production/project
POST /api/v1/cashflow/project
POST /api/v1/payment-capacity
POST /api/v1/stress-test
POST /api/v1/full-analysis
GET  /api/v1/analysis/<id>
GET  /api/v1/report/<id>
GET  /api/docs
```

A API deverá ter autenticação por API Key, rate limiting, erros padronizados, idempotência para análises completas e auditoria do consumidor. OAuth2 ficará como extensão futura.

## Persistência e auditoria

As tabelas atuais serão preservadas. Será estudada uma migração aditiva para snapshots de análise contendo identificador, organização, usuário/API, dados de entrada, parâmetros, fontes, versões de regras e modelo, resultado e timestamp. O snapshot deverá permitir reprodução sem depender dos valores atuais de mercado.

## Relatório e interface

O dashboard web atual será mantido. Novas áreas serão adicionadas progressivamente: qualidade dos dados, produção, fluxo mensal, capacidade de pagamento, stress test, premissas e relatório. O PDF existente será ampliado para refletir os mesmos blocos e premissas da API.

## Ordem de implementação

1. Contratos internos, versionamento e testes de caracterização.
2. Livestock Engine e adaptador para `ml_engine.py`.
3. Production Engine e integração com os quatro sistemas produtivos.
4. Economic Engine e decomposição financeira.
5. Cashflow Engine mensal sazonal.
6. Payment Capacity Engine sobre o cronograma atual.
7. Stress Engine.
8. Data Quality Score e explicabilidade consolidada.
9. Pipeline `full-analysis` e snapshots auditáveis.
10. API v1, API Key, OpenAPI e idempotência.
11. Relatório B2B e dashboard.
12. Demo, documentação, testes de integração e preparação comercial.

## Critérios de segurança contra regressão

- O frontend atual continuará abrindo e classificando uma análise.
- `/api/classificar` continuará aceitando o payload atual.
- PDFs, XLSM, login, multiempresa, auditoria e relatório permanecerão funcionais.
- Nenhuma fórmula existente será substituída sem teste comparativo.
- Toda mudança de parâmetro informará origem, unidade, fonte e status de estimativa.
- O score experimental será identificado como não validado.

## Limitações reconhecidas

- A validação do ML ainda depende de mais casos reais rotulados.
- A projeção financeira pode continuar estimada quando a ficha não trouxer preços, custos, pesos ou calendário.
- Benchmarks regionais não serão tratados como universais.
- A API B2B não implicará integração proprietária com bancos, cooperativas ou ERPs sem autorização e documentação.
