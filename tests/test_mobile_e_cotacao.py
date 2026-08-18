"""Celular: cotação visível e tela que não samba.

Duas queixas de uso real. A segunda ("o layout fica sambando") tinha três
causas somadas, todas medidas em iPhone 13 (390px) antes de mexer:

  · o cabeçalho tinha ALTURA FIXA de 52px; qualquer quebra de linha no grupo
    da direita transbordava para cima do ticker de notícias;
  · as etiquetas "Bezerra Desmama" e "Boi Gordo" quebravam em duas linhas e
    deixavam a tabela com linhas de 76, 102, 76 e 89px;
  · o aviso de desembolso aparecia duas vezes (erro meu ao restaurar o
    arquivo depois de um git checkout indevido).

E a cotação simplesmente não existia no celular: `#hdr-boi,#hdr-vaca` eram
`display:none`, e a faixa de cotações falhava em silêncio quando a API não
respondia.
"""
import re
from pathlib import Path

ROOT = Path(__file__).parents[1]
INDEX = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")


def _bloco_mobile() -> str:
    """Todos os @media(max-width:600px) do index.html, concatenados.

    São três blocos separados; pegar só o primeiro daria falso negativo.
    """
    partes, pos = [], 0
    while True:
        i = INDEX.find('@media(max-width:600px)', pos)
        if i < 0:
            break
        prof, fim = 0, i
        for j in range(INDEX.index('{', i), len(INDEX)):
            if INDEX[j] == '{':
                prof += 1
            elif INDEX[j] == '}':
                prof -= 1
                if prof == 0:
                    fim = j
                    break
        partes.append(INDEX[i:fim])
        pos = fim
    assert partes, 'nenhum bloco mobile encontrado'
    return '\n'.join(partes)


MOBILE = _bloco_mobile()


# ── A cotação aparece no celular ─────────────────────────────────────────────

def test_a_cotacao_do_boi_nao_e_escondida_no_celular():
    """Era o único dado ao vivo da tela, e sumia justamente onde há menos espaço."""
    assert '#hdr-boi,#hdr-vaca{display:none}' not in MOBILE
    assert '#hdr-vaca{display:none}' in MOBILE, 'a vaca sai; o boi fica'
    assert '#hdr-boi{' in MOBILE


def test_nao_existe_cotacao_inventada():
    """`_COTACOES_FALLBACK = {boi:0, vaca:0}` escrevia "Boi: 0.00 R$" na falha.

    Zero apresentado como preço é pior que ausência: quem olha rápido lê um
    número. E o toast dizia "usando última cotação conhecida", que não existia.
    """
    # A constante some; a única menção que resta é o comentário que explica
    # por que ela saiu — remover isso apagaria o motivo.
    assert 'const _COTACOES_FALLBACK' not in INDEX
    assert '_fmtValor' not in INDEX
    assert 'Usando última cotação conhecida' not in INDEX


def test_sem_cotacao_a_tela_diz_que_nao_sabe():
    assert 'function _fmtArroba(' in INDEX
    # zero e negativo viram travessão, não "R$ 0/@"
    assert "n > 0 ?" in INDEX and "'—'" in INDEX
    assert 'sem-cotacao' in INDEX


def test_a_faixa_de_cotacoes_nao_falha_calada():
    """Antes era um `return` mudo e três travessões sem explicação."""
    assert 'function _avisarCotacaoIndisponivel()' in INDEX
    assert 'if(!d || !d.ok){ _avisarCotacaoIndisponivel(); return; }' in INDEX
    assert 'Cotação indisponível agora' in INDEX


def test_a_falha_nao_preenche_os_campos_com_preco_velho():
    """Avaliar rebanho por preço que ninguém viu é pior que não avaliar."""
    bloco = INDEX[INDEX.index('function _avisarCotacaoIndisponivel()'):]
    bloco = bloco[:bloco.index('\n}')]
    for campo in ("cot-boi", "cot-vaca", "cot-bezerro", "s-preco-arr"):
        assert campo not in bloco, f'{campo} preenchido a partir de uma falha'


# ── O cabeçalho não transborda ───────────────────────────────────────────────

def test_o_cabecalho_cresce_em_vez_de_vazar():
    """height:52px fixo fazia o "Marca" pousar em cima do ticker."""
    assert 'header{padding:0 14px;height:52px}' not in MOBILE
    assert 'min-height:52px' in MOBILE


def test_o_seletor_de_empresa_cede_espaco_aos_vizinhos():
    """Cotação e Marca têm largura própria; quem encolhe é o seletor."""
    regra = re.search(r'#empresa-ativa-select\{([^}]*)\}', MOBILE).group(1)
    assert 'flex:1 1 auto' in regra
    assert 'min-width:0' in regra


