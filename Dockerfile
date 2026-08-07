# Mesma versão de runtime.txt e do ambiente de desenvolvimento. O modelo é um
# pickle do scikit-learn, e pickle não atravessa versão de biblioteca; como o
# resolvedor do pip escolhe versões conforme o Python, alinhar as três
# declarações é o que garante que produção rode o ambiente testado.
FROM python:3.11.15 AS builder

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
WORKDIR /app

RUN python -m venv .venv
COPY requirements.txt ./
RUN .venv/bin/pip install -r requirements.txt

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

# Espelha o Procfile. Bind, workers, timeout e o hook do scheduler ficam em
# gunicorn.conf.py — ver lá por que preload_app é obrigatório aqui.
ENV PORT=8080
CMD [".venv/bin/gunicorn", "-c", "gunicorn.conf.py", "app:app"]
