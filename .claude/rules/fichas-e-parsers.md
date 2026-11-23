---
paths: ["pdf_parsers.py", "services/fichas_rebanho/**"]
---

# Fichas de rebanho e parsers

Complementa o CLAUDE.md (que já lista os parsers por UF). Aqui, só o que evita regressão.

- **Um parser por UF + `parsear_generico` como fallback.** Não remova nem funda parsers
  (IDARON/RO, INDEA/MT, IAGRO-MS, AGED-MA, AGRODEFESA-GO, ADAPEC-TO, ADEPARA-PA). Ficha nova ou
  desconhecida deve cair em `parsear_generico`, nunca levantar exceção.
- **`detectar_origem` é uma cascata ordenada.** Marcadores amplos (`'AGED'`, `'IAGRO'`, `'INDEA'`)
  casam por substring: ao adicionar ou alargar um marcador, confira a ordem e que ele não
  "rouba" fichas de outra UF. INDEA/MT e AGRODEFESA/GO têm faixas etárias diferentes (5 vs 4).
- **Três caminhos de entrada com texto diferente**: `pdftotext -layout` → `pdfplumber` → OCR
  (`pytesseract` + `tesseract-ocr-por`, só para PDF escaneado), mais planilha/texto direto.
  OCR gera ruído (acentos, `0`/`O`, colunas desalinhadas); `pdftotext` desalinha colunas de tabela
  (por isso INDEA/IDARON/ADAPEC leem célula via `pdfplumber` quando há `pdf_path`).
  Ajuste de regex feito sobre um caminho deve ser testado nos outros.
- **Faixas etárias e sexo**: mantenha o mapeamento (`f00/f05/f13/f25/fac`, M/F) e normalize
  acento/caixa antes de comparar. Não troque totais: o consolidador/validador depende deles.
- **Não altere o dict de saída dos parsers** (chaves/tipos) sem ajustar `base_reader.py`,
  `consolidator.py` e `validator.py` — o ML e o parecer consomem esses campos.
- **Ao mexer em uma UF, rode os testes de todas**: `pytest tests/test_pdf_parsers.py
  tests/test_fichas_rebanho_core.py tests/test_fichas_rebanho_estados.py` (+ `test_ficha*.py`).
  Use as fixtures existentes em `tests/fixtures`; não commite fichas reais com dados pessoais.
