from services.parametros_zootecnicos import (
    NATALIDADE_PCT, PRENHEZ_PCT, DESMAME_PCT, MORTALIDADE_PCT,
    RENDIMENTO_CARCACA_PCT, DESFRUTE_PCT, peso_arroba_carcaca,
    PESO_BOI_ARR, PESO_VACA_ARR, PESO_GARROTE_ARR, PESO_BEZERRA_ARR,
    PESO_JOVEM_F_ARR, PESO_JOVEM_M_ARR,
    PESO_VIVO_KG, RENDIMENTO_ABATE, RENDIMENTO_ABATE_BOI, midpoint,
)


def test_taxas_sao_ponto_medio_do_benchmark():
    # NATALIDADE_PCT é a exceção deliberada à regra do ponto médio: o benchmark
    # nacional é 55–75 (meio 65), mas o módulo adota 70% como valor recomendado
    # — ver comentário em services/parametros_zootecnicos.py.
    # ATENÇÃO: 70% é MAIS OTIMISTA que o ponto médio (mais bezerros → mais
    # receita → DSCR maior). Revisar se o objetivo for projeção conservadora.
    assert NATALIDADE_PCT == 70.0
    assert midpoint(55, 75) == 65.0
    # Prenhez segue o valor de PROJEÇÃO do material de treinamento (70–75%,
    # piso da faixa), não o ponto médio das faixas de mercado (50–75 → 62,5).
    assert PRENHEZ_PCT == 70.0
    assert DESFRUTE_PCT['CICLO_COMPLETO'] == 30.0
    assert DESFRUTE_PCT['ENGORDA'] == 100.0
    assert MORTALIDADE_PCT == 3.0 and DESMAME_PCT == 82.0
    assert RENDIMENTO_CARCACA_PCT == 52.0


def test_conversao_peso_arroba_carcaca():
    assert peso_arroba_carcaca(540, 0.50) == 18.0
    assert peso_arroba_carcaca(210, 0.50) == 7.0


def test_pesos_derivam_de_gep_araguaia():
    """Pesos GEP 24/25: boi 560kg×55%, vaca 460kg×50%, garrote 320kg×50%, bezerra 180kg×50%."""
    assert PESO_BOI_ARR  == PESO_VIVO_KG['boi']     * RENDIMENTO_ABATE_BOI / 15  # 20.5333…
    assert PESO_VACA_ARR == PESO_VIVO_KG['vaca']    * RENDIMENTO_ABATE     / 15  # 15.3333…
    assert round(PESO_BOI_ARR, 2)     == 20.53
    assert round(PESO_VACA_ARR, 2)    == 15.33
    assert round(PESO_GARROTE_ARR, 2) == 10.67
    assert round(PESO_BEZERRA_ARR, 2) == 6.00


def test_pesos_jovens_sao_media_das_subfaixas():
    """PESO_JOVEM_F = média(bezerra 6@, novilha 9.33@) = 7.67; M = média(bezerro 6.67@, garrote 10.67@) = 8.67."""
    assert round(PESO_JOVEM_F_ARR, 2) == 7.67
    assert round(PESO_JOVEM_M_ARR, 2) == 8.67
