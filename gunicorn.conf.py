"""
Configuração do gunicorn.

O deploy rodava com `--workers 1`. Isso atende uma consultoria com cinco
analistas e trava com cinquenta: uma requisição de classificação leva alguns
segundos (simulação + SHAP), e com um worker só a segunda espera a primeira
terminar.

Multiplicar workers ingenuamente, porém, multiplica o modelo: são ~334 MB de
RSS por processo, quase todo ele o `gestao_model.pkl` carregado no import.
Quatro workers estouram qualquer container modesto.

`preload_app` resolve os dois: o app é importado UMA vez no master — modelo
inclusive — e os workers nascem de `fork()`. O Linux compartilha as páginas
por copy-on-write, então o modelo não é duplicado enquanto ninguém escreve
nele. E ele é só lido.

De quebra, worker reciclado renasce do fork do master, sem reler o pickle do
disco.

O QUE PRELOAD QUEBRARIA SE NINGUÉM OLHASSE

Com o app importado no master, qualquer coisa iniciada em escopo de módulo
acontece antes do fork:

- **Scheduler** — a thread do APScheduler NÃO sobrevive ao fork (só a thread
  que chama fork sobrevive). Iniciado no import, ele morreria em todos os
  workers e o master não estaria servindo: o scraper simplesmente nunca mais
  rodaria, em silêncio. Por isso `SCHEDULER_VIA_HOOK=1` desliga o start no
  import e `when_ready` o inicia uma única vez, no master, onde a thread vive.

- **Conexão de banco** — um handle aberto antes do fork é compartilhado por
  todos os filhos e corrompe. Aqui não há risco: `database.get_conn()` abre e
  fecha por chamada, sem pool global.
"""
import os

# Precisa vir antes do import do app, que o gunicorn faz logo em seguida
# quando preload_app está ligado.
os.environ.setdefault('SCHEDULER_VIA_HOOK', '1')

bind = f"0.0.0.0:{os.environ.get('PORT', '8080')}"

# 2 é o padrão conservador para container pequeno. Suba junto com a memória
# disponível: com preload o custo marginal por worker é bem menor que os
# 334 MB do primeiro, mas não é zero.
workers = int(os.environ.get('WEB_CONCURRENCY', '2'))
threads = int(os.environ.get('WEB_THREADS', '1'))

# Folgado de propósito: se o modelo em disco não carregar, o boot cai no
# retreino, que leva minutos.
timeout = int(os.environ.get('WEB_TIMEOUT', '120'))
graceful_timeout = 30
keepalive = 5

preload_app = True
accesslog = '-'
errorlog = '-'


def when_ready(server):
    """
    Roda UMA vez, no master, depois do preload e antes de servir.

    É o único lugar do ciclo de vida do gunicorn com essa garantia — `post_fork`
    rodaria em cada worker, e escopo de módulo perderia a thread no fork.
    """
    try:
        import app
        app.iniciar_scheduler()
    except Exception:
        server.log.exception(
            'falha ao iniciar o scheduler de cotações — a aplicação segue '
            'servindo, mas as cotações não serão atualizadas automaticamente')
