FROM python:3.11.15 AS builder

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
WORKDIR /app

RUN python -m venv .venv
COPY requirements.txt ./
RUN .venv/bin/pip install --no-cache-dir -r requirements.txt

FROM python:3.11.15-slim
WORKDIR /app

# Binários de sistema que o pip não traz — a imagem -slim não inclui nenhum:
#
# libgomp1        runtime do OpenMP. LightGBM e XGBoost o carregam em tempo de
#                 execução via ctypes, então instalar os pacotes não o traz.
#                 Sem ele, `import lightgbm` levanta OSError e o app não sobe:
#                 o pickle do modelo referencia LGBMClassifier, logo nem
#                 carregar do disco nem retreinar funcionavam.
#
# poppler-utils   fornece o `pdftotext`, primeiro estágio de
#                 extrair_texto_pdf(). Sem o binário a chamada levanta
#                 FileNotFoundError e a cascata cai direto no pdfplumber —
#                 que perde o layout em coluna das fichas de IDARON e INDEA,
#                 justamente o que os parsers usam para separar as faixas
#                 etárias.
#
# tesseract-ocr   terceiro estágio: PDF escaneado (imagem, sem camada de
# + -por          texto) não rende nada nos dois primeiros. O pacote -por traz
#                 o modelo de português; sem ele o `lang='por+eng'` falha e o
#                 OCR degrada para inglês, que erra acentuação e os rótulos
#                 das categorias.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libgomp1 \
        poppler-utils \
        tesseract-ocr \
        tesseract-ocr-por \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /app/.venv .venv/
COPY . .
ENV PATH="/app/.venv/bin:${PATH}"

# O app abre PDFs de terceiros com poppler, pdfplumber e tesseract — parsers
# em C sobre arquivo não confiável. Rodar isso como root significa que uma
# falha de memória em qualquer um dos três entrega o container inteiro.
#
# /app fica root e o processo só lê: em produção nada é gravado ali. O banco
# é PostgreSQL, os PDFs recebidos vão para tempfile em /tmp e os documentos
# guardados vão para o banco. A única gravação em /app seria salvar_modelo(),
# que só roda no retreino — caminho que não deve existir em produção e que
# já falha com aviso, sem derrubar o app.
#
# PYTHONDONTWRITEBYTECODE vale para o estágio final também: sem permissão de
# escrita em /app, o CPython tentaria criar __pycache__ a cada import e
# perderia o cache silenciosamente.
ENV PYTHONDONTWRITEBYTECODE=1
RUN useradd --create-home --uid 10001 orkavyn
USER orkavyn

# Espelha o Procfile. Bind, workers, timeout e o hook do scheduler ficam em
# gunicorn.conf.py — ver lá por que preload_app é obrigatório aqui.
ENV PORT=8080
CMD [".venv/bin/gunicorn", "-c", "gunicorn.conf.py", "app:app"]
