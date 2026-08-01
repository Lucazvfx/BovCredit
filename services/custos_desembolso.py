"""Estrutura de custo por desembolso (perfil de gasto) → custo_arroba do parecer.

Módulo puro — não importa Flask nem DB. Converte o desembolso mensal por
cabeça (R$/cab/mês, padrão do setor) no custo em R$/@·ano que o motor usa,
usando o peso médio do rebanho declarado (sem supor peso).

Fontes:
  GEP Araguaia / Inttegra (Terra Desenvolvimento Agropecuário),
  "Perfil de Desembolso" safra 24/25, por modalidade, colunas Média e Top Rentáveis.
  Confinamento: estimativa baseada em custo de ração praticado em MT/RO safra 24/25
  (R$ 0,85–1,10/kg MS, 12–14 kg MS/cab·dia, dieta milho+farelo+núcleo).
"""
from __future__ import annotations

# Componentes na ordem de exibição: (chave, rótulo).
COMPONENTES = [
    ('insumos',        'Insumos do rebanho'),
    ('mao_obra',       'Mão de obra permanente'),
    ('administracao',  'Administração'),
    ('maquinas',       'Máquinas (custeio+inv.)'),
    ('pastagem',       'Pastagem (custeio+inv.)'),
    ('infraestrutura', 'Infraestrutura (custeio+inv.)'),
    ('taxas_impostos', 'Taxas e impostos'),
    ('outros',         'Outros'),
]

# ── Custeio e investimento: o que entra no DSCR ──────────────────────────────
#
# Três rubricas da fonte GEP vêm rotuladas "custeio + investimento" — o próprio
# rótulo diz que são duas coisas somadas. Elas pesam 30 a 40% do perfil:
#
#     CRIA            35,35 de 90,88   38,9%
#     RECRIA          40,10 de 100,50  39,9%
#     CICLO COMPLETO  43,21 de 119,14  36,3%
#
# No COE publicado do painel do Pantanal as MESMAS rubricas somam 9%
# (combustível 5% + manutenção 2% + insumos de pastagem 2%). A diferença não é
# de sistema: é de perímetro. Investimento não é custo operacional.
#
# CONSEQUÊNCIA MEDIDA, antes desta separação:
#
#     nosso custo por cabeça/mês contra o painel (R$ 42,51)
#       CRIA 2,1×   RECRIA 2,4×   CICLO COMPLETO 2,8×   ENGORDA 4,3×
#
#     cria em regime permanente: COE R$ 313,74/@ contra faixa medida de
#     R$ 166–223, e resultado de −R$ 232 mil no ano 3
#
# Ou seja: o numerador que eu comparava "COE contra COE" não era COE. Era COE
# mais investimento — a mesma confusão de níveis que o módulo de benchmarks
# documenta para fora, acontecendo para dentro.
#
# O QUE ESTE NÚMERO É, E O QUE NÃO É
#
# A fonte não separa as duas parcelas, então o rateio é DERIVADO: as rubricas
# mistas são reduzidas até ocuparem no perfil a mesma proporção que ocupam num
# COE medido. Âncora única, um painel, aplicada a todas as modalidades — mesma
# limitação do fator extensivo, e declarada pelo mesmo motivo.
#
# O desembolso CHEIO continua existindo e continua sendo mostrado: é dinheiro
# que o produtor de fato gasta. O que muda é que o DSCR passa a ser medido
# sobre a capacidade OPERACIONAL, porque investimento é adiável num ano
# apertado e serviço de dívida não é.
COMPONENTES_MISTOS = ('maquinas', 'pastagem', 'infraestrutura')

SHARE_INVESTIMENTO_COE = 0.09
"""Proporção que as rubricas mistas ocupam num COE medido (painel Pantanal)."""


def _fator_custeio(comp: dict) -> float:
    """Quanto das rubricas mistas sobrevive como custeio, de 0 a 1.

    Resolve `mistas_novas / (base + mistas_novas) = SHARE`, com `base` sendo as
    rubricas que já são integralmente operacionais.
    """
    mistas = sum(float(comp.get(k, 0) or 0) for k in COMPONENTES_MISTOS)
    if mistas <= 0:
        return 1.0
    base = sum(float(v or 0) for k, v in comp.items() if k not in COMPONENTES_MISTOS)
    alvo = base * SHARE_INVESTIMENTO_COE / (1.0 - SHARE_INVESTIMENTO_COE)
    return min(alvo / mistas, 1.0)


