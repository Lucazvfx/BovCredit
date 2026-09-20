"""Mecanismo de checagem de restrições socioambientais e normativas do Bacen.

Resoluções CMN 4.945/21 e CMN 5.081/23 (Manual de Crédito Rural - MCR 2-1).
"""
from __future__ import annotations

from typing import Any

from .models import ResultadoChecagensPublicas


def verificar_restricoes_publicas(
    dados_consulta: dict[str, Any] | None = None
) -> ResultadoChecagensPublicas:
    """Consolida as checagens públicas e regulatórias do imóvel e do proponente.

    Args:
        dados_consulta: Dicionário contendo flags de consultas de bureaus, certidões ou autodeclarações.
            Exemplo:
            {
                'embargo_ibama': False,
                'embargo_icmbio': False,
                'trabalho_escravo_mte': False,
                'sobreposicao_terra_indigena': False,
                'sobreposicao_unidade_conservacao': False,
                'certidao_ibama_numero': '...',
            }
    """
    dados = dados_consulta or {}
    detalhes: list[str] = []

    embargo_ibama = bool(dados.get('embargo_ibama', False))
    embargo_icmbio = bool(dados.get('embargo_icmbio', False))
    trabalho_escravo = bool(dados.get('trabalho_escravo_mte', False))
    ti = bool(dados.get('sobreposicao_terra_indigena', False))
    uc = bool(dados.get('sobreposicao_unidade_conservacao', False))

    if embargo_ibama:
        detalhes.append('IMPEDITIVO MCR 2-1: Imóvel ou titular com embargo ativo registrado no IBAMA.')
    else:
        detalhes.append('Consulta IBAMA: Nenhuma autuação ou termo de embargo impeditivo localizado.')

    if embargo_icmbio:
        detalhes.append('IMPEDITIVO MCR 2-1: Área com termo de embargo lavrado pelo ICMBio.')

    if trabalho_escravo:
        detalhes.append(
            'IMPEDITIVO BACEN/MTE: Proponente ou administrador inscrito no Cadastro de '
            'Empregadores que tenham submetido trabalhadores a condições análogas à de escravo.'
        )
    else:
        detalhes.append('Consulta MTE: Proponente não consta na Lista Suja do Trabalho Escravo.')

    if ti:
        detalhes.append('IMPEDITIVO MCR 2-1: Propriedade incide sobre Terra Indígena demarcada ou homologada.')

    if uc:
        detalhes.append('IMPEDITIVO MCR 2-1: Propriedade incide sobre Unidade de Conservação de Proteção Integral.')

    return ResultadoChecagensPublicas(
        embargo_ibama=embargo_ibama,
        embargo_icmbio=embargo_icmbio,
        trabalho_escravo_mte=trabalho_escravo,
        sobreposicao_terra_indigena=ti,
        sobreposicao_unidade_conservacao=uc,
        detalhes=detalhes,
    )
