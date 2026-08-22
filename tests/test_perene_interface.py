"""A tela da lavoura perene existe e chega até a análise.

Sem interface, o módulo agrícola só era alcançável por `curl` — o que quer
dizer que ninguém que faz o trabalho conseguia usar. Estes testes travam o
caminho: o item no menu, o painel, os handlers e as duas conversões que, se
sumirem, produzem número errado em silêncio.
"""
import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).parents[1]
INDEX = (RAIZ / 'templates' / 'index.html').read_text(encoding='utf-8')
SIDEBAR = (RAIZ / 'templates' / 'partials' / 'fields_sidebar.html').read_text(
    encoding='utf-8')


# ── O caminho até a tela ────────────────────────────────────────────────────

def test_o_menu_lateral_leva_a_lavoura_perene():
    """O menu lateral é a navegação real; a barra de abas é acessibilidade."""
    assert 'data-ork-nav="perene"' in SIDEBAR
    assert "showTab('perene', this)" in SIDEBAR


def test_o_menu_do_celular_tambem_leva():
    """O celular tem menu próprio. Só o lateral deixaria a tela inalcançável lá."""
    mobile = (RAIZ / 'templates' / 'partials' / 'fields_mobile_nav.html').read_text(
        encoding='utf-8')

    assert 'data-ork-nav="perene"' in mobile


def test_o_painel_existe_e_tem_aba_correspondente():
    assert 'id="panel-perene"' in INDEX
    assert 'aria-controls="panel-perene"' in INDEX


def test_o_mapa_de_indices_acompanha_a_ordem_dos_botoes():
    """showTab cai no índice quando não recebe botão. Fora de ordem, abre outra aba."""
    mapa = re.search(r'const idx=\{([^}]+)\}', INDEX).group(1)
    ordem_mapa = [par.split(':')[0] for par in mapa.split(',')]
    ordem_dom = re.findall(r'aria-controls="panel-([a-z]+)"', INDEX)

    assert ordem_mapa == ordem_dom


# ── Os handlers ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize('funcao', [
    'pereneImportar', 'pereneAnalisar', 'perenePDF',
])
def test_todo_handler_da_tela_tem_funcao(funcao):
    assert f'function {funcao}' in INDEX or f'async function {funcao}' in INDEX
    assert f'{funcao}(' in INDEX


# ── As conversões que erram em silêncio ─────────────────────────────────────

def test_a_tela_manda_juros_como_fracao():
    """A tela pede % e a API recebe fração.

    Mandar 10,5 no lugar de 0,105 devolve serviço de dívida na casa dos
    bilhões — calculado com toda a seriedade, sem um aviso na tela.
    """
    trecho = INDEX[INDEX.index('_prMontarPayload'):]
    assert "juros_aa:(+document.getElementById('pr-juros').value||0)/100" in trecho


def test_o_analista_ve_o_que_falta_na_ficha_sem_ser_bloqueado():
    """Ficha meio preenchida é o caso comum; bloquear esconderia o resto."""
    assert 'Falta preencher na ficha' in INDEX
    assert 'data.completo' in INDEX


def test_a_tela_avisa_quando_a_analise_esta_incompleta():
    assert 'Análise incompleta' in INDEX


def test_a_secao_do_menu_e_agricola():
    """"Agrícola" é a casa; lavoura perene é o primeiro morador dela."""
    assert '<span class="ork-nav__label">Agrícola</span>' in SIDEBAR
    assert '<span>Lavoura perene</span>' in SIDEBAR


def test_os_campos_de_credito_tem_dica_curta():
    """Tooltip explica o campo; a leitura do resultado é que sai do dado."""
    painel = INDEX[INDEX.index('id="panel-perene"'):INDEX.index('id="panel-ajuda"')]
    for campo in ('pr-prazo', 'pr-juros', 'pr-sistema', 'pr-periodicidade'):
        trecho = painel[:painel.index(f'id="{campo}"')]
        assert 'title="' in trecho.rsplit('<div class="field">', 1)[1]


def test_a_leitura_da_analise_aparece_na_tela():
    assert 'Leitura da Análise' in INDEX
    assert 'd.dicas' in INDEX


def test_a_tela_explica_o_ano_critico():
    """O número sozinho não diz por que o aperto não cai no ano 1."""
    assert 'ano mais apertado do contrato' in INDEX
    assert 'carga alta e baixa' in INDEX


# ── Tabelas em tela estreita ────────────────────────────────────────────────

def test_as_tabelas_do_painel_rolam_dentro_do_proprio_container():
    """No celular a tabela é mais larga que a tela; quem rola é ela, não a página."""
    painel = INDEX[INDEX.index('id="panel-perene"'):INDEX.index('id="panel-ajuda"')]
    for tabela in re.finditer(r'<table class="ytbl"', painel):
        antes = painel[max(0, tabela.start() - 120):tabela.start()]
        assert 'overflow-x:auto' in antes