def desembolso_operacional(componentes: dict) -> float:
    """Desembolso mensal por cabeça contando só a parcela de custeio.

    É o número que vai ao DSCR. `sum(componentes.values())` continua sendo o
    desembolso cheio, que é o que o produtor gasta e o que a tela mostra.
    """
    if not componentes:
        return 0.0
    f = _fator_custeio(componentes)
    return sum(float(v or 0) * (f if k in COMPONENTES_MISTOS else 1.0)
               for k, v in componentes.items())


def parcela_investimento(componentes: dict) -> float:
    """A parcela do desembolso tratada como investimento — o que sai do DSCR."""
    if not componentes:
        return 0.0
    return sum(float(v or 0) for v in componentes.values()) - desembolso_operacional(componentes)

# modalidade -> {componente: (media, top_rentaveis)} em R$/cab/mês.
PERFIL_DESEMBOLSO = {
    'CRIA': {
        # Matrizes + bezerros, sistema extensivo a pasto — GEP Araguaia safra 24/25
        'insumos':        (25.53, 22.17),
        'mao_obra':       (18.20, 14.66),
        'administracao':  (7.97,  5.30),
        'maquinas':       (11.79, 7.63),
        'pastagem':       (11.97, 9.09),
        'infraestrutura': (11.59, 7.30),
        'taxas_impostos': (2.66,  2.26),
        'outros':         (1.17,  1.22),
    },  # TOTAL: média 90,88 · top 69,63

    'RECRIA': {
        # Garrotes/novilhas 13–24m a pasto extensivo, sem suplementação intensa
        # Derivado da desagregação do RECRIA_ENGORDA (GEP Araguaia safra 24/25)
        'insumos':        (30.50, 25.20),   # sal mineral, vacinas, medicamentos básicos
        'mao_obra':       (18.30, 14.80),
        'administracao':  (7.80,  5.20),
        'maquinas':       (10.90, 7.80),
        'pastagem':       (18.40, 14.10),   # reforma + manutenção + arrendamento
        'infraestrutura': (10.80, 7.10),
        'taxas_impostos': (2.60,  2.20),
        'outros':         (1.20,  1.00),
    },  # TOTAL: média 100,50 · top 77,40

    'ENGORDA': {
        # Terminação a pasto + suplementação proteico-energética (semi-intensivo)
        # Top usa mais suplemento = sistema mais intensivo → insumos maiores
        'insumos':        (85.20, 102.80),
        'mao_obra':       (20.30, 17.60),
        'administracao':  (14.80, 8.20),
        'maquinas':       (20.40, 16.70),
        'pastagem':       (15.80, 11.90),
        'infraestrutura': (19.50, 13.20),
        'taxas_impostos': (5.40,  6.00),
        'outros':         (1.20,  0.90),
    },  # TOTAL: média 182,60 · top 177,30

    'ENGORDA_CONFINAMENTO': {
        # Feedlot (ração completa: milho + farelo de soja + núcleo mineral)
        # Ração representa ~80 % do custo total
        'insumos':        (385.00, 342.00),
        'mao_obra':       (28.00,  24.50),
        'administracao':  (16.00,  10.00),
        'maquinas':       (28.00,  22.00),
        'pastagem':       (0.00,   0.00),   # sem pastagem em confinamento
        'infraestrutura': (18.00,  14.00),
        'taxas_impostos': (6.50,   6.80),
        'outros':         (2.50,   2.20),
    },  # TOTAL: média 484,00 · top 421,50

    'CICLO_COMPLETO': {
        # GEP Araguaia safra 24/25 — todas as fases integradas
        'insumos':        (44.92, 42.18),
        'mao_obra':       (18.10, 14.39),
        'administracao':  (8.49,  5.89),
        'maquinas':       (15.23, 10.71),
        'pastagem':       (14.29, 10.79),
        'infraestrutura': (13.69, 8.40),
        'taxas_impostos': (3.66,  3.10),
        'outros':         (0.76,  0.62),
    },  # TOTAL: média 119,14 · top 96,08

    # Alias legado — mantido para compatibilidade com dados gravados no BD
    'RECRIA_ENGORDA': {
        'insumos':        (77.46, 96.53),
        'mao_obra':       (19.62, 17.04),
        'administracao':  (14.04, 7.92),
        'maquinas':       (19.37, 15.49),
        'pastagem':       (15.38, 11.44),
        'infraestrutura': (18.79, 12.35),
        'taxas_impostos': (5.05,  5.77),
        'outros':         (1.03,  0.74),
    },  # TOTAL: média 170,74 · top 167,28
}


