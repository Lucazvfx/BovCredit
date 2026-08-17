"""
Configuração global de fixtures para a suíte de testes.

Flask-Limiter usa armazenamento em memória (memory://) nos testes — os
contadores acumulam durante toda a sessão. Depois de 10 chamadas a
/api/classificar dentro de um minuto, testes subsequentes no mesmo módulo
recebem 429 em vez de 200.

A solução é resetar o storage do Flask-Limiter antes de cada função de
teste. Os testes de rate limit da API v1 (test_api_v1.py) não são afetados:
cada um abre a própria janela, faz 1-3 chamadas e verifica o 429 dentro da
mesma função — o reset acontece entre funções, não durante.
"""
import pytest
from flask.testing import FlaskClient
from werkzeug.datastructures import Headers


# ── Cliente de teste que passa pelo CSRF ─────────────────────────────────────
#
# No navegador o token nasce quando uma página renderiza: index.html o publica
# numa <meta> e o wrapper de fetch o envia em todo POST. Nenhum teste renderiza
# página antes de chamar a API, então sem ajuda todos tomariam 403.
#
# Antes isso passava batido porque o app liberava POST de sessão sem token —
# o mesmo buraco que o CSRF existe para fechar. Fechado o buraco, o cliente de
# teste passa a imitar o navegador em vez de contornar a proteção.
#
# Quem quer provar a rejeição desliga com `client.csrf = False`.

_TOKEN_CSRF_TESTE = 'csrf-de-teste'
_METODOS_QUE_MUTAM = {'POST', 'PUT', 'PATCH', 'DELETE'}


class _ClienteComCSRF(FlaskClient):
    csrf = True

    def open(self, *args, **kwargs):
        metodo = str(kwargs.get('method') or 'GET').upper()
        if self.csrf and metodo in _METODOS_QUE_MUTAM:
            # Só semeia se a sessão ainda não tiver token: um teste que
            # renderizou /app já tem o dele, e sobrescrever quebraria a
            # comparação com o valor que ele guardou.
            with self.session_transaction() as s:
                token = s.get('csrf_token')
                if not token:
                    token = _TOKEN_CSRF_TESTE
                    s['csrf_token'] = token
            headers = Headers(kwargs.get('headers') or {})
            headers.setdefault('X-CSRF-Token', token)
            kwargs['headers'] = headers
        return super().open(*args, **kwargs)


@pytest.fixture(autouse=True)
def reset_rate_limit_storage():
    import app as _app_module  # garante que limiter.init_app() já rodou
    from services.rate_limit import limiter
    _app_module.app.test_client_class = _ClienteComCSRF
    limiter._storage.reset()
    yield
