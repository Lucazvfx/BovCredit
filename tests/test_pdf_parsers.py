"""
Testes do módulo pdf_parsers.

Como não temos PDFs reais no repositório, testamos:
  - detecção de origem (IDARON / INDEA / GENERICO)
  - parser INDEA com texto sintético
  - parser IDARON com texto sintético (caminho 'linhas' fallback)
  - parser de tabela IDARON com listas de listas (sem pdfplumber)
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest
from pdf_parsers import (
    detectar_origem,
    parsear_indea,
    parsear_idaron,
    _parsear_tabela_bovinos,
    _animais_vazios,
    _para_valores,
    _adicionar,
    _sexo_da_linha,
    _faixa_de_celula,
    parsear_go_declaracao_web,
    parsear_adapec_to,
)
from services.mapeamento_fichas import load_mapeamento, buscar_mapeamento, mapear_animais


# ─────────────────────────────────────────────
# DETECÇÃO DE ORIGEM
# ─────────────────────────────────────────────
def test_detectar_origem_idaron_por_nome():
    assert detectar_origem("IDARON\nFormulário de Anotações") == 'IDARON'


def test_detectar_origem_idaron_por_agencia():
    assert detectar_origem(
        "AGÊNCIA DE DEFESA SANITÁRIA AGROSILVOPASTORIL\nDocumento"
    ) == 'IDARON'


def test_detectar_origem_idaron_por_rondonia_saldo():
    assert detectar_origem("RONDÔNIA — SALDO DO REBANHO") == 'IDARON'


def test_detectar_origem_indea_por_nome():
    assert detectar_origem("INDEA-MT\nSaldo da exploração") == 'INDEA'


def test_detectar_origem_indea_por_instituto():
    assert detectar_origem(
        "INSTITUTO DE DEFESA AGROPECUÁRIA\nSaldo atual da exploração"
    ) == 'INDEA'


def test_detectar_origem_generico():
    assert detectar_origem("Documento qualquer sem palavras-chave") == 'GENERICO'


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────
def test_animais_vazios_tem_10_chaves():
    a = _animais_vazios()
    assert len(a) == 10
    assert all(v == 0 for v in a.values())


def test_para_valores_ordem_correta():
    a = _animais_vazios()
    a['f00_F'] = 1; a['f00_M'] = 2
    a['f05_F'] = 3; a['f05_M'] = 4
    a['f13_F'] = 5; a['f13_M'] = 6
    a['f25_F'] = 7; a['f25_M'] = 8
    a['fac_F'] = 9; a['fac_M'] = 10
    assert _para_valores(a) == [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]


def test_adicionar_faixa_dividida_0_a_12():
    a = _animais_vazios()
    _adicionar(a, 'f00_12', 'M', 11)
    # 11 // 2 = 5; resto vai para f05
    assert a['f00_M'] == 5
    assert a['f05_M'] == 6


def test_adicionar_faixa_normal():
    a = _animais_vazios()
    _adicionar(a, 'f13', 'F', 50)
    assert a['f13_F'] == 50


def test_sexo_da_linha():
    assert _sexo_da_linha("BOVINO MACHO 13 A 24") == 'M'
    assert _sexo_da_linha("BOVINO FÊMEA ACIMA 36") == 'F'
    assert _sexo_da_linha("BOVINO FEMEA 5 A 12") == 'F'
    assert _sexo_da_linha("LINHA SEM SEXO") is None


def test_faixa_de_celula():
    assert _faixa_de_celula("13 A 24 MESES") == 'f13'
    assert _faixa_de_celula("25 A 36 MESES") == 'f25'
    assert _faixa_de_celula("ACIMA DE 36") == 'fac'
    assert _faixa_de_celula("0 A 06 MESES") == 'f00'
    assert _faixa_de_celula("07 A 12 MESES") == 'f05'
    assert _faixa_de_celula("0 A 12") == 'f00_12'  # faixa unificada (será dividida no _adicionar)
    assert _faixa_de_celula("XYZ") is None


def test_mapeamento_carrega_regras_do_xlsm_do_projeto():
    regras = load_mapeamento()

    assert len(regras) == 74
    assert regras['MT_DECLARACAO|FEMEA|00 A 04 MESES']['classificacao'] == 'Bezerra'
    assert regras['TO_DECLARACAO|MACHO|25 A 36 MESES']['classificacao'] == 'Garrote'


def test_buscar_mapeamento_normaliza_estado_sexo_e_faixa():
    regra = buscar_mapeamento('TO', 'macho', '25 a 36 meses')

    assert regra['chave'] == 'TO_DECLARACAO|MACHO|25 A 36 MESES'
    assert regra['classificacao'] == 'Garrote'


def test_mapear_animais_usa_faixa_0_a_12_do_xlsm():
    registros = mapear_animais({'f00_F': 10, 'f05_F': 20}, 'TO')

    bezerra = next(r for r in registros if r['classificacao'] == 'Bezerra')
    assert bezerra['quantidade'] == 30
    assert bezerra['chave'] == 'TO_DECLARACAO|FEMEA|0 A 12 MESES'


GO_DECLARACAO_WEB_REALISTA = """
Declaração Rebanho - 1/2026
Propriedade
Nome: FAZENDA ZERO III
Produtor
Nome: ELCIO BRUZA RIBEIRO
UF/Município: GO/São Miguel do Araguaia
CPF/CNPJ: 13511190878
DECLARAÇÃO REBANHO
Data: 26/05/2026 Tipo: Produtor Rural
Bovinos
Existentes 22 14 0 2199 0 60 1 23 2319
ANIMAIS BOVINOS INDIVIDUALIZADOS
EXISTENTES/VACINADOS MACHO EXISTENTES/VACINADOS FEMEA
Idade Total Idade Total
Até 1 mês 0 Até 1 mês 0
1 mês 1 1 mês 1
2 meses 3 2 meses 2
3 meses 8 3 meses 4
4 meses 5 4 meses 4
5 meses 3 5 meses 3
6 meses 1 6 meses 0
7 meses 1 7 meses 0
8 meses 0 8 meses 0
9 meses 0 9 meses 0
10 meses 0 10 meses 0
11 meses 0 11 meses 0
12 meses 0 12 meses 0
TOTAL 22 TOTAL 14
"""


TO_DECLARACAO_REALISTA = """
ADAPEC TOCANTINS
DECLARAÇÃO DE DADOS CADASTRAIS
Nome do Produtor MARCELA BERGAMASCHI PEREIRA LIMA
Documento 21862651841
Município Palmas
Grupo Animal Quantidade Animais Propriedade Codigo Situacao
Bovideos 687 FAZENDA TRES MENINAS 17213070396 Ativa
Saldo 435 0 252 687
VACINACOES: 3
Grupo Animal Quantidade Animais Propriedade Codigo Situacao
Bovideos 1886 BANANAL 17182041448 Ativa
Saldo 75 244 372 880 41 23 1 250 1886
VACINACOES: 21
"""


def test_parsear_go_declaracao_web_linha_existentes_e_meses():
    dados = parsear_go_declaracao_web(GO_DECLARACAO_WEB_REALISTA)

    assert dados['total'] == 2319
    assert dados['valores'] == [11, 17, 3, 5, 2199, 0, 60, 0, 23, 1]
    assert dados['fazenda'] == 'FAZENDA ZERO III'
    assert any(r['classificacao'] == 'Vaca' and r['quantidade'] == 23 for r in dados['mapeamento'])


def test_parsear_adapec_to_soma_varias_propriedades():
    dados = parsear_adapec_to(TO_DECLARACAO_REALISTA)

    assert dados['total'] == 2573
    assert dados['valores'] == [122, 254, 122, 256, 880, 624, 23, 41, 250, 1]
    assert [f['fazenda'] for f in dados['fazendas']] == [
        'FAZENDA TRES MENINAS', 'BANANAL'
    ]
    assert any(r['classificacao'] == 'Boi Gordo' and r['quantidade'] == 1 for r in dados['mapeamento'])


# ─────────────────────────────────────────────
# INDEA
# ─────────────────────────────────────────────
INDEA_TEXT = """
INSTITUTO DE DEFESA AGROPECUÁRIA
PROPRIEDADE: 12345-67 - FAZENDA SANTA RITA
MUNICÍPIO: RONDONÓPOLIS                       SIT. ATIVA
12345678901   JOÃO DA SILVA                  Endereço aqui
Data do saldo: 10/03/2026