# ── A tabela não samba ───────────────────────────────────────────────────────

def test_cada_campo_do_rebanho_diz_de_que_sexo_e():
    """As etiquetas empilham e o cabeçalho "Fêmeas|Machos" rola para fora.

    Sem marcador na célula, o analista digita sem saber qual coluna é qual.
    """
    assert '<span class="sexo-cel" aria-hidden="true">♀</span>' in INDEX
    assert '<span class="sexo-cel" aria-hidden="true">♂</span>' in INDEX
    assert '.sexo-cel{display:none}' in INDEX, 'no desktop seria repetição'
    assert '.sexo-cel{display:block' in MOBILE


def test_os_campos_tem_rotulo_acessivel():
    """O símbolo é aria-hidden; quem lê por leitor de tela precisa do nome."""
    assert 'aria-label="${f.lF} — ${f.l}"' in INDEX
    assert 'aria-label="${f.lM} — ${f.l}"' in INDEX


def test_as_etiquetas_nao_quebram_linha():
    """Alturas medidas antes: 76, 102, 76, 89. Depois: 76 nas quatro."""
    regra = re.search(r'\.itbl td:first-child \.fc\{([^}]*)\}', MOBILE).group(1)
    assert 'white-space:nowrap' in regra
    assert 'text-overflow:ellipsis' in regra


def test_o_nome_completo_sobrevive_ao_truncamento():
    assert 'title="${f.lF} — ${f.l}"' in INDEX
    assert 'title="${f.lM} — ${f.l}"' in INDEX


# ── Regressão do meu erro de restauração ─────────────────────────────────────

def test_o_aviso_de_desembolso_aparece_uma_vez_so():
    assert INDEX.count('Usa o desembolso padrão (GEP médio)') == 1


# ── Fundo decorativo não pode brigar com o texto ─────────────────────────────

CSS_CAMPOS = (ROOT / "static" / "orkavyn-fields.css").read_text(encoding="utf-8")


def _blocos(css: str, consulta: str) -> str:
    """Concatena TODOS os @media com esta consulta.

    Há mais de um bloco por breakpoint no arquivo; pegar só o primeiro dá
    falso negativo — já me pegou duas vezes.
    """
    partes, pos = [], 0
    while True:
        i = css.find(consulta, pos)
        if i < 0:
            break
        prof, fim = 0, i
        for j in range(css.index('{', i), len(css)):
            if css[j] == '{':
                prof += 1
            elif css[j] == '}':
                prof -= 1
                if prof == 0:
                    fim = j
                    break
        partes.append(css[i:fim])
        pos = fim
    assert partes, f'nenhum bloco {consulta}'
    return '\n'.join(partes)


def test_a_foto_de_fundo_recua_no_celular():
    """`center / cover` numa viewport estreita corta a foto e joga um borrão
    claro atrás de "Inserir dados do rebanho".

    .ptitle e .psub ficam FORA de card, lidos direto sobre a textura. Medido
    em 390px alternando só a opacidade no mesmo recorte: 27 KB de PNG com a
    foto a 0.12 contra 9 KB sem ela.
    """
    regra = _blocos(CSS_CAMPOS, '@media (max-width: 480px)')
    op = re.search(r'#bg-rebanho \{ opacity: ([\d.]+); \}', regra)
    assert op, 'regra do fundo sumiu do bloco de celular'
    assert float(op.group(1)) <= 0.05, f'fundo ainda forte demais: {op.group(1)}'


def test_a_foto_continua_inteira_na_tela_grande():
    """Lá há respiro e o texto quase sempre cai sobre card."""
    base = re.search(
        r'\.ork-dashboard-surface #bg-rebanho \{(.*?)\}', CSS_CAMPOS, re.S).group(1)
    assert 'opacity: 0.12' in base


# ── A barra de abas antiga já está aposentada ────────────────────────────────

def test_a_barra_de_abas_antiga_e_so_para_leitor_de_tela():
    """Documenta o que eu tinha afirmado errado: não há duas navegações visíveis.

    `.ork-legacy-tabs` usa o padrão sr-only (1x1 + clip) com !important, e o
    arquivo carrega depois do <style> do template. A barra fica no DOM pelos
    papéis ARIA e porque showTab consulta a classe `tab-locked` dela.
    """
    regra = re.search(r'\.ork-legacy-tabs \{(.*?)\}', CSS_CAMPOS, re.S).group(1)
    assert 'position: absolute !important' in regra
    assert 'clip: rect(0, 0, 0, 0) !important' in regra
    # o JS continua dependendo da classe, então ela não pode simplesmente sair
    assert "querySelector(`.tab-btn[aria-controls=" in INDEX
    assert 'tab-locked' in INDEX
