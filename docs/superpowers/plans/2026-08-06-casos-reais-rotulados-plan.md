# Banco de Casos Reais Rotulados Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Criar uma base rastreável de casos reais confirmados por analista e usá-la como única fonte de dados reais para retreinamento.

**Architecture:** Manter `registros.class_conf` para compatibilidade e criar `casos_reais` como camada explícita de proveniência, status e revisão. A confirmação sincronizará o caso com o registro legado; a exportação combinará somente casos reais confirmados e válidos.

**Tech Stack:** Flask, SQLite/PostgreSQL via `database.py`, SQL parametrizado, pytest.

## Global Constraints

- Não remover nem alterar a compatibilidade do fluxo existente de `registros` e `class_conf`.
- Somente rótulos humanos confirmados entram no treinamento.
- Respeitar o isolamento por empresa ativa e usuário autenticado.
- Não armazenar cópia binária do PDF; guardar somente metadados de origem.

---

### Task 1: Criar tabela e operações de casos reais

**Files:**
- Modify: `database.py` nas rotinas de inicialização e classificação.
- Test: `tests/test_casos_reais_database.py`

**Interfaces:**
- Produces `criar_caso_real(...) -> int`, `listar_casos_reais(...) -> list`, `confirmar_caso_real(...) -> dict`, `descartar_caso_real(...) -> bool`, `resumo_casos_reais(...) -> dict`.

- [ ] **Step 1: Write failing tests** para criação, status inicial `PENDENTE`, validação do vetor de dez valores e confirmação idempotente.
- [ ] **Step 2: Run `pytest tests/test_casos_reais_database.py -q`** e confirmar falha por funções/tabela inexistentes.
- [ ] **Step 3: Implementar a tabela `casos_reais`** com empresa, usuário, fazenda, origem, arquivo, estado, modelo, vetor, classificação ML, confiança, rótulo humano, status, observação e timestamps.
- [ ] **Step 4: Implementar as operações parametrizadas** com validação de modalidades, status e valores não negativos.
- [ ] **Step 5: Rodar novamente os testes** e confirmar aprovação.
- [ ] **Step 6: Commitar `database.py` e o teste** com a mensagem `feat: add real labeled cases storage`.

### Task 2: Integrar classificação e confirmação

**Files:**
- Modify: `app.py` nas rotas `/api/classificar` e `/api/confirmar-ciclo`.
- Test: `tests/test_casos_reais_api.py`

**Interfaces:**
- `POST /api/classificar` cria caso pendente quando houver composição válida.
- `POST /api/confirmar-ciclo` confirma/corrige o caso associado ao `registro_id`.

- [ ] **Step 1: Escrever testes falhando** para criação pendente, confirmação correta, correção humana e isolamento por empresa.
- [ ] **Step 2: Rodar os testes e confirmar falha** antes da implementação.
- [ ] **Step 3: Criar o caso real** após salvar o registro ML, vinculando `registro_id`, usuário e empresa.
- [ ] **Step 4: Sincronizar confirmação** em `casos_reais` e `registros.class_conf`, sem duplicar uma confirmação repetida.
- [ ] **Step 5: Rodar os testes da API** e confirmar aprovação.
- [ ] **Step 6: Commitar com `feat: connect human labels to real cases`**.

### Task 3: Criar consulta, resumo e exportação segura

**Files:**
- Modify: `database.py` e `app.py`.
- Test: `tests/test_casos_reais_api.py` e `tests/test_confirmacao_ciclo.py`.

**Interfaces:**
- `GET /api/casos-reais?status=&ciclo=` lista os casos permitidos.
- `GET /api/casos-reais/resumo` retorna totais por status, origem e ciclo.
- `POST /api/casos-reais/<id>/descartar` exige motivo e impede treinamento.

- [ ] **Step 1: Escrever testes falhando** para filtros, resumo, descarte e exclusão de casos de outra empresa.
- [ ] **Step 2: Rodar os testes e confirmar falha**.
- [ ] **Step 3: Implementar rotas protegidas por login** usando a empresa ativa.
- [ ] **Step 4: Alterar `exportar_treino()`** para continuar aceitando o legado e exigir confirmação humana.
- [ ] **Step 5: Rodar `pytest tests/test_confirmacao_ciclo.py tests/test_casos_reais_api.py -q`**.
- [ ] **Step 6: Commitar com `feat: expose real cases review endpoints`**.

### Task 4: Tela de revisão e documentação

**Files:**
- Modify: `templates/index.html` e `README.md`.
- Test: `tests/test_frontend_casos_reais.py`.

- [ ] **Step 1: Escrever teste estático** para os estados Pendente, Confirmado e Descartado e as ações de confirmação/correção.
- [ ] **Step 2: Implementar painel simples de revisão** sem bloquear a classificação atual.
- [ ] **Step 3: Mostrar contagem de casos reais** por modalidade e origem.
- [ ] **Step 4: Documentar o fluxo de rotulagem e retreinamento no README**.
- [ ] **Step 5: Rodar os testes direcionados, compilação Python e validação JavaScript**.
- [ ] **Step 6: Commitar com `feat: add real cases review panel`**.

### Task 5: Validação final

- [ ] **Step 1:** Rodar os testes direcionados e a suíte completa disponível.
- [ ] **Step 2:** Confirmar que registros não confirmados não entram em `exportar_treino()`.
- [ ] **Step 3:** Confirmar que casos confirmados aparecem no resumo e no exportador.
- [ ] **Step 4:** Registrar limitações: ainda serão necessários casos reais suficientes por modalidade para treinar novamente com segurança.

