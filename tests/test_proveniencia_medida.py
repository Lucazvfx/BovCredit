"""
As primeiras medições de terceiro do projeto.

Até aqui a camada de proveniência reportava "0 medidos" em todo parecer: tudo
era referência de bibliografia, política nossa ou declaração do proponente.
Um teste guardava esse zero de propósito, para ninguém marcar algo como medido
sem fonte real.

Agora há fonte real. EMBRAPA Gado de Corte, "Desempenho produtivo nas fases de
cria e recria em um sistema de produção de gado de corte no Brasil Central":
quatro anos de acompanhamento de 468 matrizes Nelore, a pasto.

O número que mais importa é a IDADE À PRIMEIRA PARIÇÃO: 36,3 meses. Ele
sustenta, por medição independente, a guarda de classificação criada a partir
de um caso de campo — a fêmea de 25–36m ainda não pariu, então contá-la como
matriz projeta bezerro que ainda não existe.

O que estes testes prendem é o RIGOR do rótulo, não o número: medição sem
fonte não pode existir, e medição de um sistema experimental não pode ser
confundida com medição da fazenda em análise.
"""
import pytest

from services.proveniencia import MEDIDO, e_parametro
from services.parametros_zootecnicos import (
    IDADE_PRIMEIRA_PARICAO_MESES, TAXA_PRENHEZ_MEDIDA_PCT,
    PESO_DESMAMA_MACHO_KG, PESO_DESMAMA_FEMEA_KG, PESO_FEMEA_REPOSICAO_KG,
    PRENHEZ_PCT,
)

MEDIDOS = {
    'idade à primeira parição':  IDADE_PRIMEIRA_PARICAO_MESES,
    'taxa de prenhez apurada':   TAXA_PRENHEZ_MEDIDA_PCT,
    'peso à desmama, macho':     PESO_DESMAMA_MACHO_KG,
    'peso à desmama, fêmea':     PESO_DESMAMA_FEMEA_KG,
    'fêmea de reposição 24,3m':  PESO_FEMEA_REPOSICAO_KG,
}


@pytest.mark.parametrize('nome', list(MEDIDOS))
def test_medicao_carrega_fonte_citavel(nome):
    """Medição sem fonte é afirmação. O comitê pergunta de onde veio."""
    p = MEDIDOS[nome]
    assert e_parametro(p), f'{nome} não é Parametro — perdeu a etiqueta'
    assert p.origem == MEDIDO
    assert p.fonte and 'EMBRAPA' in p.fonte.upper()
    assert '468' in p.fonte, 'a amostra faz parte da fonte'


@pytest.mark.parametrize('nome', list(MEDIDOS))
def test_escopo_da_medicao_esta_declarado(nome):
    """
    É medição de UM sistema de produção, não da fazenda em análise. Deixar
    isso implícito seria vender referência ancorada como medição do
    proponente — exatamente o tipo de coisa que derruba um parecer em
    auditoria.
    """
    assert 'não nesta fazenda' in MEDIDOS[nome].nota


def test_idade_a_primeira_paricao_sustenta_a_guarda_de_classificacao():
    """
    36,3 meses é o que torna o corte dos 36m zootécnico em vez de arbitrário:
    a fêmea de 25–36m ainda não pariu.
    """
    assert float(IDADE_PRIMEIRA_PARICAO_MESES) > 36.0


def test_prenhez_experimental_nao_substitui_a_projecao_conservadora():
    """
    87,5% é rebanho experimental da Embrapa; 70% é a projeção usada no
    parecer. Trocar um pelo outro inflaria a receita de todo parecer de cria
    com um número que não descreve fazenda comercial.
    """
    assert float(TAXA_PRENHEZ_MEDIDA_PCT) > float(PRENHEZ_PCT)
    assert float(PRENHEZ_PCT) == 70.0
    assert 'NÃO substitui' in TAXA_PRENHEZ_MEDIDA_PCT.nota


def test_parecer_deixa_de_reportar_zero_medidos():
    """O contador era a régua honesta do projeto. Saiu do zero com fonte."""
    from services.proveniencia import catalogo, resumo
    r = resumo(catalogo(*MEDIDOS.values()))
    assert r['contagem']['medido'] == len(MEDIDOS)
    assert r['medidos_pct'] > 0
