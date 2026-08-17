from ml_engine import calcular_ano


def test_calcular_ano_precos_por_categoria():
    r = calcular_ano(
        matrizes=100, c0_femeas=20, c1_femeas=20, c0_machos=20, c1_machos=20,
        bois=5,
        nat_pct=0.75, desc_mat_pct=0.15, prop_boi=25, renov_boi_pct=0.2,
        venda_bez_pct=0.3, mort_pct=0.03, preco_arroba=320, custo_arroba=57,
        peso_boi=18, peso_vaca=14, peso_bezerra=7, peso_garrote=11,
        preco_boi_arr=330, preco_vaca_arr=300,
        preco_bezerra_cab=2700, preco_bezerro_cab=3000)
    # boi/vaca em R$/@ × peso; bezerra/bezerro em R$/cabeça (direto)
    esperado = (r['bois_vendidos'] * 18 * 330
                + r['descarte_matrizes'] * 14 * 300
                + r['bezerras_vendidas'] * 2700
                + r['machos_024_vendidos'] * 3000)
    assert abs(r['receita'] - esperado) < 1.0


def test_calcular_ano_fallback_preco_arroba_unico():
    # sem preços por categoria → preço da arroba único (retrocompatível)
    r = calcular_ano(
        matrizes=100, c0_femeas=20, c1_femeas=20, c0_machos=20, c1_machos=20,
        bois=5,
        nat_pct=0.75, desc_mat_pct=0.15, prop_boi=25, renov_boi_pct=0.2,
        venda_bez_pct=0.3, mort_pct=0.03, preco_arroba=320, custo_arroba=57,
        peso_boi=18, peso_vaca=14, peso_bezerra=7, peso_garrote=11)
    esperado = (r['bois_vendidos'] * 18 + r['descarte_matrizes'] * 14
                + r['bezerras_vendidas'] * 7 + r['machos_024_vendidos'] * 11) * 320
    assert abs(r['receita'] - esperado) < 1.0
