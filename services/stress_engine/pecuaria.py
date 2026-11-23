"""Estresse pecuário: tesoura de margem e ponto de ruptura da arroba.

Motor puro, aditivo: não altera `scenarios.py`. Aqui o resultado do período é
modelado por seus vetores zootécnico-financeiros, para que a tesoura de margem
(receita cai enquanto o custo sobe) seja simulada de forma explícita:

    receita   = arrobas_vendidas × preço_da_arroba
    custo     = reposição + suplementação/confinamento + outros
    resultado = receita − custo
    DSCR      = resultado / serviço_da_dívida

Mesma definição de DSCR do `run_stress_tests` (resultado ÷ serviço da dívida),
sem arredondamento: a prova inversa do ponto de ruptura exige precisão total.

Limites de DSCR: `DSCR_APROVAR` e `DSCR_RESSALVA` vêm de
`payment_capacity_engine.dscr` (fonte única, política de crédito); nada é
redefinido aqui.

PREMISSAS DOS CHOQUES (percentuais sobre o valor-base, ex.: -15 = queda de 15%)

- `arroba_pct`: preço de venda da arroba. Afeta só a receita.
- `reposicao_pct`: preço do bezerro/reposição. Afeta só o custo de reposição.
- `suplementacao_pct`: sal mineral, proteinado, ração, confinamento. Afeta só
  o custo de suplementação.
- `volume_pct`: arrobas vendidas. É o canal da SECA SEVERA / pressão de
  lotação: menos pasto reduz ganho de peso e/ou obriga a vender menos peso.
  Premissa conservadora: o custo de reposição NÃO cai junto com o volume (o
  bezerro já foi comprado e o custo fixo do rebanho permanece); a seca
  encarece a nutrição via `suplementacao_pct`.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, replace
from decimal import Decimal
from numbers import Real
from types import MappingProxyType
from typing import Any, Mapping

from services.payment_capacity_engine.dscr import DSCR_APROVAR, DSCR_RESSALVA
from services.proveniencia import e_parametro, politica

# Folga relativa para decidir "exatamente no limite" sem ruído de ponto flutuante.
_TOL_REL = 1e-12
# Tetos de sanidade: evitam overflow/inf nos resultados e entrada absurda.
_MAX_VALOR = 1e15
_MIN_POSITIVO = 0.01  # arrobas/serviço: ou 0, ou >= 0,01 (evita DSCR/preço = inf)
_MAX_PCT = 300.0
_FONTE_CHOQUE = "Premissa de estresse da instituição"


def _numero(
    valor: Any,
    nome: str,
    *,
    minimo: float,
    maximo: float,
    zero_ou_minimo_positivo: bool = False,
) -> float:
    """Valida e converte para float. Aceita int/float/Decimal/numpy; rejeita
    bool, NaN, inf e valores fora de [minimo, maximo]."""
    if isinstance(valor, bool) or not isinstance(valor, (Real, Decimal)):
        raise ValueError(f"{nome} deve ser numérico, recebido {valor!r}")
    numero = float(valor)
    if not math.isfinite(numero):
        raise ValueError(f"{nome} deve ser finito, recebido {valor!r}")
    if not minimo <= numero <= maximo:
        raise ValueError(f"{nome} deve estar entre {minimo:g} e {maximo:g}, recebido {numero:g}")
    if zero_ou_minimo_positivo and 0 < numero < _MIN_POSITIVO:
        raise ValueError(f"{nome} deve ser 0 ou >= {_MIN_POSITIVO:g}, recebido {numero:g}")
    return numero


@dataclass(frozen=True)
class BasePecuaria:
    """Cenário-base anual. Receita zero (arrobas ou preço zero) é aceita."""

    arrobas_vendidas: float
    preco_arroba: float
    custo_reposicao: float
    custo_suplementacao: float
    custo_outros: float
    servico_divida: float

    def __post_init__(self) -> None:
        for campo in (
            "arrobas_vendidas",
            "preco_arroba",
            "custo_reposicao",
            "custo_suplementacao",
            "custo_outros",
            "servico_divida",
        ):
            object.__setattr__(
                self,
                campo,
                _numero(
                    getattr(self, campo),
                    campo,
                    minimo=0.0,
                    maximo=_MAX_VALOR,
                    zero_ou_minimo_positivo=campo in ("arrobas_vendidas", "servico_divida"),
                ),
            )

    @property
    def receita(self) -> float:
        return self.arrobas_vendidas * self.preco_arroba

    @property
    def custo(self) -> float:
        return self.custo_reposicao + self.custo_suplementacao + self.custo_outros


@dataclass(frozen=True)
class ChoquePecuario:
    """Choque percentual (ver premissas no docstring do módulo).

    Limites: cada percentual em [-100, +300]. Os cenários padrão usam
    `Parametro` de origem POLÍTICA: em comitê as premissas se discutem."""

    nome: str
    descricao: str = ""
    arroba_pct: float = 0.0
    reposicao_pct: float = 0.0
    suplementacao_pct: float = 0.0
    volume_pct: float = 0.0

    def __post_init__(self) -> None:
        if not isinstance(self.nome, str) or not self.nome.strip():
            raise ValueError(f"nome deve ser texto não vazio, recebido {self.nome!r}")
        # >= -100: abaixo disso o preço/volume/custo ficaria negativo.
        for campo in ("arroba_pct", "reposicao_pct", "suplementacao_pct", "volume_pct"):
            valor = getattr(self, campo)
            convertido = _numero(valor, campo, minimo=-100.0, maximo=_MAX_PCT)
            # Parametro (float) mantém a proveniência; só converte o que não é.
            if not e_parametro(valor):
                object.__setattr__(self, campo, convertido)


def _p(valor: float, rotulo: str):
    return politica(valor, _FONTE_CHOQUE, rotulo=f"Choque pecuário: {rotulo}")


CENARIOS_PECUARIOS: Mapping[str, ChoquePecuario] = MappingProxyType(
    {
        c.nome: c
        for c in (
            ChoquePecuario(
                "queda_arroba",
                "Arroba do boi gordo cai 15%; custos inalterados.",
                arroba_pct=_p(-15, "arroba_pct"),
            ),
            ChoquePecuario(
                "alta_reposicao",
                "Bezerro/reposição encarece 20%; preço de venda inalterado.",
                reposicao_pct=_p(20, "reposicao_pct"),
            ),
            ChoquePecuario(
                "alta_suplementacao",
                "Suplementação/confinamento encarece 20%.",
                suplementacao_pct=_p(20, "suplementacao_pct"),
            ),
            ChoquePecuario(
                "seca_severa",
                "Seca severa/pressão de lotação: volume de arrobas -15% "
                "(menor ganho de peso) e suplementação +30%.",
                volume_pct=_p(-15, "volume_pct"),
                suplementacao_pct=_p(30, "suplementacao_pct"),
            ),
            ChoquePecuario(
                "tesoura_margem_moderada",
                "Tesoura moderada: arroba -10%, reposição +15%, suplementação +20%.",
                arroba_pct=_p(-10, "arroba_pct"),
                reposicao_pct=_p(15, "reposicao_pct"),
                suplementacao_pct=_p(20, "suplementacao_pct"),
            ),
            ChoquePecuario(
                "tesoura_margem_severa",
                "Tesoura severa: arroba -20%, reposição +25%, suplementação +30% "
                "e volume -10% (seca).",
                arroba_pct=_p(-20, "arroba_pct"),
                reposicao_pct=_p(25, "reposicao_pct"),
                suplementacao_pct=_p(30, "suplementacao_pct"),
                volume_pct=_p(-10, "volume_pct"),
            ),
        )
    }
)


@dataclass(frozen=True)
class ResultadoEstresse:
    nome: str
    receita: float
    custo: float
    resultado: float
    margem_liquida: float | None  # resultado / receita; None se receita = 0
    dscr: float | None  # None se não há dívida
    classificacao: str  # aprovar | ressalva | negar | sem_divida


def _fator(pct: float) -> float:
    return 1.0 + pct / 100.0


def aplicar_choque(base: BasePecuaria, choque: ChoquePecuario) -> BasePecuaria:
    """Base com o choque aplicado. Útil para compor: ruptura da arroba sob
    estresse de custo = `ponto_ruptura_arroba(aplicar_choque(base, sem_arroba))`."""
    return replace(
        base,
        arrobas_vendidas=base.arrobas_vendidas * _fator(choque.volume_pct),
        preco_arroba=base.preco_arroba * _fator(choque.arroba_pct),
        custo_reposicao=base.custo_reposicao * _fator(choque.reposicao_pct),
        custo_suplementacao=base.custo_suplementacao * _fator(choque.suplementacao_pct),
    )


def _classificar(dscr: float | None) -> str:
    if dscr is None:
        return "sem_divida"
    if dscr >= DSCR_APROVAR:
        return "aprovar"
    if dscr >= DSCR_RESSALVA:
        return "ressalva"
    return "negar"


def _avaliar(nome: str, b: BasePecuaria) -> ResultadoEstresse:
    receita, custo = b.receita, b.custo
    resultado = receita - custo
    dscr = resultado / b.servico_divida if b.servico_divida > 0 else None
    return ResultadoEstresse(
        nome=nome,
        receita=receita,
        custo=custo,
        resultado=resultado,
        margem_liquida=resultado / receita if receita > 0 else None,
        dscr=dscr,
        classificacao=_classificar(dscr),
    )


def simular_choque(base: BasePecuaria, choque: ChoquePecuario) -> ResultadoEstresse:
    """Aplica um choque (isolado ou composto) e classifica pelo DSCR."""
    if not isinstance(base, BasePecuaria) or not isinstance(choque, ChoquePecuario):
        raise ValueError("base deve ser BasePecuaria e choque deve ser ChoquePecuario")
    return _avaliar(choque.nome, aplicar_choque(base, choque))


def simular_cenarios_pecuarios(
    base: BasePecuaria,
    cenarios: Mapping[str, ChoquePecuario] | None = None,
) -> dict[str, ResultadoEstresse]:
    """Roda o conjunto padrão (ou o informado) e inclui o `base` como referência."""
    cenarios = CENARIOS_PECUARIOS if cenarios is None else cenarios
    saida = {"base": _avaliar("base", base)}
    for nome, choque in cenarios.items():
        if nome == "base":
            raise ValueError('"base" é reservado para o cenário de referência')
        if isinstance(choque, ChoquePecuario) and choque.nome != nome:
            raise ValueError(f"chave {nome!r} difere de choque.nome {choque.nome!r}")
        saida[nome] = simular_choque(base, choque)
    return saida


@dataclass(frozen=True)
class RupturaArroba:
    """Ponto de ruptura para UM alvo de DSCR.

    status:
      - "folga": preço-base acima do mínimo; `margem_seguranca_pct` > 0.
      - "ja_em_ruptura": preço-base abaixo (ou exatamente no) mínimo;
        `margem_seguranca_pct` <= 0 — negativo = quanto a arroba precisaria subir.
      - "sem_divida": serviço da dívida = 0, não há ruptura por dívida.
      - "sem_volume": sem arrobas vendidas, nenhum preço cobre a dívida.
    `preco_minimo` é None em "sem_divida" e "sem_volume". É o ínfimo: por
    ruído de ponto flutuante o DSCR no próprio `preco_minimo` pode sair 1 ulp
    abaixo do alvo e `_classificar` (>=, como em dscr.py) cair uma faixa;
    quem for usá-lo como preço deve somar uma folga (ex.: arredondar para
    cima em centavos). Margem exatamente zero conta como ruptura (política
    conservadora), embora DSCR == alvo seja classificado como passando.
    `margem_seguranca_pct` = (preço_base − preço_mínimo) / preço_base × 100, ou
    seja, a queda percentual máxima suportada da arroba; None se preço-base = 0
    ou sem preço mínimo.
    """

    dscr_alvo: float
    status: str
    preco_base: float
    preco_minimo: float | None
    margem_seguranca_pct: float | None
    em_ruptura: bool


def _ruptura(base: BasePecuaria, alvo: float) -> RupturaArroba:
    s, a, p0 = base.servico_divida, base.arrobas_vendidas, base.preco_arroba
    if s == 0:
        return RupturaArroba(alvo, "sem_divida", p0, None, None, False)
    if a == 0:
        return RupturaArroba(alvo, "sem_volume", p0, None, None, True)
    # DSCR = (a·P − C)/S = alvo  ⇒  P* = (C + alvo·S)/a   (C, S >= 0 ⇒ P* >= 0)
    p_min = (base.custo + alvo * s) / a
    margem = (p0 - p_min) / p0 * 100.0 if p0 > 0 else None
    if p0 > p_min * (1 + _TOL_REL):
        status, em_ruptura = "folga", False
    else:
        status, em_ruptura = "ja_em_ruptura", True
        if margem is not None and p0 >= p_min * (1 - _TOL_REL):
            margem = 0.0  # no limite dentro da tolerância de ponto flutuante
    return RupturaArroba(alvo, status, p0, p_min, margem, em_ruptura)


@dataclass(frozen=True)
class PontoRupturaArroba:
    ressalva: RupturaArroba  # DSCR = DSCR_RESSALVA
    aprovar: RupturaArroba  # DSCR = DSCR_APROVAR


def ponto_ruptura_arroba(base: BasePecuaria) -> PontoRupturaArroba:
    """Preço mínimo da arroba para o DSCR atingir exatamente `DSCR_RESSALVA`
    e `DSCR_APROVAR`, e a queda máxima suportada em relação ao preço-base."""
    if not isinstance(base, BasePecuaria):
        raise ValueError("base deve ser BasePecuaria")
    return PontoRupturaArroba(
        ressalva=_ruptura(base, float(DSCR_RESSALVA)),
        aprovar=_ruptura(base, float(DSCR_APROVAR)),
    )
