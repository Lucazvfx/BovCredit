# Orkavyn Livestock Intelligence Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform the existing Flask application into a reusable livestock intelligence engine while preserving the web interface, legacy endpoints, parsers, calculations, authentication and stored data.

**Architecture:** Add pure-Python domain services behind the existing Flask routes. The current `ml_engine.py` and services remain compatibility adapters until each calculation is covered by characterization tests and moved behind a stable contract. Add `/api/v1` only after the internal full-analysis pipeline is stable.

**Tech Stack:** Python 3.11, Flask, pytest, SQLite/PostgreSQL through `database.py`, existing scikit-learn/XGBoost/LightGBM model, pdfplumber/Tesseract, ReportLab, vanilla HTML/CSS/JavaScript.

## Global Constraints

- Preserve the current web application and all existing public routes.
- Do not delete or silently change existing calculations, parsers, authentication, audit behavior or database records.
- Use deterministic rules for production and financial calculations; ML remains an explainable classification input.
- Mark estimates, missing fields, synthetic-model limitations and experimental scores explicitly.
- Do not use a score as autonomous credit approval.
- Use additive database migrations and organization-level access checks.
- Run focused tests after every task and the full suite before each phase commit.
- Do not add proprietary integrations without documentation and authorization.

---

## Task 1: Characterize the existing contracts and register engine versions

**Files:**
- Create: `services/engine/__init__.py`
- Create: `services/engine/contracts.py`
- Create: `services/engine/versions.py`
- Create: `tests/test_engine_contracts.py`
- Modify: `README.md` only to document the new internal contract after tests pass

**Interfaces:**
- `HerdState(values: list[float], source: str, farm_id: int | None, metadata: dict)`
- `AnalysisContext(organization_id: int | None, user_id: int | None, input_data: dict, source_documents: list[dict])`
- `EngineVersion(rules: str, parameters: str, model: str)`
- `engine_version() -> dict`

- [ ] **Step 1: Write characterization tests** for the ten-position herd vector, non-negative counts, accepted source labels and version metadata.
- [ ] **Step 2: Run `pytest tests/test_engine_contracts.py -q` and confirm the new contract tests fail before implementation.**
- [ ] **Step 3: Implement immutable dataclasses and strict validation without importing Flask or the database.**
- [ ] **Step 4: Run the focused tests and then the existing herd-vector tests.**
- [ ] **Step 5: Document the contract and commit `feat: add engine contracts and version metadata`.**

## Task 2: Extract the Livestock Engine without changing classification behavior

**Files:**
- Create: `services/livestock_engine/__init__.py`
- Create: `services/livestock_engine/analyzer.py`
- Create: `services/livestock_engine/rules.py`
- Create: `services/livestock_engine/explanations.py`
- Create: `tests/test_livestock_engine.py`
- Modify: `ml_engine.py` with a compatibility wrapper only

**Interfaces:**
- `analyze_herd(state: HerdState, *, ml_result: dict | None = None) -> dict`
- `calculate_herd_indicators(values: list[float]) -> dict`
- `explain_system(system: str, indicators: dict, ml_result: dict | None) -> dict`

- [ ] **Step 1: Add failing tests for totals, female/male totals, matrices, bulls, finished animals, matrix/bull ratio and percentage composition.**
- [ ] **Step 2: Add tests proving the explanation distinguishes deterministic evidence, ML evidence and missing data.**
- [ ] **Step 3: Implement the analyzer by delegating existing indicator logic to the new service and preserving the ten-category vector.**
- [ ] **Step 4: Add a wrapper in `ml_engine.py` and route one internal call through it without changing the JSON keys returned by `/api/classificar`.**
- [ ] **Step 5: Run `tests/test_ml_engine.py`, `tests/test_composicao_rebanho.py`, `tests/test_analise_transparente.py` and the new tests.**
- [ ] **Step 6: Commit `feat: extract livestock analysis engine`.**

## Task 3: Centralize versioned zootechnical parameters

**Files:**
- Create: `services/engine/parameter_registry.py`
- Create: `tests/test_parameter_registry.py`
- Modify: `services/parametros_zootecnicos.py` to expose existing values through the registry
- Modify: `services/proveniencia.py` only where needed to carry source/year/unit metadata

