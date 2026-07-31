"""
Ingestão do IBGE — a primeira medição do projeto.

A camada de proveniência responde hoje: 26 parâmetros, 0 medidos. Este módulo
existe para tirar esse zero do zero, com desfrute = abate ÷ efetivo por UF.

ATENÇÃO AO LER ESTES TESTES

O módulo NUNCA foi exercitado contra a API real — o ambiente de
desenvolvimento bloqueia saída para o IBGE. As fixtures abaixo foram montadas
a partir da documentação do formato, não de uma resposta capturada.

Por isso os testes se concentram no que protege a PRIMEIRA execução com rede:
que ela falhe alto se o contrato não bater, em vez de gravar lixo em silêncio.
Um parser que "funciona" contra a própria fixture não prova nada; um que
levanta quando a forma muda, sim.
"""
import pytest

from services import ibge_sidra as sidra
from services.ibge_sidra import (
    parse_valores, desfrute_por_uf, RespostaInesperada, RESSALVA_DESFRUTE,
)

CABECALHO = {'NC': 'Nível Territorial (Código)', 'NN': 'Nível Territorial',
             'MC': 'Unidade de Medida (Código)', 'MN': 'Unidade de Medida',
             'V': 'Valor', 'D1C': 'Unidade da Federação (Código)',
             'D1N': 'Unidade da Federação', 'D2C': 'Ano (Código)', 'D2N': 'Ano'}


def _linha(uf_cod, uf, valor, ano='2024', unidade='Cabeças'):
    return {'NC': '3', 'NN': 'Unidade da Federação', 'MC': '1017',
            'MN': unidade, 'V': valor, 'D1C': uf_cod, 'D1N': uf,
            'D2C': ano, 'D2N': ano}


# ── O que protege a primeira execução com rede ──────────────────────────────
def test_cabecalho_e_detectado_nao_assumido():
    """
    Assumir `values[0]` produziria um registro com V='Valor' passando por dado
    se o IBGE mudasse a posição. A detecção é pelo conteúdo.
    """
    fora_de_ordem = [_linha('51', 'Mato Grosso', '32100000'), CABECALHO]
    regs = parse_valores(fora_de_ordem)
    assert len(regs) == 1
    assert regs[0]['uf'] == 'Mato Grosso'


def test_payload_que_nao_e_array_levanta():
    """Rede cai e volta; contrato quebrado precisa de gente olhando."""
    with pytest.raises(RespostaInesperada, match='esperado array'):
        parse_valores({'erro': 'parâmetro inválido'})


def test_elemento_que_nao_e_objeto_levanta():
    with pytest.raises(RespostaInesperada, match='não é objeto'):
        parse_valores([CABECALHO, 'texto solto'])


def test_a_mensagem_de_erro_carrega_o_payload():
    """Sem ver o que veio, ninguém conserta o parser."""
    with pytest.raises(RespostaInesperada) as e:
        parse_valores({'mensagem': 'tabela inexistente'})
    assert 'tabela inexistente' in str(e.value)


def test_resposta_sem_cabecalho_avisa_mas_nao_quebra(caplog):
    regs = parse_valores([_linha('51', 'Mato Grosso', '32100000')])
    assert len(regs) == 1
    assert 'cabeçalho' in caplog.text.lower()


# ── Marcadores do IBGE ──────────────────────────────────────────────────────
@pytest.mark.parametrize('marcador', ['-', '..', '...', 'X', '..X', '', '  '])
def test_marcador_vira_ausencia_e_nao_zero(marcador):
    """
    Tratar marcador como zero zeraria o desfrute de um estado inteiro sem
    ninguém perceber. É o erro mais silencioso possível aqui.
    """
    regs = parse_valores([CABECALHO, _linha('51', 'Mato Grosso', marcador)])
    assert regs == [], f'marcador {marcador!r} virou dado'


def test_valor_com_virgula_decimal():
    regs = parse_valores([CABECALHO, _linha('51', 'MT', '1234,56')])
    assert regs[0]['valor'] == pytest.approx(1234.56)


def test_valor_com_separador_de_milhar_e_virgula():
    regs = parse_valores([CABECALHO, _linha('51', 'MT', '32.100.000,50')])
    assert regs[0]['valor'] == pytest.approx(32100000.50)


def test_valor_com_ponto_decimal():
    regs = parse_valores([CABECALHO, _linha('51', 'MT', '1234.56')])
    assert regs[0]['valor'] == pytest.approx(1234.56)


def test_texto_invalido_nao_vira_dado():
    assert parse_valores([CABECALHO, _linha('51', 'MT', 'indisponível')]) == []


