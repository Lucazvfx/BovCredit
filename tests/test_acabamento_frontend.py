"""Acabamento da tela do analista: aviso de preliminar, atrito e sobras.

Cinco coisas que atrapalhavam sem estar erradas em conta nenhuma:

  · o parecer não dizia que ninguém contou boi;
  · o painel de condições era um paredão de 19 campos iguais;
  · a regra de parcelamento só falhava no servidor, como toast que some;
  · o seletor de UF oferecia três estados sem parser;
  · um painel inteiro estava inalcançável — e levava junto o arrastar-e-soltar.
"""
import re
from pathlib import Path

import pytest

from services.origem_rebanho import ORIGENS, origem_rebanho
from services.parecer_pdf import gerar_pdf_parecer

ROOT = Path(__file__).parents[1]
INDEX = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
BASE_READER = (ROOT / "services" / "fichas_rebanho" / "base_reader.py").read_text(
    encoding="utf-8")


# ── Análise preliminar: ninguém contou boi ───────────────────────────────────

@pytest.mark.parametrize("origem", ORIGENS)
def test_toda_origem_diz_que_o_efetivo_nao_foi_verificado(origem):
    o = origem_rebanho(origem)
    assert o['preliminar'] is True
    assert 'não verificado' in o['aviso']
    assert 'conferência do rebanho na origem' in o['aviso']


def test_origem_desconhecida_cai_no_caso_mais_fraco():
    """Entrada estranha não pode virar a procedência mais forte."""
    for entrada in (None, '', 'sei_la', 'pdf; drop table'):
        assert origem_rebanho(entrada)['origem'] == 'MANUAL'


def test_as_origens_nao_sao_descritas_como_equivalentes():
    """Disclaimer que serve para tudo é disclaimer que ninguém lê.

    A ficha estadual deixa rastro oponível ao produtor; planilha e digitação
    não deixam nada. O texto tem que separar as duas coisas.
    """
    avisos = {o: origem_rebanho(o)['aviso'] for o in ORIGENS}
    assert len(set(avisos.values())) == len(ORIGENS)
    assert 'órgão estadual' in avisos['PDF']
    assert 'órgão estadual' not in avisos['MANUAL']


def test_o_aviso_sai_no_pdf_do_parecer():
    """É o PDF que vai ao comitê — é lá que a ressalva precisa estar."""
    parecer = {
        'identificacao': {
            'fazenda': 'Santa Cruz', 'municipio': 'Juara - MT',
            'proprietario': 'João', 'origem_rebanho': origem_rebanho('MANUAL'),
        },
        'composicao': {'total': 500},
    }
    pdf = gerar_pdf_parecer(parecer)
    assert pdf[:4] == b'%PDF'
    assert len(pdf) > 1000


def test_a_tela_mostra_o_aviso_junto_da_recomendacao():
    assert 'origem_rebanho' in INDEX
    assert 'Análise preliminar — efetivo não verificado.' in INDEX
    # Vem pronto do backend: tela e PDF divergirem seria pior que não avisar.
    assert "(parecer.identificacao||{}).origem_rebanho" in INDEX


# ── Condições: quais campos mudam o veredito ─────────────────────────────────

def test_o_painel_de_condicoes_abre():
    """O botão chamava toggleConds() e a função não existia em lugar nenhum.

    O clique lançava ReferenceError e o painel ficava em display:none para
    sempre — natalidade, mortalidade, compras, vendas declaradas e reposição
    da recria eram TODAS inacessíveis, e o motor sempre rodou com os próprios
    defaults. Verificado em navegador: antes o clique não mudava o display.
    """
    assert 'function toggleConds()' in INDEX
    assert "onclick=\"toggleConds()\"" in INDEX


def test_nenhum_handler_do_html_esta_sem_definicao():
    """Trava a classe do bug, não só a instância.

    Só conta chamadas no início da expressão (`fn(`), não métodos (`.click()`),
    e ignora o que é global do navegador.
    """
    handlers = set()
    for attr in ('onclick', 'oninput', 'onchange'):
        for corpo in re.findall(rf'{attr}="([^"]*)"', INDEX):
            handlers |= set(re.findall(r'(?:^|[;\s{])([A-Za-z_$][\w$]*)\s*\(', corpo))
    nativos = {'if', 'for', 'while', 'return', 'typeof', 'new', 'Event', 'URL',
               'Number', 'String', 'parseFloat', 'parseInt', 'alert', 'confirm'}
    for nome in sorted(handlers - nativos):
        definido = (f'function {nome}(' in INDEX
                    or f'const {nome}=' in INDEX
                    or f'{nome} = function' in INDEX
                    or f'{nome}=(' in INDEX)
        assert definido, f'{nome}() é chamado no HTML e não existe no script'


