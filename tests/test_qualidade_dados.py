from services.qualidade_dados import analisar_qualidade_dados


def test_classifica_documento_usuario_estimativa_e_ausente():
    r = analisar_qualidade_dados(
        [300, 280, 563, 187, 1105, 1344, 298, 80, 593, 39],
        {'taxa_natalidade_pct': 72, 'bois_vendidos': 0},
    )

    assert r['campos']['taxa_natalidade_pct']['origem'] == 'usuario'
    assert r['campos']['bois_vendidos']['origem'] == 'usuario'
    assert r['campos']['mortalidade_pct']['origem'] == 'ausente'
    assert r['campos']['peso_medio_kg']['origem'] == 'estimativa'
    assert r['resultado_financeiro_estimado'] is True
