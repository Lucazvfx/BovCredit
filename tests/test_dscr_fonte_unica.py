"""
Os limites de DSCR (aprovar / ressalva) têm UMA definição: o motor
(services/payment_capacity_engine/dscr.py). parecer_credito.py só reexporta.

Antes eram dois `politica(...)` independentes com o mesmo valor. Mudar um sem o
outro faria o parecer e o motor aplicarem regras diferentes, sem nenhum teste
acusando. Estes testes travam isso: identidade do objeto, catálogo de
proveniência, texto do assistente e comportamento da recomendação.
"""
import pytest

import services.payment_capacity_engine as pce
import services.payment_capacity_engine.dscr as motor
import services.parecer_credito as parecer
from services.proveniencia import politica

LIMITES = ('DSCR_APROVAR', 'DSCR_RESSALVA')


def _entradas_do_catalogo(catalogo, rotulo):
    return [d for d in catalogo if d['rotulo'] == rotulo]


def _montar_parecer():
    return parecer.montar_parecer(
        identificacao={}, composicao={}, indicadores={}, benchmarks=[],
        consistencia={'score_consistencia': 90, 'flags': [],
                      'resumo': {'erros': 0}},
        financeiro={}, geracao_caixa_anual=200000,
        credito={'credito_valor': 100000, 'prazo_meses': 24,
                 'juros_aa': 0.10, 'carencia_meses': 0, 'dividas_mensais': 0})


@pytest.mark.parametrize('nome', LIMITES)
def test_parecer_reexporta_o_mesmo_objeto_do_motor(nome):
    assert getattr(parecer, nome) is getattr(motor, nome)
    assert getattr(pce, nome) is getattr(motor, nome)


def test_parecer_nao_redefine_os_limites():
    """A definição fica no motor; o módulo do parecer só importa."""
    import inspect
    fonte = inspect.getsource(parecer)
    assert 'DSCR_APROVAR = ' not in fonte
    assert 'DSCR_RESSALVA = ' not in fonte


@pytest.mark.parametrize('nome', LIMITES)
def test_catalogo_do_motor_publica_o_limite_do_motor(nome):
    param = getattr(motor, nome)
    achadas = _entradas_do_catalogo(
        motor.resumo_proveniencia()['parametros'], param.rotulo)
    assert len(achadas) == 1
    assert achadas[0]['valor'] == float(param)


@pytest.mark.parametrize('nome', LIMITES)
def test_catalogo_do_parecer_publica_o_limite_do_motor(nome):
    """
    O catálogo deduplica por (rótulo, valor, origem): se os limites divergissem,
    o parecer listaria DOIS "DSCR para aprovar" com valores diferentes.
    """
    param = getattr(motor, nome)
    achadas = _entradas_do_catalogo(
        _montar_parecer()['proveniencia']['parametros'], param.rotulo)
    assert len(achadas) == 1
    assert achadas[0]['valor'] == float(param)


def test_texto_do_assistente_usa_os_limites_do_motor():
    from services.assistente import _conceitos
    texto = _conceitos()['dscr']
    assert f'{float(motor.DSCR_APROVAR):.2f}' in texto
    assert f'{float(motor.DSCR_RESSALVA):.2f}' in texto


def test_mudar_o_limite_no_motor_muda_o_veredito_do_parecer(monkeypatch):
    """
    Com o limite de aprovação real, este caso aprova. Se o motor subir o limite,
    o parecer tem que acompanhar — prova de que não há segunda cópia decidindo.
    """
    args = (200000, 100000, 24, 0.10)
    antes = parecer.avaliar_capacidade_pagamento(*args)
    assert antes['recomendacao'] == 'aprovar'

    monkeypatch.setattr(motor, 'DSCR_APROVAR', politica(
        antes['dscr'] + 1.0, 'teste', rotulo='DSCR para aprovar'))

    depois = parecer.avaliar_capacidade_pagamento(*args)
    assert depois['recomendacao'] == 'ressalva'
