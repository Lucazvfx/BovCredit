"""Checklist mínimo de evidências para uma análise de crédito pecuário."""
from __future__ import annotations


def checklist_credito(dados: dict, qualidade: dict | None = None) -> dict:
    dados = dados or {}
    qualidade = qualidade or {}
    itens = [
        ('ficha_rebanho', 'Ficha sanitária/planilha do rebanho', True, True),
        ('gta_inventario', 'GTA ou inventário oficial atualizado', False, True),
        ('documento_propriedade', 'Documento da propriedade e CAR', False, True),
        ('custos_historico', 'Custos e movimentações dos últimos 12 meses', False, True),
        ('pesagens', 'Pesagens ou histórico de ganho de peso', False, False),
        ('endividamento', 'Relação de dívidas e parcelas existentes',
         bool(dados.get('dividas_mensais') or dados.get('dividas')), True),
    ]
    pendentes = [
        {'codigo': codigo, 'descricao': descricao, 'obrigatorio': obrigatorio}
        for codigo, descricao, recebido, obrigatorio in itens if not recebido
    ]
    return {
        'status': 'completo' if not pendentes else 'pendente',
        'recebidos': [codigo for codigo, _, recebido, _ in itens if recebido],
        'pendentes': pendentes,
        'mensagem': ('Documentação mínima recebida.' if not pendentes else
                     'A análise é preliminar: confirme os documentos pendentes antes da decisão.'),
        'confianca_dados': qualidade.get('nivel_confianca', 'media-baixa'),
    }

