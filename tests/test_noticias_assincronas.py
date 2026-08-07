import time

import app as app_module


def test_noticias_nao_bloqueiam_quando_feed_externo_demora(monkeypatch):
    app_module._noticias_cache = []
    app_module._noticias_cache_ts = 0
    app_module._noticias_refreshing = False

    def feed_lento(url, sess):
        time.sleep(0.2)
        return [{'titulo': 'Boi em alta', 'link': 'https://example.com', 'data': ''}]

    monkeypatch.setattr(app_module, '_buscar_rss', feed_lento)
    inicio = time.perf_counter()
    resultado = app_module._noticias_fresh()
    decorrido = time.perf_counter() - inicio

    assert resultado == []
    assert decorrido < 0.1

    limite = time.time() + 2
    while time.time() < limite and not app_module._noticias_cache:
        time.sleep(0.02)
    assert app_module._noticias_cache
