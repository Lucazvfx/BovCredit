"""
Capacidade de pagamento avaliada sobre o PRAZO, não sobre o ano 1.

O DSCR do primeiro ano engana numa projeção pecuária: o ano 1 liquida o
estoque acumulado que veio na ficha (bois prontos, machos em idade de abate),
enquanto os anos seguintes vendem apenas a produção corrente. Um ciclo
completo projetava DSCR 6,08 no ano 1 e −0,53 no ano 2 — e o parecer aprovava
um crédito de 36 meses.

A recomendação passa a seguir o ano mais fraco do prazo, e a `memoria`
registra o raciocínio para o analista auditar.
"""
import pytest

from services.parecer_credito import (
    avaliar_capacidade_pagamento, avaliar_capacidade_no_prazo,
)


def _conclusao(caixa_ano1=700000, credito=300000, prazo=36, juros=0.11):
    return avaliar_capacidade_pagamento(
        geracao_caixa_anual=caixa_ano1, credito_valor=credito,
        prazo_meses=prazo, juros_aa=juros)


def _projecao(*dscrs):
    """Monta projecao_anos a partir dos DSCR desejados."""
    return [{'ano': i + 1, 'dscr': d, 'resultado': d * 100000,
             'viavel': d is not None and d >= 1.0}
            for i, d in enumerate(dscrs)]


def test_ano_1_forte_e_ano_2_negativo_rebaixa():
    """O caso que motivou tudo: aprova no ano 1, quebra no ano 2."""
    base = _conclusao()
    assert base['recomendacao'] == 'aprovar'

    r = avaliar_capacidade_no_prazo(base, _projecao(6.08, -0.53, -0.13, -0.14, -0.12), 36)
    assert r['recomendacao'] == 'negar'
    assert r['rebaixado_no_prazo'] is True
    assert r['ano_critico'] == 2
    assert r['dscr_minimo'] == -0.53
    assert r['dscr_ano1'] == base['dscr']


def test_projecao_estavel_mantem_aprovacao():
    """Quem sustenta o DSCR em todos os anos continua aprovado."""
    base = _conclusao()
    r = avaliar_capacidade_no_prazo(base, _projecao(2.36, 2.44, 2.54, 2.60, 2.65), 36)
    assert r['recomendacao'] == 'aprovar'
    assert r['rebaixado_no_prazo'] is False
    assert r['anos_viaveis'] == 3


def test_avalia_apenas_os_anos_do_prazo():
    """Um crédito de 24 meses não deve ser julgado pelo ano 5."""
    base = _conclusao(prazo=24)
    # anos 1–2 bons, ano 5 péssimo — fora do prazo, não pode pesar
    r = avaliar_capacidade_no_prazo(base, _projecao(3.0, 2.8, 2.5, 2.0, -5.0), 24)
    assert r['anos_avaliados'] == 2
    assert r['recomendacao'] == 'aprovar'
    assert r['dscr_minimo'] == 2.8


def test_cobertura_estreita_vira_ressalva():
    base = _conclusao()
    r = avaliar_capacidade_no_prazo(base, _projecao(2.5, 1.10, 1.05), 36)
    assert r['recomendacao'] == 'ressalva'
    assert r['dscr_minimo'] == 1.05


def test_memoria_explica_a_decisao():
    """O analista precisa auditar o raciocínio, não só receber o veredicto."""
    base = _conclusao()
    r = avaliar_capacidade_no_prazo(base, _projecao(6.08, -0.53, -0.13), 36)
    mem = r['memoria']
    assert mem, 'memória de cálculo ausente'

    passos = ' '.join(m['passo'] for m in mem)
    for esperado in ('Prazo do crédito', 'Serviço da dívida', 'DSCR do ano 1',
                     'DSCR do ano 2', 'Ano crítico', 'Anos viáveis', 'Rebaixamento'):
        assert esperado in passos, f'passo "{esperado}" faltando na memória'

    # todo passo precisa ter valor e explicação — memória sem detalhe não audita
    for m in mem:
        assert m.get('valor'), f'passo {m["passo"]} sem valor'
        assert m.get('detalhe'), f'passo {m["passo"]} sem explicação'

    # o rebaixamento precisa dizer de onde para onde
    reb = next(m for m in mem if m['passo'] == 'Rebaixamento')
    assert 'APROVAR' in reb['valor'] and 'NEGAR' in reb['valor']


def test_sem_projecao_mantem_conclusao_do_ano_1():
    """Sem projeção multianual não há o que reavaliar — não pode quebrar."""
    base = _conclusao()
    r = avaliar_capacidade_no_prazo(base, [], 36)
    assert r['recomendacao'] == base['recomendacao']
    assert 'memoria' not in r


def test_sem_credito_nao_avalia():
    base = avaliar_capacidade_pagamento(
        geracao_caixa_anual=500000, credito_valor=0, prazo_meses=0, juros_aa=0)
    r = avaliar_capacidade_no_prazo(base, _projecao(1.0, 1.0), 36)
    assert r['recomendacao'] == base['recomendacao']
