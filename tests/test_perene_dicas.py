"""Dicas calculadas: a frase que olha o dado do analista e diz o que fazer.

Tooltip genérico — "DSCR é caixa dividido por serviço da dívida" — se lê uma
vez e nunca mais. O que muda o trabalho é a dica que sai dos números daquela
lavoura: a carência que vence antes da primeira colheita, os talhões todos na
mesma carga, o cenário que descobre a operação.

Vive no backend porque tela e PDF precisam dizer a MESMA coisa sobre a mesma
análise — o mesmo motivo de services/origem_rebanho.py existir.
"""
import io

import pdfplumber
import pytest

from services.parecer_pdf_perene import gerar_pdf_parecer_perene
from services.perennial_engine import analisar_lavoura_perene, gerar_dicas

CURVA = {'produtividade_plena': 30, 'unidade': 'saca_60kg',
         'fatores': {'1': 0, '2': 0, '3': 0.4, '4': 0.8, '5': 1.0},
         'bienalidade': 0.15, 'fonte': 'Embrapa Café — exemplo'}
CUSTO = {'formacao': 14000, 'producao': 9000, 'por_unidade': 120}


def _analisar(talhoes, carencia=24, curva=None, **extra):
    payload = {
        'ano_base': 2026, 'anos': 6, 'talhoes': talhoes,
        'curvas': {'CAFE': dict(CURVA, **(curva or {}))},
        'precos': {'CAFE': 1400}, 'custos': {'CAFE': CUSTO},
        'credito': {'credito_valor': 1_500_000, 'prazo_meses': 72,
                    'juros_aa': 0.105, 'carencia_meses': carencia,
                    'sistema_amortizacao': 'sac', 'periodicidade_meses': 12},
    }
    payload.update(extra)
    return analisar_lavoura_perene(payload)


def _titulos(analise):
    return [d['titulo'] for d in analise['dicas']]


LAVOURA_NOVA = [{'cultura': 'CAFE', 'area_ha': 60, 'ano_plantio': 2025,
                 'identificacao': 'B', 'fase_bienal': 'alta'}]
LAVOURA_MADURA = [{'cultura': 'CAFE', 'area_ha': 40, 'ano_plantio': 2021,
                   'identificacao': 'A', 'fase_bienal': 'alta'}]


# ── A dica que justifica o recurso ──────────────────────────────────────────

def test_carencia_que_vence_antes_da_primeira_colheita_e_apontada():
    """O erro clássico de financiar formação: cobrar antes de a lavoura pagar."""
    analise = _analisar(LAVOURA_NOVA, carencia=12)

    dica = next(d for d in analise['dicas'] if 'carência vence' in d['titulo'].lower())
    assert dica['tipo'] == 'atencao'
    assert 'ano 3' in dica['texto']          # primeira produção
    assert '24 meses' in dica['texto']       # a carência que alcança


def test_carencia_suficiente_nao_gera_dica():
    """Dica que aparece sempre vira ruído e para de ser lida."""
    analise = _analisar(LAVOURA_NOVA, carencia=24)

    assert not [d for d in analise['dicas'] if 'carência vence' in d['titulo'].lower()]


def test_lavoura_que_ja_produz_no_ano_1_nao_recebe_a_dica():
    analise = _analisar(LAVOURA_MADURA, carencia=0)

    assert not [d for d in analise['dicas'] if 'carência vence' in d['titulo'].lower()]


# ── As demais ───────────────────────────────────────────────────────────────

def test_cenarios_descobertos_viram_dica_com_a_contagem():
    analise = _analisar(LAVOURA_NOVA, carencia=12)

    dica = next(d for d in analise['dicas'] if 'descobrem a operação' in d['titulo'])
    assert 'DSCR cai abaixo de 1' in dica['texto']


def test_ano_critico_diferente_do_primeiro_vira_dica():
    analise = _analisar(LAVOURA_MADURA)
    ano = analise['credito']['analysis']['pior_periodo']['ano']

    assert f'Avalie pelo ano {ano}, não pelo primeiro' in _titulos(analise)


def test_curva_sem_fonte_vira_dica_acionavel():
    """Diz o que fazer — preencher a coluna Fonte —, não só que falta."""
    analise = _analisar(LAVOURA_MADURA, curva={'fonte': ''})

    dica = next(d for d in analise['dicas'] if 'não tem fonte' in d['titulo'])
    assert 'coluna Fonte' in dica['texto']


def test_lavoura_alinhada_explica_o_efeito_no_dscr():
    analise = _analisar([
        {'cultura': 'CAFE', 'area_ha': 20, 'ano_plantio': 2021, 'identificacao': 'A',
         'fase_bienal': 'alta'},
        {'cultura': 'CAFE', 'area_ha': 20, 'ano_plantio': 2020, 'identificacao': 'B',
         'fase_bienal': 'alta'}])

    dica = next(d for d in analise['dicas'] if 'oscila junta' in d['titulo'])
    assert 'fundo do poço' in dica['texto']


def test_analise_incompleta_vem_primeiro():
    """Sem os dados, as outras dicas falam sobre número parcial."""
    analise = _analisar(
        LAVOURA_MADURA + [{'cultura': 'CANA', 'area_ha': 100, 'ano_plantio': 2024,
                           'identificacao': 'K'}])

    assert analise['dicas'][0]['titulo'] == 'A análise está incompleta'
    assert 'CANA' in analise['dicas'][0]['texto']


# ── Tela e PDF dizem a mesma coisa ──────────────────────────────────────────

def test_o_pdf_traz_as_mesmas_dicas_da_analise():
    analise = _analisar(LAVOURA_NOVA, carencia=12)
    pdf = gerar_pdf_parecer_perene(analise, {'fazenda': 'Teste'})

    with pdfplumber.open(io.BytesIO(pdf)) as documento:
        texto = '\n'.join(pagina.extract_text() or '' for pagina in documento.pages)

    assert 'Leitura da análise' in texto
    for dica in analise['dicas']:
        assert dica['titulo'] in texto


def test_analise_sem_nada_a_dizer_nao_inventa_dica():
    assert gerar_dicas({'valido': True}, {}) == []