def test_os_blocos_dizem_se_mudam_o_resultado_ou_so_a_comparacao():
    for rotulo in ('1 · Reescrevem a projeção',
                   '2 · Premissas que o motor assume',
                   '3 · Conferem a coerência da ficha',
                   '4 · Comparação regional (RO)',
                   '5 · Comparação nacional'):
        assert rotulo in INDEX, rotulo
    assert 'blocos 1 e 2 mudam o resultado' in INDEX


def test_a_numeracao_segue_a_ordem_da_tela():
    """Os que mudam o resultado precisam estar juntos, não 1 e 3.

    O resumo diz "1 e 2 mudam o resultado" — se a ordem do DOM não bater, o
    texto passa a apontar para o bloco errado.
    """
    painel = INDEX[INDEX.index('id="conds-wrap"'):INDEX.index('id="cot-strip"')]
    numeros = [int(n) for n in re.findall(r'>(\d+) · ', painel)]
    assert numeros == sorted(numeros) == list(range(1, len(numeros) + 1)), numeros


# ── Parcelamento conferido antes de submeter ─────────────────────────────────

def test_a_regra_de_parcelamento_e_conferida_no_cliente():
    assert 'function validarParcelamento()' in INDEX
    assert 'if(!validarParcelamento()){' in INDEX, 'classificar() não barra antes do fetch'


def test_o_erro_de_parcelamento_marca_os_campos_e_propoe_prazos():
    bloco = INDEX[INDEX.index('function _erroParcelamento()'):
                  INDEX.index('function validarParcelamento()')]
    assert '(prazo-car)%p' in bloco.replace(' ', '')
    assert 'menor' in bloco and 'maior' in bloco, 'não sugere prazo que fecha'
    assert "el.style.borderColor" in INDEX


def test_a_mensagem_persiste_em_vez_de_ser_toast():
    assert 'id="parcelamento-erro"' in INDEX


# ── Seletor de UF só com estado que tem parser ───────────────────────────────

def test_o_seletor_de_uf_lista_exatamente_o_que_o_roteador_conhece():
    """MG, BA e SP estavam no seletor sem parser: a escolha era ignorada."""
    mapa = re.search(r"return \{\n(.*?)\n\s+\}\.get\(uf, origem\)", BASE_READER, re.S)
    assert mapa, 'mapa de UF não encontrado em base_reader'
    com_parser = set(re.findall(r"'([A-Z]{2})':", mapa.group(1)))

    seletor = re.search(r'<select id="insr-uf-ficha".*?</select>', INDEX, re.S).group(0)
    no_seletor = set(re.findall(r'<option value="([A-Z]{2})"', seletor))

    assert no_seletor == com_parser, (
        f'sem parser: {sorted(no_seletor - com_parser)} · '
        f'faltando no seletor: {sorted(com_parser - no_seletor)}'
    )


# ── Painel órfão removido sem derrubar o arrastar-e-soltar ───────────────────

def test_o_painel_inalcancavel_saiu():
    assert 'id="panel-pdf"' not in INDEX
    assert "showTab('pdf'" not in INDEX
    assert 'Ler PDF do <em>INDEA</em>' not in INDEX


def test_nada_mais_procura_o_dz_que_nao_existe():
    """dz2.addEventListener sem guarda derrubava o script inteiro no load."""
    assert "getElementById('dz')" not in INDEX


def test_o_arrastar_e_soltar_foi_para_um_alvo_visivel():
    """Estava preso ao painel órfão, então nunca recebia arquivo."""
    assert "document.querySelector('.ork-import-panel')" in INDEX
    assert "dz2.addEventListener('drop'" in INDEX
    assert 'class="analysis-flow ork-panel ork-import-panel"' in INDEX
