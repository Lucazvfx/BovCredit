from services.qualidade_dados import analisar_qualidade_dados


def test_qualidade_reconhece_dados_produtivos_declarados():
    qualidade = analisar_qualidade_dados(
        [10, 10, 8, 8, 6, 6, 30, 2, 40, 3],
        {
            'peso_medio_kg': 420,
            'peso_desmama_kg': 210,
            'vendas_anuais': 35,
            'compras_reposicao': 30,
        },
    )

    campos = qualidade['campos']
    assert campos['peso_medio_kg']['origem'] == 'usuario'
    assert campos['peso_desmama_kg']['origem'] == 'usuario'
    assert campos['vendas_anuais']['origem'] == 'usuario'
    assert campos['compras_reposicao']['origem'] == 'usuario'
