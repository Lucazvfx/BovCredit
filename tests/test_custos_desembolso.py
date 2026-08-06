from services.custos_desembolso import (
    custo_arroba_de_desembolso, preset_modalidade, PERFIL_DESEMBOLSO, COMPONENTES,
)


def test_conversao_desembolso_para_arroba():
    # 100 R$/cab/mês, rebanho com peso médio 15@ (1500@ / 100 cab)
    r = custo_arroba_de_desembolso(desembolso_cab_mes=100, arrobas_rebanho=1500, total_cabecas=100)
    assert abs(r - 100 * 12 / 15) < 1e-6  # 80 R$/@·ano


def test_conversao_rebanho_vazio_retorna_zero():
    assert custo_arroba_de_desembolso(100, 0, 0) == 0.0
    assert custo_arroba_de_desembolso(100, 1500, 0) == 0.0


def test_preset_recria_top_bate_com_a_tabela():
    p = preset_modalidade('RECRIA', 'top')
    assert set(p.keys()) == {c[0] for c in COMPONENTES}
    assert abs(sum(p.values()) - 77.40) < 0.01  # TOTAL RECRIA top (desagregado safra 24/25)


def test_preset_recria_engorda_legado_top():
    # Alias RECRIA_ENGORDA mantido para compatibilidade com dados históricos.
    p = preset_modalidade('RECRIA_ENGORDA', 'top')
    assert abs(sum(p.values()) - 167.28) < 0.01


def test_preset_cria_media_bate_total():
    p = preset_modalidade('CRIA', 'media')
    assert abs(sum(p.values()) - 90.88) < 0.01


def test_recria_e_engorda_sao_desagregados():
    # Desde safra 24/25 GEP Araguaia, RECRIA e ENGORDA têm presets próprios.
    r = preset_modalidade('RECRIA', 'media')
    e = preset_modalidade('ENGORDA', 'media')
    assert r != e
    assert abs(sum(r.values()) - 100.50) < 0.01
    assert abs(sum(e.values()) - 182.60) < 0.01


def test_modalidade_desconhecida_cai_em_ciclo_completo():
    assert preset_modalidade('QUALQUER', 'media') == preset_modalidade('CICLO_COMPLETO', 'media')
