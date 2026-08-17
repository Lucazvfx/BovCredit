# Orkavyn Agro Intelligence

Plataforma de análise de crédito pecuário. Analistas fazem upload de fichas de rebanho (PDF/Excel), o sistema extrai os dados, classifica o risco via ML e gera um parecer de crédito.

## Stack

- **Backend**: Flask 3.1 + Gunicorn (gthread, preload_app)
- **ML**: scikit-learn + LightGBM + XGBoost — modelo salvo em `gestao_model.pkl` (~300 MB RSS)
- **Banco**: PostgreSQL em produção, SQLite local (`gestao.db`)
- **OCR**: Tesseract (`tesseract-ocr-por`) via pytesseract
- **PDF**: pdfplumber + poppler-utils (`pdftotext`)
- **IA narrativa**: Groq API (`services/groq_narrativa.py`)
- **Auth**: flask-login + TOTP 2FA (`services/totp.py`)
- **Rate limit**: flask-limiter (Redis em prod, memória local)
- **Scheduler**: APScheduler — cotações de boi gordo via scraper

## Estrutura principal

```
app.py                  # rotas Flask, ~2000 linhas
database.py             # queries PostgreSQL/SQLite
ml_engine.py            # treinar_modelo, classificar, calcular_indicadores, SHAP
pdf_parsers.py          # parsers por estado (IDARON, INDEA, IAGRO-MS, AGED-MA…)
scraper.py              # cotações arroba boi gordo
gunicorn.conf.py        # workers, threads, preload, scheduler hook
treinar_ciclos.py       # retreinar gestao_model.pkl

services/
  assistente.py         # chat IA com contexto de análise
  groq_narrativa.py     # geração de narrativa via Groq
  parecer_credito.py    # montar_parecer, cronograma_price
  parecer_pdf.py        # gerar_pdf_parecer (ReportLab)
  fichas_rebanho/       # leitura, consolidação e validação de fichas
  benchmarks_nacionais.py
  rating_credito.py
  checklist_credito.py
  economic_engine/
  payment_capacity_engine/
  stress_engine/
  cashflow_engine/

templates/
  landing.html          # página pública (scroll video + animações CSS/JS)
  index.html            # dashboard principal (requer login)
  admin.html
  login.html / cadastro.html / login_2fa.html

static/
  img/logo-light.svg
  img/logo-dark.svg
```

## Variáveis de ambiente obrigatórias

| Variável | Descrição |
|---|---|
| `SECRET_KEY` | Chave Flask — gere com `secrets.token_hex(32)` |
| `DATABASE_URL` | `postgresql://user:pass@host/db` |
| `ADMIN_EMAILS` | E-mails admin separados por vírgula |
| `ADMIN_SENHA_INICIAL` | Senha do primeiro login (trocar depois) |
| `GROQ_API_KEY` | API Groq para narrativas |
| `APP_URL` | URL pública sem barra final |

Opcionais: `RATELIMIT_STORAGE_URI` (Redis), `WEB_CONCURRENCY`, `WEB_THREADS`, `WEB_TIMEOUT`.

## Desenvolvimento local

```bash
pip install -r requirements.txt
# Para o modelo: python treinar_ciclos.py  (necessário após mudar deps ML)
flask run
```

O banco SQLite (`gestao.db`) é criado automaticamente na primeira execução.

## Produção (Hostinger VPS)

- **URL**: `https://credito.orkavyn.tech`
- **Deploy**: Docker Compose (`docker compose up -d --build`)
- **App dir**: `/opt/orkavyn`
- **Atualizar**: `cd /opt/orkavyn && git pull && docker compose up -d --build`
- **Logs**: `docker compose logs -f app`
- nginx reverse proxy na porta 8080, SSL via Certbot/Let's Encrypt

## Branch de trabalho

`claude/analysis-pp4wlx` — branch ativa desta sessão de desenvolvimento.

## Decisões técnicas importantes

**`preload_app = True` no gunicorn** — obrigatório. O modelo (~300 MB) é carregado uma vez no master e compartilhado via fork CoW. Sem isso, cada worker duplica o modelo na memória. O scheduler APScheduler é iniciado via `when_ready` (não no import) para não morrer no fork.

**SHAP fora do caminho crítico** — `/api/classificar` retorna `shap_pendente=true` e o frontend busca `/api/shap` separadamente. Evita pico de memória de 460 MB coincidindo com a classificação.

**`gestao_model.pkl` é versionado** — o pickle é gerado pelo scikit-learn 1.5.2 + numpy 1.26.4. Se mudar qualquer versão ML no `requirements.txt`, rodar `python treinar_ciclos.py` antes de commitar.

**Parsers por estado** — cada UF tem seu próprio parser em `pdf_parsers.py` (IDARON/RO, INDEA/MT, IAGRO-MS, AGED-MA, AGRODEFESA-GO, ADAPEC-TO, ADEPARA-PA). Fichas genéricas usam `parsear_generico`.

## Landing page

`templates/landing.html` tem scroll-driven video animation (4 fases: formulário → classificação → DSCR → veredito). Usa `position: sticky` com 500vh de altura e cálculo de progresso via `requestAnimationFrame`. Design tokens em CSS custom properties com suporte a dark mode.
