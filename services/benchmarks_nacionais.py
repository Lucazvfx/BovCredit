"""Benchmarks nacionais de pecuária de corte para análise de crédito.

Diferencial do produto: em vez de uma faixa opaca única, cada indicador é
confrontado contra *cada fonte institucional nomeada* (Embrapa, Scot, CEPEA-USP,
ABCZ, ASBIA) e contra o benchmark financeiro nacional de desembolso
(Inttegra 2025, Média vs Top Rentáveis). Aplica-se ao Brasil todo — as fontes
são referências nacionais, não estaduais.

REGRA DE INTEGRIDADE: todo número aqui vem de fonte real (PPTX "Análise Crédito
Pecuária" e XLSX GEP Araguaia / Inttegra 2025). Nada é estimado. Onde não há
dado real, o indicador simplesmente não é avaliado (ver LACUNAS no material).

Faixas em porcentagem (0–100). Modalidades: CRIA, RECRIA, ENGORDA,
CICLO_COMPLETO (mesmas strings de `ml_engine`/`BENCHMARKS_RO`).
"""
from __future__ import annotations

# --- Taxa de prenhez, por fonte (PPTX slide 3) --------------------------------
PRENHEZ_FONTES = {
    "Embrapa": (50.0, 65.0),
    "Scot Consultoria": (60.0, 60.0),
    "CEPEA-USP": (55.0, 60.0),
    "ABCZ": (65.0, 75.0),
    "ASBIA": (65.0, 65.0),
}

# --- Taxa de natalidade, por fonte (PPTX slide 4 + EMBRAPA CNPGC) -------------
NATALIDADE_FONTES = {
    "Embrapa": (65.0, 80.0),       # EMBRAPA CNPGC: adequado 65-75%, excelente >80%
    "Scot Consultoria": (60.0, 60.0),
    "CEPEA-USP": (55.0, 60.0),
    "ABCZ": (65.0, 75.0),
}

_MULTIFONTE = {"prenhez": PRENHEZ_FONTES, "natalidade": NATALIDADE_FONTES}

# --- Prenhez por sistema de produção (PPTX slide 3) ---------------------------
PRENHEZ_SISTEMA = {
    "extensivo": (60.0, 75.0),
    "semi_intensivo": (75.0, 85.0),
    "intensivo": (85.0, 100.0),
}

# --- Desfrute por modalidade (PPTX slides 5–6) --------------------------------
# Tetos de CRIA e CICLO_COMPLETO revisados em julho/2026. Os anteriores (30% e
# 40%) vinham do slide do material de treinamento e ficavam ABAIXO do que o
# setor trata como bom desempenho — Scot Consultoria dá "acima de 35%" para
# cria e "acima de 45%" para ciclo completo, com as propriedades mais
# produtivas em torno de 56% e as de produtividade média em 47%.
#
# Uma cria fazendo 35% é boa cria, e o sistema a marcava como anomalia acima
# do teto. Alerta que dispara em desempenho bom é alerta que o analista
# aprende a ignorar — e aí não serve para o caso em que deveria disparar.
#
# As duas fontes conflitam e a divergência fica registrada aqui de propósito:
# o slide é material interno, as faixas do setor são públicas e citáveis.
# Onde conflitam, prevalece a pública.
#
# ── AGORA HÁ MOTIVO MEDIDO, E ELE VEIO DE 19 PAINÉIS ─────────────────────────
#
# O ebook Campo Futuro 2022 (CNA/Senar, elaboração Cepea-Esalq/USP) publica a
# taxa de desfrute de 19 sistemas amostrados em 17 municípios de 13 estados,
# do semiárido baiano ao bioma amazônico do Acre. É a maior amostra de campo
# que este projeto já teve para qualquer indicador.
#
# Confrontadas com as faixas que estavam aqui:
#
#     modalidade        nossa faixa   medido           dentro
#     CRIA                 18–35      31,97–39,25%      5 de 9
#     RECRIA_ENGORDA       60–85      39,63–49,64%      0 de 5   ← nenhum
#     CICLO_COMPLETO       20–45      25,38–35,57%      3 de 3
#     RECRIA isolada       35–55      79,68%            0 de 1
#     ENGORDA isolada     80–120      97,52%            1 de 1
#
# RECRIA_ENGORDA estava inteira errada: a faixa dizia 60–85% e o campo entrega
# 40–50%. Toda recria/engorda real seria marcada como "abaixo", e o alerta que
# deveria pegar liquidação de plantel virava ruído permanente.
#
# CRIA estava com o TETO baixo: quatro dos nove painéis passam de 35%, e o
# maior faz 39,25%. Já havíamos subido esse teto uma vez por bibliografia; a
# medição confirma a direção e diz onde parar.
#
# A faixa de RECRIA isolada tinha sido "validada" contra UM caso — a projeção
# da ficha de 700 cabeças caindo em 43,4%. Um painel de recria pura
# (Pontes e Lacerda/MT, 19,81 @/ha) mede 79,68%. Faz sentido: recria pura
# compra e vende no mesmo ano, então gira quase todo o plantel. A validação
# anterior confirmava a projeção contra ela mesma, não contra o campo.
#
# As faixas passam a ser o intervalo observado com folga de ~15% para cada
# lado — folga, e não o mínimo e o máximo crus, porque 19 painéis descrevem a
# dispersão mas não a esgotam.
#
# Fonte: Projeto Campo Futuro CNA/Senar (2022), "Ebook 2022 — Pecuária de
# Corte", Tabela 1: Resultados de cada painel. Elaboração Cepea-Esalq/USP.
DESFRUTE_MODALIDADE = {
    "CRIA": (27.0, 45.0),            # medido 31,97–39,25 em 9 painéis
    "RECRIA": (60.0, 95.0),          # medido 79,68 em 1 painel (Pontes e Lacerda/MT)
    "RECRIA_ENGORDA": (34.0, 57.0),  # medido 39,63–49,64 em 5 painéis
    "ENGORDA": (80.0, 120.0),        # medido 97,52 em 1 painel; faixa mantida
    # Era (21,0 – 45,0), do piso de 3 painéis do Campo Futuro (25,38–35,57%)
    # com folga, e teto pela referência do setor.
    #
    # ENTROU UMA SÉRIE TEMPORAL, e ela estoura a faixa nas DUAS pontas. O
    # painel de Corinto/MG acompanha a MESMA fazenda de ciclo completo por sete
    # anos (2005–2011), enquanto ela cresce de 1.460 para 3.980 cabeças:
    #
    #     2005  2006  2007  2008  2009  2010  2011
    #     16,5  16,9  21,6  47,2  25,5  49,3  33,6
    #
    # Os 3 painéis do Campo Futuro são fotografias de fazendas diferentes num
    # ano só; esta é a mesma fazenda ao longo do tempo, e mostra o que uma
    # fotografia não mostra: o desfrute de um ciclo completo real OSCILA muito,
    # porque retenção e venda se alternam conforme a fazenda forma ou realiza
    # plantel. Nos anos de 16,5% ela estava retendo para crescer — e terminou o
    # período com lucro operacional de R$ 341/ha contra R$ 4,97 no início.
    #
    # Uma faixa que reprovasse os dois extremos reprovaria a fazenda inteira,
    # inclusive nos anos em que ela estava fazendo a coisa certa.
    "CICLO_COMPLETO": (16.0, 50.0),
}

