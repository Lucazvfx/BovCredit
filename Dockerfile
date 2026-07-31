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

# libgomp1 é o runtime do OpenMP. LightGBM e XGBoost o carregam em tempo de
# execução via ctypes (não é dependência do pip, então instalar os pacotes não
# o traz), e a imagem -slim não o inclui. Sem ele, `import lightgbm` levanta
# OSError e o app não sobe: o pickle do modelo referencia LGBMClassifier, então
# nem carregar do disco nem retreinar funcionavam.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /app/.venv .venv/
COPY . .

# Espelha o Procfile. Bind, workers, timeout e o hook do scheduler ficam em
# gunicorn.conf.py — ver lá por que preload_app é obrigatório aqui.
ENV PORT=8080
CMD [".venv/bin/gunicorn", "-c", "gunicorn.conf.py", "app:app"]
