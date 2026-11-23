---
name: fluxo-dev
description: Executa uma tarefa de desenvolvimento em 3 etapas: mapeamento (Explore, Sonnet), implementação com testes (Sonnet) e revisão crítica independente (Opus, checklist fixa).
---

Execute a tarefa solicitada ($ARGUMENTS) seguindo estritamente estas 3 fases. Em tarefas triviais (renomear, ajustar texto), pule os subagentes e faça direto.

## Fase 1 — Mapeamento (Explore, modelo `sonnet`)
Lance um subagente `Explore` com `model: sonnet`. Somente leitura. Comece com `grep`/ripgrep; leia só trechos ao redor das ocorrências, nunca arquivos inteiros (principalmente `app.py`). Meta: ~10 chamadas de ferramenta.
O mapa deve trazer, com `arquivo:linha`:
1. Onde a mudança acontece (rota, função, trecho).
2. **Todos os chamadores de cada função que será alterada ou de que ela depende** — rotas em `app.py`, `services/`, WhatsApp, frontend (`templates/`). Funções compartilhadas (ex.: formatadores usados por mais de uma rota) são o ponto de maior risco de regressão.
3. Quais valores o backend gera hoje para esses campos (para não rejeitar dado legítimo).
4. Testes existentes, fixtures de login e como o Groq é mockado.
5. Limites de entrada e helpers já existentes; comando de testes e teste de integridade do `gestao_model.pkl`.

## Fase 2 — Implementação e testes (Sonnet)
1. Monte um plano curto e declare premissas.
2. Não altere função compartilhada sem tratar todos os chamadores listados no mapa; prefira mudar só a borda (a rota) e deixar o resto como está.
3. Escreva código e testes. Rode `pytest` nos testes afetados até passarem e, antes de finalizar, a suíte completa.

## Fase 3 — Revisão crítica (Opus, checklist fixa)
Lance um subagente `general-purpose` com `model: opus`, somente leitura, passando o `git diff` (em arquivo). Ele deve verificar SEMPRE:
- Inteiros enormes (`float()` → `OverflowError`), `NaN`/`inf`, `bool`, strings numéricas, `None`, tipos não hasheáveis.
- Fallback que **inventa dado** (ex.: `0` no lugar de "não informado" que o LLM ou o parecer tratam como valor real).
- Outros chamadores das funções alteradas; algum valor legítimo gerado pelo backend seria rejeitado? Alguma rota que funcionava passa a dar 500?
- Limites de tamanho de entrada, mensagens de erro sem `str(e)`/detalhe interno, `login_required` e rate limit preservados.
- LGPD (dados pessoais enviados ao Groq), isolamento multi-tenant, proveniência de `Parametro`.
- Se os testes provam o requisito (asserção positiva, não só "não deu erro") e se há teste de ida e volta com o backend real.
Saída: lista priorizada BLOQUEADORES vs nits, com `arquivo:linha` e correção.
Em mudança sensível (auth, crédito, ML, LGPD), faça duas revisões independentes (a segunda pode ser `revisor-credito-ml`) — a severidade varia entre rodadas.

Se houver bloqueadores, corrija em Sonnet, adicione teste para cada um e rode `pytest` de novo antes de finalizar.
