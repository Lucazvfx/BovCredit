"""Checagem que não rodou não pode se passar por checagem que passou.

A tela dizia "Nenhum alerta zootécnico encontrado com os dados disponíveis"
tanto quando tudo passou quanto quando nada pôde ser conferido. O analista
lia silêncio como atestado de saúde. Os códigos de `nao_avaliadas` existiam
só como slug cru no PDF — quem trabalha na tela não via nem isso.

Aqui também mora a terceira ocorrência da confusão de matrizes: o esperado de
nascimentos usava v[6]+v[8], inflando a referência em ~40% e desarmando
justamente o alerta que pega declaração exagerada.
"""
import re
from pathlib import Path

from services.base_reprodutiva import base_reprodutiva
from services.parecer_pdf import CHECAGEM_NAO_REALIZADA
from services.validacao_zootecnica import analisar_validacoes_zootecnicas

ROOT = Path(__file__).parents[1]
INDEX = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
VALIDACAO = (ROOT / "services" / "validacao_zootecnica.py").read_text(encoding="utf-8")

REBANHO = [40, 40, 40, 40, 60, 60, 80, 50, 200, 10]   # v[6]=80, v[8]=200


# ── Nascimentos esperados: só quem já pariu ──────────────────────────────────

def test_o_esperado_de_nascimentos_usa_so_as_matrizes():
    """Com v[6] dentro, o esperado ia a 182 e o alerta só passava de 209.

    Declarar 150 nascimentos numa base de 200 matrizes a 65% (esperado 130)
    é exagero de 15% e precisa alertar.
    """
    dados = {'taxa_natalidade': 65, 'nascimentos': 160}
    r = analisar_validacoes_zootecnicas(REBANHO, dados)
    codigos = {a['codigo'] for a in r['alertas']}
    assert 'nascimentos_incompativeis' in codigos, (
        'declaração 23% acima do esperado passou batido'
    )


def test_nascimentos_coerentes_nao_alertam():
    dados = {'taxa_natalidade': 65, 'nascimentos': 130}
    r = analisar_validacoes_zootecnicas(REBANHO, dados)
    assert 'nascimentos_incompativeis' not in {a['codigo'] for a in r['alertas']}


def test_a_validacao_nao_soma_as_coortes_a_mao():
    """Trava a fonte: quem mexer aqui tem que passar por base_reprodutiva."""
    assert 'v[6] + v[8]' not in VALIDACAO
    assert 'base_reprodutiva' in VALIDACAO


def test_o_esperado_bate_com_a_base_reprodutiva():
    esperado = base_reprodutiva(REBANHO).matrizes * 0.65
    # 1,15× é o gatilho do alerta — logo abaixo não alerta, logo acima alerta.
    abaixo = analisar_validacoes_zootecnicas(
        REBANHO, {'taxa_natalidade': 65, 'nascimentos': esperado * 1.10})
    acima = analisar_validacoes_zootecnicas(
        REBANHO, {'taxa_natalidade': 65, 'nascimentos': esperado * 1.20})
    assert 'nascimentos_incompativeis' not in {a['codigo'] for a in abaixo['alertas']}
    assert 'nascimentos_incompativeis' in {a['codigo'] for a in acima['alertas']}


# ── O que não foi conferido precisa aparecer ─────────────────────────────────

def test_sem_mortalidade_a_reconciliacao_do_rebanho_nao_roda():
    """Documenta a dependência que o rótulo da tela escondia."""
    dados = {'taxa_natalidade': 65, 'compras_reposicao': 30, 'bois_vendidos': 35}
    r = analisar_validacoes_zootecnicas(
        REBANHO, dados, projecao=[{'total': 500}])
    assert 'reconciliacao_mortalidade_ausente' in r['nao_avaliadas']


def test_com_mortalidade_a_reconciliacao_roda():
    dados = {'taxa_natalidade': 65, 'compras_reposicao': 30,
             'bois_vendidos': 35, 'mortalidade': 3}
    r = analisar_validacoes_zootecnicas(
        REBANHO, dados, projecao=[{'total': 500}])
    assert 'reconciliacao_mortalidade_ausente' not in r['nao_avaliadas']


def test_todo_codigo_de_nao_avaliada_tem_texto_no_pdf():
    """Nenhum slug interno pode vazar para um parecer que vai a comitê."""
    codigos = set(re.findall(r"nao_avaliadas\.append\('([a-z_]+)'\)", VALIDACAO))
    assert codigos, 'não encontrei os códigos na fonte'
    faltando = codigos - set(CHECAGEM_NAO_REALIZADA)
    assert not faltando, f'sem texto no PDF: {sorted(faltando)}'


def test_todo_codigo_de_nao_avaliada_tem_texto_na_tela():
    codigos = set(re.findall(r"nao_avaliadas\.append\('([a-z_]+)'\)", VALIDACAO))
    mapa = re.search(r"const CHECAGEM_PULADA=\{(.*?)\n\};", INDEX, re.S)
    assert mapa, 'mapa CHECAGEM_PULADA não encontrado no index.html'
    na_tela = set(re.findall(r"^\s{2}([a-z_]+):", mapa.group(1), re.M))
    faltando = codigos - na_tela
    assert not faltando, f'sem texto na tela: {sorted(faltando)}'


def test_a_tela_distingue_tudo_conferido_de_nada_conferido():
    """A frase antiga servia para os dois casos — era esse o problema."""
    assert 'Nenhum alerta zootécnico encontrado com os dados disponíveis' not in INDEX
    assert 'As checagens que puderam rodar não apontaram problema.' in INDEX
    assert 'Nenhum alerta zootécnico. Todas as checagens rodaram.' in INDEX
    assert 'renderChecagensPuladas(vz)' in INDEX
