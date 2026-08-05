from services.validacao_zootecnica import analisar_validacoes_zootecnicas


def test_vendas_acima_do_estoque_geram_alerta():
    r = analisar_validacoes_zootecnicas(
        [10, 10, 8, 8, 6, 6, 30, 2, 40, 3],
        {'bois_vendidos': 500},
    )

    a = next(x for x in r['alertas'] if x['codigo'] == 'vendas_acima_estoque')
    assert a['severidade'] == 'erro'
    assert '500' in a['evidencia']


def test_dado_ausente_nao_vira_alerta_falso():
    r = analisar_validacoes_zootecnicas(
        [300, 280, 563, 187, 1105, 1344, 298, 80, 593, 39], {})
    assert 'mortalidade_ausente' in r['nao_avaliadas']
