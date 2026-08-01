"""
Conferência de campo dos pesos da engorda — e uma fonte que foi recusada.

DE ONDE VEM ESTE TESTE

Chegou ao projeto um estudo de caso de engorda semi-intensiva em Theobroma/RO
(FIMCA/UNICENTRO, 2017): lote de 100 nelores, 120 dias, com pesagem em jejum a
cada 20 dias. Ele NÃO entrou como painel de custo, e a razão está registrada
aqui porque recusar fonte também precisa de justificativa auditável:

  1. o demonstrativo de resultado não tem o custo dos ANIMAIS. Receita bruta
     de R$ 270.721 menos R$ 77.434 de custos declarados dá "resultado" de
     R$ 192.942 — mas os 100 animais entraram com 437,70 kg, o equivalente a
     ~1.576@ de reposição. A R$ 160/@ isso é R$ 252 mil, e o resultado real
     vira prejuízo. O maior custo de uma engorda está fora da conta.
  2. o custo da ração aparece com três valores diferentes no mesmo trabalho:
     R$ 55.800 (Tabela 8 e DRE), R$ 63.000 (Tabela 9), R$ 28.800 ("preço
     ração").
  3. "custo da arroba produzida R$ 106,42" é custo ALIMENTAR por arroba, não
     COE — usá-lo como referência de COE subestimaria o custo pela metade.

O BLOCO FÍSICO, ESSE, FECHA

Peso vivo inicial 437,70 kg → final 569,70 kg em 120 dias, GMD 1,10 kg/dia,
rendimento de carcaça 54%. As três primeiras se verificam entre si
(1,10 × 120 = 132 = 569,70 − 437,70), e o peso final dá 20,51@ de carcaça.

Isso serve de conferência independente das duas constantes que decidem quantas
arrobas o motor atribui a um boi terminado — e a arroba é o DENOMINADOR do
COE, então errar nela desloca o custo por arroba na mesma proporção.
"""
import re

import pytest

ARROBA_KG = 15.0

# Medições do estudo de Theobroma/RO (só o bloco físico — ver o cabeçalho).
CAMPO_PVI_KG = 437.70
CAMPO_PF_KG  = 569.70
CAMPO_GMD    = 1.10
CAMPO_DIAS   = 120
CAMPO_RCQ    = 0.54


def test_o_bloco_fisico_do_estudo_e_internamente_consistente():
    """
    A razão de aceitar estes números e recusar os de custo do mesmo trabalho:
    estes se verificam entre si, aqueles se contradizem.
    """
    assert CAMPO_GMD * CAMPO_DIAS == pytest.approx(CAMPO_PF_KG - CAMPO_PVI_KG)
    assert CAMPO_PF_KG * CAMPO_RCQ / ARROBA_KG == pytest.approx(20.51, abs=0.01)


def test_a_arroba_do_boi_terminado_confere_com_a_medicao_de_campo():
    """
    O motor atribui 20,53@ a cada boi vendido. O lote medido saiu com 20,51@.

    Não é um número redondo escolhido por conveniência: bate com pesagem em
    jejum de 100 animais a 0,1%. Como essa constante é o denominador do COE
    (custo ÷ arrobas vendidas), um erro aqui apareceria como custo por arroba
    errado — que é exatamente o sintoma que estamos investigando na recria.
    """
    fonte = open('app.py').read()
    m = re.search(r"_arr_bois\s*=\s*float\(_ano1\.get\('bois_vendidos', 0\)\) \* ([\d.]+)",
                  fonte)
    assert m, 'a constante de arrobas do boi vendido mudou de forma'
    nosso = float(m.group(1))
    campo = CAMPO_PF_KG * CAMPO_RCQ / ARROBA_KG
    assert abs(nosso - campo) / campo < 0.01, (
        f'motor {nosso}@ contra {campo:.2f}@ medidos em campo'
    )


def test_o_peso_de_entrada_da_engorda_esta_na_ordem_certa():
    """
    `_PESO_ENTRADA_ENGORDA_KG` é 405 kg; o lote medido entrou com 437,70. O
    semiconfinamento termina animal mais pesado e mais rápido que o padrão a
    pasto, então entrar acima é o esperado — o que este teste prende é a ORDEM
    DE GRANDEZA, não a igualdade.

    A folga é larga de propósito: apertá-la faria um teste de regressão passar
    por medição, que é justamente o que a camada de proveniência existe para
    impedir.
    """
    from ml_engine import _PESO_ENTRADA_ENGORDA_KG
    assert 350.0 <= float(_PESO_ENTRADA_ENGORDA_KG) <= 460.0
    assert float(_PESO_ENTRADA_ENGORDA_KG) <= CAMPO_PVI_KG, (
        'o peso de entrada padrão passou o do semiconfinamento medido — '
        'a pasto não se entra mais pesado que em semiconfinamento'
    )
