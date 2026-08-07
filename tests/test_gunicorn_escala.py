"""
Escala: mais de um worker sem multiplicar o modelo nem o scheduler.

O deploy rodava com `--workers 1`. Atende cinco analistas e trava com
cinquenta — uma classificação leva alguns segundos (simulação + SHAP) e a
segunda requisição espera a primeira.

Multiplicar workers ingenuamente multiplica duas coisas, e as duas quebram:

1. **O modelo.** ~334 MB de RSS por processo, quase todo `gestao_model.pkl`
   carregado no import. Quatro workers estouram qualquer container modesto.
   `preload_app` importa uma vez no master e os workers nascem de fork, com as
   páginas compartilhadas por copy-on-write. Medido: 2 workers somam 852 MB de
   RSS ingênuo mas 351 MB de memória real (PSS), contra 334 MB de um worker só.

2. **O scheduler.** Cada worker iniciaria o seu, e o scraper bateria N vezes na
   mesma fonte no mesmo minuto. Pior: com preload, a thread do APScheduler
   iniciada no import NÃO sobrevive ao fork — morreria em todos os workers e o
   master não estaria servindo, então o scraper simplesmente nunca mais
   rodaria, em silêncio.
"""
import os
import re

import pytest


CONF = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    'gunicorn.conf.py')


@pytest.fixture(scope='module')
def conf_texto():
    with open(CONF, encoding='utf-8') as f:
        return f.read()


# ── O que torna vários workers viáveis ──────────────────────────────────────
def test_preload_esta_ligado(conf_texto):
    """
    Sem preload, cada worker relê o pickle e carrega o próprio modelo: 334 MB
    vezes o número de workers.
    """
    assert re.search(r'^preload_app\s*=\s*True', conf_texto, re.M)


def test_workers_e_configuravel_por_ambiente(conf_texto):
    """Container pequeno e container grande não querem o mesmo número."""
    assert 'WEB_CONCURRENCY' in conf_texto


def test_timeout_segue_folgado(conf_texto):
    """
    Se o modelo em disco não carregar, o boot cai no retreino, que leva
    minutos. O padrão de 30s do gunicorn derrubaria o deploy — já derrubou.
    """
    assert 'WEB_TIMEOUT' in conf_texto
    assert "'120'" in conf_texto or '"120"' in conf_texto


def test_porta_vem_do_ambiente(conf_texto):
    """Railway e Fly injetam $PORT; bind fixo não sobe."""
    assert "os.environ.get('PORT'" in conf_texto


# ── O scheduler: exatamente um ──────────────────────────────────────────────
def test_o_conf_desliga_o_start_no_import(conf_texto):
    """
    Com preload o import roda no master, antes do fork. Se o scheduler subisse
    ali, a thread morreria em todos os workers e o master não serve — o
    scraper nunca mais rodaria, sem erro nenhum.
    """
    assert "SCHEDULER_VIA_HOOK" in conf_texto
    idx_env = conf_texto.index('SCHEDULER_VIA_HOOK')
    idx_hook = conf_texto.index('def when_ready')
    assert idx_env < idx_hook, (
        'a variável precisa ser definida antes do gunicorn importar o app'
    )


def test_o_start_acontece_no_when_ready(conf_texto):
    """
    `when_ready` é o único ponto do ciclo de vida do gunicorn que roda uma vez
    só, no master, depois do preload. `post_fork` rodaria em cada worker.
    """
    assert 'def when_ready' in conf_texto
    assert 'iniciar_scheduler' in conf_texto
    assert 'def post_fork' not in conf_texto


def test_falha_do_scheduler_nao_impede_servir(conf_texto):
    """
    Cotação desatualizada é ruim; aplicação fora do ar é pior. O hook engole a
    exceção e registra.
    """
    trecho = conf_texto[conf_texto.index('def when_ready'):]
    assert 'try:' in trecho and 'except Exception' in trecho


