from services.fichas_rebanho.base_reader import registros_do_parse
from services.fichas_rebanho.mapping_loader import load_mapping
from services.fichas_rebanho.validator import validar_registros


def test_carrega_mapeamento_real_do_xlsm():
    mapping = load_mapping()

    regra = mapping.lookup('MT_DECLARACAO', 'FEMEA', '13 A 24 MESES')

    assert regra is not None
    assert regra.classificacao == 'Bezerra Desmama'
    assert regra.chave == 'MT_DECLARACAO|FEMEA|13 A 24 MESES'


def test_converte_parse_em_registros_sem_perder_quantidade():
    dados = {
        'fazenda': 'Fazenda Teste',
        'animais': {
            'f00_F': 12, 'f05_F': 8, 'f13_F': 20, 'f25_F': 30, 'fac_F': 40,
            'f00_M': 10, 'f05_M': 6, 'f13_M': 18, 'f25_M': 25, 'fac_M': 35,
        },
        'total': 204,
    }

    registros = registros_do_parse(
        dados,
        estado='MT_DECLARACAO',
        arquivo='teste.pdf',
    )

    assert sum(r['quantidade'] for r in registros) == 204
    assert all(r['especie'] == 'BOVINO' for r in registros)
    assert all(r['status'] == 'Distribuído' for r in registros)


def test_validador_marca_quantidade_invalida_e_nao_descarta_linha():
    registros = [{
        'arquivo': 'teste.pdf',
        'estado': 'MT_DECLARACAO',
        'especie': 'BOVINO',
        'sexo': 'FEMEA',
        'estratificacao': '13 A 24 MESES',
        'quantidade': -2,
        'chave': 'MT_DECLARACAO|FEMEA|13 A 24 MESES',
        'status': 'Distribuído',
    }]

    resultado = validar_registros(registros)

    assert resultado['valido'] is False
    assert resultado['erros']
    assert resultado['registros'][0]['status'] == 'Revisão'