**Interfaces:**
- `Parameter(name, value, unit, system, region, source, reference_year, editable, plausible_range)`
- `get_parameter(name: str, system: str, region: str | None = None) -> Parameter`
- `resolve_parameters(overrides: dict, system: str, region: str | None = None) -> dict`

- [ ] **Step 1: Test that existing defaults for natality, mortality, GMD, weights, carcass yield and matrix/bull ratio remain unchanged.**
- [ ] **Step 2: Test valid overrides, range rejection and provenance metadata.**
- [ ] **Step 3: Implement the registry using current source declarations and no new unsupported benchmark values.**
- [ ] **Step 4: Adapt `parametros_zootecnicos.py` callers while keeping its public functions compatible.**
- [ ] **Step 5: Run parameter, provenance and benchmark tests.**
- [ ] **Step 6: Commit `feat: centralize zootechnical parameters`.**

## Task 4: Extract Production Engine for cria, recria, engorda and ciclo completo

**Files:**
- Create: `services/production_engine/__init__.py`
- Create: `services/production_engine/models.py`
- Create: `services/production_engine/projector.py`
- Create: `services/production_engine/cria.py`
- Create: `services/production_engine/recria.py`
- Create: `services/production_engine/engorda.py`
- Create: `services/production_engine/ciclo_completo.py`
- Create: `tests/test_production_engine.py`
- Modify: `ml_engine.py` to delegate through a compatibility function

**Interfaces:**
- `project_production(state: HerdState, system: str, parameters: dict, years: int = 5) -> dict`
- `project_cria(...) -> dict`
- `project_recria(...) -> dict`
- `project_engorda(...) -> dict`
- `project_full_cycle(...) -> dict`

- [ ] **Step 1: Add characterization tests for existing cria, recria, engorda and recria-engorda outputs.**
- [ ] **Step 2: Add tests for mortality, GMD-to-duration, fractional annual turns, replacement and no double counting in ciclo completo.**
- [ ] **Step 3: Move the smallest pure calculations first, preserving existing output keys such as `receita`, `custo`, `resultado`, `vendidos` and `lotes_por_ano`.**
- [ ] **Step 4: Implement the dispatcher and compatibility adapter.**
- [ ] **Step 5: Compare old and new outputs for the real labeled fixtures and synthetic regression fixtures with explicit tolerances.**
- [ ] **Step 6: Run all production, volume, conservation and real-case tests.**
- [ ] **Step 7: Commit `feat: add production projection engine`.**

## Task 5: Separate Economic Engine and preserve cost transparency

**Files:**
- Create: `services/economic_engine/__init__.py`
- Create: `services/economic_engine/revenues.py`
- Create: `services/economic_engine/costs.py`
- Create: `services/economic_engine/margins.py`
- Create: `tests/test_economic_engine.py`
- Modify: `services/custos_desembolso.py` only through adapters
- Modify: `app.py` to consume the new result without changing current response fields

**Interfaces:**
- `calculate_revenues(production: dict, prices: dict) -> dict`
- `calculate_costs(production: dict, cost_parameters: dict) -> dict`
- `calculate_economic_result(revenues: dict, costs: dict, inventory_change: float = 0) -> dict`

- [ ] **Step 1: Test revenue by category, fixed/variable cost separation, investment separation, replacement cost and operating result.**
- [ ] **Step 2: Test the existing transparency invariant: maintenance plus replacement equals operational cost.**
- [ ] **Step 3: Implement pure economic functions using current cost presets and provenance.**
- [ ] **Step 4: Add the compatibility mapper for the existing GEP flow and pare­cer JSON.**
- [ ] **Step 5: Run cost, replacement, breakeven, transparency and credit regression tests.**
- [ ] **Step 6: Commit `feat: separate economic production calculations`.**

## Task 6: Build monthly Cashflow Engine with explicit estimated fallback

**Files:**
- Create: `services/cashflow_engine/__init__.py`
- Create: `services/cashflow_engine/models.py`
- Create: `services/cashflow_engine/monthly.py`
- Create: `services/cashflow_engine/seasonality.py`
- Create: `tests/test_cashflow_engine.py`
- Modify: `services/fluxo_mensal_credito.py` to delegate to the new service

