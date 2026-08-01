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

from services.proveniencia import referencia, medido


def midpoint(lo: float, hi: float) -> float:
    """Ponto médio de uma faixa de benchmark."""
    return (lo + hi) / 2.0


# ── Taxas: ponto médio do benchmark ──────────────────────────────────────────
# Natalidade nacional (pptx): faixas 55–75; conservador recomendado = 70%.
NATALIDADE_PCT = referencia(70.0, 'Benchmark nacional — faixa 60–80%', rotulo='Taxa de natalidade')
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
MORTALIDADE_PCT = referencia(3.0, 'Benchmark regional — faixa 2–5%', rotulo='Mortalidade geral')  # BENCHMARKS_RO.mortalidade médio (taxa geral)
MORTALIDADE_ADULTO_PCT = referencia(2.0, 'EMBRAPA — adultos 1,5–2,5%', rotulo='Mortalidade adulto')  # EMBRAPA: adultos 1.5–2.5%; médio 2%
MORTALIDADE_BEZERRA_PCT = referencia(7.0, 'EMBRAPA — bezerros pré-desmame 5–10%', rotulo='Mortalidade bezerro')  # EMBRAPA: bezerros pré-desmame 5–10%; médio 7%
DESMAME_PCT = referencia(82.0, 'Benchmark regional — desmama', rotulo='Taxa de desmama')  # BENCHMARKS_RO.desmama médio
RENDIMENTO_CARCACA_PCT = referencia(52.0, 'Benchmark regional — engorda', rotulo='Rendimento de carcaça')  # BENCHMARKS_RO.rend_carcaca médio (engorda)
GANHO_ARROBA_MES = referencia(0.7, 'Benchmark regional — ganho de peso', rotulo='Ganho @/mês')  # BENCHMARKS_RO.ganho_peso_arr médio
RELACAO_FM = 2.2               # BENCHMARKS_RO.relacao_fm médio
PCT_MATRIZES = 35.0            # BENCHMARKS_RO.pct_matrizes médio

# ── Primeira medição de terceiro que entra no sistema ────────────────────────
# Até aqui a camada de proveniência reportava "0 medidos": todo parâmetro era
# referência de bibliografia, política nossa ou declaração do proponente.
# Nenhum vinha de série apurada por terceiro e citável.
#
# Fonte: EMBRAPA Gado de Corte. "Desempenho produtivo nas fases de cria e
# recria em um sistema de produção de gado de corte no Brasil Central."
# Quatro anos de acompanhamento de 468 matrizes Nelore, pastagem cultivada,
# lotação média de 1,4 UA/ha no período seco.
#
# É medição de UM sistema de produção, não da fazenda em análise nem do país.
# Continua sendo referência no sentido de não descrever este produtor — mas é
# apurada, tem amostra, tem método e se cita num comitê, que é o que separa
# medição de bibliografia. A nota de cada parâmetro diz isso por escrito.
_EMBRAPA_CRIA_RECRIA = ('EMBRAPA Gado de Corte — Desempenho produtivo nas fases '
                        'de cria e recria, Brasil Central (468 matrizes Nelore, '
                        '4 anos)')
_NOTA_ESCOPO = ('Apurado em um sistema de produção da Embrapa, não nesta '
                'fazenda. Serve de referência ancorada, não de medição do '
                'proponente.')

# O número que sustenta a guarda de classificação em ml_engine.py: a fêmea só
# vira matriz de fato depois dos 36 meses. Contar a faixa de 25–36m como
# matriz projeta bezerro que ainda não existe.
IDADE_PRIMEIRA_PARICAO_MESES = medido(
    36.3, _EMBRAPA_CRIA_RECRIA, rotulo='Idade à primeira parição',
    nota=_NOTA_ESCOPO)

TAXA_PRENHEZ_MEDIDA_PCT = medido(
    87.5, _EMBRAPA_CRIA_RECRIA, rotulo='Taxa de prenhez do rebanho apurado',
    nota=_NOTA_ESCOPO + ' Rebanho experimental: acima da média comercial, '
         'por isso NÃO substitui PRENHEZ_PCT (70%), que é a projeção '
         'conservadora usada no parecer.')

PESO_DESMAMA_MACHO_KG = medido(
    177.0, _EMBRAPA_CRIA_RECRIA, rotulo='Peso à desmama, macho (202 dias)',
    nota=_NOTA_ESCOPO)

PESO_DESMAMA_FEMEA_KG = medido(
    162.0, _EMBRAPA_CRIA_RECRIA, rotulo='Peso à desmama, fêmea (202 dias)',
    nota=_NOTA_ESCOPO)

PESO_FEMEA_REPOSICAO_KG = medido(
    299.0, _EMBRAPA_CRIA_RECRIA,
    rotulo='Fêmea de reposição aos 24,3 meses, só a pasto',
    nota=_NOTA_ESCOPO)


