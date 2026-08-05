from ml_engine import carregar_modelo, classificar, comparar_cenarios
from services.qualidade_dados import analisar_qualidade_dados


def setup_module():
    carregar_modelo()


CASOS = {
    '400_cabecas': [40, 40, 40, 40, 40, 50, 30, 25, 90, 5],
    '5837_cabecas': [500, 500, 500, 500, 900, 800, 1000, 300, 800, 37],
    'indea_4789': [300, 280, 563, 187, 1105, 1344, 298, 80, 593, 39],
}


def test_casos_reais_mantem_totais_independentes():
    assert {nome: sum(v) for nome, v in CASOS.items()} == {
        '400_cabecas': 400,
        '5837_cabecas': 5837,
        'indea_4789': 4789,
    }
    for v in CASOS.values():
        r = comparar_cenarios(v, 'CICLO_COMPLETO')
        assert {x['premissas_comuns']['total_inicial']
                for x in [r]} == {sum(v)}
        assert {x['anos'][0]['total_inicial'] for x in r['cenarios']} == {sum(v)}


def test_indea_sem_vendas_fica_limitada_sem_virar_zero():
    v = CASOS['indea_4789']
    r = classificar(v)
    q = analisar_qualidade_dados(v, {})
    assert r['tipo'] == 'CICLO_COMPLETO'
    assert r['classificacao_limitada'] is True
    assert r['dados_faltantes'] == ['bois_vendidos']
    assert q['campos']['bois_vendidos']['origem'] == 'ausente'
    assert q['campos']['bois_vendidos']['valor'] is None
