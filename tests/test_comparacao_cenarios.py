from ml_engine import comparar_cenarios


def test_comparacao_tem_quatro_cenarios_e_mesmo_rebanho():
    r = comparar_cenarios(
        [300, 280, 563, 187, 1105, 1344, 298, 80, 593, 39],
        'CICLO_COMPLETO',
    )

    assert [x['id'] for x in r['cenarios']] == [
        'base_estimado', 'conservador', 'provavel', 'otimista']
    assert {x['anos'][0]['total_inicial'] for x in r['cenarios']} == {4789}
    assert all('acumulado' in x and 'premissas' in x for x in r['cenarios'])