# ── A mesma fazenda por sete anos ────────────────────────────────────────────
#
# Tabela 3.5 do relatório de cenários para a pecuária: ciclo completo em
# Corinto/MG, 2005 a 2011. É a única série TEMPORAL da nossa base — todo o
# resto são fotografias de fazendas diferentes num ano só.
#
# O que só uma série mostra:
#   · o desfrute oscila de 16,5% a 49,3% na mesma fazenda, sem que ela tenha
#     virado outra coisa. Retenção e realização se alternam
#   · a prenhez COMERCIAL começa em 54% e chega a 80% em cinco anos. O nosso
#     87,5% medido é de rebanho experimental da Embrapa; a faixa real de uma
#     fazenda em operação vai de 54 a 91
#   · a mortalidade cai de 6,5% para 1,3% conforme a fazenda intensifica —
#     não é constante da espécie, é resultado de manejo
#   · o lucro operacional sai de R$ 4,97/ha para R$ 341/ha. É o perfil de
#     cliente que este sistema mais reprova, e ele deu certo
#
# (ano, cabeças, ha, lotação cab/ha, desfrute %, prenhez %, mortalidade %,
#  lucro operacional R$/ha, retorno sobre capital % a.a.)
PAINEL_CORINTO_MG = [
    (2005, 1460, 2350, 0.62, 16.5, 54.0, 6.5,   4.97,  0.79),
    (2006, 1700, 2350, 0.72, 16.9, 56.0, 5.7,   1.72,  0.19),
    (2007, 1700, 3070, 0.55, 21.6, 60.0, 5.2,  27.20,  3.05),
    (2008, 1900, 3070, 0.62, 47.2, 64.0, 4.2, 167.00, 20.90),
    (2009, 2950, 5250, 0.56, 25.5, 80.0, 2.6, 248.00, 30.10),
    (2010, 3330, 5250, 0.64, 49.3, 79.0, 1.4, 338.00, 37.20),
    (2011, 3980, 5250, 0.76, 33.6, 76.0, 1.3, 341.00, 28.40),
]

# ── Lotação de 71 fazendas comerciais do bioma amazônico ─────────────────────
#
# Benchmark EXAGRO, dados de 2013 (Tabela 3.9). O banco tem 234 fazendas em 16
# estados; este recorte são as 71 do bioma amazônico, exclusivamente a pasto,
# sem confinamento — que é a nossa praça.
#
# Serve para conferir os limiares de nivel_tecnologico.py contra fazenda
# comercial de verdade, e não contra média nacional de bibliografia. A mediana
# de 0,80 UA/ha sustenta o nosso limiar de 0,70 para extensivo: a metade de
# baixo de um grupo que se submete a benchmarking fica logo acima dele.
#
# (estado, nº de fazendas, área média mil ha, animais mil, cab/ha, UA/ha)
EXAGRO_LOTACAO_2013 = [
    ("AC",  1, 11.30, 15.00, 1.30, 1.10),
    ("MA",  1, 13.60, 14.60, 1.10, 0.70),
    ("MT", 33,  5.73,  7.55, 1.30, 0.89),
    ("PA", 28,  2.76,  3.14, 1.10, 0.82),
    ("RO",  1,  2.40,  3.92, 1.60, 1.21),
    ("TO",  7,  3.00,  2.67, 0.90, 0.56),
]
EXAGRO_LOTACAO_MEDIA_UA_HA   = 0.90
EXAGRO_LOTACAO_MEDIANA_UA_HA = 0.80

