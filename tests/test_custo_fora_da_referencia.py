"""
O custo que nega, mas não se apresenta.

O sistema já comparava o COE calculado com a referência Campo Futuro/CNA da
praça e rotulava o nível — e depois negava o crédito sem nunca dizer ao
analista que o CUSTO podia ser o problema.

Medido em rebanhos reais:

    ficha de recria, 700 cabeças ... R$ 387,02/@ contra R$ 183,50  (+110,9%)
    cria de 1.705 cabeças .......... R$ 249,60/@ contra R$ 189,76  ( +31,5%)
    ciclo completo de 790 .......... R$ 185,86/@ contra R$ 164,61  ( +12,9%)

Nos dois primeiros o parecer nega por caixa insuficiente, e a causa provável
do caixa insuficiente é o custo de ENTRADA — que o analista confere e corrige
em trinta segundos, se souber que deve.

Este aviso NÃO rebaixa nem altera número. É a diferença entre um parecer que
nega e um parecer que se explica: sem ele, uma recusa por custo fora da praça
é lida como recusa por fazenda ruim.

CONTEXTO QUE VALE REGISTRAR

O perfil de custo da RECRIA (R$ 100,50/cab/mês) é um dos TRÊS que foram
derivados por desagregação e não vieram da fonte GEP — junto com ENGORDA e
ENGORDA_CONFINAMENTO. Que justo ele seja o mais distante da referência não é
coincidência, e o aviso é o que torna isso visível enquanto não há dado
melhor.
"""
import pytest

import database as db
from app import app
from services.parecer_credito import COE_DIVERGENCIA_AVISO, montar_parecer


@pytest.fixture(scope='module')
def cli():
    db.init_db()
    email = 'coe@example.com'
    u = db.buscar_usuario_email(email)
    if not u:
        db.criar_usuario(email, 'COE', 'senha123')
        u = db.buscar_usuario_email(email)
    app.config['TESTING'] = True
    c = app.test_client()
    with c.session_transaction() as s:
        s['_user_id'] = str(u['id'])
    return c


FICHA_RECRIA = [22, 219, 0, 0, 105, 234, 45, 16, 59, 0]


def _parecer(cli, v):
    return cli.post('/api/classificar', json={
        'valores': v, 'preco': 320, 'credito_valor': sum(v) * 1200,
        'prazo_meses': 36, 'juros_aa': 0.125}).get_json()['parecer']


def test_custo_muito_acima_da_praca_e_avisado(cli):
    c = _parecer(cli, FICHA_RECRIA)['conclusao']
    fora = c.get('custo_fora_da_referencia')
    assert fora is not None, (
        'o parecer nega por caixa e não diz que o custo está fora da praça'
    )
    assert fora['delta_pct'] >= COE_DIVERGENCIA_AVISO
    assert fora['referencia'] > 0 and fora['local']


def test_o_aviso_entra_na_memoria_de_calculo(cli):
    """
    Memória de cálculo é o que o comitê lê. Um campo no JSON que não aparece
    ali não existe para quem decide.
    """
    c = _parecer(cli, FICHA_RECRIA)['conclusao']
    passos = [m for m in (c.get('memoria') or [])
              if 'Custo' in str(m.get('passo'))
              and 'referência' in str(m.get('passo')) + str(m.get('detalhe'))]
    assert passos, 'aviso ausente da memória de cálculo'
    detalhe = passos[0]['detalhe']
    assert 'Confira o custo' in detalhe
    assert 'subestimad' in detalhe, (
        'o aviso precisa dizer o que a superestimação do custo faz com o DSCR'
    )