BOVINO FÊMEA 00 A 04                                              120
BOVINO MACHO 00 A 04                                              115
BOVINO FÊMEA 05 A 12                                              200
BOVINO MACHO 05 A 12                                              180
BOVINO FÊMEA 13 A 24                                              300
BOVINO MACHO 13 A 24                                              250
BOVINO FÊMEA 25 A 36                                              150
BOVINO MACHO 25 A 36                                               80
BOVINO FÊMEA ACIMA                                                400
BOVINO MACHO ACIMA                                                 30
"""


def test_parsear_indea_extrai_animais():
    r = parsear_indea(INDEA_TEXT)
    assert r['valores'] == [120, 115, 200, 180, 300, 250, 150, 80, 400, 30]
    assert r['total'] == 1825


def test_parsear_indea_extrai_metadados():
    r = parsear_indea(INDEA_TEXT)
    assert 'SANTA RITA' in r['fazenda'].upper()
    assert r['cpf'] == '12345678901'
    assert 'JOÃO' in r['proprietario'].upper() or 'JOAO' in r['proprietario'].upper()
    assert r['data_saldo'] == '10/03/2026'


def test_parsear_indea_texto_vazio():
    r = parsear_indea("")
    assert r['total'] == 0
    assert r['valores'] == [0] * 10


def test_parsear_indea_ignora_qtd_invalida():
    txt = "BOVINO MACHO 13 A 24                                         9999999"
    r = parsear_indea(txt)
    # qtd > 500_000 deve ser descartada
    assert r['valores'][5] == 0


# ─────────────────────────────────────────────
# IDARON (caminho de texto, sem PDF)
# ─────────────────────────────────────────────
IDARON_TEXT = """
IDARON - AGÊNCIA DE DEFESA SANITÁRIA AGROSILVOPASTORIL DE RONDÔNIA
NOME DA PROPRIEDADE: FAZENDA BOA VISTA
MUNICÍPIO: ARIQUEMES / RO
IE: 123.456.789
CPF: 111.222.333-44 MARIA OLIVEIRA DOS SANTOS
Data: 15/04/2026

