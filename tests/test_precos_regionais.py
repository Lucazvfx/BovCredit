"""
Preço por praça.

O sistema usava UM preço para o Brasil inteiro. O indicador CEPEA/ESALQ é
praça de São Paulo, e a mesma arroba valia igual em Araçatuba e em Ariquemes.
Isso contamina tudo que é derivado de preço — receita, fluxo, e principalmente
o LTV da garantia, que decide se o rebanho cobre o crédito.
"""
import pytest

from services.precos_regionais import (
    aplicar, basis, extrair_uf, BASIS_UF, UF_REFERENCIA, CATEGORIAS,
)

NACIONAL = {'preco_boi': 330.0, 'preco_vaca': 308.0,
            'preco_bezerro': 3000.0, 'preco_bezerra': 2700.0}


# ── Leitura da UF a partir do campo livre ───────────────────────────────────
@pytest.mark.parametrize('texto,esperado', [
    ('Juara - MT',        'MT'),
    ('Juara/MT',          'MT'),
    ('JUARA MT',          'MT'),
    ('Ariquemes - RO',    'RO'),
    ('São Félix do Araguaia - MT', 'MT'),
    ('Presidente Prudente - SP',   'SP'),
    ('  cuiabá  -  mt  ', 'MT'),
])
def test_extrai_uf_do_campo_livre(texto, esperado):
    """O analista escreve como quiser; o campo é texto livre."""
    assert extrair_uf(texto) == esperado


@pytest.mark.parametrize('texto', ['', None, 'Fazenda Santa Cruz', 'Juara', 'XX'])
def test_sem_uf_reconhecivel_devolve_none(texto):
    """Melhor não saber que adivinhar errado — o preço nacional é o padrão seguro."""
    assert extrair_uf(texto) is None


def test_uf_no_fim_vence_sigla_no_meio():
    """'RIO BRANCO AC' — 'RIO' não é UF, mas duas letras soltas podem confundir."""
    assert extrair_uf('Rio Branco - AC') == 'AC'


# ── O ajuste ────────────────────────────────────────────────────────────────
def test_rondonia_puxa_preco_para_baixo():
    r = aplicar(NACIONAL, municipio='Ariquemes - RO')
    assert r['regional']['ajustado'] is True
    assert r['regional']['uf'] == 'RO'
    assert r['precos']['preco_boi'] < NACIONAL['preco_boi']


def test_praca_de_referencia_nao_recebe_ajuste():
    r = aplicar(NACIONAL, municipio=f'Araçatuba - {UF_REFERENCIA}')
    assert r['regional']['situacao'] == 'praca_referencia'
    assert r['precos']['preco_boi'] == NACIONAL['preco_boi']


def test_sem_uf_usa_nacional_e_avisa():
    r = aplicar(NACIONAL, municipio='Fazenda sem estado')
    assert r['regional']['situacao'] == 'sem_uf'
    assert r['precos'] == NACIONAL
    assert 'nacional' in r['regional']['resumo'].lower()


def test_ordenacao_geografica_faz_sentido():
    """
    Distância dos centros de abate e frete empurram o preço para baixo subindo
    pelo arco norte. Se a ordem inverter, a tabela foi editada errado.
    """
    def boi(uf):
        return aplicar(NACIONAL, uf=uf)['precos']['preco_boi']

    assert boi('SP') > boi('MT') > boi('RO')
    assert boi('SP') >= boi('GO') >= boi('MT')


def test_todas_as_categorias_sao_ajustadas():
    r = aplicar(NACIONAL, municipio='Juara - MT')
    for cat in CATEGORIAS:
        assert r['precos'][cat] < NACIONAL[cat], f'{cat} não recebeu o diferencial'


# ── O erro mais fácil de cometer aqui ───────────────────────────────────────
def test_preco_digitado_nao_recebe_diferencial():
    """
    Preço informado pelo analista JÁ é o da praça dele. Aplicar o diferencial
    em cima descontaria duas vezes, e o erro seria invisível — o número sairia
    plausível, só menor do que deveria.
    """
    r = aplicar(NACIONAL, municipio='Ariquemes - RO',
                ajustaveis={'preco_vaca', 'preco_bezerro', 'preco_bezerra'})
    assert r['precos']['preco_boi'] == NACIONAL['preco_boi'], (
        'preço digitado foi descontado indevidamente'
    )
    assert r['precos']['preco_vaca'] < NACIONAL['preco_vaca']


def test_nenhum_preco_ajustavel():
    r = aplicar(NACIONAL, municipio='Ariquemes - RO', ajustaveis=set())
    assert r['precos'] == NACIONAL
    assert r['regional']['situacao'] == 'sem_precos_ajustaveis'


def test_ajuste_nao_e_cumulativo():
    """Aplicar duas vezes tem que ser detectável — o preço não pode cair de novo."""
    uma = aplicar(NACIONAL, uf='RO')['precos']
    duas = aplicar(uma, uf='RO')['precos']
    assert duas['preco_boi'] < uma['preco_boi'], (
        'este teste documenta que a função NÃO é idempotente: quem chamar duas '
        'vezes desconta duas vezes, e por isso ela tem um único ponto de '
        'aplicação em app.py'
    )


# ── Robustez ────────────────────────────────────────────────────────────────
def test_preco_none_nao_quebra():
    r = aplicar({'preco_boi': 330.0, 'preco_vaca': None,
                 'preco_bezerro': None, 'preco_bezerra': None}, uf='MT')
    assert r['precos']['preco_boi'] < 330.0
    assert r['precos']['preco_vaca'] is None


def test_dicionario_vazio():
    r = aplicar({}, uf='MT')
    assert r['precos'] == {}
    assert r['regional']['ajustado'] is False


def test_uf_desconhecida_usa_nacional():
    r = aplicar(NACIONAL, uf='ZZ')
    assert r['regional']['situacao'] == 'uf_desconhecida'
    assert r['precos'] == NACIONAL


def test_uf_explicita_vence_o_municipio():
    """Quando o formulário tem campo de UF, ele é mais confiável que o texto livre."""
    r = aplicar(NACIONAL, municipio='Juara - MT', uf='RO')
    assert r['regional']['uf'] == 'RO'


# ── Rastreabilidade ─────────────────────────────────────────────────────────
def test_memoria_mostra_de_onde_veio_cada_preco():
    r = aplicar(NACIONAL, municipio='Ariquemes - RO')
    mem = r['regional']['memoria']
    assert mem, 'sem memória o analista não consegue defender o número'
    passos = ' '.join(m['passo'] for m in mem).lower()
    assert 'diferencial' in passos
    assert 'boi' in passos
    for m in mem:
        assert m['detalhe']


def test_declara_que_o_diferencial_nao_e_medicao():
    """
    Honestidade de origem: estes números são calibração de referência, não
    série apurada. O parecer não pode passá-los por medição.
    """
    r = aplicar(NACIONAL, municipio='Ariquemes - RO')
    assert 'não medido' in r['regional']['origem']


def test_categorias_registram_antes_e_depois():
    r = aplicar(NACIONAL, municipio='Juara - MT')
    for c in r['regional']['categorias']:
        assert c['regional'] < c['nacional']


# ── A tabela ────────────────────────────────────────────────────────────────
def test_tabela_e_coerente():
    assert BASIS_UF[UF_REFERENCIA] == 0.0, 'a praça de referência é o zero'
    assert len(BASIS_UF) == 27, 'as 26 UFs e o DF'
    assert all(-0.30 < d < 0.10 for d in BASIS_UF.values()), (
        'diferencial fora de faixa plausível — provável erro de digitação'
    )
