"""Parâmetros zootécnicos de referência — defaults sourced dos cálculos.

Fonte-da-verdade dos valores default do motor e da UI. Cada valor tem origem:
- **Taxas** = ponto médio dos benchmarks nacionais (pptx de Análise de Crédito,
  encodados em `services/benchmarks_nacionais.py`); quando não há benchmark
  nacional, usa a banda "médio" do benchmark regional `ml_engine.BENCHMARKS_RO`.
- **Pesos por categoria** = referência de mercado (kg vivo × rendimento de abate
  ÷ 15). Boi terminado segue o padrão CEPEA/B3 (16–21@, meio ≈ 18@).

Módulo puro — só constantes e helpers, sem I/O.
"""
from __future__ import annotations


def midpoint(lo: float, hi: float) -> float:
    """Ponto médio de uma faixa de benchmark."""
    return (lo + hi) / 2.0


# ── Taxas: ponto médio do benchmark ──────────────────────────────────────────
# Natalidade nacional (pptx): faixas 55–75; conservador recomendado = 70%.
NATALIDADE_PCT = 70.0
# Prenhez — referência de MERCADO por fonte: Embrapa 50–65%, Scot ~60%,
# CEPEA-USP 55–60%, ABCZ 65–75%, ASBIA 65%. Por sistema: extensivo 60–75%,
# semi-intensivo 75–85%, intensivo acima de 85%.
#
# O material de treinamento ("Análise de Crédito na Pecuária Bovina", slide
# "Taxa de Prenhez Bovina") é explícito quanto ao valor de PROJEÇÃO:
#   "Referência utilizada em projeção de caixa: normalmente entre 70% e 75%,
#    de forma conservadora, salvo quando o cliente apresenta histórico técnico
#    comprovando índices maiores."
# Adota-se o piso dessa faixa — projetar prenhez alta infla a produção de
# bezerros e, por consequência, a capacidade de pagamento.
PRENHEZ_PCT = 70.0

# ── Relação de troca: preço da reposição derivado do boi gordo ───────────────
# Quantas arrobas de boi gordo são necessárias para comprar 1 animal de
# reposição. Permite precificar a compra sem depender de uma cotação própria —
# o preço do boi já é buscado diariamente pelo scraper.
#
# Boi magro (macho nelore reposição, 375 kg ≈ 12,5@): ~12,4@ de boi gordo por
#   cabeça (CEPEA, praça de São Paulo).
# Bezerro desmamado (~200 kg): relação de troca boi/bezerro ≈ 2,16 cab por boi
#   gordo de 20@ (média nacional, jun/2025) → 20 ÷ 2,16 ≈ 9,26@ por cabeça.
#
# Fontes: Notícias Agrícolas (cotação de reposição), Scot Consultoria,
# Portal DBO (relação de troca reposição/boi gordo).
TROCA_ARROBAS_BOI_MAGRO = 12.4
TROCA_ARROBAS_BEZERRO   = 9.26

# Sem benchmark nacional para estas — banda "médio" do benchmark regional
# (ml_engine.BENCHMARKS_RO), documentada como tal.
MORTALIDADE_PCT = 3.0          # BENCHMARKS_RO.mortalidade médio (taxa geral)
MORTALIDADE_ADULTO_PCT  = 2.0  # EMBRAPA: adultos 1.5–2.5%; médio 2%
MORTALIDADE_BEZERRA_PCT = 7.0  # EMBRAPA: bezerros pré-desmame 5–10%; médio 7%
DESMAME_PCT = 82.0             # BENCHMARKS_RO.desmama médio
RENDIMENTO_CARCACA_PCT = 52.0  # BENCHMARKS_RO.rend_carcaca médio (engorda)
GANHO_ARROBA_MES = 0.7         # BENCHMARKS_RO.ganho_peso_arr médio
RELACAO_FM = 2.2               # BENCHMARKS_RO.relacao_fm médio
PCT_MATRIZES = 35.0            # BENCHMARKS_RO.pct_matrizes médio

# Desfrute por modalidade (nacional DESFRUTE_MODALIDADE, meio de cada faixa).
DESFRUTE_PCT = {
    'CRIA': midpoint(18.0, 30.0),            # 24.0
    'RECRIA': midpoint(35.0, 55.0),          # 45.0
    'ENGORDA': midpoint(80.0, 120.0),        # 100.0
    'CICLO_COMPLETO': midpoint(20.0, 40.0),  # 30.0
}

# ── Pesos por categoria: GEP Araguaia safra 24/25 (fonte primária) ───────────
# Derivados de: peso_kg × rendimento ÷ 15. Boi tem rendimento 55%; demais 50%.
# Fonte: MODELAGEM RESULTADO CC 2 (GEP Araguaia / Fazenda Alvorada).
# Estes valores são idênticos aos de CATEGORIAS_GEP em fluxo_caixa_gep.py —
# manter sincronizados manualmente caso a fonte mude.
RENDIMENTO_ABATE     = 0.50   # padrão (vaca, novilha, garrote, bezerra)
RENDIMENTO_ABATE_BOI = 0.55   # boi terminado (maior musculatura e acabamento)

PESO_VIVO_KG = {'boi': 560.0, 'vaca': 460.0, 'garrote': 320.0, 'bezerra': 180.0}


def peso_arroba_carcaca(kg_vivo: float, rendimento: float = RENDIMENTO_ABATE) -> float:
    """@ de carcaça = kg vivo × rendimento ÷ 15 (1@ = 15 kg de carcaça)."""
    return kg_vivo * rendimento / 15.0


PESO_BOI_ARR     = peso_arroba_carcaca(PESO_VIVO_KG['boi'],     RENDIMENTO_ABATE_BOI)  # 20.53
PESO_VACA_ARR    = peso_arroba_carcaca(PESO_VIVO_KG['vaca'])                            # 15.33
PESO_GARROTE_ARR = peso_arroba_carcaca(PESO_VIVO_KG['garrote'])                         # 10.67
PESO_BEZERRA_ARR = peso_arroba_carcaca(PESO_VIVO_KG['bezerra'])                         # 6.00

# Jovens 0–24m agregados (usados em arrobas_categorias e val_fim legado):
# média simples das duas sub-faixas etárias dentro do grupo.
# novilha (13-24m F): 280 kg × 50% / 15 = 9.33@ ; bezerro (0-12m M): 200 kg × 50% / 15 = 6.67@
PESO_JOVEM_F_ARR = (PESO_BEZERRA_ARR + peso_arroba_carcaca(280.0)) / 2  # (6.00 + 9.33) / 2 = 7.67
PESO_JOVEM_M_ARR = (peso_arroba_carcaca(200.0) + PESO_GARROTE_ARR) / 2  # (6.67 + 10.67) / 2 = 8.67