def test_na_recria_o_aviso_declara_que_o_perimetro_e_diferente():
    """
    A recria isolada é comparada com o painel de recria E engorda, que vende
    boi terminado (~20@) enquanto a nossa entrega animal de ~13,5@. O desvio
    existe, mas parte dele é produto diferente, não custo alto.

    O aviso CONTINUA — o que ele pede ("confira o custo") vale de todo jeito —
    mas para de atribuir o desvio inteiro ao custo. Calar o aviso perderia o
    sinal que motivou o recurso; afirmar "110% acima da praça" afirmaria o que
    não se sabe.
    """
    from services.benchmarks_nacionais import avaliar_coe
    b = avaliar_coe('RECRIA', 400.0)
    assert b['perimetro_parcial'] and not b['comparavel']

    p = montar_parecer(
        identificacao={}, composicao={}, indicadores={}, benchmarks={},
        consistencia={}, financeiro={}, geracao_caixa_anual=500_000,
        credito={'credito_valor': 500_000, 'prazo_meses': 36, 'juros_aa': 0.1},
        fluxo_gep={'coe_benchmark': b})
    fora = p['conclusao']['custo_fora_da_referencia']
    assert fora['atribuivel'] is False
    passo = [m for m in p['conclusao']['memoria'] if 'Custo' in str(m.get('passo'))][0]
    assert 'NÃO são o mesmo produto' in passo['detalhe']
    assert 'boi terminado' in passo['detalhe']


def test_na_cria_o_desvio_continua_atribuivel():
    """Cria tem painel próprio: ali o desvio é do custo, e o texto afirma isso."""
    from services.benchmarks_nacionais import avaliar_coe
    b = avaliar_coe('CRIA', 400.0)
    assert b['comparavel'] and b['perimetro_parcial'] is None
    p = montar_parecer(
        identificacao={}, composicao={}, indicadores={}, benchmarks={},
        consistencia={}, financeiro={}, geracao_caixa_anual=500_000,
        credito={'credito_valor': 500_000, 'prazo_meses': 36, 'juros_aa': 0.1},
        fluxo_gep={'coe_benchmark': b})
    assert p['conclusao']['custo_fora_da_referencia']['atribuivel'] is True
    passo = [m for m in p['conclusao']['memoria'] if 'Custo acima' in str(m.get('passo'))][0]
    assert 'COE contra COE' in passo['detalhe']


def test_o_aviso_nao_rebaixa_a_recomendacao(cli):
    """
    Custo fora da referência é sinal para conferir, não prova de nada. Se
    rebaixasse, viraria política disfarçada de aviso.
    """
    p = _parecer(cli, FICHA_RECRIA)
    c = p['conclusao']
    assert c.get('custo_fora_da_referencia')
    # a recusa aqui vem do DSCR, não do aviso
    assert c['dscr_minimo'] < 1.0
    justificativa = c.get('justificativa') or ''
    assert 'custo acima' not in justificativa.lower(), (
        'o aviso vazou para a justificativa e virou motivo de rebaixamento'
    )


def test_custo_dentro_da_faixa_nao_gera_ruido():
    """
    Aviso que dispara sempre é aviso que se aprende a ignorar. Abaixo do
    limiar, silêncio.
    """
    p = montar_parecer(
        identificacao={}, composicao={}, indicadores={}, benchmarks={},
        consistencia={}, financeiro={}, geracao_caixa_anual=500_000,
        credito={'credito_valor': 500_000, 'prazo_meses': 36, 'juros_aa': 0.1},
        fluxo_gep={'coe_benchmark': {'coe_calculado': 170.0,
                                     'coe_referencia': 164.61,
                                     'delta_pct': 3.3, 'nivel': 'atencao'}},
    )
    assert 'custo_fora_da_referencia' not in p['conclusao']


def test_sem_benchmark_de_coe_nao_quebra():
    """Modalidade sem referência de praça: silêncio, não erro."""
    p = montar_parecer(
        identificacao={}, composicao={}, indicadores={}, benchmarks={},
        consistencia={}, financeiro={}, geracao_caixa_anual=500_000,
        credito={'credito_valor': 500_000, 'prazo_meses': 36, 'juros_aa': 0.1},
        fluxo_gep={'coe_benchmark': None},
    )
    assert 'custo_fora_da_referencia' not in p['conclusao']
