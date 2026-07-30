"""
Casos resolvidos do material "Análise de Crédito na Pecuária Bovina".

Estes são os ÚNICOS casos rotulados por especialista que o projeto possui —
todo o restante do conjunto de treino é sintético. Servem como conjunto de
validação fixo do classificador de ciclo e da detecção de compra de animais.

Mapeamento de faixas etárias
----------------------------
O material estratifica em 4 faixas (0–12, 13–24, 25–36, +36 meses), enquanto o
sistema usa 5 (0–4, 5–12, 13–24, 25–36, +36). A coorte de 0–12 do material é
dividida entre as duas primeiras faixas do sistema na proporção 45/55, que é a
distribuição etária típica de uma coorte anual de nascimentos.

Fonte: Sónia Morais Romeiro Mendes, "Análise de Crédito na Pecuária Bovina".
"""
import pytest

from ml_engine import classificar, carregar_modelo
from services.consistencia_rebanho import estimar_compra_animais


@pytest.fixture(scope='module', autouse=True)
def _modelo():
    carregar_modelo()


def _mapear(m0_12, f0_12, m13_24, f13_24, m25_36, f25_36, m36, f36):
    """Converte a ficha de 4 faixas do material no vetor de 10 do sistema."""
    return [
        round(f0_12 * 0.45), round(m0_12 * 0.45),   # f00F, f00M  (0–4m)
        round(f0_12 * 0.55), round(m0_12 * 0.55),   # f05F, f05M  (5–12m)
        f13_24, m13_24,                              # f13F, f13M
        f25_36, m25_36,                              # f25F, f25M
        f36, m36,                                    # facF, facM
    ]


# (nome, ficha do material, ciclo esperado, desfrute do material)
CASOS = [
    ('slide 7 — Ciclo Completo (1.779 cab)',
     _mapear(140, 356, 41, 290, 110, 230, 98, 514), 'CICLO_COMPLETO', 43.1),
    ('slide 8 — Cria pura (493 cab)',
     _mapear(90, 92, 8, 30, 5, 10, 8, 250), 'CRIA', 48.3),
    ('slide 10 — Cria+Recria, caso real PA (1.061 cab)',
     _mapear(411, 145, 15, 142, 44, 31, 17, 256), 'CRIA_RECRIA', 30.6),
    ('slide 12 — Recria (1.230 cab)',
     _mapear(80, 70, 300, 280, 220, 180, 40, 60), 'RECRIA', 59.9),
    ('slide 13 — Recria/Engorda, caso real MT (10.302 cab)',
     _mapear(847, 0, 2444, 394, 6211, 286, 21, 99), 'RECRIA_ENGORDA', 91.8),
    ('slide 14 — Engorda intensiva (1.000 cab)',
     _mapear(0, 0, 850, 50, 100, 0, 0, 0), 'ENGORDA', 95.0),
]


@pytest.mark.parametrize('nome,v,esperado,_desfrute', CASOS)
def test_classificador_acerta_caso_do_material(nome, v, esperado, _desfrute):
    """O ciclo detectado precisa bater com o enquadramento do especialista."""
    r = classificar(v)
    assert r['tipo'] == esperado, (
        f'{nome}: esperado {esperado}, obtido {r["tipo"]} '
        f'(origem={r["origem_decisao"]}, regra={r["regra_aplicada"]}, '
        f'probabilidades={r["probabilidades"]})'
    )


# Lacuna conhecida do conjunto de treino: os dois rebanhos de engorda/
# confinamento do material caem FORA da distribuição sintética (distância
# 9,5 e 11,4 contra um p99 de 9,0). São fichas reais — logo o gerador de
# amostras não cobre confinamento de verdade. Enquanto essa lacuna existir,
# a probabilidade do ML não é significativa nesses casos, e a decisão precisa
# vir de regra determinística (que é o que acontece hoje).
CASOS_FORA_DA_DISTRIBUICAO = {
    'slide 13 — Recria/Engorda, caso real MT (10.302 cab)',
    'slide 14 — Engorda intensiva (1.000 cab)',
}


@pytest.mark.parametrize('nome,v,esperado,_desfrute', CASOS)
def test_rebanho_atipico_nao_decide_pelo_ml(nome, v, esperado, _desfrute):
    """
    Invariante de segurança: quando o rebanho está fora da distribuição de
    treino, a classificação não pode repousar na probabilidade do modelo —
    ali ela não tem significado estatístico.
    """
    r = classificar(v)
    at = r.get('atipicidade')
    if at is None:
        pytest.skip('atipicidade indisponível')

    if at['nivel'] == 'muito_atipico':
        assert nome in CASOS_FORA_DA_DISTRIBUICAO, (
            f'{nome}: rebanho real virou muito atípico (distância '
            f'{at["distancia"]}, p99 {at["limiar_p99"]}) — lacuna nova no treino'
        )
        assert r['origem_decisao'] == 'regra', (
            f'{nome}: está fora da distribuição de treino mas a decisão veio do '
            f'ML (confiança {r["confianca_ml"]}%) — sem base estatística'
        )
    else:
        assert nome not in CASOS_FORA_DA_DISTRIBUICAO, (
            f'{nome}: deixou de ser atípico — atualize CASOS_FORA_DA_DISTRIBUICAO'
        )


def test_detecta_compra_no_caso_real_do_para():
    """
    Slide 10: 256 matrizes produzem ~179 bezerros a 70% de natalidade, mas a
    ficha declara 556 animais de 0–12 meses. O excedente é compra de desmama.
    """
    v = _mapear(411, 145, 15, 142, 44, 31, 17, 256)
    r = estimar_compra_animais(v, natalidade=0.70)
    assert r['coorte_0_12m'] == pytest.approx(556, abs=2)
    assert r['indica_compra'] is True
    # O material calcula 377 usando apenas fêmeas +36m como matrizes; o sistema
    # inclui também as de 25–36m, então estima um pouco menos.
    assert 300 <= r['compra_estimada'] <= 400


def test_nao_acusa_compra_em_cria_pura():
    """Slide 8: toda a produção é própria — não pode acusar compra."""
    v = _mapear(90, 92, 8, 30, 5, 10, 8, 250)
    r = estimar_compra_animais(v, natalidade=0.70)
    assert r['indica_compra'] is False, (
        f'acusou compra de {r["compra_estimada"]} em rebanho de produção própria'
    )


def test_engorda_repoe_um_para_um():
    """
    Slides 13 e 14: "1 animal vendido = 1 animal reposto". A compra precisa
    aparecer e ter custo — sem isso o resultado fica ~4× superestimado.
    """
    from ml_engine import simular_cenario
    v = _mapear(0, 0, 850, 50, 100, 0, 0, 0)
    a = simular_cenario(v, 'conservador', ciclo='ENGORDA',
                        preco_arroba=320, custo_arroba=119)['anos'][0]
    assert a['compras'] > 0, 'engorda precisa declarar a reposição'
    assert a['custo_reposicao'] > 0, 'a reposição precisa ter custo'
    # a compra é o maior componente do custo num sistema de passagem
    assert a['custo_reposicao'] > a['custo_manutencao']
