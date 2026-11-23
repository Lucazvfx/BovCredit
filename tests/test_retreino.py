"""O retreino é offline (`avaliar_retreino.py`, coberto em test_avaliar_retreino.py).

O app não expõe rota de retreino nem mantém contador de confirmações:
reintroduzir isso exige decisão explícita, não pode acontecer por acidente.
"""
import os

from app import app

RAIZ = os.path.join(os.path.dirname(__file__), '..')


def test_app_nao_expoe_rota_de_retreino():
    rotas = [r.rule for r in app.url_map.iter_rules()]
    assert not [r for r in rotas if 'retrain' in r or 'retreino' in r]


def test_app_nao_mantem_contador_de_retreino_automatico():
    with open(os.path.join(RAIZ, 'app.py'), encoding='utf-8') as f:
        src = f.read()
    for simbolo in ('api_retrain', 'RETRAIN_A_CADA',
                    '_confirmacoes_desde_retrain', '_auto_retrain'):
        assert simbolo not in src