def custo_arroba_de_desembolso(desembolso_cab_mes: float,
                               arrobas_rebanho: float,
                               total_cabecas: float) -> float:
    """Converte desembolso (R$/cab/mês) em custo R$/@·ano exato.

    custo_arroba = desembolso × 12 / peso_médio_@, onde
    peso_médio_@ = arrobas_rebanho / total_cabecas (da composição declarada).
    """
    if total_cabecas <= 0:
        return 0.0
    peso_medio_arroba = arrobas_rebanho / total_cabecas
    if peso_medio_arroba <= 0:
        return 0.0
    return desembolso_cab_mes * 12.0 / peso_medio_arroba


# ── O terceiro degrau: extensivo ─────────────────────────────────────────────
#
# PERFIL_DESEMBOLSO tem duas colunas MEDIDAS componente a componente (GEP
# Araguaia): `média` e `top rentáveis`. Faltava o degrau de baixo — a fazenda
# extensiva, que é tratada como média e tem o custo por arroba SUBESTIMADO,
# porque produz menos arroba sobre a mesma estrutura.
#
# Este fator NÃO é uma terceira coluna de componentes. Inventar oito valores de
# componente que ninguém mediu seria passar por apuração o que é aritmética, e
# a camada de proveniência existe justamente para impedir isso. É um
# multiplicador, com a derivação escrita:
#
#     painéis de cria não-extensivos   Altamira/PA  R$ 189,76/@
#                                      Pelotas/RS   R$ 166,35/@   média 178,06
#     painel de cria extensiva         Pantanal/MS  R$ 223,21/@   (0,30 UA/ha)
#
#     fator = 223,21 / 178,06 = 1,254
#
# LIMITES DESTE NÚMERO, por escrito:
#   · sai de UM par de comparação, na modalidade CRIA. Aplicá-lo às demais é
#     suposição, não medição
#   · o Pantanal é um extensivo particular (planície alagável, pastagem
#     nativa); nem todo extensivo é tão caro
#   · com um segundo painel extensivo em outra modalidade, isto vira uma média
#     e deixa de ser extrapolação. É o próximo dado a procurar.
FATOR_EXTENSIVO = 1.25

# Perfis reconhecidos. 'media' e 'top' são medidos; 'extensivo' é derivado.
PERFIS = ('extensivo', 'media', 'top')


def preset_modalidade(tipo: str, perfil: str) -> dict:
    """Devolve {componente: valor R$/cab/mês} do preset da modalidade.

    tipo: CRIA | RECRIA | ENGORDA | ENGORDA_CONFINAMENTO | CICLO_COMPLETO.
    perfil: 'extensivo' | 'media' | 'top'.

    'extensivo' é a coluna média multiplicada por FATOR_EXTENSIVO — derivação
    documentada acima. Perfil desconhecido cai em 'media', que é o
    comportamento antigo.
    """
    # Modalidades sem perfil próprio herdam o mais próximo. RECRIA_ENGORDA
    # NÃO entra aqui: já tem perfil dedicado em PERFIL_DESEMBOLSO (GEP
    # Araguaia), e redirecioná-lo para ENGORDA descartaria esse perfil.
    _HERDA = {'CRIA_RECRIA': 'CRIA'}
    tipo = _HERDA.get(tipo, tipo)
    mod = tipo if tipo in PERFIL_DESEMBOLSO else 'CICLO_COMPLETO'

    if perfil == 'extensivo':
        return {k: round(v[0] * FATOR_EXTENSIVO, 2)
                for k, v in PERFIL_DESEMBOLSO[mod].items()}

    idx = 1 if perfil == 'top' else 0
    return {k: v[idx] for k, v in PERFIL_DESEMBOLSO[mod].items()}


