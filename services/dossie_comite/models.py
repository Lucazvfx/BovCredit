"""Modelos de dados e estruturas para o Dossiê do Comitê de Crédito."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, List, Optional


@dataclass
class Proponente:
    nome: str = 'Produtor Rural'
    cpf_cnpj: str = '000.000.000-00'
    fazenda: str = 'Fazenda Modelo'
    municipio: str = 'Região Agropecuária'
    uf: str = 'BR'
    area_total_ha: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class OperacaoProposta:
    codigo_operacao: str = ''
    finalidade: str = 'Custeio Agropecuário / Barter / Investimento'
    valor_solicitado: float = 0.0
    prazo_meses: int = 12
    carencia_meses: int = 0
    juros_aa: float = 12.0
    sistema_amortizacao: str = 'PRICE'
    periodicidade: str = 'ANUAL'

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ConsolidadoAtividades:
    # Pecuária
    tem_pecuaria: bool = False
    rebanho_total_cabecas: int = 0
    rebanho_uas: float = 0.0
    taxa_desfrute_pct: float = 0.0
    receita_pecuaria_anual: float = 0.0

    # Agrícola
    tem_agricola: bool = False
    area_plantada_ha: float = 0.0
    culturas_principais: List[str] = field(default_factory=list)
    produtividade_media_sc_ha: float = 0.0
    breakeven_medio_sc_ha: float = 0.0
    receita_agricola_anual: float = 0.0

    # Resumo
    resumo_texto: str = ''

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ConsolidadoESG:
    numero_car: str = ''
    status_car: str = 'ATIVO'
    bioma: str = 'CERRADO'
    area_total_ha: float = 0.0
    reserva_legal_ha: float = 0.0
    reserva_legal_pct: float = 0.0
    exigencia_reserva_legal_pct: float = 20.0
    app_ha: float = 0.0
    status_ibama: str = 'REGULAR'
    status_icmbio: str = 'REGULAR'
    sobreposicao_indigena_quilombola: bool = False
    parecer_compliance: str = 'APROVADO'  # APROVADO, ALERTA, BLOQUEIO
    observacoes: List[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ConsolidadoGarantias:
    total_bens: int = 0
    valor_mercado_total: float = 0.0
    valor_liquidacao_forcada_total: float = 0.0
    ltv_mercado_pct: float = 0.0
    ltv_liquidacao_forcada_pct: float = 0.0
    faixa_risco_ltv: str = 'CONFORTAVEL'  # CONFORTAVEL, MODERADO, ELEVADO, CRITICO
    detalhes_itens: List[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class LinhaFluxoAnual:
    ano: int
    receita_bruta: float
    custos_despesas: float
    ebitda: float
    servico_divida: float
    fluxo_caixa_livre: float
    dscr: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ConsolidadoFinanceiro:
    receita_bruta_anual: float = 0.0
    custo_operacional_anual: float = 0.0
    ebitda_anual: float = 0.0
    margem_ebitda_pct: float = 0.0
    servico_divida_anual: float = 0.0
    dscr_ano_1: float = 0.0
    dscr_minimo: float = 0.0
    dscr_medio: float = 0.0
    ano_critico: int = 1
    projecao_plurianual: List[LinhaFluxoAnual] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            'receita_bruta_anual': self.receita_bruta_anual,
            'custo_operacional_anual': self.custo_operacional_anual,
            'ebitda_anual': self.ebitda_anual,
            'margem_ebitda_pct': self.margem_ebitda_pct,
            'servico_divida_anual': self.servico_divida_anual,
            'dscr_ano_1': self.dscr_ano_1,
            'dscr_minimo': self.dscr_minimo,
            'dscr_medio': self.dscr_medio,
            'ano_critico': self.ano_critico,
            'projecao_plurianual': [p.to_dict() for p in self.projecao_plurianual],
        }


@dataclass
class DeliberacaoComite:
    codigo_dossie: str = ''
    data_emissao: str = ''
    rating_final: str = 'A1'
    recomendacao: str = 'FAVORAVEL'  # FAVORAVEL, FAVORAVEL_COM_RESSALVAS, DESFAVORAVEL
    limite_sugerido: float = 0.0
    covenants_obrigatorios: List[str] = field(default_factory=list)
    parecer_risco_tecnico: str = ''
    parecer_gerencia_b2b: str = ''
    parecer_diretoria: str = ''
    hash_sha256: str = ''

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DossieComite:
    proponente: Proponente
    operacao: OperacaoProposta
    atividades: ConsolidadoAtividades
    esg: ConsolidadoESG
    garantias: ConsolidadoGarantias
    financeiro: ConsolidadoFinanceiro
    deliberacao: DeliberacaoComite

    def to_dict(self) -> dict[str, Any]:
        return {
            'proponente': self.proponente.to_dict(),
            'operacao': self.operacao.to_dict(),
            'atividades': self.atividades.to_dict(),
            'esg': self.esg.to_dict(),
            'garantias': self.garantias.to_dict(),
            'financeiro': self.financeiro.to_dict(),
            'deliberacao': self.deliberacao.to_dict(),
        }
