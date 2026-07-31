# Mesma versão de runtime.txt e do ambiente de desenvolvimento. O pickle do
# modelo é sensível à versão do scikit-learn, e o resolvedor do pip escolhe
# versões diferentes conforme o Python — 3.10 não recebe sklearn 1.9, então
# uma imagem em 3.10 carregava um sklearn incompatível com gestao_model.pkl.
FROM python:3.11.15 AS builder

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
WORKDIR /app

RUN python -m venv .venv
COPY requirements.txt ./
RUN .venv/bin/pip install -r requirements.txt

FROM python:3.11.15-slim
WORKDIR /app
COPY --from=builder /app/.venv .venv/
COPY . .

# Espelha o Procfile. A porta vem do ambiente (Railway/Fly injetam $PORT) e o
# timeout precisa ser folgado: se o modelo em disco não carregar, o boot cai no
# retreino, que leva minutos e estourava o padrão de 30s do gunicorn.
ENV PORT=8080
CMD .venv/bin/gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --timeout 120
