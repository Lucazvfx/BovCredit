"""Detecção de inconsistências no rebanho declarado (análise de crédito).

Recebe o vetor de composição do rebanho por faixa etária/sexo (o mesmo padrão
da Ficha de Rebanho estadual e do template `modelo_composicao_rebanho.xlsx`) e
verifica se a composição é biologicamente/tecnicamente plausível, sinalizando
as divergências que um analista de crédito procura antes de aprovar o crédito.

Ordem do vetor (10 posições), idêntica a `ml_engine.classificar`:
    0 f00_F  1 f00_M   (0–4 meses)
    2 f05_F  3 f05_M   (5–12 meses)
    4 f13_F  5 f13_M   (13–24 meses)
    6 f25_F  7 f25_M   (25–36 meses)
    8 fac_F  9 fac_M   (acima de 36 meses)

Convenções: matrizes = f25_F + fac_F; touros = fac_M; bezerros = f00_F + f00_M.
"""
from __future__ import annotations

ERRO = "erro"
ALERTA = "alerta"
OK = "ok"

_PESO = {ERRO: 25, ALERTA: 8, OK: 0}


def estimar_compra_animais(v: list, natalidade: float = 0.70) -> dict:
    """
    Estima compra de animais desmamados confrontando a coorte de 0–12 meses
    declarada com a produção biologicamente possível do próprio rebanho.

        produção própria = matrizes × natalidade
        compra estimada  = coorte 0–12m observada − produção própria

    Técnica do material "Análise de Crédito na Pecuária Bovina" (caso real do
    Pará): uma propriedade com 256 matrizes produz ~179 bezerros a 70% de
    natalidade, mas declarava 556 animais de 0–12 meses — os 377 excedentes
    só podem ter sido comprados.

    Importa para o crédito por dois motivos: muda o enquadramento (cria pura
    vira sistema misto cria+recria) e revela um desembolso de compra que não
    aparece em nenhuma declaração do produtor.

    Returns:
        Dict com `coorte_0_12m`, `producao_propria`, `compra_estimada`,
        `indica_compra` (bool) e `proporcao_comprada` (fração da coorte).
    """
    if len(v) != 10:
        raise ValueError(f"Esperado vetor de 10 posições, recebido {len(v)}.")
    v = [max(float(x), 0.0) for x in v]

    matrizes = v[6] + v[8]
    coorte = v[0] + v[1] + v[2] + v[3]          # 0–4m + 5–12m
    producao = matrizes * max(natalidade, 0.0)
    compra = coorte - producao

    # Margem de 15% absorve variação de natalidade e defasagem entre safras;
    # só acima disso a diferença é grande demais para ser produção própria.
    limiar = max(producao * 0.15, 5.0)
    indica = compra > limiar

    return {
        'coorte_0_12m':       round(coorte, 1),
        'producao_propria':   round(producao, 1),
        'compra_estimada':    round(max(compra, 0.0), 1),
        'indica_compra':      bool(indica),
        'proporcao_comprada': round(max(compra, 0.0) / coorte, 3) if coorte > 0 else 0.0,
        'natalidade_usada':   natalidade,
    }


def _flag(codigo, severidade, titulo, mensagem, declarado=None, esperado=None):
    div = None
    if declarado is not None and esperado not in (None, 0):
        div = round((declarado - esperado) / esperado * 100, 1)
    return {
        "codigo": codigo,
        "severidade": severidade,
        "titulo": titulo,
        "mensagem": mensagem,
        "declarado": None if declarado is None else round(declarado, 1),
        "esperado": None if esperado is None else round(esperado, 1),
        "divergencia_pct": div,
    }


