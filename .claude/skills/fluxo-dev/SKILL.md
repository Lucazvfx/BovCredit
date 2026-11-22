---
name: fluxo-dev
description: Executa uma tarefa de desenvolvimento completa em 3 etapas: pesquisa em Haiku, implementação em Sonnet e revisão/validação crítica em Opus.
---

Execute a tarefa solicitada ($ARGUMENTS) seguindo estritamente estas 3 fases:

## Fase 1 — Pesquisa (Haiku)
Lance um subagente usando o modelo `haiku` apenas para mapear os arquivos, funções e testes relevantes para esta tarefa. Não edite código nesta fase.

## Fase 2 — Plano e Construção (Sonnet)
Com base no mapa retornado pelo Haiku:
1. Monte um plano curto de implementação.
2. Escreva o código e os testes necessários.
3. Execute `pytest` nos testes afetados até passarem.

## Fase 3 — Revisão Crítica (Opus)
Lance um subagente usando o modelo `opus` passando o `git diff` atual para:
- Verificar bugs, casos de borda e regressões;
- Checar regras do Orkavyn (proveniência de `Parametro`, LGPD, isolamento multi-tenant, limites de entrada).

Se o Opus apontar bloqueadores, corrija em Sonnet e rode `pytest` novamente antes de finalizar.
