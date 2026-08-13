"""Checklist de evidências para análise de crédito rural pecuário.

Cada item tem: código, descrição, nível (impeditivo/alerta/ok),
como é verificado nos dados, e se é obrigatório para aprovação definitiva.
"""
from __future__ import annotations

IMPEDITIVO = 'impeditivo'
ALERTA = 'alerta'
OK = 'ok'

# (codigo, descricao, nivel_ausente, obrigatorio, chave_nos_dados)
_ITENS = [
    # Rebanho
    ('ficha_rebanho',        'Ficha sanitária / declaração de rebanho',       IMPEDITIVO, True,  'vetor_rebanho'),
    ('area_ha',              'Área de pastagem (ha)',                          IMPEDITIVO, True,  'area_ha'),
    ('composicao_rebanho',   'Composição por sexo e faixa etária',             IMPEDITIVO, True,  'vetor_rebanho'),
    # Financeiro
    ('receitas_comprovadas', 'Notas de venda — últimos 12–24 meses',          IMPEDITIVO, True,  'receitas_comprovadas'),
    ('custos_historico',     'Custos e movimentações — últimos 12 meses',     IMPEDITIVO, True,  'custos_historico'),
    ('credito_valor',        'Valor e finalidade do crédito solicitado',       IMPEDITIVO, True,  'credito_valor'),
    ('dividas_existentes',   'Relação de dívidas e parcelas em andamento',    ALERTA,     True,  'dividas_existentes'),
    ('extratos_bancarios',   'Extratos bancários (6–12 meses)',                ALERTA,     True,  'extratos_bancarios'),
    ('retiradas_produtor',   'Retiradas mensais do produtor / pró-labore',    ALERTA,     False, 'retiradas_produtor'),
    # Documental
    ('documento_posse',      'Matrícula, arrendamento ou contrato de posse',  ALERTA,     True,  'documento_propriedade'),
    ('car_ccir',             'CAR e CCIR da propriedade',                      ALERTA,     True,  'car_ccir'),
    ('itr',                  'ITR (quando aplicável)',                         ALERTA,     False, 'itr'),
    ('restricoes_cadastrais','Consulta de restrições cadastrais (CPF/CNPJ)',   ALERTA,     True,  'restricoes_cadastrais'),
    # Zootécnico
    ('pesagens',             'Pesagens / GMD comprovado',                      ALERTA,     False, 'pesagens'),
    ('indices_reprodutivos', 'Natalidade / prenhez / desmama comprovados',    ALERTA,     False, 'indices_reprodutivos'),
    ('mortes_causa',         'Causa das mortes declaradas',                   ALERTA,     False, 'mortes_causa'),
    # Garantias
    ('garantias',            'Garantias ofertadas e avaliação formal',        ALERTA,     True,  'garantias'),
    ('gravames',             'Verificação de gravames sobre as garantias',    ALERTA,     True,  'gravames'),
    # Calendário
    ('calendario_vendas',    'Calendário previsto de vendas (sazonalidade)',  ALERTA,     False, 'calendario_vendas'),
]


def _presente(dados: dict, chave: str) -> bool:
    v = dados.get(chave)
    if v is None:
        return False
    if isinstance(v, (list, dict)):
        return bool(v)
    try:
        return float(v) > 0
    except (TypeError, ValueError):
        return bool(v)


def checklist_credito(dados: dict, qualidade: dict | None = None) -> dict:
    """Avalia completude da documentação e retorna checklist estruturado.

    Args:
        dados: Campos da análise (vetor_rebanho, area_ha, credito_valor, etc.).
        qualidade: Dict opcional com 'nivel_confianca' do QualidadeDados.

    Returns:
        {status, score_completude, impeditivos, alertas, ok,
         bloqueio_aprovacao, mensagem, confianca_dados}
    """
    dados = dados or {}
    qualidade = qualidade or {}

    impeditivos, alertas, ok_list = [], [], []

    for codigo, descricao, nivel_ausente, obrigatorio, chave in _ITENS:
        presente = _presente(dados, chave)
        item = {
            'codigo': codigo,
            'descricao': descricao,
            'obrigatorio': obrigatorio,
        }
        if presente:
            ok_list.append({**item, 'nivel': OK})
        elif nivel_ausente == IMPEDITIVO:
            impeditivos.append({**item, 'nivel': IMPEDITIVO})
        else:
            alertas.append({**item, 'nivel': ALERTA})

    bloqueio = bool(impeditivos)
    total = len(_ITENS)
    score = round(len(ok_list) / total * 100) if total else 0

    if not impeditivos and not alertas:
        status = 'completo'
        msg = 'Documentação completa. Análise definitiva possível.'
    elif not impeditivos:
        status = 'parcial'
        msg = f'Pré-análise possível. {len(alertas)} item(ns) pendente(s) para parecer conclusivo.'
    else:
        status = 'incompleto'
        msg = (f'{len(impeditivos)} dado(s) impeditivo(s) ausente(s). '
               'Aprovação definitiva bloqueada.')

    return {
        'status': status,
        'score_completude': score,
        'impeditivos': impeditivos,
        'alertas': alertas,
        'ok': ok_list,
        'bloqueio_aprovacao': bloqueio,
        'mensagem': msg,
        'confianca_dados': qualidade.get('nivel_confianca', 'media-baixa'),
    }