# Os 19 painéis, para os testes conferirem as faixas contra o dado e não
# contra si mesmas. (município, UF, sistema, desfrute %, @/ha, lotação UA/ha)
PAINEIS_DESFRUTE_2022 = [
    ("Xapuri", "AC", "CRIA", 39.09, 6.77, 1.69),
    ("Cruzeiro do Sul", "AC", "CRIA", 32.77, 3.36, 1.01),
    ("Barreiras", "BA", "CRIA", 34.27, 1.86, 0.50),
    ("Itamaraju", "BA", "CRIA", 32.53, 3.61, 0.86),
    ("Altamira", "PA", "CRIA", 34.71, 3.47, 0.82),
    ("Vila Rica", "MT", "CRIA", 39.25, 4.82, 1.10),
    ("São Félix do Xingu", "PA", "CRIA", 37.48, 4.32, 1.05),
    ("Juara", "MT", "CRIA", 31.97, 4.58, 1.09),
    ("Alta Floresta", "MT", "CRIA", 38.09, 6.57, 1.53),
    ("Barra do Garças", "MT", "RECRIA_ENGORDA", 49.62, 9.16, 0.80),
    ("Cruzeiro do Sul", "AC", "RECRIA_ENGORDA", 39.63, 6.09, 0.65),
    ("Itamaraju", "BA", "RECRIA_ENGORDA", 49.64, 11.40, 1.03),
    ("Itapetinga", "BA", "RECRIA_ENGORDA", 49.25, 9.37, 0.89),
    ("Araguaína", "TO", "RECRIA_ENGORDA", 47.94, 9.68, 0.80),
    ("Rio Branco", "AC", "CICLO_COMPLETO", 25.38, 8.39, 1.51),
    ("Paragominas", "PA", "CICLO_COMPLETO", 27.90, 8.56, 1.25),
    ("Santana do Araguaia", "PA", "CICLO_COMPLETO", 35.57, 18.84, 2.19),
    ("Pontes e Lacerda", "MT", "RECRIA", 79.68, 19.81, 1.20),
    ("Feira de Santana", "BA", "ENGORDA", 97.52, 12.71, 0.68),
]

# Escala geral de interpretação do desfrute (PPTX slide 5), independente de
# modalidade: (teto_exclusivo, classe).
_DESFRUTE_ESCALA = [
    (18.0, "muito_baixo"),
    (30.0, "baixo"),
    (55.0, "medio"),
    (85.0, "alto"),
    (float("inf"), "muito_alto"),
]

# --- Desembolso R$/cab/mês — Inttegra 2025 (XLSX GEP, aba PERFIL DESEMB) -------
# Média = produtor médio; Top = 25% mais rentáveis. Menor é melhor.
DESEMBOLSO_INTTEGRA = {
    "CRIA":           {"media": 90.88,  "top": 69.63},
    "RECRIA":         {"media": 100.50, "top": 77.40},   # desagregado de RECRIA_ENGORDA
    "ENGORDA":        {"media": 182.60, "top": 177.30},  # desagregado de RECRIA_ENGORDA
    "RECRIA_ENGORDA": {"media": 170.74, "top": 167.28},  # alias legado
    "CICLO_COMPLETO": {"media": 119.14, "top": 96.08},
}
FONTE_DESEMBOLSO = "GEP Araguaia / Inttegra (2025)"

_MAP_DESEMBOLSO = {
    "CRIA":           "CRIA",
    "RECRIA":         "RECRIA",
    "ENGORDA":        "ENGORDA",
    "RECRIA_ENGORDA": "RECRIA_ENGORDA",
    "CICLO_COMPLETO": "CICLO_COMPLETO",
}

# --- Benchmarks zootécnicos EMBRAPA CNPGC (Apostila Nelore + Doc 151 + Mais Precoce) ---
# Estrutura: {indicador: {ciclo: (baixo, adequado_lo, adequado_hi, excelente)}}
# "baixo" = abaixo disso é alerta; "excelente" = acima disso é ótimo
EMBRAPA_ZOOTECNICO = {
    "natalidade_pct": {
        # Taxa de natalidade (%)
        "CRIA":           (55.0, 65.0, 75.0, 80.0),
        "CICLO_COMPLETO": (55.0, 65.0, 75.0, 80.0),
        "RECRIA":         None,  # não se aplica
        "ENGORDA":        None,
    },
    "desmama_pct": {
        # Taxa de desmama (%)
        "CRIA":           (50.0, 60.0, 72.0, 75.0),
        "CICLO_COMPLETO": (50.0, 60.0, 72.0, 75.0),
        "RECRIA":         None,
        "ENGORDA":        None,
    },
    "desfrute_pct": {
        # Taxa de desfrute (%)
        "CRIA":           (15.0, 20.0, 30.0, 35.0),
        "RECRIA":         (30.0, 35.0, 50.0, 55.0),
        "ENGORDA":        (70.0, 80.0, 100.0, 120.0),
        "CICLO_COMPLETO": (18.0, 25.0, 35.0, 45.0),
    },
    "lotacao_ua_ha": {
        # Lotação (UA/ha)
        "CRIA":           (0.3, 0.5, 1.0, 1.5),
        "RECRIA":         (0.5, 1.0, 2.0, 3.0),
        "ENGORDA":        (0.5, 1.5, 3.0, 4.0),
        "CICLO_COMPLETO": (0.5, 1.0, 2.0, 2.5),
    },
    "gmd_g_dia": {
        # Ganho médio diário (g/dia) — pastagem
        "RECRIA":         (300.0, 400.0, 600.0, 700.0),
        "ENGORDA":        (400.0, 700.0, 1000.0, 1200.0),
        "CRIA":           None,
        "CICLO_COMPLETO": (300.0, 400.0, 600.0, 700.0),
    },
    "gmd_conf_g_dia": {
        # Ganho médio diário (g/dia) — confinamento
        "ENGORDA":        (800.0, 1000.0, 1400.0, 1500.0),
        "CICLO_COMPLETO": (800.0, 1000.0, 1400.0, 1500.0),
        "CRIA":           None,
        "RECRIA":         None,
    },
    "mortalidade_bezerros_pct": {
        # Mortalidade pré-desmama (%) — menor é melhor
        "CRIA":           (8.0, 6.0, 3.0, 2.0),   # invertido: alerta se > 8%
        "CICLO_COMPLETO": (8.0, 6.0, 3.0, 2.0),
        "RECRIA":         None,
        "ENGORDA":        None,
    },
    "idade_abate_meses": {
        # Idade ao abate (meses) — menor é melhor
        "ENGORDA":        (42.0, 36.0, 30.0, 20.0),  # invertido
        "CICLO_COMPLETO": (42.0, 36.0, 30.0, 20.0),
        "CRIA":           None,
        "RECRIA":         None,
    },
}

