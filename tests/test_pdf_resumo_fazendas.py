from pdf_parsers import detectar_origem, parsear_resumo_fazendas
from services.fichas_rebanho.base_reader import registros_do_parse


TEXTO = '''Fazenda Município Situação Macho 0-12 Fêmea 0-12 Macho 13-24
FAZENDA TESTE UM Morrinhos Ativo 0 127 0
FAZENDA TESTE DOIS Buriti Alegre Ativo 0 39 0
FAZENDA TESTE TRES Buriti Alegre Ativo 241 201 1
FAZENDA TESTE QUATRO Buriti Alegre Ativo 0 0 0
FAZENDA TESTE CINCO Morrinhos Ativo 151 0 376
FAZENDA TESTE SEIS Morrinhos Ativo 0 0 0
FAZENDA TESTE SETE Buriti Alegre Inativo 0 0 0
TESTE OITO Morrinhos Inativo 0 0 0
392 367 377
Fêmea 13-24 Macho 25-36 Fêmea 25-36 Macho >36 Fêmea >36 Total Bovinos
90 0 59 0 0 276
47 0 180 0 0 266
35 6 133 7 954 1578
0 0 0 0 0 0
0 4 0 0 0 531
0 0 153 0 0 153
0 0 0 0 0 0
0 0 0 0 0 0
172 10 525 7 954 2804'''


def test_detecta_resumo_de_rebanho_por_fazenda():
    assert detectar_origem(TEXTO) == 'RESUMO_FAZENDAS'


def test_le_fazendas_e_preserva_total_agregado():
    dados = parsear_resumo_fazendas(TEXTO)

    assert len(dados['fazendas']) == 8
    assert dados['fazendas'][0]['fazenda'] == 'FAZENDA TESTE UM'
    assert dados['fazendas'][0]['municipio'] == 'Morrinhos'
    assert dados['fazendas'][0]['total'] == 276
    assert dados['fazendas'][2]['total'] == 1578
    assert dados['total'] == 2804
    assert sum(dados['valores']) == 2804


def test_resumo_de_goias_distribui_as_linhas_no_mapeamento():
    dados = parsear_resumo_fazendas(TEXTO)
    registros = registros_do_parse(dados, 'RESUMO_FAZENDAS', modelo='RESUMO_FAZENDAS')

    assert all(item['status'] != 'RevisÃ£o' for item in registros)
    assert sum(item['quantidade'] for item in registros) == 2804