**Interfaces:**
- `project_cashflow(annual_projection: dict, debt_schedule: dict, *, horizon_months: int, calendar: dict | None = None, seasonality: dict | None = None) -> dict`
- Return each month with `saldo_inicial`, `entradas`, `custos_operacionais`, `investimentos`, `parcelas`, `juros`, `saldo_operacional`, `saldo_final`, `estimated` and `warnings`.

- [ ] **Step 1: Test the current linear fallback and assert that it is explicitly marked estimated.**
- [ ] **Step 2: Test a custom seasonal calendar for purchases, calf sales, finished cattle sales and costs.**
- [ ] **Step 3: Test horizons of 12, 24, 36, 48 and 60 months.**
- [ ] **Step 4: Implement monthly cashflow without changing the existing annual DSCR input.**
- [ ] **Step 5: Run monthly, carência and annual compatibility tests.**
- [ ] **Step 6: Commit `feat: add monthly cashflow engine`.**

## Task 7: Consolidate Payment Capacity and Stress Engines

**Files:**
- Create: `services/payment_capacity_engine/__init__.py`
- Create: `services/payment_capacity_engine/dscr.py`
- Create: `services/stress_engine/__init__.py`
- Create: `services/stress_engine/scenarios.py`
- Create: `tests/test_payment_capacity_engine.py`
- Create: `tests/test_stress_engine.py`
- Modify: `services/parecer_credito.py` through compatibility adapters

**Interfaces:**
- `calculate_payment_capacity(cashflow: dict, debt_request: dict, existing_debt: dict | None = None) -> dict`
- `run_stress_tests(base_analysis: dict, scenarios: list[dict]) -> dict`
- `default_stress_scenarios() -> list[dict]`

- [ ] **Step 1: Test DSCR minimum, average, best period, worst period, debt service and maximum supportable amount.**
- [ ] **Step 2: Test the existing Price schedule, grace period and existing debt handling.**
- [ ] **Step 3: Test moderate and severe combined shocks with an explicit list of applied changes.**
- [ ] **Step 4: Mark scenarios with DSCR below 1.0 as uncovered and preserve the base analysis.**
- [ ] **Step 5: Route existing credit calculations through the new adapter and compare current responses.**
- [ ] **Step 6: Commit `feat: add payment capacity and stress engines`.**

## Task 8: Add consolidated data quality, experimental score and explanations

**Files:**
- Create: `services/analysis_engine/__init__.py`
- Create: `services/analysis_engine/data_quality.py`
- Create: `services/analysis_engine/risk_explanation.py`
- Create: `services/analysis_engine/experimental_score.py`
- Create: `tests/test_analysis_engine.py`
- Modify: `services/qualidade_dados.py` and `services/rating_credito.py` through compatibility wrappers

**Interfaces:**
- `assess_data_quality(input_data: dict, herd: dict, production: dict | None = None) -> dict`
- `build_explanation(analysis: dict) -> dict`
- `calculate_experimental_score(analysis: dict) -> dict`

- [ ] **Step 1: Test `COMPLETO`, `PARCIAL` and `INSUFICIENTE` using missing prices, costs, weights and productive indexes.**
- [ ] **Step 2: Test that data confidence is separate from economic risk.**
- [ ] **Step 3: Test explanations with positive factors, attention points, sources, assumptions and limitations.**
- [ ] **Step 4: Implement a 0–1000 experimental score only as a labeled, non-validated output with component values and no autonomous decision.**
- [ ] **Step 5: Preserve the existing 0–100 rating response for current consumers.**
- [ ] **Step 6: Commit `feat: consolidate analysis quality and explanations`.**

## Task 9: Implement the full-analysis application pipeline and reproducible snapshots

**Files:**
- Create: `services/analysis_pipeline.py`
- Create: `tests/test_analysis_pipeline.py`
- Modify: `database.py` with additive tables for analysis snapshots and API keys
- Modify: `app.py` only to call the pipeline from a new internal entry point

**Interfaces:**
- `run_full_analysis(payload: dict, context: AnalysisContext) -> dict`
- `save_analysis_snapshot(result: dict, context: AnalysisContext) -> str`
- `load_analysis_snapshot(analysis_id: str, organization_id: int | None) -> dict | None`

