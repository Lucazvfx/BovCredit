"""Pipeline orquestrador de avaliação da Matriz de Garantias e LTV B2B.
"""
from __future__ import annotations

from typing import Any

from .calculator import calcular_item_garantia, consolidar_matriz_garantias
from .models import (
    ItemGarantia,
    MatrizGarantiasConsolidada,
    TipoGarantia,
    TipoGravame,
)


def avaliar_matriz_garantias(payload: dict[str, Any]) -> MatrizGarantiasConsolidada:
    """Processa o pacote de garantias ofertadas e afere a suficiência do LTV.

    Aceita tanto uma lista explícita `itens` quanto atalhos estruturados (`imovel_rural`,
    `penhor_safra`, `avalista`, `penhor_rebanho`).
    """
    payload = payload or {}
    credito = float(payload.get('credito_solicitado', 0.0) or 0.0)
    cobertura_min = float(payload.get('cobertura_minima_pct', 130.0) or 130.0)

    itens_calculados: list[ItemGarantia] = []

    # 1. Se foi enviada a lista de itens genérica
    for raw in payload.get('itens') or []:
        itens_calculados.append(calcular_item_garantia(
            tipo=raw.get('tipo', TipoGarantia.IMOVEL_RURAL),
            gravame=raw.get('gravame', TipoGravame.ALIENACAO_FIDUCIARIA),
            descricao=raw.get('descricao', ''),
            identificador_registro=raw.get('identificador_registro', ''),
            valor_mercado_bruto=float(raw.get('valor_mercado_bruto', 0.0) or 0.0),
            dividas_previas_averbadas=float(raw.get('dividas_previas_averbadas', 0.0) or 0.0),
            area_ha=float(raw.get('area_ha', 0.0) or 0.0),
            desagio_customizado_pct=raw.get('desagio_customizado_pct'),
            observacoes=raw.get('observacoes', ''),
            id_garantia=raw.get('id_garantia', ''),
        ))

    # 2. Atalho Imóvel Rural / Terra
    imovel = payload.get('imovel_rural')
    if imovel and (imovel.get('area_ha') or imovel.get('valor_total') or imovel.get('valor_ha')):
        area = float(imovel.get('area_ha', 0.0) or 0.0)
        valor_ha = float(imovel.get('valor_ha', 0.0) or 0.0)
        vm_terra = float(imovel.get('valor_total', 0.0) or (area * valor_ha))
        gravame_str = imovel.get('gravame', 'ALIENACAO_FIDUCIARIA')
        itens_calculados.append(calcular_item_garantia(
            tipo=TipoGarantia.IMOVEL_RURAL,
            gravame=gravame_str,
            descricao=f"Imóvel Rural ({area:.1f} ha) - {imovel.get('denominacao', 'Fazenda')}",
            identificador_registro=f"Matrícula {imovel.get('matricula', 'S/N')} - {imovel.get('cartorio', 'CRI')}",
            valor_mercado_bruto=vm_terra,
            dividas_previas_averbadas=float(imovel.get('dividas_previas', 0.0) or 0.0),
            area_ha=area,
            observacoes=imovel.get('observacoes', ''),
            id_garantia="GAR-TERRA-01",
        ))

    # 3. Atalho Penhor de Safra / CPR
    safra = payload.get('penhor_safra')
    if safra and (safra.get('sacas') or safra.get('valor_total')):
        sc = float(safra.get('sacas', 0.0) or 0.0)
        preco = float(safra.get('preco_saca', 0.0) or 0.0)
        vm_safra = float(safra.get('valor_total', 0.0) or (sc * preco))
        itens_calculados.append(calcular_item_garantia(
            tipo=TipoGarantia.PENHOR_SAFRA,
            gravame=TipoGravame.PENHOR_PRIMEIRO_GRAU,
            descricao=f"Penhor Cedular de Safra ({sc:,.0f} sc de {safra.get('cultura', 'Soja')})",
            identificador_registro=safra.get('numero_cpr', 'CPR em Emissão'),
            valor_mercado_bruto=vm_safra,
            area_ha=float(safra.get('area_ha', 0.0) or 0.0),
            observacoes="Penhor de primeiro grau sobre lavoura em formação",
            id_garantia="GAR-SAFRA-01",
        ))

    # 4. Atalho Avalista / Garantia Pessoal
    aval = payload.get('avalista')
    if aval and (aval.get('patrimonio_liquido') or aval.get('nome')):
        patrimonio = float(aval.get('patrimonio_liquido', 0.0) or 0.0)
        itens_calculados.append(calcular_item_garantia(
            tipo=TipoGarantia.AVAL_PESSOAL,
            gravame=TipoGravame.AVAL_SOLIDARIO,
            descricao=f"Aval Pessoal / Fiança - {aval.get('nome', 'Avalista')}",
            identificador_registro=f"CPF/CNPJ {aval.get('cpf_cnpj', 'Não informado')}",
            valor_mercado_bruto=patrimonio,
            observacoes="Aval solidário com renúncia ao benefício de ordem",
            id_garantia="GAR-AVAL-01",
        ))

    return consolidar_matriz_garantias(
        itens=itens_calculados,
        credito_solicitado=credito,
        cobertura_minima_exigida_pct=cobertura_min,
    )