# ── Segunda medição, no extremo oposto da escala de intensificação ───────────
#
# Os parâmetros acima vêm de UM sistema: Brasil Central, pastagem cultivada,
# 1,4 UA/ha. Uma medição só não diz se o número é do sistema ou da espécie.
#
# O painel do Pantanal de Corumbá (Embrapa Pantanal, Circular Técnica 126,
# out/2024, dados de 2023) mede uma cria extensiva modal de 4.657 cabeças em
# 10.000 ha — 0,30 UA/ha, quase cinco vezes menos lotação. É o contraponto
# útil: se um índice se mantém nos dois, é da espécie; se muda, é do manejo.
#
#     índice                    Brasil Central     Pantanal
#     idade à 1ª cria           36,3 meses         40,0 meses
#     peso desmama macho        177 kg (202 d)     180 kg (8 meses)
#     peso desmama fêmea        162 kg             165 kg
#     lotação                   1,4 UA/ha          0,30 UA/ha
#
# Os pesos à desmama praticamente não mudam; a IDADE à primeira cria, sim. É
# consistente com o que se espera: a fêmea atinge peso de cobertura mais tarde
# onde a oferta de pasto é menor. Isto REFORÇA a guarda de 36 meses em
# ml_engine.py — no sistema extensivo o número real é ainda mais tardio, então
# contar a faixa de 25–36m como matriz erra mais, não menos.
_EMBRAPA_PANTANAL = ('EMBRAPA Pantanal — Circular Técnica 126 (2024), painel '
                     'de cria extensiva modal no Pantanal de Corumbá/MS '
                     '(4.657 cab, 10.000 ha, dados de 2023)')
_NOTA_PANTANAL = ('Sistema extensivo de baixa lotação (0,30 UA/ha). Serve de '
                  'piso da escala de intensificação, não de projeção padrão.')

IDADE_PRIMEIRA_CRIA_EXTENSIVO_MESES = medido(
    40.0, _EMBRAPA_PANTANAL, rotulo='Idade à primeira cria, sistema extensivo',
    nota=_NOTA_PANTANAL)

# Desfrute MEDIDO de uma cria real, contra a faixa de bibliografia que usamos
# (DESFRUTE_MODALIDADE['CRIA'] = 18–35%). Cai dentro, perto do teto — o que
# sustenta o teto de 35% adotado antes por referência.
DESFRUTE_CRIA_MEDIDO_PCT = medido(
    31.67, _EMBRAPA_PANTANAL, rotulo='Taxa de desfrute, cria extensiva',
    nota=_NOTA_PANTANAL)

# Natalidade medida sobre matrizes (62,39%) e sobre multíparas (64,40%). Fica
# ABAIXO da faixa "adequado 65–75%" da bibliografia — e é uma fazenda modal,
# não uma fazenda ruim. Registro do que o campo entrega, não do que o manual
# recomenda.
NATALIDADE_MATRIZES_EXTENSIVO_PCT = medido(
    62.39, _EMBRAPA_PANTANAL, rotulo='Natalidade sobre matrizes, extensivo',
    nota=_NOTA_PANTANAL)

# Confirmação independente de um valor que era só referência: a mortalidade
# pré-desmama medida no Pantanal é 7,00%, exatamente o meio da faixa 5–10% que
# MORTALIDADE_BEZERRA_PCT já adotava. Não muda o número — muda o quanto se
# pode confiar nele.
MORTALIDADE_PRE_DESMAMA_MEDIDA_PCT = medido(
    7.0, _EMBRAPA_PANTANAL, rotulo='Mortalidade pré-desmama medida',
    nota=_NOTA_PANTANAL + ' Coincide com MORTALIDADE_BEZERRA_PCT (7,0%), que '
         'até aqui era ponto médio de faixa bibliográfica.')

# Desfrute por modalidade (nacional DESFRUTE_MODALIDADE, meio de cada faixa).
# Cada valor carrega a origem (services/proveniencia.py). São REFERÊNCIA:
# ponto médio de faixa de bibliografia, não medição desta nem de qualquer
# fazenda. Substituíveis por medição (IBGE PPM ÷ Abate, por UF) trocando o
# registro — nenhuma fórmula muda, porque Parametro herda de float.
def _desfrute(ciclo, lo, hi, nota=''):
    return referencia(
        midpoint(lo, hi),
        f'Benchmark nacional — ponto médio da faixa {lo:.0f}–{hi:.0f}%',
        rotulo=f'Desfrute de referência · {ciclo}', nota=nota)


DESFRUTE_PCT = {
    'CRIA':           _desfrute('CRIA', 18.0, 35.0),
    'RECRIA':         _desfrute('RECRIA', 35.0, 55.0),
    'ENGORDA':        _desfrute('ENGORDA', 80.0, 120.0),
    'CICLO_COMPLETO': _desfrute('CICLO_COMPLETO', 20.0, 45.0),
    'RECRIA_ENGORDA': _desfrute('RECRIA_ENGORDA', 60.0, 85.0),
    'CRIA_RECRIA':    _desfrute('CRIA_RECRIA', 25.0, 45.0,
        nota='Sistema misto: base de cria com compra de desmama. Fica acima de '
             'uma cria pura porque o volume recriado também é comercializado.'),
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
