"""
Recria termina onde a engorda começa.

O memorial §16 configurava recria de 10@ a 18@ (300 → 540 kg vivo) e engorda
de 300 a 520 kg. As duas COMEÇAVAM no mesmo peso e terminavam a uma arroba de
distância — eram a mesma fase com dois nomes, e a recria vendia o animal como
se o tivesse terminado.

O argumento decisivo é definicional e dispensa fonte externa:

    "recria ocorre da desmama até o início da reprodução nas fêmeas ou até o
     INÍCIO DA FASE DE ENGORDA nos machos"

A saída da recria É a entrada da engorda. Sobreposição é impossível por
definição, não por calibração — e é isso que este arquivo prende.

OS NÚMEROS E DE ONDE VÊM

    entrada da recria (desmama)  Rehagro 6–8@; Embrapa mediu 177 kg (macho) e
                                 162 kg (fêmea), que a 50% são 5,4–5,9@.
                                 Adotado 6,5@ = 195 kg vivo.

    saída da recria              Rehagro 13–14@ (em arroba, explícito);
                                 Premix 360–450 kg = 12–15@.
                                 Adotado 13,5@ = 405 kg vivo.

    entrada da engorda           = saída da recria, por definição.
    saída da engorda             520 kg, inalterada — nenhuma fonte contesta.

IMPACTO E RISCO, DECLARADOS

Na ficha real de 700 cabeças a receita do ano 1 cai 25% e o resultado vira de
+R$ 248.719 para −R$ 77.174. É correção que vai na direção de NEGAR, ao
contrário dos outros defeitos conhecidos do projeto, que erram a favor de
aprovar.

O 10@/18@ vem do material do próprio projeto e não é chute. A ficha real
validou o VOLUME de vendas (304 contra 315), nunca a receita — então nenhuma
validação não-sintética cobre esta escolha. `PESO_RECRIA_MEMORIAL=1` reverte.
"""
import inspect

import pytest

import ml_engine as M
from services.parametros_zootecnicos import (
    RENDIMENTO_ABATE, RENDIMENTO_ABATE_BOI, PESO_BOI_ARR,
)

DEFAULTS = {k: v.default
            for k, v in inspect.signature(M.simular_cenario).parameters.items()}

# Sob `PESO_RECRIA_MEMORIAL=1` estas verificações não se aplicam — e não por
# conveniência: a configuração do memorial FALHA todas elas, e é esse o
# motivo de a correção existir. A flag é alavanca de emergência de produção
# para quem decidir que o material interno vale mais que as fontes externas;
# quem a liga está escolhendo a cadeia sobreposta de olhos abertos.
pytestmark = pytest.mark.skipif(
    M._PESO_MEMORIAL,
    reason='PESO_RECRIA_MEMORIAL=1 restaura a cadeia sobreposta de propósito',
)


def _arrobas(kg, rendimento):
    return kg * rendimento / 15.0


def _kg_vivo(arrobas, rendimento):
    return arrobas * 15.0 / rendimento


def test_saida_da_recria_e_a_entrada_da_engorda():
    """A fronteira. Se as duas fases se sobrepõem, são a mesma fase."""
    saida_recria_kg = _kg_vivo(DEFAULTS['peso_saida_arr'], RENDIMENTO_ABATE)
    entrada_engorda_kg = DEFAULTS['peso_entrada_kg']
    assert saida_recria_kg == pytest.approx(entrada_engorda_kg, rel=0.02), (
        f'recria sai a {saida_recria_kg:.0f} kg e engorda entra a '
        f'{entrada_engorda_kg:.0f} kg — as fases não se encontram'
    )


def test_as_fases_nao_se_sobrepoem():
    """Regressão direta do estado anterior: ambas iam de 300 a ~540 kg."""
    entrada_recria = _kg_vivo(DEFAULTS['peso_entrada_arr'], RENDIMENTO_ABATE)
    entrada_engorda = DEFAULTS['peso_entrada_kg']
    assert entrada_recria < entrada_engorda, (
        'recria e engorda começam no mesmo peso — modelam o mesmo animal'
    )


def test_recria_nao_termina_o_animal():
    """
    Antes a recria saía a 18@ contra 20,53@ de um boi terminado: 88% de um
    boi gordo. Recria entrega animal para terminar, não animal terminado.
    """
    saida = DEFAULTS['peso_saida_arr']
    assert saida < float(PESO_BOI_ARR) * 0.75, (
        f'recria sai a {saida:.2f}@, {saida/float(PESO_BOI_ARR):.0%} de um boi '
        f'terminado ({float(PESO_BOI_ARR):.2f}@)'
    )


def test_entrada_da_recria_e_peso_de_desmama():
    """
    Recria começa na desmama. A Embrapa mediu 162–177 kg; a faixa do Rehagro
    é 6–8@. Entrar a 300 kg seria começar a recria onde ela deveria acabar.
    """
    entrada_kg = _kg_vivo(DEFAULTS['peso_entrada_arr'], RENDIMENTO_ABATE)
    assert 150 <= entrada_kg <= 250, (
        f'recria entra a {entrada_kg:.0f} kg — fora do peso de desmama'
    )


def test_a_cadeia_inteira_e_monotona():
    """desmama → recria → engorda → abate, sempre subindo."""
    pontos = [
        _kg_vivo(DEFAULTS['peso_entrada_arr'], RENDIMENTO_ABATE),
        _kg_vivo(DEFAULTS['peso_saida_arr'], RENDIMENTO_ABATE),
        DEFAULTS['peso_entrada_kg'],
        DEFAULTS['peso_saida_kg'],
    ]
    assert pontos == sorted(pontos), f'cadeia de pesos fora de ordem: {pontos}'


def test_reversao_pelo_memorial_continua_disponivel():
    """
    A escolha contraria o material do próprio projeto e nenhuma validação
    não-sintética a cobre. A saída tem de existir e estar documentada.
    """
    import os
    fonte = open(M.__file__, encoding='utf-8').read()
    assert 'PESO_RECRIA_MEMORIAL' in fonte
    assert M._PESO_ENTRADA_RECRIA_ARR == (10.0 if M._PESO_MEMORIAL else 6.5)
