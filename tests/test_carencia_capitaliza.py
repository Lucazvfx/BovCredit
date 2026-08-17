"""
Carência não é de graça.

O sistema calculava a parcela sobre `prazo − carência` e mantinha o principal
parado, como se os meses de carência não existissem. Durante eles o saldo
devedor rende juros, e quem amortiza depois amortiza um saldo maior.

    R$ 1.000.000 · 36 meses · 12 de carência · 12,5% a.a.

        parcela antes ....... R$ 46.997
        parcela correta ..... R$ 52.872      +12,5%

A parcela saía 11,1% abaixo do devido e o DSCR subia na mesma proporção — o
erro corria a favor de APROVAR. Carência é padrão em custeio pecuário, então
o caso não é raro: é o normal.

A OUTRA CONVENÇÃO, que existe e não é esta

Há linhas em que o tomador PAGA os juros durante a carência e só o principal
fica suspenso. Nelas o saldo não cresce — mas há desembolso de juros nos meses
da carência, que o modelo também não representava. Adotada a capitalização por
ser a estrutura corrente em custeio e a mais conservadora das duas.

O QUE PRECISA ANDAR JUNTO

`credito_maximo` é a inversa de `avaliar_capacidade_pagamento`. Corrigir uma e
esquecer a outra faria o sistema oferecer um teto de crédito que ele próprio
reprovaria — e o erro só apareceria quando alguém pedisse exatamente o valor
sugerido.
"""
import pytest

from services.parecer_credito import (
    parcela_price, principal_apos_carencia, credito_maximo, cronograma_price,
    avaliar_capacidade_pagamento, DSCR_APROVAR,
)


def test_cronograma_respeita_carencia_e_ultimo_ano_parcial():
    c = cronograma_price(500_000, 0.10, prazo_meses=30, carencia_meses=6)
    assert [a['parcelas_nova_operacao'] for a in c['anos']] == [6, 12, 6]
    assert c['anos'][0]['servico_nova_operacao'] == pytest.approx(
        6 * c['parcela_mensal'], abs=0.10)
    assert c['anos'][2]['servico_nova_operacao'] == pytest.approx(
        6 * c['parcela_mensal'], abs=0.10)


def test_cronograma_rejeita_carencia_igual_ao_prazo():
    with pytest.raises(ValueError, match='menor que o prazo'):
        cronograma_price(100_000, 0.10, prazo_meses=12, carencia_meses=12)

PV, JUROS, PRAZO, CARENCIA = 1_000_000.0, 0.125, 36, 12


# ── A capitalização ─────────────────────────────────────────────────────────
def test_principal_cresce_pelos_juros_da_carencia():
    p = principal_apos_carencia(PV, JUROS, CARENCIA)
    # doze meses a 12,5% a.a. compostos ao mês = exatamente 12,5% no período
    assert p == pytest.approx(PV * 1.125, rel=1e-6)


def test_a_parcela_sobe_o_esperado():
    antes = parcela_price(PV, JUROS, PRAZO - CARENCIA)
    agora = parcela_price(principal_apos_carencia(PV, JUROS, CARENCIA),
                          JUROS, PRAZO - CARENCIA)
    assert antes == pytest.approx(46_997.06, abs=1.0)
    assert agora == pytest.approx(52_871.69, abs=1.0)
    assert agora / antes == pytest.approx(1.125, rel=1e-3)


def test_sem_carencia_nada_muda():
    """A correção não pode mexer em crédito sem carência, que é a maioria."""
    assert principal_apos_carencia(PV, JUROS, 0) == PV
    b = avaliar_capacidade_pagamento(
        geracao_caixa_anual=900_000, credito_valor=PV,
        prazo_meses=PRAZO, juros_aa=JUROS, carencia_meses=0)
    assert b['parcela_mensal'] == pytest.approx(
        parcela_price(PV, JUROS, PRAZO), abs=0.01)
    assert b['capitalizacao_carencia'] is None


