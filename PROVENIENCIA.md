# Procedência dos artefatos de classificação de rebanho

Registro do que veio de fora do projeto, o que foi de fato usado, o que foi
reescrito e o que o histórico do git atesta. Escrito em 2026-08-20, quando a
empresa autora das planilhas questionou o uso delas.

Este documento é descritivo: registra fatos verificáveis no repositório, não
conclusões sobre direitos. Cada afirmação traz o comando que a reproduz.

## 1. Arquivos de terceiro que estiveram versionados

Dois arquivos `.xlsm` foram versionados em `static/` e removidos no commit
`cd2e49b` (2026-08-20). Ambos declaram a mesma autoria nos metadados OOXML:

```sh
git show 43368d7:static/classificacao_rebanho_fichas.xlsm | base64 -d > /tmp/a.xlsm
unzip -p /tmp/a.xlsm docProps/core.xml
```

| | `classificacao_rebanho_fichas.xlsm` | `ficha_consolidado_exemplo.xlsm` |
|---|---|---|
| `dc:creator` | Vitoria Santos Silva | Vitoria Santos Silva |
| `cp:lastModifiedBy` | Lucas Vinicius dos Santos Nascimento | lucas nascimento vinicius |
| `dcterms:created` | 2026-07-09T13:00:31Z | 2026-07-09T13:00:31Z |
| `dcterms:modified` | 2026-08-04T18:38:47Z | 2026-07-23T02:08:01Z |
| Tamanho | 194.227 bytes (gravado em base64) | 149.504 bytes |
| `xl/vbaProject.bin` | 297.472 bytes | 247.296 bytes |
| Abas | CONSOLIDADO, MAPEAMENTO, LOG, Etapas do Projeto | as mesmas |

Além dos metadados, `classificacao_rebanho_fichas.xlsm` traz a autoria escrita
na própria planilha: `CONSOLIDADO!B1 = "Desenvolvido por:"`, `C1 = "Vitoria Silva"`.

### 1.1. O VBA embarcado

O `vbaProject.bin` das duas planilhas contém rotinas que leem PDFs de
declaração estadual — `ProcessarPA_SIGEAGRO`, `BuscarQuantidadesSIGEAGROPA` — e
diálogos como `"Selecione o PDF AGRODEFESA - Goiás"` e `"10 PDFs IAGRO"`.

```sh
unzip -p /tmp/a.xlsm xl/vbaProject.bin | strings | grep -i sigeagro
```

É uma ferramenta de macro que resolve, no Excel do analista, um problema
parecido com o que o servidor resolve. Não era chamada pelo nosso código em
nenhum ponto: nada em `services/` ou em `app.py` executava VBA.

### 1.2. Dado real de produtor

A aba LOG de `classificacao_rebanho_fichas.xlsm` continha 10 linhas de um
processamento real, com a propriedade identificada pela inscrição estadual:

```
2026-08-04 14:37:41 | MT_DECLARACAO | 51000170455 | MT | BOVINO | FEMEA | 00 A 04 MESES | 300
2026-08-04 14:37:41 | MT_DECLARACAO | 51000170455 | MT | BOVINO | MACHO | 00 A 04 MESES | 280
(… 8 linhas)
```

O primeiro bloco da aba CONSOLIDADO vinha preenchido com esse mesmo rebanho —
863 / 1.105 / 298 / 593 fêmeas e 467 / 1.344 / 80 / 39 machos, 4.789 cabeças.

Isso importa por dois motivos: o arquivo era servido por `/api/ficha/download`
a qualquer usuário autenticado, e estava versionado no git. A ficha em branco
`ficha_consolidado_exemplo.xlsm` não tinha esse problema: LOG vazio e números
de exemplo redondos (120/115/85/80/60/55/320/80).

## 2. O que o sistema realmente usava

De todo o conteúdo das planilhas, o código lia **apenas a aba MAPEAMENTO**:
74 linhas × 8 colunas, um de-para entre (estado, sexo, faixa etária) e a
classificação do animal. Dois pontos de leitura, ambos por `openpyxl`:

- `services/fichas_rebanho/mapping_loader.py`
- `services/mapeamento_fichas.py`

As duas planilhas traziam essa aba **idêntica** — mesmas 74 linhas, mesma
ordem. A única diferença era a coluna CHAVE, preenchida em uma e vazia na
outra; onde vazia, o próprio código a derivava de `ESTADO|SEXO|ESTRATIFICAÇÃO`.

O conteúdo dessa tabela é factual, não autoral: as faixas etárias são as
publicadas por cada órgão estadual (INDEA-MT, IDARON-RO, IAGRO-MS, AGED-MA,
AGRODEFESA-GO, ADAPEC-TO, ADEPARÁ-PA) nos próprios formulários de declaração,
e a classificação é a nomenclatura zootécnica corrente — fêmea bovina acima de
36 meses é vaca, macho de 25 a 36 meses é garrote.

Isso é verificável, não é opinião: **as 74 linhas são função pura de (sexo,
faixa)**. Doze pares cobrem a tabela inteira, sem uma única exceção por estado:

```
FEMEA  0 A 12 / 00 A 04 / 05 A 12  → Bezerra          MACHO → Bezerro
FEMEA  13 A 24                     → Bezerra Desmama  MACHO → Bezerro Desmama
FEMEA  25 A 36                     → Novilha          MACHO → Garrote
FEMEA  ACIMA DE 36                 → Vaca             MACHO → Boi Gordo
```

O que varia por estado é apenas *quais* faixas o formulário daquele órgão usa —
cinco em MT, quatro em RO/MS/MA/TO/PA, as duas formas em GO (que emite a
declaração detalhada e o resumo "Rebanho por Fazenda"). E essas faixas os
parsers já leem do próprio PDF, onde aparecem literalmente.

