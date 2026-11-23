"""PDF do parecer: blocos de Ciclo de 12 meses, Estresse da arroba e Ponto de ruptura.

Os dicts vêm de `montar_parecer` (números reais dos motores); aqui se prova só a
RENDERIZAÇÃO: aparece com dado completo, some sem dado, não quebra com dado
parcial/malformado e não altera o parecer recebido.
"""
import copy
import io

import pdfplumber
import pytest

from services.parecer_credito import montar_parecer
from services.parecer_pdf import gerar_pdf_parecer

ANO = {'ano': 1, 'receita': 600000.0, 'custo': 300000.0, 'resultado': 300000.0,
       'dscr': 1.39, 'viavel': True, 'servico_divida_anual': 216000.0}
ENTRADA = {'preco_arroba_base': 300.0, 'custo_reposicao_anual': 60000.0,
           'custo_suplementacao_anual': 40000.0}


def _parecer(**extra):
    return montar_parecer(
        identificacao={'fazenda': 'Faz. Teste'}, composicao={}, indicadores={},
        benchmarks=[], consistencia={'score_consistencia': 90, 'flags': [],
                                     'resumo': {'erros': 0}},
        financeiro={}, geracao_caixa_anual=300000,
        credito={'credito_valor': 1000000, 'prazo_meses': 36, 'juros_aa': 0.125,
                 'carencia_meses': 0},
        projecao_anos=[ANO], **extra)


def _texto(pdf: bytes) -> str:
    with pdfplumber.open(io.BytesIO(pdf)) as doc:
        return ' '.join(' '.join(p.extract_text() or '' for p in doc.pages).split())


@pytest.fixture(scope='module')
def completo():
    p = _parecer(sistema_produtivo='cria', estresse_pecuario_entrada=ENTRADA)
    assert p['ciclo_pecuario']['disponivel'] and p['estresse_pecuario']['disponivel']
    return p


def test_dados_completos_renderizam_os_tres_blocos(completo):
    t = _texto(gerar_pdf_parecer(completo))
    assert 'Ciclo de 12 meses' in t
    assert 'Estresse da arroba' in t
    assert 'Ponto de ruptura da arroba' in t
    # números formatados em pt-BR (moeda, %, DSCR com vírgula)
    assert 'R$ 216.000,00' in t
    assert 'queda_arroba R$ 510.000,00 R$ 300.000,00 R$ 210.000,00 41,2% 0,97 negar' in t


def test_vale_de_caixa_e_destacado_quando_ha_deficit(completo):
    c = copy.deepcopy(completo)
    c['ciclo_pecuario']['vale_caixa'] = -50000.0
    c['ciclo_pecuario']['mes_vale'] = 3
    c['ciclo_pecuario']['meses_deficit'] = [3, 4]
    t = _texto(gerar_pdf_parecer(c))
    assert 'Vale de caixa' in t and '-50.000,00' in t


def test_sem_vale_de_caixa_quando_saldo_nunca_fica_negativo(completo):
    c = copy.deepcopy(completo)
    c['ciclo_pecuario']['vale_caixa'] = 1000.0
    assert 'Sem vale de caixa' in _texto(gerar_pdf_parecer(c))


def test_nao_muda_o_parecer_recebido(completo):
    antes = copy.deepcopy(completo)
    gerar_pdf_parecer(completo)
    assert completo == antes


def test_sem_ciclo_nem_estresse_pdf_igual_ao_de_antes():
    p = _parecer()
    assert 'ciclo_pecuario' not in p and 'estresse_pecuario' not in p
    t = _texto(gerar_pdf_parecer(p))
    for titulo in ('Ciclo de 12 meses', 'Estresse da arroba', 'Ponto de ruptura'):
        assert titulo not in t


@pytest.mark.parametrize('valor', [None, {}, [], 'x', 5])
def test_chaves_vazias_ou_malformadas_nao_quebram(valor):
    p = {**_parecer(), 'ciclo_pecuario': valor, 'estresse_pecuario': valor}
    assert gerar_pdf_parecer(p).startswith(b'%PDF')


