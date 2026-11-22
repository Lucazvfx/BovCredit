"""
Fluxo de caixa sazonal por ciclo pecuário e recomendação de cronograma.

POR QUE ISTO EXISTE. O DSCR anual mede se a geração de caixa do ano cobre o
serviço da dívida. Ele não vê o calendário: uma cria vende o bezerro em
abril–junho e paga suplementação o ano todo; uma engorda compra o magro no
início do ano e só recebe na entressafra. Com parcela mensal, o produtor pode
ter DSCR 1,33 e ficar sem caixa de janeiro a maio. Este módulo projeta os 12
meses, acha o vale de caixa e testa se pagar semestral ou anual, nos meses de
pico de entrada, resolve.

PREMISSAS (declaradas, não escondidas)
- `parcela_divida` é o valor de UMA parcela na frequência informada. O serviço
  anual é parcela × pagamentos por ano (12, 2 ou 1).
- As alternativas semestral/anual mantêm o MESMO serviço anual: é uma
  simulação de calendário, sem juros adicionais de repactuação. A taxa real da
  nova estrutura precisa ser cotada com o credor.
- Os perfis sazonais são premissa estilizada do motor (calendário típico de
  pecuária de corte no Brasil Central, seca de junho a outubro), não série
  medida. Estão marcados como REFERENCIA na proveniência; calibre com o
  histórico da propriedade quando houver.
- O DSCR aqui é (receita − custo operacional) / serviço anual da dívida, na
  faixa de aprovação da política (`DSCR_APROVAR`).

MATEMÁTICA. Todo o cálculo é em centavos inteiros. Pesos são inteiros em ‰
(soma 1000) e o resíduo de cada distribuição vai para os meses de maior resto
(maiores restos), então a soma dos 12 meses é igual ao total anual, sem perder
um centavo. Só na saída os valores viram `float` com 2 casas.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from services.proveniencia import referencia

from .dscr import DSCR_APROVAR

SISTEMAS = ("cria", "recria", "engorda", "ciclo_completo")
FREQUENCIAS = ("mensal", "semestral", "anual")
_PAGAMENTOS_ANO = {"mensal": 12, "semestral": 2, "anual": 1}

MESES = ("jan", "fev", "mar", "abr", "mai", "jun",
         "jul", "ago", "set", "out", "nov", "dez")

# Teto de sanidade (R$ 1 trilhão): evita overflow e digitação absurda.
VALOR_MAXIMO = 1e12

_TOTAL_PERMIL = 1000


@dataclass(frozen=True, slots=True)
class PerfilSazonal:
    """Distribuição mensal (em ‰, soma 1000) de entradas e saídas do ano."""

    sistema: str
    entradas_permil: tuple
    saidas_permil: tuple
    descricao: str

    @property
    def pesos_entradas(self) -> tuple:
        return tuple(p / _TOTAL_PERMIL for p in self.entradas_permil)

    @property
    def pesos_saidas(self) -> tuple:
        return tuple(p / _TOTAL_PERMIL for p in self.saidas_permil)


def _perfil(sistema, entradas, saidas, descricao):
    for nome, pesos in (("entradas", entradas), ("saidas", saidas)):
        if len(pesos) != 12 or sum(pesos) != _TOTAL_PERMIL or min(pesos) < 0:
            raise ValueError(
                f"perfil '{sistema}': pesos de {nome} devem ter 12 meses, "
                f"não negativos, somando {_TOTAL_PERMIL}‰.")
    return PerfilSazonal(sistema, tuple(entradas), tuple(saidas), descricao)


#             jan feb mar abr mai jun jul ago set out nov dez
PERFIS: dict = {
    # Cria: vende bezerro desmamado de abril a julho (pico em maio) e descarta
    # vacas em nov–dez. Saída sobe na seca (suplementação, jun–set) e na
    # vacinação de maio/novembro.
    "cria": _perfil(
        "cria",
        entradas=(0, 0, 40, 180, 260, 220, 120, 60, 20, 0, 40, 60),
        saidas=(70, 60, 60, 60, 90, 100, 110, 110, 110, 90, 70, 70),
        descricao="Venda de desmama concentrada em abr–jul; suplementação na seca.",
    ),
    # Recria: compra o desmamado em abr–jul (reposição pesada), segura na seca
    # com suplemento e vende o garrote/novilho ao fim das águas seguintes.
    "recria": _perfil(
        "recria",
        entradas=(20, 60, 160, 230, 200, 80, 20, 0, 0, 40, 90, 100),
        saidas=(30, 30, 50, 150, 180, 160, 110, 80, 70, 50, 40, 50),
        descricao="Compra de reposição em abr–jul; venda de recriados em mar–mai.",
    ),
    # Engorda: compra o magro após as águas (fev–mai) e vende o boi gordo na
    # entressafra (jul–out), quando a arroba costuma sustentar preço.
    "engorda": _perfil(
        "engorda",
        entradas=(20, 20, 30, 40, 60, 110, 150, 170, 170, 120, 60, 50),
        saidas=(60, 70, 130, 170, 150, 100, 70, 60, 50, 40, 50, 50),
        descricao="Compra de magro em fev–mai; boi gordo vendido em jul–out.",
    ),
    # Ciclo completo: bezerro, recria e terminação sobrepostos na mesma
    # fazenda; as entradas se espalham porque há sempre lote em fase de venda.
    "ciclo_completo": _perfil(
        "ciclo_completo",
        entradas=(20, 30, 60, 110, 140, 130, 110, 110, 100, 80, 60, 50),
        saidas=(70, 70, 80, 100, 100, 100, 100, 100, 90, 80, 60, 50),
        descricao="Entradas diluídas (desmama + gordo); custos maiores de abr–ago.",
    ),
}

# Proveniência: o perfil é premissa estilizada, não medição.
PROVENIENCIA_PERFIL = {
    s: referencia(
        _TOTAL_PERMIL,
        "Calendário típico de pecuária de corte (Brasil Central) — premissa "
        "do motor, não série medida",
        rotulo=f"Perfil sazonal — {s}",
        nota="Pesos em ‰ (soma 1000). Calibrar com o histórico da propriedade.",
    )
    for s in SISTEMAS
}


# ──────────────────────────── validação ────────────────────────────

def _texto_valido(valor: Any, nome: str, validos: tuple) -> str:
    if not isinstance(valor, str):
        raise ValueError(f"{nome} deve ser texto; recebido {type(valor).__name__}.")
    norm = valor.strip().lower()
    if norm not in validos:
        raise ValueError(
            f"{nome} desconhecido: {valor!r}. Esperado um de {list(validos)}.")
    return norm


def _centavos(valor: Any, nome: str) -> int:
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        raise ValueError(f"{nome} deve ser numérico; recebido {valor!r}.")
    if not math.isfinite(valor):
        raise ValueError(f"{nome} deve ser finito; recebido {valor!r}.")
    if valor < 0:
        raise ValueError(f"{nome} não pode ser negativo; recebido {valor!r}.")
    if valor > VALOR_MAXIMO:
        raise ValueError(f"{nome} acima do limite de {VALOR_MAXIMO:.0f}; recebido {valor!r}.")
    return int(round(valor * 100))


def _reais(centavos: int) -> float:
    return round(centavos / 100, 2)


# ──────────────────────────── distribuição ────────────────────────────

def distribuir_centavos(total: int, pesos_permil: tuple) -> list:
    """Reparte `total` centavos pelos 12 meses sem perder nenhum centavo."""
    base = [total * p // _TOTAL_PERMIL for p in pesos_permil]
    restos = [total * p % _TOTAL_PERMIL for p in pesos_permil]
    faltam = total - sum(base)
    ordem = sorted(range(12), key=lambda i: (-restos[i], i))
    for i in ordem[:faltam]:
        base[i] += 1
    return base


def _meses_de_pagamento(frequencia: str, entradas_permil: tuple) -> list:
    """Índices (0–11) dos meses de pagamento; parcelas não mensais caem no
    mês de maior entrada de cada janela (empate → o mais cedo)."""
    if frequencia == "mensal":
        return list(range(12))
    janelas = [range(0, 12)] if frequencia == "anual" else [range(0, 6), range(6, 12)]
    return [max(j, key=lambda i: (entradas_permil[i], -i)) for j in janelas]


def _servico_mensal(servico_anual: int, meses_pgto: list) -> list:
    """Divide o serviço anual entre os meses de pagamento (resto vai ao primeiro)."""
    n = len(meses_pgto)
    parcela, resto = divmod(servico_anual, n)
    out = [0] * 12
    for k, m in enumerate(meses_pgto):
        out[m] = parcela + (resto if k == 0 else 0)
    return out


# ──────────────────────────── núcleo ────────────────────────────

def _simular(entradas, saidas, servico, giro) -> dict:
    meses, acum = [], giro
    for i in range(12):
        saldo = entradas[i] - saidas[i] - servico[i]
        acum += saldo
        meses.append({
            "mes": i + 1,
            "rotulo": MESES[i],
            "entradas": _reais(entradas[i]),
            "saidas_operacionais": _reais(saidas[i]),
            "servico_divida": _reais(servico[i]),
            "saldo_mensal": _reais(saldo),
            "saldo_acumulado": _reais(acum),
            "_acum_c": acum,
        })
    piores = min(m["_acum_c"] for m in meses)
    mes_pior = next(m["mes"] for m in meses if m["_acum_c"] == piores)
    deficit = [m["mes"] for m in meses if m["_acum_c"] < 0]
    for m in meses:
        del m["_acum_c"]
    return {
        "meses": meses,
        "vale_caixa": _reais(piores),
        "mes_vale": mes_pior,
        "meses_deficit": deficit,
        "saldo_final": _reais(acum),
        "_vale_c": piores,
    }


def _estrutura(freq, meses_pgto, resultado) -> dict:
    return {
        "frequencia": freq,
        "meses_pagamento": [m + 1 for m in meses_pgto],
        "vale_caixa": resultado["vale_caixa"],
        "mes_vale": resultado["mes_vale"],
        "meses_deficit": resultado["meses_deficit"],
        "elimina_vale": not resultado["meses_deficit"],
    }


def projetar_fluxo_ciclo(
    *,
    sistema: str,
    receita_anual: float,
    custo_operacional_anual: float,
    parcela_divida: float,
    frequencia: str = "mensal",
    capital_giro_inicial: float = 0.0,
) -> dict:
    """Fluxo mensal de 12 meses, vale de caixa e, se couber, recomendação.

    Retorna dict (convenção do motor de capacidade de pagamento) com
    `meses`, `vale_caixa`, `meses_deficit`, `dscr_anual`, `quebra_caixa_com_dscr_ok`,
    `recomendacao` e `justificativa`. Levanta `ValueError` para entrada inválida.
    """
    sistema = _texto_valido(sistema, "sistema produtivo", SISTEMAS)
    frequencia = _texto_valido(frequencia, "frequência", FREQUENCIAS)
    receita = _centavos(receita_anual, "receita_anual")
    custo = _centavos(custo_operacional_anual, "custo_operacional_anual")
    parcela = _centavos(parcela_divida, "parcela_divida")
    giro = _centavos(capital_giro_inicial, "capital_giro_inicial")

    perfil = PERFIS[sistema]
    entradas = distribuir_centavos(receita, perfil.entradas_permil)
    saidas = distribuir_centavos(custo, perfil.saidas_permil)

    servico_anual = parcela * _PAGAMENTOS_ANO[frequencia]
    meses_pgto = _meses_de_pagamento(frequencia, perfil.entradas_permil)
    servico = _servico_mensal(servico_anual, meses_pgto) if servico_anual else [0] * 12

    base = _simular(entradas, saidas, servico, giro)
    sem_divida = _simular(entradas, saidas, [0] * 12, giro)

    fc_anual = receita - custo
    # Sem dívida não há divisão: DSCR indefinido, não infinito nem zero.
    dscr = round(fc_anual / servico_anual, 4) if servico_anual else None
    if servico_anual:
        dscr_ok = dscr >= float(DSCR_APROVAR)
    else:
        dscr_ok = fc_anual >= 0
    quebra = bool(servico_anual and dscr_ok and base["meses_deficit"])

    recomendacao = None
    if frequencia == "mensal" and servico_anual and base["meses_deficit"]:
        recomendacao = _recomendar(entradas, saidas, servico_anual, giro,
                                   perfil, base)

    return {
        "sistema": sistema,
        "frequencia": frequencia,
        "meses_pagamento": [m + 1 for m in meses_pgto],
        "meses": base["meses"],
        "totais": {
            "entradas": _reais(sum(entradas)),
            "saidas_operacionais": _reais(sum(saidas)),
            "servico_divida": _reais(sum(servico)),
            "saldo_final": base["saldo_final"],
        },
        "vale_caixa": base["vale_caixa"],
        "mes_vale": base["mes_vale"],
        "meses_deficit": base["meses_deficit"],
        "vale_operacional": sem_divida["vale_caixa"],
        "servico_divida_anual": _reais(servico_anual),
        "dscr_anual": dscr,
        "dscr_anual_suficiente": dscr_ok,
        "quebra_caixa_com_dscr_ok": quebra,
        "recomendacao": recomendacao,
        "justificativa": _justificar(sistema, dscr, dscr_ok, base, sem_divida,
                                     quebra, recomendacao, servico_anual),
        "proveniencia": PROVENIENCIA_PERFIL[sistema].para_dict(),
    }


def _recomendar(entradas, saidas, servico_anual, giro, perfil, base) -> dict:
    alternativas = {}
    for freq in ("semestral", "anual"):
        meses_pgto = _meses_de_pagamento(freq, perfil.entradas_permil)
        res = _simular(entradas, saidas,
                       _servico_mensal(servico_anual, meses_pgto), giro)
        alternativas[freq] = (_estrutura(freq, meses_pgto, res), res["_vale_c"])

    # Melhor = vale menos profundo; empate → semestral (menos concentração de
    # risco de pagamento num único mês).
    ordem = ("semestral", "anual")
    melhor = max(ordem, key=lambda f: (alternativas[f][1], -ordem.index(f)))
    melhora = alternativas[melhor][1] > base["_vale_c"]
    escolhida = alternativas[melhor][0] if melhora else None
    return {
        "estrutura_recomendada": melhor if melhora else "mensal",
        "melhora_vale": melhora,
        "elimina_vale": bool(escolhida and escolhida["elimina_vale"]),
        "vale_mensal": base["vale_caixa"],
        "reducao_vale": _reais(alternativas[melhor][1] - base["_vale_c"]) if melhora else 0.0,
        "alternativas": [alternativas[f][0] for f in ordem],
    }


def _brl(v: float) -> str:
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _justificar(sistema, dscr, dscr_ok, base, sem_divida, quebra, rec,
                servico_anual) -> list:
    out = []
    if servico_anual:
        out.append(
            f"DSCR anual {dscr:.2f} "
            f"({'atende' if dscr_ok else 'não atende'} a faixa de aprovação "
            f"{float(DSCR_APROVAR):.2f}).")
    else:
        out.append("Sem serviço de dívida: DSCR não se aplica.")
    if base["meses_deficit"]:
        meses = ", ".join(MESES[m - 1] for m in base["meses_deficit"])
        out.append(
            f"Caixa acumulado negativo em {meses}; pior ponto "
            f"{_brl(base['vale_caixa'])} em {MESES[base['mes_vale'] - 1]}.")
        if sem_divida["meses_deficit"]:
            out.append(
                f"Parte do vale é operacional (sem dívida o pior ponto já seria "
                f"{_brl(sem_divida['vale_caixa'])}): exige capital de giro, não "
                f"só reescalonamento.")
    else:
        out.append("Caixa acumulado não fica negativo em nenhum mês.")
    if quebra:
        out.append(
            "ATENÇÃO: DSCR anual suficiente, mas a parcela neste calendário "
            "gera quebra de caixa sazonal.")
    if rec:
        if rec["melhora_vale"]:
            efeito = "elimina" if rec["elimina_vale"] else "reduz"
            out.append(
                f"Pagamento {rec['estrutura_recomendada']} nos meses de pico de "
                f"entrada {efeito} o vale (de {_brl(rec['vale_mensal'])}); "
                f"mesmo serviço anual, sem custo de repactuação.")
        else:
            out.append(
                "Nenhuma estrutura semestral/anual melhora o vale; manter "
                "mensal e cobrir o vale com capital de giro.")
    return out
