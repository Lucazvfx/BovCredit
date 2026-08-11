# Task 2 report — livestock analysis engine extraction

## Changed files

- `services/livestock_engine/__init__.py`
- `services/livestock_engine/analyzer.py`
- `services/livestock_engine/rules.py`
- `services/livestock_engine/explanations.py`
- `tests/test_livestock_engine.py`
- `ml_engine.py`

## What changed

- Extracted pure-Python herd indicator calculation into `services.livestock_engine.calculate_herd_indicators`.
- Added deterministic system analysis in `services.livestock_engine.analyze_herd` using the existing herd-composition rule thresholds already present in the legacy classifier.
- Added `services.livestock_engine.explain_system` so deterministic evidence, ML evidence, and missing data are reported separately.
- Kept `ml_engine.calcular_indicadores` as a compatibility wrapper that preserves the legacy response shape while delegating the math to the new service.

## Verification run

- `pytest -q tests/test_livestock_engine.py`
- `git diff --check`

Focused Task 2 coverage passed on August 11, 2026.

## Concerns

- Per the latest stop instruction, I reran only the focused Task 2 test before commit rather than the broader regression command from the original brief.
- `git diff --check` is clean, but Git warns that `ml_engine.py` will be normalized from LF to CRLF on a future touch in this worktree.

## Fix follow-up

This follow-up finalized the live-signal alignment requested for Task 2:

- `services/livestock_engine/rules.py` now exposes the classifier-facing live metrics: `p_matrizes`, `p_mac_13_24`, `p_bois`, `p_bez`, `p_fem_total`, `p_garrotes_25_36`, `intensidade_engorda`, `intensidade_cria`, and `indice_ciclo`.
- `services/livestock_engine/analyzer.py` now preserves all six live labels from the classifier output path and threads live-sale metadata into the rule evaluation.
- `services/livestock_engine/explanations.py` now grounds deterministic explanations in live signals rather than legacy percentage names.

## Verification run

- `pytest -q tests/test_livestock_engine.py`
- `pytest -q tests/test_ml_engine.py tests/test_composicao_rebanho.py tests/test_analise_transparente.py`
- `git diff --check`

All requested verification commands passed.
