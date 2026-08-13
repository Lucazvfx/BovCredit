"""Detector de dados impeditivos para análise de crédito rural pecuário.

Classifica cada dado ausente ou inválido em três níveis:
  - impeditivo : bloqueia a aprovação definitiva
  - alerta     : permite pré-análise mas impede parecer conclusivo
  - ok         : dado presente e válido

A função principal `detectar` retorna status geral, listas por nível e um
score de completude (0–100) proporcional ao peso dos dados presentes.
"""
from __future__ import annotations

IMPEDITIVO = 'impeditivo'
ALERTA = 'alerta'
OK = 'ok'

# (codigo, descricao, nivel_se_ausente, peso_na_completude, como_verificar)
_ITENS = [
    # ── Dados do rebanho ─────────────────────────────────────────────────────
    ('ficha_rebanho',         'Ficha sanitária/declaração de rebanho',          IMPEDITIVO, 15, 'vetor_rebanho'),
    ('area_ha',               'Área de pastagem (ha)',                           IMPEDITIVO, 12, 'area_ha'),
    ('composicao_rebanho',    'Composição por sexo e faixa etária',              IMPEDITIVO, 10, 'vetor_rebanho'),
    # ── Financeiro ───────────────────────────────────────────────────────────
    ('receitas_comprovadas',  'Notas de venda dos últimos 12–24 meses',          IMPEDITIVO, 12, 'receitas_comprovadas'),
    ('custos_historico',      'Custos e movimentações dos últimos 12 meses',     IMPEDITIVO, 10, 'custos_historico'),
    ('dividas_existentes',    'Relação de dívidas e parcelas em andamento',      ALERTA,      8, 'dividas_existentes'),
    ('extratos_bancarios',    'Extratos bancários (6–12 meses)',                 ALERTA,      8, 'extratos_bancarios'),
    ('retiradas_produtor',    'Retiradas mensais/anuais do produtor',            ALERTA,      5, 'retiradas_produtor'),
    # ── Propriedade e documental ─────────────────────────────────────────────
    ('documento_propriedade', 'Matrícula, arrendamento ou contrato de posse',   ALERTA,      6, 'documento_propriedade'),
    ('car_ccir',              'CAR e CCIR da propriedade',                       ALERTA,      4, 'car_ccir'),
    ('itr',                   'ITR (quando aplicável)',                          ALERTA,      3, 'itr'),
    # ── Zootécnico ───────────────────────────────────────────────────────────
    ('pesagens',              'Pesagens ou GMD comprovado',                      ALERTA,      4, 'pesagens'),
    ('indices_reprodutivos',  'Natalidade/prenhez/desmama comprovados',          ALERTA,      5, 'indices_reprodutivos'),
    ('mortes_causa',          'Causa das mortes declaradas',                     ALERTA,      3, 'mortes_causa'),
    # ── Garantias ────────────────────────────────────────────────────────────
    ('garantias',             'Garantias ofertadas e avaliação',                 ALERTA,      5, 'garantias'),
    ('gravames',              'Verificação de gravames sobre as garantias',      ALERTA,      4, 'gravames'),
    # ── Operação ─────────────────────────────────────────────────────────────
    ('credito_valor',         'Valor solicitado e finalidade',                   IMPEDITIVO,  4, 'credito_valor'),
    ('calendario_vendas',     'Calendário previsto de vendas (sazonalidade)',    ALERTA,      3, 'calendario_vendas'),
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


def detectar(dados: dict) -> dict:
    """Analisa `dados` e retorna status, itens por nível e score de completude.

    Args:
        dados: Dict com os campos da análise. Campos esperados espelham as
            chaves em `_ITENS` (coluna `como_verificar`).

    Returns:
        {
          'status': 'completo' | 'parcial' | 'incompleto',
          'score_completude': int 0–100,
          'impeditivos': [...],
          'alertas': [...],
          'ok': [...],
          'bloqueio_aprovacao': bool,
          'mensagem': str,
        }
    """
    dados = dados or {}
    impeditivos, alertas, ok_list = [], [], []
    peso_total = sum(p for *_, p, _ in _ITENS)
    peso_ok = 0

    for codigo, descricao, nivel_ausente, peso, chave in _ITENS:
        presente = _presente(dados, chave)
        item = {'codigo': codigo, 'descricao': descricao, 'nivel': nivel_ausente}
        if presente:
            ok_list.append({**item, 'nivel': OK})
            peso_ok += peso
        elif nivel_ausente == IMPEDITIVO:
            impeditivos.append(item)
        else:
            alertas.append(item)

    # Área = 0 é tão crítica quanto ausente
    if _presente(dados, 'area_ha'):
        try:
            if float(dados['area_ha']) == 0:
                # já está em impeditivos pela lógica acima (0 → não presente)
                pass
        except (TypeError, ValueError):
            pass

    score = round(peso_ok / peso_total * 100) if peso_total > 0 else 0
    bloqueio = bool(impeditivos)

    if not impeditivos and not alertas:
        status = 'completo'
        msg = 'Documentação completa. Análise definitiva possível.'
    elif not impeditivos:
        status = 'parcial'
        msg = f'Pré-análise possível. {len(alertas)} ponto(s) pendente(s) para parecer conclusivo.'
    else:
        status = 'incompleto'
        msg = (f'{len(impeditivos)} dado(s) impeditivo(s) ausente(s). '
               'Aprovação definitiva bloqueada até regularização.')

    return {
        'status': status,
        'score_completude': score,
        'impeditivos': impeditivos,
        'alertas': alertas,
        'ok': ok_list,
        'bloqueio_aprovacao': bloqueio,
        'mensagem': msg,
    }