@pytest.mark.parametrize('pv,juros,car', [
    (0, 0.125, 12), (PV, 0, 12), (PV, 0.125, 0), (-100, 0.125, 12),
])
def test_bordas_nao_explodem(pv, juros, car):
    assert principal_apos_carencia(pv, juros, car) >= 0


# ── A inversa tem de concordar com a direta ─────────────────────────────────
def test_credito_maximo_produz_exatamente_o_dscr_alvo():
    """
    Se as duas discordarem, o sistema sugere um teto que ele mesmo reprova —
    e o erro só aparece quando alguém pede exatamente o valor sugerido.
    """
    caixa = 1_000_000.0
    cm = credito_maximo(geracao_caixa_anual=caixa, juros_aa=JUROS,
                        prazo_meses=PRAZO, carencia_meses=CARENCIA)
    r = avaliar_capacidade_pagamento(
        geracao_caixa_anual=caixa, credito_valor=cm,
        prazo_meses=PRAZO, juros_aa=JUROS, carencia_meses=CARENCIA)
    assert r['dscr'] == pytest.approx(float(DSCR_APROVAR), abs=0.01)


def test_carencia_reduz_o_credito_maximo():
    """
    Mais carência, mais juros capitalizados, menos principal que a mesma
    geração de caixa suporta. Antes a carência AUMENTAVA o teto, porque só
    encurtava o prazo de amortização sem cobrar nada por isso.
    """
    caixa = 1_000_000.0
    sem = credito_maximo(caixa, JUROS, PRAZO, 0)
    com = credito_maximo(caixa, JUROS, PRAZO, CARENCIA)
    assert com < sem, 'carência ainda está saindo de graça no crédito máximo'


# ── O analista precisa ver de onde veio ─────────────────────────────────────
def test_a_capitalizacao_e_declarada():
    b = avaliar_capacidade_pagamento(
        geracao_caixa_anual=900_000, credito_valor=PV,
        prazo_meses=PRAZO, juros_aa=JUROS, carencia_meses=CARENCIA)
    cap = b['capitalizacao_carencia']
    assert cap['principal_liberado'] == PV
    assert cap['principal_amortizado'] == pytest.approx(1_125_000, abs=1)
    assert cap['acrescimo_pct'] == pytest.approx(12.5, abs=0.1)


def test_entra_na_memoria_de_calculo():
    """
    Sem esta linha o analista vê uma parcela maior que a conta ingênua dele e
    não tem como saber de onde veio a diferença.
    """
    from services.parecer_credito import avaliar_capacidade_no_prazo
    b = avaliar_capacidade_pagamento(
        geracao_caixa_anual=900_000, credito_valor=PV,
        prazo_meses=PRAZO, juros_aa=JUROS, carencia_meses=CARENCIA)
    anos = [{'ano': i, 'dscr': 1.5, 'resultado': 900_000, 'viavel': True}
            for i in (1, 2, 3)]
    c = avaliar_capacidade_no_prazo(b, anos, PRAZO)
    passos = [m for m in c['memoria'] if 'Carência' in m['passo']]
    assert passos, 'a capitalização não aparece na memória de cálculo'
    assert '12.5' in passos[0]['detalhe'] or '12,5' in passos[0]['detalhe']


# ── A reversão ──────────────────────────────────────────────────────────────
def test_reversao_documentada():
    """Convenção alternativa existe; a saída tem de existir e estar escrita.

    O texto migrou de services/parecer_credito.py para o motor quando as duas
    cópias da matemática de amortização foram unificadas (a inclusão do SAC
    teria criado uma terceira). O parecer agora só reexporta; a documentação
    vive junto da conta que ela descreve.
    """
    import services.payment_capacity_engine.dscr as D
    fonte = open(D.__file__, encoding='utf-8').read()
    assert "CARENCIA_SEM_CAPITALIZACAO" in fonte
    assert 'PAGA os juros durante a carência' in fonte
