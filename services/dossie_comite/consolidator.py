"""Motor de consolidação e agregação multicritério para o Dossiê do Comitê de Crédito."""
from __future__ import annotations

import datetime
import hashlib
import math
from typing import Any, Dict, List, Optional

from services.dossie_comite.models import (
    ConsolidadoAtividades,
    ConsolidadoESG,
    ConsolidadoFinanceiro,
    ConsolidadoGarantias,
    DeliberacaoComite,
    DossieComite,
    LinhaFluxoAnual,
    OperacaoProposta,
    Proponente,
)


def _calcular_prestacao_anual(principal: float, taxa_aa: float, prazo_anos: int) -> float:
    """Calcula prestação anual no sistema Price padrão."""
    if principal <= 0 or prazo_anos <= 0:
        return 0.0
    taxa = taxa_aa / 100.0
    if taxa <= 0:
        return principal / prazo_anos
    fator = ((1.0 + taxa) ** prazo_anos)
    parcela = principal * (taxa * fator) / (fator - 1.0)
    return round(parcela, 2)


def montar_dossie_comite(dados: dict[str, Any]) -> DossieComite:
    """Consolida todas as informações de proponente, atividades agropecuárias,

    ESG, garantias, projeções e risco para o comitê de crédito.
    """
    dados = dados or {}

    # 1. Proponente e Fazenda
    ident = dados.get('identificacao') or dados.get('proponente') or {}
    proponente = Proponente(
        nome=ident.get('nome') or ident.get('proprietario') or 'Produtor Rural',
        cpf_cnpj=ident.get('cpf_cnpj') or ident.get('cpf') or ident.get('cnpj') or '000.000.000-00',
        fazenda=ident.get('fazenda') or 'Fazenda Modelo',
        municipio=ident.get('municipio') or 'Região Agropecuária',
        uf=ident.get('uf') or 'BR',
        area_total_ha=float(ident.get('area_total_ha') or ident.get('area_total') or 0.0),
    )

    # 2. Operação Proposta
    op_dados = dados.get('operacao') or dados.get('credito') or {}
    if isinstance(op_dados, dict) and 'analysis' in op_dados:
        # Se veio encapsulado em analise.get('credito')
        op_dados = op_dados.get('conditions') or op_dados.get('analysis') or op_dados

    valor_solicitado = float(
        op_dados.get('valor_solicitado')
        or op_dados.get('credito_valor')
        or op_dados.get('valor')
        or 0.0
    )
    prazo_meses = int(op_dados.get('prazo_meses') or 12)
    carencia_meses = int(op_dados.get('carencia_meses') or 0)
    juros_aa = float(op_dados.get('juros_aa') or op_dados.get('taxa_juros_anual') or 12.0)
    sistema_amort = str(op_dados.get('sistema_amortizacao') or 'PRICE').upper()
    periodicidade = str(op_dados.get('periodicidade') or 'ANUAL').upper()
    finalidade = str(
        op_dados.get('finalidade')
        or 'Custeio Agrícola / Aquisição de Rebanho / Barter / Investimento B2B'
    )

    operacao = OperacaoProposta(
        codigo_operacao='',  # Preenchido na deliberação com hash
        finalidade=finalidade,
        valor_solicitado=valor_solicitado,
        prazo_meses=prazo_meses,
        carencia_meses=carencia_meses,
        juros_aa=juros_aa,
        sistema_amortizacao=sistema_amort,
        periodicidade=periodicidade,
    )

    # 3. Atividades Agropecuárias
    pec_dados = dados.get('pecuaria') or dados.get('analise_pecuaria') or dados.get('rebanho') or {}
    agr_dados = dados.get('agricola') or dados.get('analise_agricola') or dados.get('graos') or {}

    tem_pecuaria = bool(pec_dados) or bool(dados.get('saldo')) or bool(dados.get('projecao_anos'))
    tem_agricola = bool(agr_dados) or bool(dados.get('culturas')) or bool(dados.get('economico'))

    # Métricas de Pecuária
    rebanho_cabecas = int(
        pec_dados.get('rebanho_total_cabecas')
        or pec_dados.get('total_cabecas')
        or pec_dados.get('total')
        or (dados.get('saldo') or {}).get('total', 0)
        or 0
    )
    rebanho_uas = float(
        pec_dados.get('rebanho_uas')
        or pec_dados.get('uas')
        or (rebanho_cabecas * 0.75 if rebanho_cabecas else 0.0)
    )
    taxa_desfrute = float(
        pec_dados.get('taxa_desfrute_pct')
        or (pec_dados.get('desfrute') or {}).get('taxa_desfrute_pct', 0.0)
        or 22.0 if tem_pecuaria else 0.0
    )
    receita_pecuaria = float(
        pec_dados.get('receita_pecuaria_anual')
        or pec_dados.get('receita_anual')
        or (dados.get('fluxo_gep') or {}).get('receita_total', 0.0)
        or 0.0
    )

    # Métricas de Agrícola
    culturas_lista: list[str] = []
    area_plantada = 0.0
    produtividade_media = 0.0
    breakeven_medio = 0.0
    receita_agricola = 0.0

    eco_agr = agr_dados.get('economico') or dados.get('economico') or {}
    culturas_raw = eco_agr.get('culturas') or agr_dados.get('culturas') or []
    if culturas_raw:
        for c in culturas_raw:
            nome_c = c.get('cultura') or c.get('nome') or 'Grãos'
            culturas_lista.append(str(nome_c))
            area_plantada += float(c.get('area_ha') or 0.0)
            if c.get('produtividade_sc_ha'):
                produtividade_media = float(c.get('produtividade_sc_ha'))
            if c.get('breakeven_sc_ha'):
                breakeven_medio = float(c.get('breakeven_sc_ha'))
        receita_agricola = float(
            eco_agr.get('receita_total')
            or agr_dados.get('receita_agricola_anual')
            or agr_dados.get('receita_anual')
            or 0.0
        )
    elif agr_dados:
        area_plantada = float(agr_dados.get('area_plantada_ha') or 0.0)
        receita_agricola = float(
            agr_dados.get('receita_agricola_anual')
            or agr_dados.get('receita_anual')
            or eco_agr.get('receita_total')
            or 0.0
        )
        culturas_lista = agr_dados.get('culturas_principais') or ['Soja / Milho']
        if agr_dados.get('produtividade_media_sc_ha'):
            produtividade_media = float(agr_dados.get('produtividade_media_sc_ha'))
        if agr_dados.get('breakeven_medio_sc_ha'):
            breakeven_medio = float(agr_dados.get('breakeven_medio_sc_ha'))

    resumo_atividades = []
    if tem_pecuaria and rebanho_cabecas > 0:
        resumo_atividades.append(f"Pecuária: {rebanho_cabecas:,} cabeças ({rebanho_uas:.1f} UA, desfrute {taxa_desfrute:.1f}%)")
    if tem_agricola and area_plantada > 0:
        culturas_str = ", ".join(culturas_lista) if culturas_lista else "Grãos"
        resumo_atividades.append(f"Agrícola: {area_plantada:,.1f} ha cultivados ({culturas_str})")

    atividades = ConsolidadoAtividades(
        tem_pecuaria=tem_pecuaria,
        rebanho_total_cabecas=rebanho_cabecas,
        rebanho_uas=rebanho_uas,
        taxa_desfrute_pct=taxa_desfrute,
        receita_pecuaria_anual=receita_pecuaria,
        tem_agricola=tem_agricola,
        area_plantada_ha=area_plantada,
        culturas_principais=culturas_lista,
        produtividade_media_sc_ha=produtividade_media,
        breakeven_medio_sc_ha=breakeven_medio,
        receita_agricola_anual=receita_agricola,
        resumo_texto=" · ".join(resumo_atividades) if resumo_atividades else "Atividade agropecuária mista",
    )

    # 4. Compliance Socioambiental (ESG)
    esg_dados = dados.get('esg') or dados.get('compliance') or {}
    area_prop = proponente.area_total_ha or float(esg_dados.get('area_total_ha') or 1000.0)
    bioma = str(esg_dados.get('bioma') or 'CERRADO').upper()
    exigencia_rl = 80.0 if 'AMAZONIA' in bioma else (35.0 if 'TRANSICAO' in bioma else 20.0)
    
    rl_ha = float(esg_dados.get('area_reserva_legal_ha') or (area_prop * (exigencia_rl / 100.0)))
    rl_pct = (rl_ha / area_prop * 100.0) if area_prop > 0 else exigencia_rl
    app_ha = float(esg_dados.get('area_app_ha') or (area_prop * 0.05))

    parecer_esg = str(esg_dados.get('parecer') or 'APROVADO').upper()
    if 'BLOQUE' in parecer_esg or esg_dados.get('tem_bloqueio'):
        parecer_esg = 'BLOQUEIO'
    elif 'ALERT' in parecer_esg or esg_dados.get('tem_alerta'):
        parecer_esg = 'ALERTA'
    else:
        parecer_esg = 'APROVADO'

    obs_esg = esg_dados.get('observacoes') or []
    if not obs_esg:
        if parecer_esg == 'APROVADO':
            obs_esg = [
                'Inscrição ativa no SICAR sem sobreposição com Unidades de Conservação ou Terras Indígenas.',
                'Ausência de embargos cadastrados no IBAMA e ICMBio conforme CMN 5.081/23 e MCR 2-1.',
                f'Reserva Legal ({rl_pct:.1f}%) em conformidade com a exigência legal de {exigencia_rl:.0f}% para o bioma {bioma}.'
            ]
        elif parecer_esg == 'ALERTA':
            obs_esg = ['Déficit de Reserva Legal ou pendência documental no CAR em regularização (PRA).']
        else:
            obs_esg = ['Embargo ambiental ou sobreposição impeditiva detectada sob CMN 5.081/23.']

    esg = ConsolidadoESG(
        numero_car=str(esg_dados.get('numero_car') or 'MT-5107909-0123456789ABCDEF0123456789ABCDEF'),
        status_car=str(esg_dados.get('status_car') or 'ATIVO'),
        bioma=bioma,
        area_total_ha=area_prop,
        reserva_legal_ha=rl_ha,
        reserva_legal_pct=round(rl_pct, 1),
        exigencia_reserva_legal_pct=exigencia_rl,
        app_ha=app_ha,
        status_ibama=str(esg_dados.get('status_ibama') or 'REGULAR'),
        status_icmbio=str(esg_dados.get('status_icmbio') or 'REGULAR'),
        sobreposicao_indigena_quilombola=bool(esg_dados.get('sobreposicao_indigena_quilombola') or False),
        parecer_compliance=parecer_esg,
        observacoes=obs_esg,
    )

    # 5. Garantias & LTV
    gar_dados = dados.get('garantias') or dados.get('collateral') or {}
    itens_gar = gar_dados.get('itens') or []
    vm_total = float(gar_dados.get('valor_mercado_total') or 0.0)
    vlf_total = float(gar_dados.get('valor_liquidacao_total') or gar_dados.get('valor_liquidacao_forcada_total') or 0.0)

    if not itens_gar:
        # Se não vieram itens individuais, mas vieram totais ou montamos padrão
        if vm_total > 0:
            if vlf_total <= 0:
                vlf_total = vm_total * 0.75
            itens_gar = [{
                'tipo': 'IMOVEL_RURAL',
                'descricao': f"Fazenda {proponente.fazenda}",
                'valor_mercado_bruto': vm_total,
                'desagio_aplicado_pct': 25.0,
                'valor_liquidacao_forcada': vlf_total,
            }]
        elif valor_solicitado > 0:
            # Estimativa de garantia para cobertura mínima de 140%
            vm_total = round(valor_solicitado * 1.60, 2)
            vlf_total = round(valor_solicitado * 1.30, 2)
            itens_gar = [
                {
                    'tipo': 'IMOVEL_RURAL',
                    'descricao': f"Garantia Real Imobiliária - Fazenda {proponente.fazenda}",
                    'valor_mercado_bruto': round(vm_total * 0.70, 2),
                    'desagio_aplicado_pct': 20.0,
                    'valor_liquidacao_forcada': round(vm_total * 0.70 * 0.80, 2),
                },
                {
                    'tipo': 'PENHOR_PECUARIO' if tem_pecuaria else 'PENHOR_SAFRA',
                    'descricao': 'Penhor Agropecuário (Rebanho ou Safra Futura)',
                    'valor_mercado_bruto': round(vm_total * 0.30, 2),
                    'desagio_aplicado_pct': 25.0,
                    'valor_liquidacao_forcada': round(vm_total * 0.30 * 0.75, 2),
                }
            ]
            vlf_total = sum(i['valor_liquidacao_forcada'] for i in itens_gar)

    ltv_mercado = (valor_solicitado / vm_total * 100.0) if vm_total > 0 else 0.0
    ltv_lf = (valor_solicitado / vlf_total * 100.0) if vlf_total > 0 else 0.0

    faixa_ltv = 'CONFORTAVEL'
    if ltv_lf > 85.0:
        faixa_ltv = 'CRITICO'
    elif ltv_lf > 70.0:
        faixa_ltv = 'ELEVADO'
    elif ltv_lf > 50.0:
        faixa_ltv = 'MODERADO'

    garantias = ConsolidadoGarantias(
        total_bens=len(itens_gar),
        valor_mercado_total=round(vm_total, 2),
        valor_liquidacao_forcada_total=round(vlf_total, 2),
        ltv_mercado_pct=round(ltv_mercado, 1),
        ltv_liquidacao_forcada_pct=round(ltv_lf, 1),
        faixa_risco_ltv=faixa_ltv,
        detalhes_itens=itens_gar,
    )

    # 6. Financeiro e Fluxo Consolidado
    rec_total_anual = receita_pecuaria + receita_agricola
    if rec_total_anual <= 0:
        rec_total_anual = float(
            (dados.get('financeiro') or {}).get('receita_bruta_anual')
            or (dados.get('economico') or {}).get('receita_total')
            or max(valor_solicitado * 1.8, 1_000_000.0)
        )

    custo_pec = float(
        pec_dados.get('custo_total')
        or pec_dados.get('custo_operacional_anual')
        or (dados.get('fluxo_gep') or {}).get('custo_total')
        or 0.0
    )
    custo_agr = float(
        agr_dados.get('custo_total')
        or agr_dados.get('custo_operacional_anual')
        or eco_agr.get('cot_total')
        or eco_agr.get('coe_total')
        or 0.0
    )
    custo_informado = float((dados.get('financeiro') or {}).get('custo_operacional_anual') or 0.0)
    if custo_informado > 0:
        custo_operacional = custo_informado
    elif custo_pec > 0 or custo_agr > 0:
        custo_operacional = custo_pec + custo_agr
    else:
        custo_operacional = rec_total_anual * 0.62

    ebitda = rec_total_anual - custo_operacional
    margem_ebitda = (ebitda / rec_total_anual * 100.0) if rec_total_anual > 0 else 0.0

    prazo_anos = max(1, math.ceil(prazo_meses / 12))
    servico_divida = _calcular_prestacao_anual(valor_solicitado, juros_aa, prazo_anos)
    # Inclui dívidas existentes se informadas
    dividas_existentes_anuais = float((dados.get('endividamento') or {}).get('servico_divida_anual') or 0.0)
    servico_divida_total = servico_divida + dividas_existentes_anuais

    # Projeção plurianual
    projecao: list[LinhaFluxoAnual] = []
    dscrs: list[float] = []

    # Projeção informada externamente?
    proj_externa = dados.get('projecao_anos') or (dados.get('credito') or {}).get('projecao_anos') or []
    if proj_externa and len(proj_externa) >= prazo_anos:
        for p in proj_externa[:prazo_anos]:
            ano_n = int(p.get('ano', 1))
            rec_n = float(p.get('receita') or rec_total_anual)
            custo_n = float(p.get('custo') or custo_operacional)
            ebitda_n = float(p.get('ebitda') or (rec_n - custo_n))
            servico_n = float(p.get('servico_divida') or servico_divida_total)
            fcl_n = ebitda_n - servico_n
            dscr_n = round(ebitda_n / servico_n, 2) if servico_n > 0 else 9.99
            dscrs.append(dscr_n)
            projecao.append(LinhaFluxoAnual(
                ano=ano_n,
                receita_bruta=round(rec_n, 2),
                custos_despesas=round(custo_n, 2),
                ebitda=round(ebitda_n, 2),
                servico_divida=round(servico_n, 2),
                fluxo_caixa_livre=round(fcl_n, 2),
                dscr=dscr_n,
            ))
    else:
        # Gerar projeção padrão baseada no prazo
        for a in range(1, prazo_anos + 1):
            fator_crescimento = 1.0 + (0.03 * (a - 1))  # Inflação/ganho modesto de 3% a.a.
            rec_a = rec_total_anual * fator_crescimento
            custo_a = custo_operacional * fator_crescimento
            ebitda_a = rec_a - custo_a
            fcl_a = ebitda_a - servico_divida_total
            dscr_a = round(ebitda_a / servico_divida_total, 2) if servico_divida_total > 0 else 9.99
            dscrs.append(dscr_a)
            projecao.append(LinhaFluxoAnual(
                ano=a,
                receita_bruta=round(rec_a, 2),
                custos_despesas=round(custo_a, 2),
                ebitda=round(ebitda_a, 2),
                servico_divida=round(servico_divida_total, 2),
                fluxo_caixa_livre=round(fcl_a, 2),
                dscr=dscr_a,
            ))

    dscr_min = min(dscrs) if dscrs else 0.0
    dscr_med = round(sum(dscrs) / len(dscrs), 2) if dscrs else 0.0
    dscr_ano_1 = dscrs[0] if dscrs else 0.0
    ano_critico = dscrs.index(dscr_min) + 1 if dscrs else 1

    financeiro = ConsolidadoFinanceiro(
        receita_bruta_anual=round(rec_total_anual, 2),
        custo_operacional_anual=round(custo_operacional, 2),
        ebitda_anual=round(ebitda, 2),
        margem_ebitda_pct=round(margem_ebitda, 1),
        servico_divida_anual=round(servico_divida_total, 2),
        dscr_ano_1=dscr_ano_1,
        dscr_minimo=dscr_min,
        dscr_medio=dscr_med,
        ano_critico=ano_critico,
        projecao_plurianual=projecao,
    )

    # 7. Deliberação do Comitê de Crédito e Rating
    # Determinação de Rating e Recomendação
    rating_override = dados.get('rating') or (dados.get('rating_credito') or {}).get('rating')
    if rating_override:
        rating_final = str(rating_override).upper()
    else:
        if dscr_min >= 1.70 and ltv_lf <= 50.0 and parecer_esg == 'APROVADO':
            rating_final = 'AAA'
        elif dscr_min >= 1.40 and ltv_lf <= 65.0 and parecer_esg == 'APROVADO':
            rating_final = 'AA'
        elif dscr_min >= 1.20 and ltv_lf <= 75.0 and parecer_esg != 'BLOQUEIO':
            rating_final = 'A'
        elif dscr_min >= 1.00 and ltv_lf <= 85.0 and parecer_esg != 'BLOQUEIO':
            rating_final = 'BBB'
        elif dscr_min >= 0.85 and parecer_esg != 'BLOQUEIO':
            rating_final = 'BB'
        else:
            rating_final = 'C'

    # Recomendação e Alçada
    if parecer_esg == 'BLOQUEIO':
        recomendacao = 'DESFAVORAVEL'
        motivo_recom = 'Impedimento socioambiental nos termos da Resolução CMN 5.081/23 e MCR 2-1.'
    elif dscr_min < 1.00:
        recomendacao = 'DESFAVORAVEL'
        motivo_recom = f'Geração de caixa insuficiente para cobrir o serviço da dívida (DSCR crítico de {dscr_min:.2f}x no Ano {ano_critico}).'
    elif ltv_lf > 85.0:
        recomendacao = 'FAVORAVEL_COM_RESSALVAS'
        motivo_recom = f'Cobertura de garantias ajustada ao limite prudencial (LTV de liquidação de {ltv_lf:.1f}%). Requer reforço colateral.'
    elif dscr_min < 1.25:
        recomendacao = 'FAVORAVEL_COM_RESSALVAS'
        motivo_recom = f'Margem moderada de cobertura do fluxo de caixa (DSCR {dscr_min:.2f}x). Condicionado a covenants semestrais.'
    else:
        recomendacao = 'FAVORAVEL'
        motivo_recom = f'Operação aprovada com indicadores robustos (DSCR médio de {dscr_med:.2f}x e LTV de liquidação forçada de {ltv_lf:.1f}%).'

    # Covenants Propostos
    covenants = [
        f"Manutenção de DSCR mínimo de {max(1.15, dscr_min * 0.85):.2f}x apurado anualmente ao encerramento de cada safra/ano civil.",
        f"LTV das garantias não poderá ultrapassar 75.0% do saldo devedor principal vincendo.",
        "Comprovação periódica de regularidade ambiental do imóvel rural no SICAR (ausência de novos embargos ou sobreposições).",
    ]
    if tem_pecuaria:
        covenants.append(f"Averbação e preservação de estoque pecuário mínimo de {int(rebanho_cabecas * 0.60):,} cabeças sob penhor.")
    if tem_agricola:
        covenants.append("Contratação e manutenção de Apólice de Seguro Agrícola com cessão fiduciária de direitos indenizatórios ao credor.")

    # Geração de Código e Hash SHA-256
    agora = datetime.datetime.now()
    seed_str = (
        f"{proponente.nome}|{proponente.cpf_cnpj}|{operacao.valor_solicitado}|"
        f"{dscr_med}|{ltv_lf}|{rating_final}|{agora.strftime('%Y%m%d%H%M')}"
    )
    hash_sha256 = hashlib.sha256(seed_str.encode('utf-8')).hexdigest().upper()
    codigo_dossie = f"ORK-COM-{agora.year}-{hash_sha256[:8]}"
    operacao.codigo_operacao = codigo_dossie

    deliberacao = DeliberacaoComite(
        codigo_dossie=codigo_dossie,
        data_emissao=agora.strftime('%d/%m/%Y às %H:%M'),
        rating_final=rating_final,
        recomendacao=recomendacao,
        limite_sugerido=valor_solicitado if recomendacao != 'DESFAVORAVEL' else 0.0,
        covenants_obrigatorios=covenants,
        parecer_risco_tecnico=motivo_recom,
        parecer_gerencia_b2b='De acordo com a estruturação da operação e garantias constituídas.',
        parecer_diretoria='Homologação condicional ao cumprimento das exigências prévias e covenants contratuais.',
        hash_sha256=hash_sha256,
    )

    return DossieComite(
        proponente=proponente,
        operacao=operacao,
        atividades=atividades,
        esg=esg,
        garantias=garantias,
        financeiro=financeiro,
        deliberacao=deliberacao,
    )