def test_iniciar_scheduler_e_idempotente(monkeypatch):
    """Chamar duas vezes não pode criar dois agendadores."""
    import app as appmod
    monkeypatch.setattr(appmod, 'rotina_diaria_cotacoes', lambda: None)
    primeiro = appmod.iniciar_scheduler()
    try:
        segundo = appmod.iniciar_scheduler()
        assert primeiro is segundo
        assert appmod._scheduler_iniciado is True
    finally:
        primeiro.shutdown(wait=False)
        appmod.scheduler = None
        appmod._scheduler_iniciado = False


def test_app_nao_inicia_scheduler_sozinho_sob_o_hook():
    """
    Guarda de leitura: o start em escopo de módulo é condicionado a
    SCHEDULER_VIA_HOOK != '1'. Se alguém remover a condição, o preload volta a
    matar o scheduler silenciosamente.
    """
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(raiz, 'app.py'), encoding='utf-8') as f:
        fonte = f.read()
    assert "os.environ.get('SCHEDULER_VIA_HOOK') != '1'" in fonte


# ── Procfile e Dockerfile apontam para a mesma configuração ─────────────────
def _raiz(nome):
    caminho = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), nome)
    with open(caminho, encoding='utf-8') as f:
        return f.read()


def test_procfile_usa_a_configuracao():
    assert 'gunicorn.conf.py' in _raiz('Procfile')


def test_dockerfile_usa_a_configuracao():
    """
    Divergir aqui já custou um deploy: o Dockerfile fixava a porta em 8080 e
    usava o timeout padrão de 30s enquanto o Procfile mandava 120.
    """
    assert 'gunicorn.conf.py' in _raiz('Dockerfile')


def test_runtime_encontra_gunicorn_dentro_da_venv():
    assert '.venv/bin/gunicorn' in _raiz('Procfile')
    assert 'PATH="/app/.venv/bin:${PATH}"' in _raiz('Dockerfile')


def test_nem_procfile_nem_dockerfile_fixam_workers():
    """
    Se fixassem, a configuração seria ignorada e a briga entre os dois voltaria.
    """
    for nome in ('Procfile', 'Dockerfile'):
        assert '--workers' not in _raiz(nome), f'{nome} sobrepõe a configuração'


# ── Memória por requisição: o que causou o 502 em produção ──────────────────
# O 502 aparecia exatamente na tela de classificar. Causa: cada classificação
# aloca ~160 MB (os TreeExplainer do SHAP, quatro estimadores) que só voltam
# ao fim da chamada. Com o modelo compartilhado por preload:
#
#     1 worker classificando ..... 300 + 160 = 460 MB   cabe em 512
#     2 workers classificando .... 300 + 320 = 620 MB   estoura
#
# Não é limite que se ajuste no código — é o pico por requisição contra o teto
# do contêiner. Enquanto o SHAP estiver no caminho crítico, o default tem de
# ser 1.

def test_default_de_workers_cabe_na_memoria(conf_texto):
    """
    Se alguém subir o default sem tirar o SHAP do caminho crítico, o 502
    volta. O teste falha antes do deploy em vez de na tela do analista.
    """
    m = re.search(r"workers\s*=\s*int\(os\.environ\.get\('WEB_CONCURRENCY',\s*'(\d+)'\)\)",
                  conf_texto)
    assert m, 'não achei o default de workers'
    assert int(m.group(1)) == 1, (
        f"default de {m.group(1)} workers: com ~160 MB de pico por "
        f"classificação e ~300 MB de base, dois workers estouram 512 MB"
    )


def test_o_motivo_esta_escrito_junto(conf_texto):
    """
    Um número sem o porquê vira 2 de novo no primeiro reload lento. O
    comentário precisa citar o SHAP e a conta.
    """
    assert 'SHAP' in conf_texto
    assert '512' in conf_texto and '620' in conf_texto


def test_a_tentativa_que_falhou_esta_registrada(conf_texto):
    """
    Cachear os TreeExplainer entre requisições PIORA (459 → 550 MB): eles não
    vazam, são liberados ao fim da chamada. Registrado para ninguém repetir.
    """
    assert 'cachear' in conf_texto.lower() or 'cache' in conf_texto.lower()