# ── Cálculo do desfrute ─────────────────────────────────────────────────────
@pytest.fixture
def series():
    efetivo = parse_valores([CABECALHO,
        _linha('51', 'Mato Grosso', '32100000'),
        _linha('11', 'Rondônia',    '17600000'),
        _linha('35', 'São Paulo',   '10000000')])
    abate = parse_valores([CABECALHO,
        _linha('51', 'Mato Grosso', '7000000'),
        _linha('11', 'Rondônia',    '3800000'),
        _linha('35', 'São Paulo',   '2000000')])
    return efetivo, abate


def test_desfrute_e_a_razao_em_pontos_percentuais(series):
    d = desfrute_por_uf(*series)
    assert d['51']['desfrute_pct'] == pytest.approx(7000000 / 32100000 * 100, abs=0.01)
    assert d['51']['uf'] == 'Mato Grosso'


def test_casa_por_codigo_e_nao_por_nome():
    """
    'Rondônia' vs 'RONDÔNIA' vs 'Rondonia' nunca casariam pelo nome, e o
    resultado seria um dicionário vazio — sem erro nenhum.
    """
    ef = parse_valores([CABECALHO, _linha('11', 'Rondônia', '17600000')])
    ab = parse_valores([CABECALHO, _linha('11', 'RONDONIA', '3800000')])
    assert desfrute_por_uf(ef, ab)['11']['desfrute_pct'] > 0


def test_uf_sem_os_dois_lados_e_descartada():
    ef = parse_valores([CABECALHO, _linha('51', 'MT', '32100000'),
                                   _linha('99', 'Fantasia', '1000')])
    ab = parse_valores([CABECALHO, _linha('51', 'MT', '7000000')])
    assert set(desfrute_por_uf(ef, ab)) == {'51'}


def test_razao_implausivel_e_descartada(caplog):
    """
    Acima de 200% o dado está errado ou o recorte não bate. Propagar isso para
    o parecer seria pior que não ter medição nenhuma.
    """
    ef = parse_valores([CABECALHO, _linha('35', 'São Paulo', '1000')])
    ab = parse_valores([CABECALHO, _linha('35', 'São Paulo', '9000')])   # 900%
    assert desfrute_por_uf(ef, ab) == {}
    assert 'implausível' in caplog.text


def test_efetivo_zero_nao_divide_por_zero():
    ef = parse_valores([CABECALHO, _linha('35', 'SP', '0')])
    ab = parse_valores([CABECALHO, _linha('35', 'SP', '9000')])
    assert desfrute_por_uf(ef, ab) == {}


def test_series_vazias():
    assert desfrute_por_uf([], []) == {}
    assert parse_valores([]) == []


# ── Rede ────────────────────────────────────────────────────────────────────
def test_falha_de_rede_devolve_vazio_sem_levantar(monkeypatch):
    """Rede é instável por natureza; o job não pode morrer por isso."""
    import requests

    def _explode(*a, **k):
        raise requests.ConnectionError('sem rota para o host')

    monkeypatch.setattr(requests, 'get', _explode)
    assert sidra.baixar(sidra.TAB_EFETIVO, '105', 'last 1') == []


def test_falha_de_formato_levanta_mesmo_pela_rede(monkeypatch):
    """
    O contrário da anterior, e é deliberado: rede cai e volta sozinha, formato
    quebrado precisa de gente olhando.
    """
    import requests

    class _Resp:
        status_code = 200
        def raise_for_status(self): pass
        def json(self): return {'erro': 'tabela inexistente'}

    monkeypatch.setattr(requests, 'get', lambda *a, **k: _Resp())
    with pytest.raises(RespostaInesperada):
        sidra.baixar(sidra.TAB_EFETIVO, '105', 'last 1')


def test_url_montada_com_a_tabela_e_o_periodo(monkeypatch):
    capturado = {}

    class _Resp:
        status_code = 200
        def raise_for_status(self): pass
        def json(self): return [CABECALHO]

    import requests
    monkeypatch.setattr(requests, 'get',
                        lambda url, **k: (capturado.update(url=url), _Resp())[1])
    sidra.baixar('3939', '105', 'last 1', classificacao='c79/2670')
    assert '/t/3939/' in capturado['url']
    assert '/v/105/' in capturado['url']
    assert capturado['url'].endswith('c79/2670')


# ── Honestidade do número ───────────────────────────────────────────────────
def test_a_ressalva_acompanha_a_serie():
    """
    Abate ÷ efetivo não é desfrute exato. O parecer precisa dizer o que o
    número é — MT exporta boi em pé, SP abate mais do que cria.
    """
    assert 'proxy' in RESSALVA_DESFRUTE.lower()
    assert 'fora da UF' in RESSALVA_DESFRUTE