# Composição típica de rebanho estabilizado (EMBRAPA CNPGC — sistema Nelore 256 cab.)
COMPOSICAO_TIPICA_EMBRAPA = {
    "vacas_pct":          32.8,   # matrizes adultas
    "novilhas_repo_pct":  14.1,   # novilhas 1-3 anos (reposição)
    "machos_sobreano_pct": 14.5,  # sobreanos / garrotes
    "bezerros_pct":       31.3,   # bezerros e bezerras
    "touros_pct":          1.6,
}

# Ciclos x categorias (EMBRAPA CNPGC) — quais categorias compõem cada ciclo
CICLO_CATEGORIAS = {
    "RECRIA_ENGORDA": {
        "principais": ["garrote", "boi"],
        "secundarias": ["novilha"],
        "descricao": "Compra de magro + terminação (13–36 m). Produto: boi gordo. Retenção muito baixa, giro alto.",
        "peso_saida_kg": (500, 560),
        "desmama_meses": (0, 0),
    },
    "CRIA_RECRIA": {
        "principais": ["vaca", "bezerra", "bezerro", "novilha", "garrote"],
        "secundarias": [],
        "descricao": "Base de cria + compra de desmama para recria (sistema misto). Produto: bezerro, garrote e fêmeas excedentes.",
        "peso_saida_kg": (300, 380),
        "desmama_meses": (6, 7),
    },
    "CRIA":   {
        "principais": ["vaca", "bezerra", "bezerro"],
        "secundarias": ["novilha"],
        "descricao": "Matrizes + bezerros até desmama (0–7 m). Produto: bezerro desmamado 130–160 kg.",
        "peso_saida_kg": (130, 160),
        "desmama_meses": (6, 7),
    },
    "RECRIA": {
        "principais": ["bezerra_desmama", "bezerro_desmama", "novilha", "garrote"],
        "secundarias": [],
        "descricao": "Pós-desmama até peso de entrada na engorda (7–30 m). Produto: garrote 300–380 kg.",
        "peso_saida_kg": (300, 380),
        "gmd_pastagem_g_dia": (300, 700),
    },
    "ENGORDA": {
        "principais": ["garrote", "boi_gordo"],
        "secundarias": ["vaca"],  # vaca de descarte
        "descricao": "Terminação: garrote → boi gordo 450–600 kg. Confinamento: 60–110 dias.",
        "peso_entrada_kg": (300, 360),
        "peso_saida_kg": (450, 600),
        "rendimento_carcaca_pct": (52, 57),
    },
    "CICLO_COMPLETO": {
        "principais": ["vaca", "bezerra", "bezerro", "novilha", "garrote", "boi_gordo"],
        "secundarias": ["bezerra_desmama", "bezerro_desmama"],
        "descricao": "Cria + Recria + Engorda na mesma propriedade. Produto final: boi gordo 15–42 meses.",
        "idade_abate_meta_meses": (15, 42),
    },
}

FONTE_EMBRAPA = "EMBRAPA CNPGC — Apostila Nelore 2000 · Doc 151 · Plataforma Mais Precoce"


def avaliar_zootecnico(modalidade: str, indicadores: dict) -> list[dict]:
    """Avalia indicadores zootécnicos contra benchmarks EMBRAPA CNPGC.

    Args:
        modalidade: CRIA, RECRIA, ENGORDA ou CICLO_COMPLETO.
        indicadores: dict com quaisquer chaves de EMBRAPA_ZOOTECNICO.

    Returns:
        Lista de avaliações, uma por indicador presente.
    """
    resultado = []
    for ind_key, ciclos in EMBRAPA_ZOOTECNICO.items():
        valor = indicadores.get(ind_key)
        if valor is None:
            continue
        faixa = ciclos.get(modalidade)
        if faixa is None:
            continue
        alerta, adeq_lo, adeq_hi, excelente = faixa
        valor = float(valor)
        # Indicadores onde menor é melhor (mortalidade, idade abate)
        invertido = ind_key in ("mortalidade_bezerros_pct", "idade_abate_meses")
        if invertido:
            if valor <= excelente:
                nivel = "excelente"
            elif valor <= adeq_lo:
                nivel = "adequado"
            elif valor <= alerta:
                nivel = "atencao"
            else:
                nivel = "baixo"
        else:
            if valor >= excelente:
                nivel = "excelente"
            elif valor >= adeq_lo:
                nivel = "adequado"
            elif valor >= alerta:
                nivel = "atencao"
            else:
                nivel = "baixo"
        resultado.append({
            "indicador": ind_key,
            "valor": round(valor, 2),
            "nivel": nivel,
            "faixa": {"alerta": alerta, "adequado": (adeq_lo, adeq_hi), "excelente": excelente},
            "invertido": invertido,
            "fonte": FONTE_EMBRAPA,
        })
    return resultado


