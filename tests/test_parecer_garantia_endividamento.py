"""
Onde garantia e endividamento encontram a recomendação.

Capacidade de pagamento, garantia e endividamento são perguntas independentes.
O fluxo pode cobrir a parcela e o rebanho não cobrir o principal numa execução;
ou os dois estarem bem e o produtor já ter comprometido a renda em outros
bancos. Vale sempre a pior das respostas — nunca a média, nunca a primeira.
"""
import pytest

from services.parecer_credito import montar_parecer

# Projeção folgada: DSCR alto em todos os anos, para isolar o efeito testado.
_PROJ = [{'ano': a, 'dscr': 3.0, 'geracao_caixa': 900_000, 'viavel': True}
         for a in (1, 2, 3)]


def _parecer(**extra):
    base = dict(
        identificacao={'fazenda': 'Teste'}, composicao={'total': 800},
        indicadores={}, benchmarks={}, consistencia={}, financeiro={},
        geracao_caixa_anual=900_000,
        credito={'credito_valor': 500_000, 'prazo_meses': 36,
                 'juros_aa': 0.125, 'carencia_meses': 0, 'dividas_mensais': 0},
        projecao_anos=_PROJ,
    )
    base.update(extra)
    return montar_parecer(**base)


def test_sem_garantia_nem_endividamento_o_parecer_segue_como_antes():
    """Compatibilidade: os dois argumentos são opcionais."""
    p = _parecer()
    assert p['conclusao']['recomendacao'] == 'aprovar'
    assert p['garantia'] is None
    assert p['endividamento'] is None


def test_garantia_insuficiente_rebaixa_uma_aprovacao():
    """O caso que motivou o módulo: fluxo cobre a parcela, rebanho não cobre o principal."""
    p = _parecer(garantia={'veredito': 'insuficiente', 'ltv': 118.4})
    c = p['conclusao']
    assert c['recomendacao'] == 'ressalva'
    assert '118.4' in c['justificativa']
    assert any('garantia' in m['passo'].lower() for m in c['memoria']), (
        'o rebaixamento precisa aparecer na memória de cálculo — é o que o '
        'comitê lê para entender por que caiu'
    )


@pytest.mark.parametrize('veredito', ['suficiente', 'ajustada'])
def test_garantia_que_cobre_nao_rebaixa(veredito):
    p = _parecer(garantia={'veredito': veredito, 'ltv': 55.0})
    assert p['conclusao']['recomendacao'] == 'aprovar'


def test_endividamento_critico_rebaixa_uma_aprovacao():
    p = _parecer(endividamento={'alerta': 'critico', 'comprometimento_pct': 88.0})
    c = p['conclusao']
    assert c['recomendacao'] == 'ressalva'
    assert '88.0' in c['justificativa']
    assert any('endividamento' in m['passo'].lower() for m in c['memoria'])


def test_endividamento_ok_nao_rebaixa():
    p = _parecer(endividamento={'alerta': 'ok', 'comprometimento_pct': 30.0})
    assert p['conclusao']['recomendacao'] == 'aprovar'


def test_rebaixamento_nunca_promove_uma_negativa():
    """
    Um DSCR que nega não pode virar ressalva porque a garantia está boa. O
    rebaixamento só desce.
    """
    proj_ruim = [{'ano': a, 'dscr': 0.2, 'geracao_caixa': 50_000, 'viavel': False}
                 for a in (1, 2, 3)]
    p = _parecer(projecao_anos=proj_ruim,
                 garantia={'veredito': 'suficiente', 'ltv': 20.0},
                 endividamento={'alerta': 'ok', 'comprometimento_pct': 10.0})
    assert p['conclusao']['recomendacao'] == 'negar'


def test_motivos_de_rebaixamento_se_acumulam_na_memoria():
    """
    Garantia ruim E endividamento alto: a recomendação cai uma vez, mas o
    comitê precisa ver os dois motivos, não só o primeiro que disparou.
    """
    p = _parecer(garantia={'veredito': 'insuficiente', 'ltv': 130.0},
                 endividamento={'alerta': 'critico', 'comprometimento_pct': 95.0})
    c = p['conclusao']
    assert c['recomendacao'] == 'ressalva'
    passos = ' '.join(m['passo'].lower() for m in c['memoria'])
    assert 'garantia' in passos
    assert 'endividamento' in passos


def test_as_duas_secoes_entram_no_parecer():
    """Se não estiverem em `secoes`, o PDF e a tela não as renderizam."""
    p = _parecer(garantia={'veredito': 'ajustada', 'ltv': 70.0},
                 endividamento={'alerta': 'ok', 'comprometimento_pct': 40.0})
    assert 'garantia' in p['secoes']
    assert 'endividamento' in p['secoes']
    assert p['garantia']['ltv'] == 70.0
    assert p['endividamento']['comprometimento_pct'] == 40.0