def analisar_consistencia(
    v: list,
    *,
    natalidade_min: float = 0.55,
    natalidade_max: float = 0.85,
    matriz_touro_max: float = 40.0,
    matriz_touro_min: float = 15.0,
    prop_sexual_bezerro: tuple = (0.8, 1.25),
    reposicao_min: float = 0.10,
    piramide_fator: float = 1.5,
) -> dict:
    """Analisa a consistência de um rebanho declarado.

    Args:
        v: Lista de 10 quantidades por faixa etária/sexo (ver ordem no módulo).
        natalidade_min: Piso da taxa de natalidade plausível (bezerros/matriz).
        natalidade_max: Teto da taxa de natalidade plausível.
        matriz_touro_max: Máx. de matrizes por touro antes de sinalizar (monta natural).
        matriz_touro_min: Mín. de matrizes por touro antes de sinalizar excesso.
        prop_sexual_bezerro: Faixa (min, max) plausível da razão F/M ao nascer.
        reposicao_min: Razão mínima novilhas/matrizes para o rebanho se sustentar.
        piramide_fator: Fator acima do qual uma faixa mais velha excede a mais nova.

    Returns:
        Dict com `total_animais`, `matrizes`, `score_consistencia` (0–100),
        `resumo` (contagem por severidade) e `flags` (lista de checagens).

    Raises:
        ValueError: Se `v` não tiver exatamente 10 posições.
    """
    if len(v) != 10:
        raise ValueError(f"Esperado vetor de 10 posições, recebido {len(v)}.")
    v = [max(float(x), 0.0) for x in v]
    total = sum(v)

    bezerros = v[0] + v[1]
    matrizes = v[6] + v[8]
    touros = v[9]

    # ── v[6] estava contado NOS DOIS lados ───────────────────────────────────
    #
    # Era `novilhas_repo = v[4] + v[6]`, com `matrizes = v[6] + v[8]` logo
    # acima. As mesmas 150 fêmeas de 25–36 meses eram simultaneamente o plantel
    # a repor e a reposição dele.
    #
    # Num parecer real de 1.775 cabeças isso publicava "Reposição de 33% das
    # matrizes — adequada" onde a taxa verdadeira é 13%. O erro corria a favor
    # de aprovar: fazia um plantel apertado parecer folgado.
    #
    # Achado ao comparar com `avaliar_reposicao` (parametros_zootecnicos), que
    # nasceu do artigo da Embrapa-CPATSA e usa só v[4]. Os dois davam números
    # diferentes para a mesma coisa no mesmo documento — a classe de defeito
    # que já custou a sensibilidade e o benchmark de custo.
    #
    # QUAL DOS DOIS LADOS CEDEU, e por quê: v[6] segue como matriz, porque é
    # assim que ml_engine o trata em todo o motor (`va[6] + va[8]`). Mudar o
    # denominador do rebanho inteiro para acertar um flag seria o rabo abanando
    # o cachorro.
    #
    # FICA REGISTRADO O INCÔMODO: a faixa 25–36m como matriz contradiz
    # IDADE_PRIMEIRA_PARICAO_MESES (36,3 medido pela Embrapa, 40,0 no Pantanal
    # extensivo) — uma fêmea de 30 meses ainda não pariu. O motor documenta a
    # escolha em ml_engine.py:68. É item aberto, não desta correção.
    novilhas_repo = v[4]

    flags = []

    # 1. Bezerros vs esperado biológico (matrizes × natalidade)
    if matrizes == 0:
        if bezerros > 0:
            flags.append(_flag(
                "bezerros_vs_esperado", ERRO,
                "Bezerros sem matrizes",
                f"{bezerros:.0f} bezerros declarados sem nenhuma matriz — impossível.",
                declarado=bezerros, esperado=0.001))
        else:
            flags.append(_flag("bezerros_vs_esperado", OK,
                               "Bezerros vs esperado", "Sem matrizes e sem bezerros."))
    else:
        esp_min = matrizes * natalidade_min
        esp_max = matrizes * natalidade_max
        centro = matrizes * (natalidade_min + natalidade_max) / 2
        if bezerros > esp_max * 1.15:
            flags.append(_flag(
                "bezerros_vs_esperado", ERRO,
                "Bezerros acima do plausível",
                f"{bezerros:.0f} bezerros para {matrizes:.0f} matrizes excede o teto "
                f"biológico (~{esp_max:.0f}). Possível rebanho inflado.",
                declarado=bezerros, esperado=centro))
        elif bezerros < esp_min * 0.6:
            flags.append(_flag(
                "bezerros_vs_esperado", ALERTA,
                "Bezerros abaixo do esperado",
                f"{bezerros:.0f} bezerros para {matrizes:.0f} matrizes está abaixo do "
                f"piso esperado (~{esp_min:.0f}). Baixa eficiência ou subdeclaração.",
                declarado=bezerros, esperado=centro))
        else:
            flags.append(_flag(
                "bezerros_vs_esperado", OK, "Bezerros vs esperado",
                f"{bezerros:.0f} bezerros de 0–5 meses, compatível com {matrizes:.0f} matrizes.",
                declarado=bezerros, esperado=centro))

    # 1b. Compra de animais desmamados (coorte 0–12m vs produção própria).
    # Diferente da checagem acima: olha a coorte inteira de 0–12m e QUANTIFICA
    # o excedente. Excedente aqui não é rebanho inflado — é compra, e muda tanto
    # o enquadramento do sistema quanto o desembolso projetado.
    _nat_ref = (natalidade_min + natalidade_max) / 2
    compra_info = estimar_compra_animais(v, natalidade=_nat_ref)
    if compra_info['indica_compra']:
        _pct = compra_info['proporcao_comprada'] * 100
        flags.append(_flag(
            "compra_animais_desmama", ALERTA,
            "Compra de animais na desmama",
            f"{compra_info['coorte_0_12m']:.0f} animais de 0–12 meses para uma produção "
            f"própria de ~{compra_info['producao_propria']:.0f} "
            f"({matrizes:.0f} matrizes × {_nat_ref:.0%}). "
            f"Indica compra de ~{compra_info['compra_estimada']:.0f} desmamados "
            f"({_pct:.0f}% da coorte) — sistema misto, com desembolso de aquisição "
            f"não declarado.",
            declarado=compra_info['coorte_0_12m'],
            esperado=compra_info['producao_propria']))
    elif matrizes > 0:
        flags.append(_flag(
            "compra_animais_desmama", OK,
            "Compra de animais na desmama",
            f"Coorte de 0–12 meses ({compra_info['coorte_0_12m']:.0f}) compatível com "
            f"a produção própria (~{compra_info['producao_propria']:.0f}) — "
            f"sem indício de compra.",
            declarado=compra_info['coorte_0_12m'],
            esperado=compra_info['producao_propria']))

    # 2. Proporção sexual dos bezerros (~50/50 ao nascer)
    if bezerros >= 20:
        razao = v[0] / max(v[1], 1)
        lo, hi = prop_sexual_bezerro
        if razao < lo or razao > hi:
            flags.append(_flag(
                "prop_sexual_bezerros", ALERTA,
                "Proporção sexual de bezerros atípica",
                f"Razão fêmea/macho dos bezerros = {razao:.2f}, fora da faixa natural "
                f"({lo}–{hi}).", declarado=v[0], esperado=v[1]))
        else:
            flags.append(_flag("prop_sexual_bezerros", OK,
                               "Proporção sexual de bezerros", "Dentro do esperado (~50/50)."))
    else:
        flags.append(_flag("prop_sexual_bezerros", OK,
                           "Proporção sexual de bezerros", "Amostra pequena — não avaliado."))

    # 3. Relação touro:matriz
    if matrizes > 0:
        if touros == 0:
            flags.append(_flag(
                "touro_matriz", ALERTA,
                "Matrizes sem touro declarado",
                f"{matrizes:.0f} matrizes e nenhum touro. Plausível apenas com IATF/inseminação.",
                declarado=0, esperado=matrizes / matriz_touro_max))
        else:
            razao = matrizes / touros
            if razao > matriz_touro_max:
                flags.append(_flag(
                    "touro_matriz", ALERTA,
                    "Poucos touros para tantas matrizes",
                    # Dizia "Prenhez declarada implausível sem IATF" mesmo em
                    # ficha sem prenhez nenhuma declarada — o parecer real de
                    # 1.775 cabeças trazia essa frase com zero parâmetros
                    # declarados no rodapé. Afirmar que uma declaração é
                    # implausível quando ela não existe é afirmar sobre o nada.
                    f"{razao:.0f} matrizes por touro (> {matriz_touro_max:.0f}). "
                    f"A monta natural nessa proporção não sustenta prenhez alta — "
                    f"confirme se há IATF ou estação de monta.",
                    declarado=touros, esperado=matrizes / matriz_touro_max))
            elif razao < matriz_touro_min:
                flags.append(_flag(
                    "touro_matriz", ALERTA,
                    "Excesso de touros",
                    f"{razao:.0f} matrizes por touro (< {matriz_touro_min:.0f}).",
                    declarado=touros, esperado=matrizes / matriz_touro_min))
            else:
                flags.append(_flag("touro_matriz", OK, "Relação touro:matriz",
                                   f"{razao:.0f} matrizes por touro — adequado."))
    else:
        flags.append(_flag("touro_matriz", OK, "Relação touro:matriz", "Sem matrizes."))

    # 4. Continuidade da pirâmide etária (sem compra, faixa velha <= faixa nova)
    #    Não se aplica às faixas +36m (fêmeas adultas acumulam vários ciclos).
    transicoes = [
        ("machos 5–12 vs 0–4", v[3], v[1]),
        ("machos 13–24 vs 5–12", v[5], v[3]),
        ("machos 25–36 vs 13–24", v[7], v[5]),
        ("fêmeas 5–12 vs 0–4", v[2], v[0]),
        ("fêmeas 13–24 vs 5–12", v[4], v[2]),
        ("fêmeas 25–36 vs 13–24", v[6], v[4]),
    ]
    piramide_flags = [
        (nome, velha, nova) for nome, velha, nova in transicoes
        if velha > 20 and velha > nova * piramide_fator
    ]
    if piramide_flags:
        nome, velha, nova = piramide_flags[0]
        flags.append(_flag(
            "piramide_etaria", ALERTA,
            "Descontinuidade na pirâmide etária",
            f"{len(piramide_flags)} faixa(s) mais velha(s) maior(es) que a mais nova sem "
            f"compra declarada (ex: {nome}: {velha:.0f} vs {nova:.0f}). Animais 'aparecendo'.",
            declarado=velha, esperado=nova))
    else:
        flags.append(_flag("piramide_etaria", OK, "Pirâmide etária",
                           "Faixas etárias coerentes."))

    # 5. Reposição de fêmeas
    if matrizes > 50:
        taxa_repo = novilhas_repo / matrizes
        if taxa_repo < reposicao_min:
            flags.append(_flag(
                "reposicao_femeas", ALERTA,
                "Reposição de fêmeas insuficiente",
                f"Apenas {novilhas_repo:.0f} novilhas de reposição para {matrizes:.0f} "
                f"matrizes ({taxa_repo:.0%}). Rebanho não se sustenta.",
                declarado=novilhas_repo, esperado=matrizes * reposicao_min))
        else:
            flags.append(_flag("reposicao_femeas", OK, "Reposição de fêmeas",
                               f"Reposição de {taxa_repo:.0%} das matrizes — adequada."))
    else:
        flags.append(_flag("reposicao_femeas", OK, "Reposição de fêmeas",
                           "Rebanho pequeno — não avaliado."))

    resumo = {
        "erros": sum(1 for f in flags if f["severidade"] == ERRO),
        "alertas": sum(1 for f in flags if f["severidade"] == ALERTA),
        "ok": sum(1 for f in flags if f["severidade"] == OK),
    }
    penalidade = sum(_PESO[f["severidade"]] for f in flags)
    score = max(0, 100 - penalidade)

    return {
        "total_animais": int(total),
        "matrizes": int(matrizes),
        "score_consistencia": score,
        "resumo": resumo,
        "flags": flags,
    }