As mesmas doze regras já existiam em outros dois pontos do código, sem passar
pela planilha: `_FEMALE_MAP` / `_MALE_MAP` em `services/importar_excel.py` e
`_VALOR_POR_CLASSIFICACAO` em `services/fichas_rebanho/consolidator.py`.

Nada mais das planilhas era consumido: nem o VBA, nem a aba LOG, nem a aba
Etapas do Projeto, nem as imagens.

## 3. O que é do projeto

A leitura de PDF é do projeto e não depende das planilhas:

- `pdf_parsers.py` (1.532 linhas) — extração em cascata `pdftotext` →
  pdfplumber → OCR Tesseract, detecção de origem e um parser por órgão
- `services/fichas_rebanho/` — leitura, validação e consolidação
- `services/importar_excel.py` (212 linhas) — leitura da aba CONSOLIDADO
- `ml_engine.py` — classificação de ciclo e indicadores

O modelo de ML é treinado com dados sintéticos gerados por `treinar_ciclos.py`
a partir de faixas de referência declaradas no próprio script. Os únicos casos
rotulados por especialista estão em `tests/test_casos_material_treinamento.py`
e vêm do material "Análise de Crédito na Pecuária Bovina", de Sónia Morais
Romeiro Mendes, citado na fonte — usados como validação, não como treino.

## 4. O que foi feito (commit `cd2e49b`, 2026-08-20)

1. A tabela MAPEAMENTO passou a viver em `data/mapeamento_classificacao.csv`,
   versionada em texto, e é **gerada** por `scripts/generate_mapeamento.py` a
   partir da regra descrita em 2 — não transcrita da planilha. A suíte
   regenera e compara a cada execução. Os dois carregadores leem o CSV.
2. `scripts/generate_ficha_consolidado.py` passou a gerar
   `static/templates/ficha_consolidado_rebanho.xlsx` — ficha própria, sem VBA,
   com totais em fórmula comum. É ela que `/api/ficha/download` entrega.
3. As duas `.xlsm` foram removidas do repositório, e com elas a aba LOG.
4. As instruções deixaram de mandar o analista habilitar macros.
5. Comentários e testes deixaram de nomear as duas propriedades reais usadas
   na calibração (passaram a ser `RECRIA_700` e `RECRIA_753`); os valores
   medidos continuam.
6. `tests/test_ficha_sem_planilha_de_terceiro.py` falha se qualquer `.xlsm`
   voltar ao repositório, se a ficha distribuída passar a conter VBA, se o CSV
   divergir do gerador, ou se alguma classificação passar a depender do estado.

## 5. O que o histórico do git atesta — e o que não atesta

`43368d7` é o **commit raiz** do repositório (`git rev-list --count HEAD` = 100
em 2026-08-20, com `43368d7` na base). Todo o código e as duas planilhas
entraram nesse mesmo commit, em 2026-08-11.

Consequência honesta: o histórico do git **não** estabelece o que veio antes —
nem que o `pdf_parsers.py` precedeu as planilhas, nem o contrário. Os metadados
OOXML datam as planilhas de 2026-07-09. Qualquer cronologia anterior ao commit
raiz precisa vir de fora do repositório.

## 6. Origem declarada dos arquivos

O repositório não contém documento que estabeleça a origem das planilhas. O
que segue é a declaração do mantenedor do projeto, registrada aqui em
2026-08-20 por ser a única fonte disponível — e identificada como declaração,
não como fato verificado no repositório:

- O acesso às planilhas se deu no contexto do vínculo empregatício com a
  empresa autora, em função que não é de desenvolvimento de software
  (estoquista).
- Não houve contrato, prestação de serviço, cessão de direitos ou pagamento
  relacionados a este projeto.
- Este projeto não foi vendido à empresa autora nem desenvolvido para ela; não
  há relação comercial entre os dois.

Isso é consistente com o `cp:lastModifiedBy` das duas planilhas, que traz o
nome do mantenedor: acesso ao arquivo, sem documento de cessão.

Duas consequências, sem conclusão jurídica — que não cabe a este documento:

1. **Nada aqui autorizava redistribuir as planilhas.** Acesso no trabalho não
   é licença. É exatamente o que a remoção no commit `cd2e49b` trata, e por
   isso ela não depende de como a discussão termine.
2. **A titularidade do software é questão separada da titularidade das
   planilhas**, e depende do escopo do vínculo — atribuição da função,
   recursos do empregador, se houve cláusula sobre criações. Software feito
   fora do escopo da função e sem recursos do empregador tem tratamento
   próprio em lei. Esclarecer isso é assunto para orientação jurídica, com
   este documento e o histórico do repositório em mãos.

## 7. Pendências

- **Histórico**: remover do working tree não removeu do histórico. As duas
  `.xlsm` — e o dado do produtor `51000170455` — seguem acessíveis via
  `git show 43368d7:static/...`. Limpar exige reescrita de histórico
  (`git filter-repo`) e force-push, com reclone por todos e mudança dos hashes
  que o deploy fixa. Decisão pendente, e não puramente técnica: a remoção do
  histórico depois de a empresa ter questionado é decisão a tomar com
  orientação, não por conveniência de repositório.
- **Dado de terceiro**: a exposição do rebanho da propriedade `51000170455`
  independe da discussão sobre as planilhas. Marcos registrados: entrada no
  repositório em 2026-08-11 (`43368d7`), contenção em 2026-08-20 (`cd2e49b`),
  histórico ainda contém. Se há notificação a fazer, é decisão pendente.
