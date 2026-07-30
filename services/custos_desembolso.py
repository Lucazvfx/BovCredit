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


def preset_modalidade(tipo: str, perfil: str) -> dict:
    """Devolve {componente: valor R$/cab/mês} do preset da modalidade.

    tipo: CRIA | RECRIA | ENGORDA | ENGORDA_CONFINAMENTO | CICLO_COMPLETO.
    perfil: 'media' | 'top'.
    """
    # Modalidades sem perfil próprio herdam o mais próximo:
    #   RECRIA_ENGORDA -> ENGORDA (mesma estrutura de terminação)
    #   CRIA_RECRIA    -> CRIA    (mesma base reprodutiva)
    _HERDA = {'RECRIA_ENGORDA': 'ENGORDA', 'CRIA_RECRIA': 'CRIA'}
    tipo = _HERDA.get(tipo, tipo)
    mod = tipo if tipo in PERFIL_DESEMBOLSO else 'CICLO_COMPLETO'
    idx = 0 if perfil == 'media' else 1
    return {k: v[idx] for k, v in PERFIL_DESEMBOLSO[mod].items()}
