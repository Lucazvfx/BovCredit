"""Modelos de dados para culturas anuais e grãos (Soja, Milho Safrinha, Algodão...).

Diferente da lavoura perene — cuja produção depende da idade acumulada do talhão ao
longo dos anos —, as culturas anuais operam no ciclo Safra/Safrinha:
    1ª Safra (Verão)    — Plantio set–dez, colheita jan–abr (ex: Soja, Milho Verão)
    2ª Safra (Safrinha) — Plantio jan–mar, colheita jun–ago (ex: Milho Safrinha, Algodão)
    3ª Safra / Irrigado — Opcional em áreas irrigadas/pivô

NENHUM NÚMERO AGRONÔMICO MORA AQUI. Produtividade (sc/ha), custos (COE/COT em R$/ha)
e preços (R$/sc) são entradas declaradas pelo analista ou produtor.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

SAFRA_VERAO = '1_SAFRA'
SAFRA_SAFRINHA = '2_SAFRA'
SAFRA_IRRIGADO = '3_SAFRA'

_SAFRAS_VALIDAS = (SAFRA_VERAO, SAFRA_SAFRINHA, SAFRA_IRRIGADO)


@dataclass(frozen=True, slots=True)
class CulturaSafra:
    """Uma cultura plantada em determinada janela (Safra ou Safrinha)."""
    cultura: str
    safra_tipo: str
    area_ha: float
    produtividade_ha: float
    preco_unitario: float
    coe_ha: float
    cot_ha: float | None = None
    unidade: str = 'sc'
    identificacao: str = ''

    def __post_init__(self):
        if not str(self.cultura or '').strip():
            raise ValueError('cultura não pode ser vazia')
        if float(self.area_ha) <= 0:
            raise ValueError(f'área inválida ({self.area_ha} ha) para {self.cultura}')
        if float(self.produtividade_ha) <= 0:
            raise ValueError(f'produtividade inválida ({self.produtividade_ha}) para {self.cultura}')
        if float(self.preco_unitario) <= 0:
            raise ValueError(f'preço unitário inválido ({self.preco_unitario}) para {self.cultura}')
        if float(self.coe_ha) < 0:
            raise ValueError(f'COE/ha não pode ser negativo para {self.cultura}')
        if self.cot_ha is not None and float(self.cot_ha) < float(self.coe_ha):
            raise ValueError(f'COT/ha ({self.cot_ha}) não pode ser menor que o COE/ha ({self.coe_ha})')

    @property
    def cot_efetivo_ha(self) -> float:
        """COT declarado ou, se omitido, assume o COE."""
        return float(self.cot_ha) if self.cot_ha is not None else float(self.coe_ha)

    @property
    def producao_total(self) -> float:
        """Volume físico total produzido (ex: sacas de 60kg)."""
        return round(float(self.area_ha) * float(self.produtividade_ha), 2)

    @property
    def receita_bruta(self) -> float:
        """Receita bruta esperada (R$)."""
        return round(self.producao_total * float(self.preco_unitario), 2)

    @property
    def coe_total(self) -> float:
        """Custo Operacional Efetivo total (R$) — desembolso direto."""
        return round(float(self.area_ha) * float(self.coe_ha), 2)

    @property
    def cot_total(self) -> float:
        """Custo Operacional Total (R$) — desembolso + depreciação."""
        return round(float(self.area_ha) * self.cot_efetivo_ha, 2)

    @property
    def margem_contribuicao_total(self) -> float:
        """Margem de contribuição (Receita - COE)."""
        return round(self.receita_bruta - self.coe_total, 2)

    @property
    def resultado_operacional_total(self) -> float:
        """Resultado operacional (Receita - COT)."""
        return round(self.receita_bruta - self.cot_total, 2)

    @property
    def breakeven_produtividade(self) -> float:
        """Ponto de equilíbrio em produtividade (sc/ha para cobrir o COE)."""
        if self.preco_unitario <= 0:
            return 0.0
        return round(self.coe_ha / self.preco_unitario, 2)

    @property
    def breakeven_preco(self) -> float:
        """Ponto de equilíbrio em preço (R$/sc para cobrir o COE com a produtividade esperada)."""
        if self.produtividade_ha <= 0:
            return 0.0
        return round(self.coe_ha / self.produtividade_ha, 2)

    @property
    def margem_seguranca_sc_ha(self) -> float:
        """Quantas sc/ha o produtor pode perder antes de entrar no prejuízo operacional."""
        return round(self.produtividade_ha - self.breakeven_produtividade, 2)


@dataclass(frozen=True, slots=True)
class PlanoSafra:
    """Conjunto de culturas e safras planejadas para um ano-safra agrícola."""
    culturas: tuple[CulturaSafra, ...]
    ano_agricola: str = '2026/27'
    ano_base: int = 2026
    despesas_administrativas: float = 0.0

    def __post_init__(self):
        if not self.culturas:
            raise ValueError('plano de safra sem culturas informadas')
        if float(self.despesas_administrativas) < 0:
            raise ValueError('despesas administrativas não podem ser negativas')

    @property
    def area_fisica_estimada_ha(self) -> float:
        """Área física da fazenda: estimada como o maior bloco plantado em uma mesma safra."""
        areas_por_janela: dict[str, float] = {}
        for c in self.culturas:
            areas_por_janela[c.safra_tipo] = areas_por_janela.get(c.safra_tipo, 0.0) + c.area_ha
        return max(areas_por_janela.values()) if areas_por_janela else 0.0

    @property
    def area_plantada_total_ha(self) -> float:
        """Soma de todas as áreas plantadas (safra + safrinha)."""
        return round(sum(c.area_ha for c in self.culturas), 2)

    @property
    def receita_total(self) -> float:
        """Receita consolidada de todas as culturas do ano-safra."""
        return round(sum(c.receita_bruta for c in self.culturas), 2)

    @property
    def coe_total(self) -> float:
        """COE consolidado de todas as culturas."""
        return round(sum(c.coe_total for c in self.culturas), 2)

    @property
    def cot_total(self) -> float:
        """COT consolidado de todas as culturas + despesas administrativas."""
        return round(sum(c.cot_total for c in self.culturas) + float(self.despesas_administrativas), 2)

    @property
    def resultado_operacional(self) -> float:
        """Resultado operacional total (Receita - COT)."""
        return round(self.receita_total - self.cot_total, 2)