# --- COE R$/@ vendida — Campo Futuro / CNA Brasil ----------------------------
#
# QUAL CUSTO É ESTE, EXATAMENTE
#
# A metodologia Campo Futuro/Cepea separa três níveis, e confundi-los é o erro
# mais comum na análise de custo pecuário:
#
#   COE  Custo Operacional Efetivo — só o DESEMBOLSO. Tudo que o produtor paga
#        a alguém e sai do caixa: alimentação, sanidade, mão de obra, impostos
#        e a AQUISIÇÃO DE ANIMAIS (que costuma ser o maior item de todos numa
#        recria/engorda).
#   COT  Custo Operacional Total — COE + depreciação (benfeitorias, máquinas,
#        matrizes e reprodutores) + pró-labore. Depreciação não é desembolso:
#        o produtor não paga a ninguém, guarda para repor no fim da vida útil.
#   CT   Custo Total — COT + remuneração do capital empatado em terra,
#        benfeitorias, máquinas e animais.
#
# O NOSSO numerador é `custo_operacional` do fluxo GEP, que é custo de caixa e
# inclui a compra de animais (`custo_manutencao + custo_reposicao` na
# simulação). Ou seja: comparamos COE contra COE, mesmo perímetro. Isto está
# escrito aqui de propósito — acrescentar depreciação ao numerador "para ficar
# mais completo" quebraria a comparação sem que nenhum teste falhasse.
#
# POR QUE COE, E NÃO O CUSTO "COMPLETO"
#
# Comparar em CT parece mais rigoroso e seria um erro de crédito grave. O
# painel do Pantanal de Corumbá publica os três níveis para a mesma fazenda:
#
#     receita  R$ 275,32/@        COE  R$ 223,21/@   →  margem bruta   POSITIVA
#                                 COT  R$ 260,76/@   →  margem líquida POSITIVA
#                                 CT   R$ 431,09/@   →  lucro NEGATIVO em
#                                                       R$ 1,66 milhão/ano
#
# Não é uma fazenda ruim: é uma fazenda modal. Santos et al. (2014), sobre 193
# propriedades modais em 13 estados que concentram 90% do rebanho nacional,
# acharam que em MAIS DE 90% delas a receita não remunera o custo de
# oportunidade do capital investido — porque o ativo principal é a TERRA, cuja
# valorização não entra na receita do ano.
#
# Um analista que comparasse custo em CT reprovaria nove em cada dez fazendas
# brasileiras, e estaria medindo o preço da terra, não a capacidade de pagar.
# O crédito rural se paga com CAIXA. COE é o nível que descreve caixa, e é por
# isso que ele é o nosso.
#
# UM PAINEL NÃO É UM BENCHMARK NACIONAL
#
# Até aqui havia UM painel por modalidade, os três do Pará, e o sistema
# comparava a fazenda contra aquele ponto — dissesse ela ser de Rondônia ou do
# Rio Grande do Sul. Com um segundo painel por modalidade fica visível o que um
# ponto escondia: a MESMA metodologia, no MESMO sistema, dá números e
# composições bem diferentes conforme a praça.
#
#   CRIA             Altamira/PA  R$ 189,76/@   mão de obra 18,2%
#                    Pelotas/RS   R$ 166,35/@   mão de obra 42,9%
#   RECRIA_ENGORDA   Paragominas/PA R$ 183,50/@ reposição 62,2%
#                    Colorado d'Oeste/RO R$ 171,88/@ aquisição 51,6%
#
# O custo por arroba varia ~7% entre painéis da mesma modalidade, mas a
# COMPOSIÇÃO varia muito mais: mão de obra pesa 18,2% na cria paraense e 42,9%
# na gaúcha. Quem lê só o total não vê isso.
#
# Consequência para o parecer: a comparação passa a ser contra a FAIXA
# observada, não contra um ponto, e só o que passa do teto da faixa conta como
# "acima da praça". Uma fazenda entre os dois painéis não está fora de lugar
# nenhum — está entre duas realidades igualmente reais.
#
# Unidade: R$/arroba VENDIDA. O sistema converte
# `coe_calculado = custo_operacional / arrobas_vendidas`.
COE_PAINEIS = {
    "CICLO_COMPLETO": [
        {
            "local": "Santana do Araguaia, PA", "uf": "PA", "ano": 2025,
            "coe_arroba": 164.61,
            "descricao": "5.100 cab . ciclo completo (cria + recria + engorda)",
            "maiores_itens_pct": {"Suplem. mineral": 51.3, "Mao de obra": 16.5},
        },
    ],
    "CRIA": [
        {
            "local": "Altamira, PA", "uf": "PA", "ano": 2025,
            "coe_arroba": 189.76,
            "descricao": "150 matrizes . producao de bezerros",
            "maiores_itens_pct": {"Mao de obra": 18.2, "Suplem. mineral": 15.4},
        },
        {
            "local": "Pelotas, RS", "uf": "RS", "ano": 2024,
            "coe_arroba": 166.35,
            "descricao": "250 ha . 100 matrizes . 56 animais comercializados/ano",
            "maiores_itens_pct": {"Mao de obra": 42.9, "Reposicao animais": 18.5},
        },
        {
            # Primeiro painel de CRIA do Centro-Oeste — o buraco que faltava.
            # Campo Futuro/CNA em Juara/MT (400 vacas, 266 paridas), publicado
            # no boletim de fevereiro/2023 comparando duas opções de manejo de
            # pastagem. Adotado o cenário de ADUBAÇÃO, que é o de menor custo
            # dos dois e o que o próprio boletim recomenda; o de aluguel de
            # pasto dá COE R$ 175,51/@ e COT R$ 245,54/@.
            #
            # Aritmética conferida: receita R$ 344,46/@ menos COE R$ 169,97 dá
            # margem bruta de R$ 174,49 (publicada: 174,49) e menos COT
            # R$ 240,00 dá margem líquida de R$ 104,46 (publicada: 104,46).
            # Fecha ao centavo nas duas linhas.
            "local": "Juara, MT", "uf": "MT", "ano": 2022,
            "coe_arroba": 169.97,
            "cot_arroba": 240.00,
            "receita_arroba": 344.46,
            "descricao": "400 vacas . 266 paridas . cria com adubação de pastagem",
            "maiores_itens_pct": {"Manut. pastagem": 48.9, "Mao de obra": 16.0},
        },
        {
            # Único painel da base com os TRÊS níveis publicados, e o que
            # justifica a escolha do nível COE — ver a nota logo abaixo.
            # Embrapa Pantanal, Circular Técnica 126 (out/2024), dados de 2023.
            # Metodologia painel Cepea/Famasul/Senar. Aritmética conferida: as
            # três margens do documento reproduzem ao centavo a partir de
            # receita R$ 2.930.387,26 e 10.643,45@ vendidas (arroba de carcaça).
            "local": "Pantanal de Corumbá, MS", "uf": "MS", "ano": 2023,
            "coe_arroba": 223.21,
            "cot_arroba": 260.76,
            "ct_arroba":  431.09,
            "descricao": "10.000 ha . 4.657 cab . cria extensiva . 0,30 UA/ha",
            "maiores_itens_pct": {"Mao de obra": 36.0, "Suplem. mineral": 28.0},
        },
    ],
    "RECRIA_ENGORDA": [
        {
            "local": "Paragominas, PA", "uf": "PA", "ano": 2025,
            "coe_arroba": 183.50,
            "descricao": "500 ha pastagem . recria e terminacao a pasto",
            "maiores_itens_pct": {"Reposicao animais": 62.2, "Suplem. mineral": 10.5},
        },
        {
            "local": "Colorado d'Oeste, RO", "uf": "RO", "ano": 2024,
            "coe_arroba": 171.88,
            "descricao": "recria e engorda em semiconfinamento . 100 cab abatidas/ano",
            "maiores_itens_pct": {"Aquisicao animais": 51.6, "Alimentacao": 19.8},
        },
    ],
}

