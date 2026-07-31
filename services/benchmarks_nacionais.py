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
DESFRUTE_MODALIDADE = {
    "CRIA": (18.0, 30.0),
    "RECRIA": (35.0, 55.0),
    "RECRIA_ENGORDA": (60.0, 85.0),
    "ENGORDA": (80.0, 120.0),
    "CICLO_COMPLETO": (20.0, 40.0),
}

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


# --- COE R$/@ vendida — Campo Futuro / CNA Brasil (agosto 2025, Para) ---------
# Paineis realizados em 3 municipios do PA. Unidade: R$/arroba VENDIDA.
# COE = Custo Operacional Efetivo / total de arrobas comercializadas no ano.
# O sistema converte: coe_calculado = custo_operacional / arrobas_vendidas_est
# onde arrobas_vendidas_est ~= receita_vendas / preco_arroba_ref.
COE_CAMPO_FUTURO = {
    "CICLO_COMPLETO": {
        "local": "Santana do Araguaia, PA",
        "coe_arroba": 164.61,
        "descricao": "5.100 cab . ciclo completo (cria + recria + engorda)",
        "maiores_itens_pct": {"Suplem. mineral": 51.3, "Mao de obra": 16.5},
    },
    "CRIA": {
        "local": "Altamira, PA",
        "coe_arroba": 189.76,
        "descricao": "150 matrizes . producao de bezerros",
        "maiores_itens_pct": {"Mao de obra": 18.2, "Suplem. mineral": 15.4},
    },
    "RECRIA_ENGORDA": {
        "local": "Paragominas, PA",
        "coe_arroba": 183.50,
        "descricao": "500 ha pastagem . recria e terminacao a pasto",
        "maiores_itens_pct": {"Reposicao animais": 62.2, "Suplem. mineral": 10.5},
    },
}
FONTE_COE = "Campo Futuro / CNA Brasil, agosto 2025 (Para)"


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


def avaliar_coe(modalidade: str, coe_calculado: float) -> dict | None:
    """Compara o COE calculado (R$/@ vendida) com referencia Campo Futuro 2025.

    coe_calculado = custo_operacional_anual / arrobas_vendidas_estimadas
    Referencia e para sistemas extensivos do Para - serve como piso de
    comparacao; sistemas mais intensivos tendem a ter COE maior.
    """
    ref_key = modalidade if modalidade in COE_CAMPO_FUTURO else (
        "RECRIA_ENGORDA" if modalidade in ("RECRIA", "ENGORDA") else None
    )
    ref = COE_CAMPO_FUTURO.get(ref_key) if ref_key else None
    if ref is None or coe_calculado <= 0:
        return None
    coe_ref = ref["coe_arroba"]
    delta_pct = (coe_calculado - coe_ref) / coe_ref * 100
    if coe_calculado <= coe_ref * 0.90:
        nivel = "excelente"
    elif coe_calculado <= coe_ref:
        nivel = "bom"
    elif coe_calculado <= coe_ref * 1.20:
        nivel = "atencao"
    else:
        nivel = "alto"
    return {
        "coe_calculado":  round(coe_calculado, 2),
        "coe_referencia": coe_ref,
        "local_ref":      ref["local"],
        "descricao_ref":  ref["descricao"],
        "delta_pct":      round(delta_pct, 1),
        "nivel":          nivel,
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