# Nível tecnológico → perfil de custo. É o mapa que faltava: o sistema tinha os
# perfis e não tinha critério para escolher entre eles, então aplicava sempre
# `media` e deixava o `top` num botão que o analista clicava no olho.
PERFIL_POR_NIVEL = {
    'extensivo':  'extensivo',
    'medio':      'media',
    'intensivo':  'top',
    'indefinido': 'media',   # sem área declarada: mantém o comportamento antigo
}


def perfil_do_nivel(nivel: str) -> str:
    """Perfil de custo correspondente ao nível tecnológico."""
    return PERFIL_POR_NIVEL.get(nivel, 'media')


# ── Desembolso padrão por modalidade (R$/cab/mês) ────────────────────────────
# Soma da coluna "média" de PERFIL_DESEMBOLSO (GEP Araguaia safra 24/25).
# Existe porque o app usava 119 R$/@ fixo para todas as modalidades — que é o
# valor do CICLO_COMPLETO, sistema que inclui terminação e é intensivo em
# ração. Aplicado a uma cria extensiva superestimava o custo em ~30% e
# produzia caixa negativo em rebanhos saudáveis.
DESEMBOLSO_PADRAO_CAB_MES = {
    modalidade: round(sum(faixa[0] for faixa in componentes.values()), 2)
    for modalidade, componentes in PERFIL_DESEMBOLSO.items()
}


# Peso médio usado só quando o rebanho não é conhecido. NÃO é medição: é o
# número que reproduzia a conversão antiga do CICLO_COMPLETO (119 R$/@), e ele
# só sobrevive como último recurso — em toda chamada que tem o rebanho na mão,
# o peso vem de lá.
ARROBAS_POR_CABECA_FALLBACK = 11.7


def custo_arroba_padrao(tipo: str, arrobas_por_cabeca: float = None,
                        nivel: str = None) -> float:
    """
    Custo padrão em R$/@·ano para a modalidade, quando o analista não informa
    o desembolso por componente.

        R$/@·ano = (R$/cab/mês × 12) ÷ arrobas por cabeça

    `arrobas_por_cabeca` é o PESO MÉDIO do rebanho, e quem chama deve passá-lo
    a partir da composição declarada. O default de 11,7 era aplicado a
    qualquer rebanho, e peso médio depende da composição: rebanho com muito
    animal jovem pesa bem menos.

    Medido nas duas fazendas reais do projeto:

        Fazenda 3 Furnas (ADAPEC) .... 9,75 @/cab contra 11,7  → custo −17%
        Vale do Coco ................. 9,87 @/cab contra 11,7  → custo −16%

    Dividir por um número maior que o real infla o denominador e REDUZ o custo
    por arroba — menos custo, mais caixa, DSCR maior. O erro corria a favor de
    aprovar, como a carência e como o peso de saída da recria.

    O sistema já sabia calcular certo: `custo_arroba_de_desembolso` usa o peso
    do rebanho declarado desde sempre. Só não era chamado no caminho sem
    componentes, que é o que a maioria usa.

    `nivel` é o nível tecnológico (services/nivel_tecnologico.py) e escolhe a
    coluna do perfil. Sem ele — ou com nível indefinido, que é o caso de quem
    não declara área — vale a coluna `media`, o comportamento anterior.
    """
    if not arrobas_por_cabeca or arrobas_por_cabeca <= 0:
        arrobas_por_cabeca = ARROBAS_POR_CABECA_FALLBACK
    _HERDA = {'CRIA_RECRIA': 'CRIA'}
    tipo = _HERDA.get(tipo, tipo)
    if tipo not in PERFIL_DESEMBOLSO:
        tipo = 'CICLO_COMPLETO'
    # Só a parcela de custeio vai ao DSCR — ver COMPONENTES_MISTOS acima.
    cab_mes = desembolso_operacional(preset_modalidade(tipo, perfil_do_nivel(nivel)))
    return round(cab_mes * 12 / max(arrobas_por_cabeca, 1.0), 2)