# Compatibilidade: o painel de referência (o primeiro) por modalidade. Código
# antigo que lia um ponto continua lendo um ponto.
COE_CAMPO_FUTURO = {mod: paineis[0] for mod, paineis in COE_PAINEIS.items()}

FONTE_COE = "Campo Futuro / CNA Brasil (paineis PA 2025, RO e RS 2024)"

# Vizinhança por região: quando não há painel na UF da fazenda, um painel da
# mesma região é comparação mais honesta que um do outro extremo do país. As
# UFs sem painel caem no mais próximo pela região; sem isso, na faixa inteira.
_REGIAO_UF = {
    "N":  {"AC", "AM", "AP", "PA", "RO", "RR", "TO"},
    "NE": {"AL", "BA", "CE", "MA", "PB", "PE", "PI", "RN", "SE"},
    "CO": {"DF", "GO", "MS", "MT"},
    "SE": {"ES", "MG", "RJ", "SP"},
    "S":  {"PR", "RS", "SC"},
}
_UF_REGIAO = {uf: reg for reg, ufs in _REGIAO_UF.items() for uf in ufs}


def posicao_valor(valor: float, lo: float, hi: float) -> str:
    """Posição do valor frente a uma faixa: 'abaixo', 'dentro' ou 'acima'."""
    if valor < lo:
        return "abaixo"
    if valor > hi:
        return "acima"
    return "dentro"


def avaliar_multifonte(indicador: str, valor: float) -> list:
    """Confronta um indicador contra cada fonte institucional que o publica.

    Args:
        indicador: 'prenhez' ou 'natalidade'.
        valor: Valor observado, em % (0–100).

    Returns:
        Lista de `{fonte, faixa, posicao}`, uma por fonte.

    Raises:
        ValueError: Se o indicador não tiver benchmark multi-fonte.
    """
    fontes = _MULTIFONTE.get(indicador)
    if fontes is None:
        raise ValueError(
            f"Sem benchmark multi-fonte para '{indicador}'. "
            f"Disponíveis: {', '.join(_MULTIFONTE)}."
        )
    return [
        {"fonte": nome, "faixa": (lo, hi), "posicao": posicao_valor(valor, lo, hi)}
        for nome, (lo, hi) in fontes.items()
    ]


def _classe_desfrute(valor: float) -> str:
    for teto, classe in _DESFRUTE_ESCALA:
        if valor < teto:
            return classe
    return "muito_alto"


def avaliar_desfrute(modalidade: str, valor: float) -> dict | None:
    """Avalia o desfrute frente à faixa esperada da modalidade.

    Returns:
        `{modalidade, faixa, posicao, classe, fonte}` ou None se a modalidade
        não tiver faixa de desfrute conhecida.
    """
    faixa = DESFRUTE_MODALIDADE.get(modalidade)
    if faixa is None:
        return None
    lo, hi = faixa
    return {
        "modalidade": modalidade,
        "valor": round(valor, 1),
        "faixa": faixa,
        "posicao": posicao_valor(valor, lo, hi),
        "classe": _classe_desfrute(valor),
        "fonte": "Metodologia Análise Crédito Pecuária",
    }


