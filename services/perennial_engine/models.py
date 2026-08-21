"""Talhão de lavoura perene e a curva que descreve a produção dele.

O talhão é a coorte da lavoura. Assim como o rebanho projeta faixas etárias de
animais ao longo dos anos, a lavoura perene projeta blocos plantados em anos
diferentes: o que um talhão produz depende da idade dele, não do calendário.

NENHUM NÚMERO AGRONÔMICO MORA AQUI. A curva de produtividade é entrada
declarada — do analista, do laudo ou de fonte citável. Sem curva o motor
recusa projetar, porque uma curva chutada produz um DSCR com aparência de
cálculo e conteúdo de palpite.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

ALTA = 'alta'
BAIXA = 'baixa'
_FASES = (ALTA, BAIXA)


@dataclass(frozen=True, slots=True)
class Talhao:
    """Um bloco plantado, identificado pelo ano em que foi plantado.

    `fase_bienal` só vale para cultura com bienalidade (café): diz se o talhão
    está em ano de carga alta ou baixa na safra de referência. Talhões de um
    mesmo cafezal costumam estar em fases diferentes, e é isso que suaviza (ou
    não) a receita da fazenda — ver `PerennialState.fases_alinhadas`.
    """
    cultura: str
    area_ha: float
    ano_plantio: int
    identificacao: str = ''
    fase_bienal: str | None = None

    def __post_init__(self):
        if not str(self.cultura or '').strip():
            raise ValueError('talhão sem cultura')
        if float(self.area_ha) <= 0:
            raise ValueError(f'área inválida no talhão {self.identificacao or self.cultura}')
        if self.fase_bienal is not None and self.fase_bienal not in _FASES:
            raise ValueError(f'fase bienal deve ser {ALTA} ou {BAIXA}')

    def idade_em(self, ano_calendario: int) -> int:
        """Idade em anos completos. Zero ou negativo = ainda não plantado."""
        return ano_calendario - int(self.ano_plantio)


@dataclass(frozen=True, slots=True)
class CurvaProdutividade:
    """Quanto um hectare produz em função da IDADE do talhão.

    `fatores` mapeia idade → fração da produtividade plena. É onde cabem os dois
    fenômenos que decidem o parecer de uma perene, sem mecanismo especial para
    cada um:

      café  — formação sem receita nos primeiros anos, depois produção plena
      cana  — decaimento a cada corte: {1: 0, 2: 1.0, 3: 0.9, 4: 0.81, ...}

    `ciclo_anos` é a duração do ciclo do talhão — do plantio à reforma do
    canavial ou à recepa do cafezal. Passado o ciclo, o talhão volta à idade 1
    e refaz a curva desde a formação.

    `bienalidade` é a amplitude da alternância de carga do café — 0.15 significa
    1,15 no ano alto e 0,85 no baixo. Zero desliga.
    """
    cultura: str
    produtividade_plena: float
    unidade: str
    fatores: Mapping[int, float] = field(default_factory=dict)
    ciclo_anos: int | None = None
    bienalidade: float = 0.0
    fonte: str = ''

    def __post_init__(self):
        if float(self.produtividade_plena) <= 0:
            raise ValueError(f'produtividade plena inválida para {self.cultura}')
        if not self.fatores:
            raise ValueError(f'curva de {self.cultura} sem fatores por idade')
        if any(float(v) < 0 for v in self.fatores.values()):
            raise ValueError(f'curva de {self.cultura} com fator negativo')
        if not 0 <= float(self.bienalidade) < 1:
            raise ValueError('bienalidade deve estar entre 0 e 1')
        if self.ciclo_anos is not None and int(self.ciclo_anos) < 2:
            raise ValueError('ciclo deve ter mais de um ano')

    def fator(self, idade: int) -> float:
        """Fator da idade. Acima da maior idade declarada, mantém a última.

        Extrapolar para cima seria inventar; repetir o último ponto é o que o
        analista declarou sobre o talhão mais velho que ele descreveu.
        """
        if idade <= 0:
            return 0.0
        if idade in self.fatores:
            return float(self.fatores[idade])
        maior = max(self.fatores)
        return float(self.fatores[maior]) if idade > maior else 0.0


@dataclass(frozen=True, slots=True)
class PerennialState:
    """A lavoura na safra de referência."""
    talhoes: tuple[Talhao, ...]
    ano_base: int

    def __post_init__(self):
        if not self.talhoes:
            raise ValueError('lavoura sem talhões')

    @property
    def area_total_ha(self) -> float:
        return round(sum(float(t.area_ha) for t in self.talhoes), 4)

    @property
    def culturas(self) -> tuple[str, ...]:
        return tuple(sorted({t.cultura for t in self.talhoes}))

    def fases_alinhadas(self) -> bool:
        """True quando todo talhão bienal está na MESMA fase de carga.

        Importa para crédito: lavoura alinhada oscila inteira, e o ano de carga
        baixa aperta tudo ao mesmo tempo. Escalonada se compensa sozinha.
        """
        fases = {t.fase_bienal for t in self.talhoes if t.fase_bienal}
        return len(fases) == 1