def test_indisponivel_mostra_o_motivo_sem_quebrar():
    p = {**_parecer(),
         'ciclo_pecuario': {'disponivel': False, 'motivo': 'Sem projeção.'},
         'estresse_pecuario': {'disponivel': False, 'motivo': 'Sem base <b>.'}}
    t = _texto(gerar_pdf_parecer(p))
    assert 'Sem projeção.' in t and 'Sem projeção..' not in t
    assert 'Sem base' in t


def test_dados_parciais_nao_quebram(completo):
    p = copy.deepcopy(completo)
    p['ciclo_pecuario'] = {'disponivel': True, 'meses': [{'mes': 1}, 'lixo', None],
                           'vale_caixa': 'abc'}
    p['estresse_pecuario'] = {'disponivel': True, 'base': {'receita': 'x'},
                              'cenarios': {'queda': None, 'alta': {'dscr': None}},
                              'ponto_ruptura_arroba': {'aprovar': {}, 'ressalva': 3}}
    assert gerar_pdf_parecer(p).startswith(b'%PDF')


def test_texto_com_marcacao_e_escapado(completo):
    p = copy.deepcopy(completo)
    p['estresse_pecuario']['avisos'] = ['<para>quebra & <b>teste']
    p['ciclo_pecuario']['justificativa'] = ['<unclosed']
    assert gerar_pdf_parecer(p).startswith(b'%PDF')


def test_entradas_gigantes_sao_limitadas():
    meses = [{'mes': i, 'rotulo': 'M' * 5000} for i in range(1, 500)]
    p = {**_parecer(),
         'ciclo_pecuario': {'disponivel': True, 'meses': meses,
                            'justificativa': ['j'] * 1000},
         'estresse_pecuario': {'disponivel': True,
                               'cenarios': {str(i): {} for i in range(500)}}}
    assert gerar_pdf_parecer(p).startswith(b'%PDF')


def test_ruptura_destaca_preco_base_abaixo_do_minimo(completo):
    c = copy.deepcopy(completo)
    c['estresse_pecuario']['ponto_ruptura_arroba']['aprovar']['em_ruptura'] = True
    t = _texto(gerar_pdf_parecer(c))
    assert 'Em ruptura' in t and 'no preço mínimo ou abaixo dele' in t


def test_proveniencia_e_premissas_aparecem_no_pdf(completo):
    t = _texto(gerar_pdf_parecer(completo))
    assert 'não série medida' in t           # perfil sazonal é premissa do motor
    assert 'Arroba do boi gordo cai 15%' in t  # descrição do choque, não só a chave
    assert 'Origem dos choques' in t


def test_motivo_do_motor_nao_duplica_prefixo():
    p = {**_parecer(), 'ciclo_pecuario': {
        'disponivel': False,
        'motivo': 'Fluxo sazonal indisponível: custo negativo'}}
    assert 'indisponível: Fluxo sazonal' not in _texto(gerar_pdf_parecer(p))


@pytest.mark.parametrize('ruim', [float('nan'), float('inf'), 10 ** 400])
def test_numeros_nao_finitos_ou_gigantes_nao_quebram_nem_afirmam(completo, ruim):
    p = copy.deepcopy(completo)
    p['ciclo_pecuario']['vale_caixa'] = ruim
    p['estresse_pecuario']['base']['margem_liquida'] = ruim
    p['estresse_pecuario']['base']['receita'] = ruim
    t = _texto(gerar_pdf_parecer(p))
    assert 'Sem vale de caixa' not in t and 'nan' not in t.lower().replace('financ', '')


def test_e_comercial_em_celula_de_tabela_nao_vira_entidade(completo):
    p = copy.deepcopy(completo)
    p['estresse_pecuario']['cenarios'] = {'a&b': {'dscr': 1.0}}
    assert 'a&b' in _texto(gerar_pdf_parecer(p)) and '&amp;' not in _texto(gerar_pdf_parecer(p))