- [ ] **Step 1: Test pipeline order: validation, herd, production, economic, cashflow, debt, stress, quality and explanation.**
- [ ] **Step 2: Test that all output blocks carry engine, rules, parameters and model versions.**
- [ ] **Step 3: Add additive database migration functions and organization-scoped lookup.**
- [ ] **Step 4: Test reproducibility from a stored snapshot without reading current live prices.**
- [ ] **Step 5: Test that one organization cannot load another organization's analysis.**
- [ ] **Step 6: Commit `feat: add reproducible full analysis pipeline`.**

## Task 10: Add versioned B2B API, API keys and OpenAPI

**Files:**
- Create: `services/api_v1/__init__.py`
- Create: `services/api_v1/authentication.py`
- Create: `services/api_v1/schemas.py`
- Create: `services/api_v1/routes.py`
- Create: `services/api_v1/errors.py`
- Create: `docs/API.md`
- Create: `tests/test_api_v1.py`
- Modify: `app.py` to register the blueprint
- Modify: `requirements.txt` only if an OpenAPI dependency is necessary and compatible with the pinned environment

- [ ] **Step 1: Test API key creation, hashing, revocation, organization scope, rate limiting and malformed-key responses.**
- [ ] **Step 2: Add failing tests for all listed `/api/v1` endpoints and standard error envelopes.**
- [ ] **Step 3: Implement the blueprint using `analysis_pipeline.py`; do not copy calculations into route functions.**
- [ ] **Step 4: Add idempotency handling for `POST /api/v1/full-analysis` using an organization-scoped request key.**
- [ ] **Step 5: Publish OpenAPI at `/api/docs` with request, response and error examples.**
- [ ] **Step 6: Test legacy routes and v1 routes together.**
- [ ] **Step 7: Commit `feat: expose versioned livestock intelligence api`.**

## Task 11: Upgrade report, dashboard and demonstration mode

**Files:**
- Create: `templates/demo.html`
- Create: `tests/test_report_v1.py`
- Modify: `services/parecer_pdf.py` to add the B2B sections
- Modify: `templates/index.html` incrementally, preserving existing selectors and upload/classification flow
- Modify: `app.py` with `/demo` and report retrieval endpoints

- [ ] **Step 1: Test report sections for summary, herd, production, revenue, cost, cashflow, debt, DSCR, stress, risk, data quality, assumptions, sources and limitations.**
- [ ] **Step 2: Add the dashboard navigation areas without replacing the existing analysis controls.**
- [ ] **Step 3: Add `/demo` using clearly fictitious data and a visible demonstration label.**
- [ ] **Step 4: Add browser/static tests for accessibility, loading, error, empty and long-running analysis states.**
- [ ] **Step 5: Run frontend and PDF tests.**
- [ ] **Step 6: Commit `feat: add b2b report and demonstration flow`.**

## Task 12: Documentation, validation fixtures and production gate

**Files:**
- Create: `docs/ARCHITECTURE.md`
- Create: `docs/CALCULATIONS.md`
- Create: `docs/DATA_DICTIONARY.md`
- Create: `docs/ASSUMPTIONS.md`
- Create: `docs/VALIDATION.md`
- Create: `docs/SECURITY.md`
- Create: `tests/fixtures/properties.py`
- Modify: `README.md` with execution, API, limitations and deployment instructions

- [ ] **Step 1: Add deterministic fixtures `CRIA_A`, `CRIA_B`, `RECRIA_A`, `ENGORDA_A` and `CICLO_COMPLETO_A`.**
- [ ] **Step 2: Document every formula, unit, source, parameter precedence and estimated fallback.**
- [ ] **Step 3: Document tenant isolation, API keys, retention and sensitive-data logging rules.**
- [ ] **Step 4: Run the complete test suite and record the result.**
- [ ] **Step 5: Run `git diff --check`, build the Docker image and exercise `/healthz`.**
- [ ] **Step 6: Review the deployment configuration and commit `docs: document livestock intelligence platform`.**

## Verification gates

Before each phase is considered complete:

```powershell
python -m pytest -q tests/<focused-files>
python -m pytest -q
git diff --check
```

Before production publication:

```powershell
docker build -t orkavyn-intelligence .
docker run --rm -e SECRET_KEY=test -p 5050:5050 orkavyn-intelligence
Invoke-WebRequest http://localhost:5050/healthz
```

The existing untracked environment folders `.claude/`, `.pytest-local/` and `.superpowers/` must not be included in commits.
