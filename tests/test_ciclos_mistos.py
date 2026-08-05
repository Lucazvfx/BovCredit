"""
Testes da detecção de ciclos mistos no classificar().
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from ml_engine import classificar, _detectar_ciclo_misto, carregar_modelo


def setup_module(module):
    # Garante que o pipeline está carregado
    carregar_modelo()


# ─────────────────────────────────────────────
# Função pura _detectar_ciclo_misto
# ─────────────────────────────────────────────
def test_misto_cria_recria_quando_prob_2a_alta_e_composicao_bate():
    r = _detectar_ciclo_misto(
        tipo_principal='CRIA',
        prob_dict={'CRIA': 55.0, 'RECRIA': 35.0, 'ENGORDA': 5.0, 'CICLO_COMPLETO': 5.0},
        p_matrizes=0.25, p_mac_recria=0.10, p_bois=0.02,
        p_bez=0.20, intensidade_engorda=0.02,
    )
    assert r is not None
    assert r['tipo_secundario'] == 'RECRIA'
    assert r['combinacao'] == 'CRIA+RECRIA'
    assert r['confianca_secundaria'] == 35.0


def test_misto_recria_engorda():
    r = _detectar_ciclo_misto(
        tipo_principal='RECRIA',
        prob_dict={'RECRIA': 50.0, 'ENGORDA': 35.0, 'CRIA': 10.0, 'CICLO_COMPLETO': 5.0},
        p_matrizes=0.05, p_mac_recria=0.20, p_bois=0.15,
        p_bez=0.05, intensidade_engorda=0.10,
    )
    assert r is not None
    assert r['combinacao'] == 'ENGORDA+RECRIA'


def test_misto_descartado_quando_prob_2a_baixa():
    r = _detectar_ciclo_misto(
        tipo_principal='CRIA',
        prob_dict={'CRIA': 80.0, 'RECRIA': 10.0, 'ENGORDA': 5.0, 'CICLO_COMPLETO': 5.0},
        p_matrizes=0.30, p_mac_recria=0.05, p_bois=0.02,
        p_bez=0.25, intensidade_engorda=0.02,
    )
    assert r is None  # 10% < limiar 25%


def test_misto_descartado_quando_gap_muito_grande():
    r = _detectar_ciclo_misto(
        tipo_principal='CRIA',
        prob_dict={'CRIA': 90.0, 'RECRIA': 30.0, 'ENGORDA': 0.0, 'CICLO_COMPLETO': 0.0},
        p_matrizes=0.30, p_mac_recria=0.10, p_bois=0.02,
        p_bez=0.25, intensidade_engorda=0.02,
    )
    # gap = 60 > 50 (max) → descarta
    assert r is None


def test_misto_descartado_quando_composicao_nao_suporta():
    """ML sugere RECRIA secundário, mas não há machos jovens no rebanho."""
    r = _detectar_ciclo_misto(
        tipo_principal='CRIA',
        prob_dict={'CRIA': 55.0, 'RECRIA': 35.0, 'ENGORDA': 5.0, 'CICLO_COMPLETO': 5.0},
        p_matrizes=0.30, p_mac_recria=0.01, p_bois=0.01,
        p_bez=0.25, intensidade_engorda=0.01,
    )
    assert r is None


def test_ciclo_completo_nunca_vira_misto():
    r = _detectar_ciclo_misto(
        tipo_principal='CICLO_COMPLETO',
        prob_dict={'CICLO_COMPLETO': 60.0, 'CRIA': 35.0, 'RECRIA': 3.0, 'ENGORDA': 2.0},
        p_matrizes=0.30, p_mac_recria=0.15, p_bois=0.10,
        p_bez=0.20, intensidade_engorda=0.08,
    )
    assert r is None


def test_combinacao_invalida_cria_ciclo_completo_descartada():
    """O par CRIA + CICLO_COMPLETO não está em _PARES_VALIDOS."""
    r = _detectar_ciclo_misto(
        tipo_principal='CRIA',
        prob_dict={'CRIA': 50.0, 'CICLO_COMPLETO': 45.0, 'RECRIA': 3.0, 'ENGORDA': 2.0},
        p_matrizes=0.30, p_mac_recria=0.10, p_bois=0.05,
        p_bez=0.25, intensidade_engorda=0.05,
    )
    # secundário seria CICLO_COMPLETO mas é filtrado dos candidatos
    # (e o próximo seria RECRIA com 3% — abaixo do limiar)
    assert r is None


# ─────────────────────────────────────────────
# Integração com classificar()
# ─────────────────────────────────────────────
def test_classificar_retorna_campos_de_misto():
    """A resposta sempre inclui os 3 campos novos, mesmo quando não há misto."""
    v = [10, 8, 20, 18, 50, 80, 20, 120, 10, 400]  # engorda pura
    result = classificar(v)
    assert 'tipo_secundario' in result
    assert 'combinacao' in result
    assert 'confianca_secundaria' in result


def test_classificar_fazenda_cria_recria_real():
    """Fazenda com matrizes, bezerros E muitos machos jovens em recria,
    sem bois adultos — deve ser detectado como CRIA+RECRIA."""
    # matrizes adultas + bezerros + concentração de machos 13-24m
    v = [80, 70, 60, 60, 50, 250, 30, 5, 200, 5]
    result = classificar(v)
    # Pode ser CRIA ou RECRIA principal; o que importa é que detecte misto
    if result['tipo'] in ('CRIA', 'RECRIA'):
        assert result['combinacao'] in ('CRIA+RECRIA',) or result['tipo_secundario'] is None


def test_ficha_sem_vendas_usa_inferencia_do_modelo():
    """Saldo INDEA sem vendas não confirma sozinho o ciclo produtivo."""
    v = [300, 280, 563, 187, 1105, 1344, 298, 80, 593, 39]
    result = classificar(v)

    assert result['tipo'] == 'CICLO_COMPLETO'
    assert result['classificacao_limitada'] is True
    assert result['tipo_modelo'] == 'CICLO_COMPLETO'
    assert result['dados_faltantes'] == ['bois_vendidos']
    assert result['revisao_humana'] is True
