import pytest

from services.fichas_rebanho.base_reader import registros_do_parse
from services.fichas_rebanho.mapping_loader import load_mapping
from services.fichas_rebanho.reader_go_ir import dados_go_ir


@pytest.mark.parametrize('modelo', [
    'RO_DECLARACAO', 'PA_DECLARACAO', 'MT_DECLARACAO',
    'GO_DECLARACAO', 'GO IR', 'MA', 'TO_DECLARACAO', 'MS',
])
def test_mapeamento_estadual_tem_femea_macho_e_faixas(modelo):
    mapping = load_mapping()
    dados = {
        'fazenda': 'Teste',
        'animais': {
            'f00_F': 1, 'f05_F': 2, 'f13_F': 3, 'f25_F': 4, 'fac_F': 5,
            'f00_M': 6, 'f05_M': 7, 'f13_M': 8, 'f25_M': 9, 'fac_M': 10,
        },
    }

    registros = registros_do_parse(
        dados, estado=modelo, modelo=modelo, mapping=mapping)

    assert registros
    assert {r['sexo'] for r in registros} == {'FEMEA', 'MACHO'}
    assert all(r['status'] == 'Distribuído' for r in registros)
    assert sum(r['quantidade'] for r in registros) == 55


def test_go_ir_exige_o_total_da_ficha():
    dados = dados_go_ir(
        'Inscricao estadual 123456789 '
        '1 2 3 4 5 6 7 8 36'
    )

    assert len(dados) == 1
    assert dados[0]['codigo_propriedade'] == '123456789'
    assert dados[0]['total'] == 36
