"""Pipeline orquestrador de Compliance Socioambiental & ESG.

Gera o Dossiê Socioambiental conclusivo com base no MCR 2-1 e Resolução CMN 5.081.
"""
from __future__ import annotations

from typing import Any

from .car_rules import calcular_metricas_florestais
from .checker import verificar_restricoes_publicas
from .models import (
    DossieSocioambiental,
    ParecerESG,
    StatusCAR,
)


def analisar_compliance_socioambiental(payload: dict[str, Any]) -> DossieSocioambiental:
    """Executa a análise completa de conformidade socioambiental da operação de crédito rural.

    Args:
        payload: Dict contendo dados do CAR, da propriedade e certidões/consultas públicas.
            Exemplo:
            {
                'numero_car': 'MT-5107602-C75A20B7631E44AA8BF0D382A13894E2',
                'status_car': 'ATIVO',
                'bioma': 'AMAZONIA_CERRADO',
                'area_total_ha': 1000.0,
                'area_reserva_legal_ha': 360.0,
                'area_app_ha': 50.0,
                'embargo_ibama': False,
                'embargo_icmbio': False,
                'trabalho_escravo_mte': False,
                'sobreposicao_terra_indigena': False,
                'sobreposicao_unidade_conservacao': False,
            }
    """
    car_res = calcular_metricas_florestais(
        numero_car=payload.get('numero_car', ''),
        status=payload.get('status_car', StatusCAR.ATIVO),
        bioma=payload.get('bioma', 'CERRADO'),
        area_total_ha=float(payload.get('area_total_ha', 0.0) or 0.0),
        area_reserva_legal_ha=float(payload.get('area_reserva_legal_ha', 0.0) or 0.0),
        area_app_ha=float(payload.get('area_app_ha', 0.0) or 0.0),
    )

    checagens_res = verificar_restricoes_publicas(payload)

    motivos_impedimento: list[str] = []
    alertas_monitoramento: list[str] = []

    # 1. Impeditivos Absolutos pelo Banco Central (MCR 2-1 e CMN 5.081)
    if checagens_res.embargo_ibama:
        motivos_impedimento.append('Embargo ambiental ativo pelo IBAMA (Veto absoluto MCR 2-1).')
    if checagens_res.embargo_icmbio:
        motivos_impedimento.append('Embargo ambiental ativo pelo ICMBio (Veto absoluto MCR 2-1).')
    if checagens_res.trabalho_escravo_mte:
        motivos_impedimento.append('Inscrição no Cadastro de Empregadores de Trabalho Escravo MTE.')
    if checagens_res.sobreposicao_terra_indigena:
        motivos_impedimento.append('Sobreposição territorial com Terra Indígena (Veto MCR 2-1).')
    if checagens_res.sobreposicao_unidade_conservacao:
        motivos_impedimento.append('Sobreposição com Unidade de Conservação de Proteção Integral.')

    if car_res.status in (StatusCAR.CANCELADO, StatusCAR.SUSPENSO):
        motivos_impedimento.append(
            f'CAR da propriedade com status {car_res.status.value}. Operação vetada até regularização.'
        )

    if not car_res.sintaxe_valida:
        alertas_monitoramento.append('Número do CAR informado não possui formato SICAR padronizado.')

    # 2. Alertas de Regularidade Florestal
    if not car_res.em_conformidade_florestal and car_res.area_total_ha > 0:
        alertas_monitoramento.append(
            f'Déficit de Reserva Legal ({abs(car_res.deficit_ou_excedente_rl_ha):.1f} ha). '
            'Exige comprovação de adesão ao PRA (Programa de Regularização Ambiental) ou compensação.'
        )

    if car_res.status == StatusCAR.PENDENTE:
        alertas_monitoramento.append('CAR em status PENDENTE de análise/homologação pelo órgão estadual.')

    # 3. Determinação do Parecer Conclusivo e Score ESG
    if motivos_impedimento:
        parecer = ParecerESG.IMPEDIDO_BACEN
        score_esg = max(0, 40 - len(motivos_impedimento) * 15)
        selo = 'CRÉDITO IMPEDIDO PELO BANCO CENTRAL (MCR 2-1)'
        elegivel = False
        recs = (
            'OPERAÇÃO DE CRÉDITO OU EMISSÃO DE CPR VETADA. Foram identificados impeditivos '
            'regulatórios de ordem socioambiental conforme as Resoluções CMN 4.945 e 5.081. '
            'O crédito não pode ser deferido até que as restrições sejam formalmente baixadas nos órgãos emissores.'
        )
    elif alertas_monitoramento:
        parecer = ParecerESG.ALERTA
        score_esg = max(60, 95 - len(alertas_monitoramento) * 12)
        selo = 'REGULARIDADE CONDICIONADA (EXIGE PRA/HOMOLOGAÇÃO)'
        elegivel = True
        recs = (
            'CRÉDITO ELEGÍVEL COM CONDICIONANTES. Não há embargos ativos ou trabalho escravo. '
            'Recomenda-se solicitar termo de adesão ao PRA (se houver déficit de RL) e acompanhar a homologação do CAR.'
        )
    else:
        parecer = ParecerESG.APROVADO
        score_esg = 100
        selo = 'EM CONFORMIDADE COM CMN 5.081/23 (ESG VERIFICADO)'
        elegivel = True
        recs = (
            'PARECER SOCIOAMBIENTAL FAVORÁVEL. Propriedade com CAR ativo e reserva florestal regular. '
            'Certidões negativas no IBAMA, ICMBio e MTE. Elegibilidade plena para Crédito Rural, Barter e CPR.'
        )

    return DossieSocioambiental(
        parecer=parecer,
        score_esg=score_esg,
        selo_conformidade_cmn=selo,
        elegivel_credito_rural=elegivel,
        car=car_res,
        checagens=checagens_res,
        motivos_impedimento=motivos_impedimento,
        alertas_monitoramento=alertas_monitoramento,
        recomendacoes_comite=recs,
    )