def avaliar_desembolso(modalidade: str, valor_real: float) -> dict | None:
    """Confronta o desembolso (R$/cab/mês) contra Média e Top Rentáveis.

    Menor é melhor: abaixo do Top = excelente; entre Top e Média = bom;
    acima da Média = atenção (custo acima do produtor médio nacional).

    Returns:
        `{modalidade, valor, media, top, nivel, fonte}` ou None se não houver
        perfil financeiro para a modalidade.
    """
    chave = _MAP_DESEMBOLSO.get(modalidade)
    ref = DESEMBOLSO_INTTEGRA.get(chave) if chave else None
    if ref is None:
        return None
    if valor_real <= ref["top"]:
        nivel = "excelente"
    elif valor_real <= ref["media"]:
        nivel = "bom"
    else:
        nivel = "atencao"
    return {
        "modalidade": modalidade,
        "valor": round(valor_real, 2),
        "media": ref["media"],
        "top": ref["top"],
        "nivel": nivel,
        "fonte": FONTE_DESEMBOLSO,
    }


# Modalidades que NÃO têm painel próprio e caem no de RECRIA_ENGORDA. O painel
# cobre as duas fases e vende BOI TERMINADO (~20@); uma recria isolada entrega
# animal de ~13,5@ e uma engorda isolada parte de animal já formado. São
# perímetros diferentes, e comparar o COE por arroba entre eles infla o nosso
# lado — na recria, em cerca de 48% só por causa do peso de saída.
#
# Foi um erro meu ao criar o mapeamento: apliquei a mesma lógica de "cai no
# painel mais próximo" que uso para UF, onde ela é inofensiva, a um eixo onde
# ela troca o produto comparado. É a mesma classe do COE contra CT.
#
# Como não existe painel publicado de recria isolada, a comparação continua
# sendo feita — mas declarada como parcial, e sem disparar o aviso automático
# de custo fora da praça, que não teria como distinguir custo alto de
# perímetro diferente.
_PERIMETRO_PARCIAL = {
    "RECRIA":  "o painel cobre recria E engorda e vende boi terminado (~20@); "
               "esta análise cobre só a recria, que entrega animal de ~13,5@",
    "ENGORDA": "o painel cobre recria E engorda e inclui a fase de recria; "
               "esta análise cobre só a terminação",
}


def paineis_coe(modalidade: str) -> list:
    """Painéis Campo Futuro da modalidade, ou lista vazia se não houver.

    RECRIA e ENGORDA isoladas caem no painel de RECRIA_ENGORDA — com a ressalva
    de perímetro registrada em `_PERIMETRO_PARCIAL`.
    """
    chave = modalidade if modalidade in COE_PAINEIS else (
        "RECRIA_ENGORDA" if modalidade in ("RECRIA", "ENGORDA") else None
    )
    return list(COE_PAINEIS.get(chave, ())) if chave else []


def _painel_da_praca(paineis: list, uf: str | None) -> dict:
    """Painel mais próximo da praça: mesma UF > mesma região > o primeiro.

    Comparar a fazenda com o painel da própria praça não muda muito o número
    (a dispersão entre painéis é de ~7%), mas muda o que o analista lê: um
    parecer que confronta uma fazenda rondoniense com Paragominas/PA soa
    errado mesmo quando o valor está certo, e um analista que desconfia da
    referência para de usar o aviso.
    """
    uf = (uf or "").strip().upper()
    if uf:
        for p in paineis:
            if p["uf"] == uf:
                return p
        regiao = _UF_REGIAO.get(uf)
        if regiao:
            for p in paineis:
                if _UF_REGIAO.get(p["uf"]) == regiao:
                    return p
    return paineis[0]


def avaliar_coe(modalidade: str, coe_calculado: float,
                uf: str | None = None) -> dict | None:
    """Compara o COE calculado (R$/@ vendida) com os painéis Campo Futuro.

    `coe_calculado = custo_operacional_anual / arrobas_vendidas`. Numerador e
    referência são ambos COE — custo de DESEMBOLSO, incluindo compra de
    animais, sem depreciação nem remuneração do capital (ver o cabeçalho de
    COE_PAINEIS).

    A comparação é contra a FAIXA entre os painéis da modalidade, não contra um
    ponto: `delta_pct` mede quanto o custo passa do TETO da faixa. Dentro da
    faixa o delta é zero — a fazenda está entre dois painéis reais, e não há o
    que apontar.

    Args:
        modalidade: CRIA, RECRIA, ENGORDA, RECRIA_ENGORDA ou CICLO_COMPLETO.
        coe_calculado: COE da fazenda, em R$/arroba vendida.
        uf: UF da fazenda, para escolher o painel da praça mais próxima.

    Returns:
        Dict com o comparativo, ou None se não houver painel para a
        modalidade ou o COE calculado não for positivo.
    """
    paineis = paineis_coe(modalidade)
    if not paineis or coe_calculado <= 0:
        return None

    ref = _painel_da_praca(paineis, uf)
    valores = [p["coe_arroba"] for p in paineis]
    faixa_lo, faixa_hi = min(valores), max(valores)

    if coe_calculado > faixa_hi:
        delta_pct = (coe_calculado - faixa_hi) / faixa_hi * 100
    else:
        delta_pct = 0.0

    if coe_calculado <= faixa_lo * 0.90:
        nivel = "excelente"
    elif coe_calculado <= faixa_lo:
        nivel = "bom"
    elif coe_calculado <= faixa_hi:
        nivel = "dentro"          # entre dois painéis publicados
    elif coe_calculado <= faixa_hi * 1.20:
        nivel = "atencao"
    else:
        nivel = "alto"

    parcial = _PERIMETRO_PARCIAL.get(modalidade)
    return {
        "coe_calculado":  round(coe_calculado, 2),
        "coe_referencia": ref["coe_arroba"],
        "faixa_paineis":  (faixa_lo, faixa_hi),
        "n_paineis":      len(paineis),
        "local_ref":      ref["local"],
        "uf_ref":         ref["uf"],
        "descricao_ref":  ref["descricao"],
        "maiores_itens_pct": dict(ref["maiores_itens_pct"]),
        "delta_pct":      round(delta_pct, 1),
        "nivel":          nivel,
        "base":           "COE (desembolso operacional, inclui compra de animais)",
        "perimetro_parcial": parcial,
        "comparavel":     parcial is None,
        "fonte":          FONTE_COE,
    }


