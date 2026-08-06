# Transparência de custos de produção e reposição Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Expor separadamente manutenção e reposição no fluxo de caixa da análise bovina.

**Architecture:** O motor continuará produzindo os custos por ano. `app.py` agregará as parcelas do primeiro ano ao objeto `fluxo_gep`; o template e o gerador de PDF somente renderizarão os novos campos. O cálculo do caixa e do DSCR permanece inalterado.

**Tech Stack:** Python, Flask, pytest, template HTML/JavaScript e PDF via ReportLab.

## Global Constraints

- Preservar `custo_operacional` como manutenção mais reposição.
- Não alterar premissas de reposição, preços ou custos.
- Não incluir os arquivos não relacionados já presentes como untracked.

### Task 1: API e fluxo GEP

**Files:**
- Modify: `app.py:1358-1477`
- Test: `tests/test_transparencia_custos_reposicao.py`

- [ ] Escrever teste falhando que verifica os cinco campos financeiros e suas identidades matemáticas para uma recria real.
- [ ] Executar `pytest tests/test_transparencia_custos_reposicao.py -q` e confirmar falha pela ausência dos campos.
- [ ] Somar `custo_manutencao` e `custo_reposicao` do primeiro ano em `fluxo_gep`; calcular `resultado_antes_reposicao` sem alterar `resultado_operacional`.
- [ ] Executar o teste novamente e confirmar aprovação.

### Task 2: Painel web

**Files:**
- Modify: `templates/index.html:2312-2326`
- Test: `tests/test_transparencia_custos_reposicao.py`

- [ ] Acrescentar teste de resposta/template que confirme os rótulos de manutenção, reposição e resultado antes da reposição.
- [ ] Executar o teste em vermelho.
- [ ] Inserir as linhas na demonstração de fluxo do painel, mantendo o subtotal e o resultado operacional.
- [ ] Executar os testes da API e da transparência em verde.

### Task 3: Parecer PDF

**Files:**
- Modify: `services/parecer_pdf.py:197-210`
- Test: `tests/test_transparencia_custos_reposicao.py`

- [ ] Acrescentar teste que extraia o texto do PDF e procure os rótulos da decomposição.
- [ ] Executar o teste em vermelho.
- [ ] Adicionar manutenção, resultado antes da reposição e reposição antes do resultado operacional.
- [ ] Executar os testes focados e a suíte completa disponível.

### Task 4: Verificação e entrega

**Files:**
- No new production files.

- [ ] Rodar `git diff --check`.
- [ ] Rodar testes focados de custos, casos reais, API e PDF.
- [ ] Registrar no resumo que os seis failures ambientais/preexistentes permanecem, se ainda ocorrerem.
