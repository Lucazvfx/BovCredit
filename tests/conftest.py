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


@pytest.fixture(autouse=True)
def reset_rate_limit_storage():
    import app as _app_module  # garante que limiter.init_app() já rodou
    from services.rate_limit import limiter
    limiter._storage.reset()
    yield
