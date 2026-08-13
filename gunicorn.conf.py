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

# 1 worker por padrão — e a razão não é o modelo, é o SHAP.
#
# Com `preload_app` os ~300 MB do modelo são compartilhados por copy-on-write,
# então o segundo worker custa quase nada em repouso. O problema é o pico POR
# REQUISIÇÃO: cada classificação constrói os TreeExplainer dos quatro
# estimadores do ensemble e aloca ~160 MB que só voltam ao fim da chamada.
#
# Medido num processo real (RSS, não marca d'água):
#
#     após carregar o modelo ........ 300 MB
#     durante uma classificação ..... 459 MB
#
# A conta com o teto de 512 MB do contêiner:
#
#     1 worker classificando ..... 300 + 160 = 460 MB   cabe
#     2 workers classificando .... 300 + 320 = 620 MB   estoura
#
# Duas classificações simultâneas matavam o processo por falta de memória e o
# gateway devolvia 502 — exatamente na tela de classificar, que foi como o
# problema apareceu em produção.
#
# TENTATIVA QUE NÃO FUNCIONOU, registrada para ninguém repetir: cachear os
# TreeExplainer entre requisições PIORA. Eles não vazam — são liberados ao fim
# da chamada. Mantê-los vivos elevou o patamar de 459 para 550 MB.
#
# A correção de verdade é tirar o SHAP do caminho crítico, como já foi feito
# com a narrativa da IA: calcular sob demanda numa segunda requisição. Até lá,
# um worker é o que cabe. Suba `WEB_CONCURRENCY` junto com a memória do plano.
workers = int(os.environ.get('WEB_CONCURRENCY', '1'))

# gthread: threads compartilham a memória do processo (modelo incluído), então
# 2 threads não duplicam os 300 MB. O GIL bloqueia CPU-bound (SHAP), mas
# libera durante I/O — DB, cotações, geração de PDF, envio de e-mail.
# Resultado: endpoints rápidos (login, dashboard, histórico) não ficam
# enfileirados atrás de uma classificação em andamento.
# Suba WEB_THREADS=4 junto com um plano de memória maior se o uso crescer.
worker_class = 'gthread'
threads = int(os.environ.get('WEB_THREADS', '2'))

# Recicla o worker a cada N requisições, liberando memória que pode ter
# acumulado (fragmentação do alocador Python). O jitter evita que todos
# os workers reiniciem no mesmo instante.
max_requests = 500
max_requests_jitter = 50

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