def analisar_consistencia_historica(
    v_atual: list,
    v_anterior: list,
    *,
    crescimento_max: float = 0.40,
    desaparecimento_min: int = 30,
) -> list:
    """Compara o rebanho atual com a declaração anterior e retorna flags adicionais.

    Args:
        v_atual: Vetor de 10 quantidades da declaração atual.
        v_anterior: Vetor de 10 quantidades da declaração anterior.
        crescimento_max: Percentual máximo de crescimento total plausível entre
            declarações sem compra declarada.
        desaparecimento_min: Mínimo de animais que, ao zerar de uma declaração
            para outra, gera um flag de desaparecimento.

    Returns:
        Lista de flags (mesmo formato que `analisar_consistencia`).
    """
    if len(v_atual) != 10 or len(v_anterior) != 10:
        return []

    v_atual = [max(float(x), 0.0) for x in v_atual]
    v_anterior = [max(float(x), 0.0) for x in v_anterior]
    flags = []
    total_atual = sum(v_atual)
    total_anterior = sum(v_anterior)

    # 1. Crescimento total implausível
    if total_anterior > 10:
        crescimento = (total_atual - total_anterior) / total_anterior
        if crescimento > crescimento_max:
            flags.append(_flag(
                "crescimento_implicavel", ERRO,
                "Crescimento implausível entre declarações",
                f"Rebanho cresceu {crescimento:.0%} desde a última declaração "
                f"({total_anterior:.0f} → {total_atual:.0f}). Acima do limite "
                f"biológico de {crescimento_max:.0%} sem compra declarada.",
                declarado=total_atual, esperado=total_anterior * (1 + crescimento_max)))

    # 2. Categoria que desaparece (venda seletiva escondida)
    NOMES_FAIXAS = [
        "fêmeas 0–4m", "machos 0–4m",
        "fêmeas 5–12m", "machos 5–12m",
        "fêmeas 13–24m", "machos 13–24m",
        "fêmeas 25–36m", "machos 25–36m",
        "fêmeas +36m", "machos +36m",
    ]
    for i, (ant, atu) in enumerate(zip(v_anterior, v_atual)):
        if ant >= desaparecimento_min and atu == 0:
            flags.append(_flag(
                f"desaparecimento_{i}", ERRO,
                f"Categoria desapareceu: {NOMES_FAIXAS[i]}",
                f"{ant:.0f} animais em {NOMES_FAIXAS[i]} na declaração anterior; "
                f"agora zerou. Venda seletiva ou subdeclaração.",
                declarado=atu, esperado=ant))

    return flags
