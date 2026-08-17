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

# 1 worker por padrão — motivo: memória do contêiner, não o modelo em si.
#
# Medido num processo real (RSS, não marca d'água):
#
#     após carregar o modelo ........ 300 MB
#     durante /api/shap ............. 459 MB   (TreeExplainer × 4 estimadores)
#
# SHAP JÁ ESTÁ FORA DO CAMINHO CRÍTICO
#
# Tentativa descartada: cachear os TreeExplainer entre requisições PIORA o
# perfil de memória (459 → 550 MB). Eles não vazam — são liberados ao fim de
# cada chamada. Manter o cache aumenta a linha de base sem reduzir o pico.
#
# /api/classificar não chama SHAP: devolve shap_pendente=true e o frontend
# busca /api/shap em seguida. O pico de 160 MB do SHAP não coincide mais com
# a classificação — a memória volta antes da próxima requisição pesada.
#
# Com gthread e 2 threads (1 processo, 2 threads):
#
#     Thread A: /api/classificar .... 300 MB   (sem SHAP)
#     Thread B: /api/shap ........... 460 MB   (os 300 MB são compartilhados)
#     Pior caso simultâneo .......... 460 MB   cabe em 512 MB
#
# Se o plano tiver 1 GB+, defina WEB_CONCURRENCY=2 no Railway para dobrar a
# capacidade: com preload_app os dois workers compartilham os 300 MB via CoW,
# e o segundo pico de SHAP acontece no outro processo — ~460 + ~160 = ~620 MB.
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

# Dimensionado pela requisição mais lenta (classificação + geração de parecer),
# não pelo boot: se o modelo em disco não carregar, o app aborta o import em
# vez de cair no retreino de minutos.
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