BOVINO FÊMEA 00 A 04                                                 50
BOVINO MACHO 00 A 04                                                 48
BOVINO FÊMEA 05 A 12                                                 80
BOVINO MACHO 05 A 12                                                 75
BOVINO FÊMEA 13 A 24                                                120
BOVINO MACHO 13 A 24                                                100
BOVINO FÊMEA 25 A 36                                                 60
BOVINO MACHO 25 A 36                                                 30
BOVINO FÊMEA ACIMA                                                  200
BOVINO MACHO ACIMA                                                   15
"""


def test_parsear_idaron_extrai_animais_via_texto():
    # sem pdf_path -> usa _parse_idaron_linhas
    r = parsear_idaron(IDARON_TEXT)
    assert r['total'] == 778
    assert r['valores'][8] == 200  # facF
    assert r['valores'][9] == 15   # facM


def test_parsear_idaron_extrai_metadados():
    r = parsear_idaron(IDARON_TEXT)
    assert 'BOA VISTA' in r['fazenda'].upper()
    assert 'ARIQUEMES' in r['municipio'].upper()
    # CPF é normalizado removendo pontuação
    assert r['cpf'] == '11122233344'
    assert 'MARIA' in r['proprietario'].upper()
    assert r['ie'] == '123.456.789'
    assert r['data_saldo'] == '15/04/2026'


def test_parsear_idaron_sem_dados():
    r = parsear_idaron("")
    assert r['total'] == 0


# ─────────────────────────────────────────────
# IDARON - parsing de tabela (entrada como list[list])
# ─────────────────────────────────────────────
def test_parsear_tabela_bovinos_fallback_alternado():
    """Sem células F/M explícitas: parser alterna F/M por ordem das colunas."""
    table = [
        ['13 A 24 MESES', '13 A 24 MESES', 'ACIMA DE 36', 'ACIMA DE 36'],
        ['100',           '80',            '200',          '15'],
    ]
    a = _parsear_tabela_bovinos(table)
    # Ordem alternada: 1ª col = F, 2ª = M, 3ª = F, 4ª = M
    assert a['f13_F'] == 100
    assert a['f13_M'] == 80
    assert a['fac_F'] == 200
    assert a['fac_M'] == 15


def test_parsear_tabela_bovinos_com_celulas_fm():
    """Layout com F/M em células próximas das faixas."""
    table = [
        ['',  '13 A 24 MESES', '13 A 24 MESES'],
        ['',  'F',             'M'],
        ['',  '120',           '100'],
    ]
    a = _parsear_tabela_bovinos(table)
    assert a['f13_F'] == 120
    assert a['f13_M'] == 100


def test_parsear_tabela_bovinos_vazia():
    assert _parsear_tabela_bovinos([]) == _animais_vazios()
    assert _parsear_tabela_bovinos(None) == _animais_vazios()
    assert _parsear_tabela_bovinos([['A']]) == _animais_vazios()


def test_parsear_tabela_bovinos_sem_faixa_reconhecida():
    table = [
        ['cabeçalho_qualquer', 'outra_coisa'],
        ['F', '10'],
    ]
    assert _parsear_tabela_bovinos(table) == _animais_vazios()


def test_parsear_tabela_bovinos_descarta_qtd_invalida():
    table = [
        ['', '13 A 24 MESES', '13 A 24 MESES'],
        ['F', '600000', '50'],
        ['M', '0', '999999'],
    ]
    a = _parsear_tabela_bovinos(table)
    # 600_000 e 999_999 ultrapassam o limite; só 50 deve sobreviver
    valores_validos = [v for v in a.values() if v > 0]
    assert all(v == 50 for v in valores_validos)