def avaliar_nacional(modalidade: str, dados: dict) -> dict:
    """Monta o painel nacional a partir dos indicadores disponíveis.

    Args:
        modalidade: CRIA, RECRIA, ENGORDA ou CICLO_COMPLETO.
        dados: Dict com quaisquer de `prenhez`, `natalidade` (% 0–100),
            `desfrute` (% 0–100) e `desembolso` (R$/cab/mês). Só o que estiver
            presente é avaliado.

    Returns:
        `{modalidade, multifonte, desfrute, desembolso}`.
    """
    multifonte = []
    for indicador in ("prenhez", "natalidade"):
        if dados.get(indicador) is not None:
            multifonte.append({
                "indicador": indicador,
                "valor": round(float(dados[indicador]), 1),
                "fontes": avaliar_multifonte(indicador, float(dados[indicador])),
            })

    desfrute = None
    if dados.get("desfrute") is not None:
        desfrute = avaliar_desfrute(modalidade, float(dados["desfrute"]))

    desembolso = None
    if dados.get("desembolso") is not None:
        desembolso = avaliar_desembolso(modalidade, float(dados["desembolso"]))

    return {
        "modalidade": modalidade,
        "multifonte": multifonte,
        "desfrute": desfrute,
        "desembolso": desembolso,
    }


# ── Desfrute real: o que sobra depois de descontar compra e queda de estoque ──
#
# O sistema sempre mediu desfrute como `vendas ÷ rebanho inicial`. É a forma
# simplificada, e é a que a ficha de referência usa (a de recria de 700 cabeças
# declara 45%, e a projeção bate 43,4%) — por isso ela CONTINUA sendo a que se
# compara com DESFRUTE_MODALIDADE. Trocá-la tornaria as faixas incomparáveis.
#
# O problema é que essa forma não distingue duas coisas muito diferentes:
#
#     vender a produção do ano          (o negócio funcionando)
#     vender o próprio plantel          (o negócio sendo consumido)
#
# A literatura resolve isso descontando compras e a variação de estoque:
#
#     desfrute = [(estoque_final − estoque_inicial − compras + vendas)
#                 ÷ estoque_inicial] × 100
#
# Medido na projeção de um ciclo completo de 4.250 cabeças que fechava o ano em
# 2.494: a forma simplificada dizia 53,4% — dentro da faixa de um bom produtor.
# A forma completa dizia 12,0%. A diferença inteira era plantel virando caixa.
#
# UNIDADE IMPORTA. A fórmula aceita cabeças ou arrobas. Em cabeças, recria e
# engorda dão perto de zero por construção — compram um animal e vendem um
# animal; o que elas produzem é PESO, não cabeça. Por isso o afastamento entre
# as duas formas só é sinal de liquidação onde o rebanho deveria se reproduzir.
_CICLOS_QUE_REPRODUZEM = frozenset({"CRIA", "CRIA_RECRIA", "CICLO_COMPLETO"})

# Distância entre as duas formas a partir da qual a venda deixa de ser produção
# e passa a ser plantel. Não é norma do setor — é limiar de política nosso.
DESFRUTE_AFASTAMENTO_ALERTA = 15.0


def calcular_desfrute(vendas: float, estoque_inicial: float,
                      estoque_final: float | None = None,
                      compras: float = 0.0) -> dict:
    """Desfrute nas duas formas, na mesma unidade em que os argumentos vierem.

    `simplificado` é `vendas ÷ estoque_inicial` — comparável com
    DESFRUTE_MODALIDADE e com a ficha de referência.

    `real` desconta compras e variação de estoque. Fica `None` quando
    `estoque_final` não é informado, porque sem ele a conta não existe.
    """
    if estoque_inicial <= 0:
        return {"simplificado": 0.0, "real": None, "afastamento": None}

    simplificado = vendas / estoque_inicial * 100.0
    if estoque_final is None:
        return {"simplificado": round(simplificado, 1), "real": None,
                "afastamento": None}

    real = ((estoque_final - estoque_inicial - compras + vendas)
            / estoque_inicial * 100.0)
    return {
        "simplificado": round(simplificado, 1),
        "real":         round(real, 1),
        "afastamento":  round(simplificado - real, 1),
    }


def alerta_liquidacao(modalidade: str, desfrute: dict) -> dict | None:
    """Sinaliza venda que veio do plantel, não da produção.

    Só se aplica a ciclos que reproduzem: em recria e engorda a diferença
    entre as duas formas é estrutural (compra-se e vende-se cabeça; o produto
    é arroba) e não indica nada.
    """
    if modalidade not in _CICLOS_QUE_REPRODUZEM:
        return None
    real = desfrute.get("real")
    afast = desfrute.get("afastamento")
    if real is None or afast is None or afast < DESFRUTE_AFASTAMENTO_ALERTA:
        return None
    return {
        "modalidade":   modalidade,
        "simplificado": desfrute["simplificado"],
        "real":         real,
        "afastamento":  afast,
        "severidade":   "erro" if real < 0 else "alerta",
        "mensagem": (
            f"Desfrute aparente de {desfrute['simplificado']:.1f}% mas real de "
            f"{real:.1f}%: {afast:.1f} pontos vieram da redução do plantel, "
            f"não da produção do ano. Venda de rebanho não se repete no ano "
            f"seguinte — confira o prazo do crédito contra essa projeção."
        ),
    }
