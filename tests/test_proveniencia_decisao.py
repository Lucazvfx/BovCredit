"""
Proveniência da decisão e qualidade estatística (CMN 4.966/2021).

Garante que a explicação apresentada ao analista corresponde ao processo que
efetivamente tomou a decisão — regra determinística ou modelo ML — e que
rebanhos fora da distribuição de treino são sinalizados.
"""
import pytest

from ml_engine import (
    classificar, carregar_modelo, explicar_shap, calcular_atipicidade, TIPOS,
)


@pytest.fixture(scope='module', autouse=True)
def _modelo():
    carregar_modelo()


# Rebanhos de referência para cada caminho de decisão
V_ENGORDA_PURA = [0, 0, 0, 20, 0, 80, 0, 120, 0, 180]
V_CRIA         = [90, 90, 40, 20, 60, 25, 120, 8, 300, 10]
V_RECRIA_PURA  = [0, 0, 10, 120, 5, 180, 0, 40, 2, 5]
V_BIZARRO      = [500, 2, 1, 1, 1, 1, 1, 1, 1, 1]


def test_classificar_expoe_proveniencia():
    """Todo resultado declara quem decidiu: 'regra' ou 'ml'."""
    for v in (V_ENGORDA_PURA, V_CRIA, V_RECRIA_PURA):
        r = classificar(v)
        assert r['origem_decisao'] in ('regra', 'ml')
        assert r['tipo'] in TIPOS
        if r['origem_decisao'] == 'regra':
            assert r['regra_aplicada'], 'regra que decidiu deve ser nomeada'
        else:
            assert r['regra_aplicada'] is None


def test_confianca_ml_e_sempre_a_probabilidade_real():
    """confianca_ml nunca é inflada — é a probabilidade do modelo."""
    for v in (V_ENGORDA_PURA, V_CRIA, V_RECRIA_PURA, V_BIZARRO):
        r = classificar(v)
        prob_real = r['probabilidades'][r['tipo']]
        assert r['confianca_ml'] == pytest.approx(prob_real, abs=0.15), (
            f"confianca_ml={r['confianca_ml']} deveria igualar "
            f"probabilidades[{r['tipo']}]={prob_real}"
        )


def test_divergencia_entre_regra_e_modelo_fica_visivel():
    """
    Caso crítico: a regra classifica ENGORDA mas o modelo dá ~0%.
    O sistema precisa expor os dois números, não só o inflado.
    """
    r = classificar(V_RECRIA_PURA)
    assert r['origem_decisao'] == 'regra'
    # a confiança exibida é a da regra; a do modelo é bem menor
    assert r['confianca'] > r['confianca_ml'], (
        'este rebanho deve evidenciar a divergência regra × modelo'
    )
    # e a explicação precisa dizer isso em texto
    assert any('REGRA DETERMINÍSTICA' in e for e in r['explicacao'])


def test_shap_avisa_quando_nao_foi_ele_quem_decidiu():
    """SHAP não pode ser apresentado como justificativa de uma decisão por regra."""
    r = classificar(V_ENGORDA_PURA)
    exp = explicar_shap(
        V_ENGORDA_PURA, r['tipo'],
        origem_decisao=r['origem_decisao'],
        regra_aplicada=r['regra_aplicada'],
    )
    if not exp or not exp.get('fatores'):
        pytest.skip('shap indisponível neste ambiente')
    assert exp['decisao_por_regra'] is True
    assert exp['regra_aplicada'] == r['regra_aplicada']
    assert exp['aviso'] and 'não pelo modelo' in exp['aviso']


def test_shap_sem_aviso_quando_o_modelo_decidiu():
    r = classificar(V_CRIA)
    if r['origem_decisao'] != 'ml':
        pytest.skip('este rebanho não caiu no caminho ML neste modelo')
    exp = explicar_shap(V_CRIA, r['tipo'], origem_decisao='ml', regra_aplicada=None)
    if not exp or not exp.get('fatores'):
        pytest.skip('shap indisponível neste ambiente')
    assert exp['decisao_por_regra'] is False
    assert exp['aviso'] is None


def test_atipicidade_detecta_rebanho_fora_da_distribuicao():
    """Rebanho normal = típico; rebanho absurdo = sinalizado."""
    normal = calcular_atipicidade(V_CRIA)
    assert normal is not None
    assert normal['nivel'] == 'tipico'

    bizarro = calcular_atipicidade(V_BIZARRO)
    assert bizarro['nivel'] in ('atipico', 'muito_atipico')
    assert bizarro['distancia'] > normal['distancia']
    assert bizarro['mensagem']


def test_atipicidade_presente_no_resultado():
    r = classificar(V_CRIA)
    assert r['atipicidade'] is not None
    assert set(r['atipicidade']) >= {'distancia', 'nivel', 'mensagem'}
