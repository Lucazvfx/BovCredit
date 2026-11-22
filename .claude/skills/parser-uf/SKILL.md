---
name: parser-uf
description: Use esta skill ao criar, corrigir ou atualizar parsers de fichas de rebanho estaduais em pdf_parsers.py ou services/fichas_rebanho/.
---

# Objetivo
Adicionar ou manter parsers de órgãos estaduais de defesa agropecuária sem quebrar os estados já suportados (IDARON/RO, INDEA/MT, IAGRO/MS, AGED/MA, AGRODEFESA/GO, ADAPEC/TO, ADEPARÁ/PA) nem o fallback `parsear_generico`.

# Regras inegociáveis
1. Pipeline de extração: sempre `pdftotext -layout` -> `pdfplumber` -> OCR Tesseract como último recurso.
2. OCR obrigatório: sempre `--psm 6`. Nunca usar `--psm 3` (descarta silenciosamente a coluna QUANTIDADE).
3. Classificação de categorias: função pura de `(sexo, faixa etária)`, sem exceção por estado.
4. Proveniência: preservar a identificação exata do parser usado para rastreabilidade no parecer PDF.

# Passo a passo
1. Inspecione `pdf_parsers.py` e `services/fichas_rebanho/` para manter exatamente o contrato de retorno.
2. Implemente ou ajuste o parser da UF tratando cabeçalhos, quebras de linha e formatação numérica.
3. Crie ou atualize testes de regressão em `tests/` cobrindo categorias, totais, coluna QUANTIDADE e integridade dos outros estados.
4. Rode `pytest` nos testes de parser e resuma o que mudou e o resultado.
