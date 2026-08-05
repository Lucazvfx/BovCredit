from services.explicacao_classificacao import montar_explicacao_classificacao


def test_explicacao_preserva_modelo_regra_e_fatores():
    r = montar_explicacao_classificacao(
        {'tipo': 'CICLO_COMPLETO', 'tipo_modelo': 'CICLO_COMPLETO',
         'confianca': 56.9, 'confianca_ml': 56.9,
         'probabilidades': {'CICLO_COMPLETO': 56.9},
         'origem_decisao': 'ml', 'regra_aplicada': None,
         'explicacao': ['ML confirmou: CICLO_COMPLETO'],
         'dados_faltantes': ['bois_vendidos'], 'revisao_humana': True},
        {'total': 4789, 'fem_adultas': 2859, 'matrizes': 891},
    )

    assert r['ciclo_final'] == 'CICLO_COMPLETO'
    assert r['decisao'] == 'modelo'
    assert r['dados_faltantes'] == ['bois_vendidos']
    assert any(f['campo'] == 'matrizes' for f in r['fatores'])
