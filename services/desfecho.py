"""Vocabulário do desfecho de um parecer, e o que conta como resposta.

O sistema emitia parecer e nunca perguntava o que aconteceu. Sem isso o rating
é indicativo por construção — está escrito em services/rating_credito.py — e o
classificador segue treinado em dado sintético.

A REGRA QUE ESTE MÓDULO EXISTE PARA GUARDAR: "não sei" é resposta, e é
diferente de ninguém ter respondido. Juntar as duas coisas esconde a taxa de
resposta, e taxa de resposta é o número que diz se o conjunto presta. É a mesma
distinção que validacao_zootecnica faz entre checagem que falhou e checagem que
não rodou.

Módulo puro: define e valida, não escreve. A escrita fica em database.py.
"""
from __future__ import annotations

# ── Etapas ──────────────────────────────────────────────────────────────────
CONTRATACAO = 'contratacao'
ADIMPLENCIA = 'adimplencia'
ETAPAS = (CONTRATACAO, ADIMPLENCIA)

# ── Situações de contratação ────────────────────────────────────────────────
CONTRATADA = 'contratada'
RECUSADA = 'recusada'
DESISTIU = 'desistiu'

# ── Situações de adimplência ────────────────────────────────────────────────
EM_DIA = 'em_dia'
ATRASO_ATE_30 = 'atraso_ate_30'
ATRASO_31_90 = 'atraso_31_90'
ATRASO_MAIS_90 = 'atraso_mais_90'
RENEGOCIADA = 'renegociada'
LIQUIDADA = 'liquidada'

# Vale nas duas etapas. Registrado de propósito, nunca inferido.
NAO_SEI = 'nao_sei'

SITUACOES = {
    CONTRATACAO: (CONTRATADA, RECUSADA, DESISTIU, NAO_SEI),
    ADIMPLENCIA: (EM_DIA, ATRASO_ATE_30, ATRASO_31_90, ATRASO_MAIS_90,
                  RENEGOCIADA, LIQUIDADA, NAO_SEI),
}

ROTULO = {
    CONTRATADA:     'Operação contratada',
    RECUSADA:       'Recusada pelo agente financeiro',
    DESISTIU:       'Proponente desistiu',
    EM_DIA:         'Em dia',
    ATRASO_ATE_30:  'Atraso de até 30 dias',
    ATRASO_31_90:   'Atraso de 31 a 90 dias',
    ATRASO_MAIS_90: 'Atraso acima de 90 dias',
    RENEGOCIADA:    'Renegociada',
    LIQUIDADA:      'Liquidada',
    NAO_SEI:        'Não sei',
}

# Situações que indicam que a operação passou a existir. Só elas admitem as
# condições contratadas — registrar valor numa operação recusada seria guardar
# número que não corresponde a contrato nenhum.
GEROU_OPERACAO = (CONTRATADA,)

# O desfecho ruim é o que mais ensina, e é o que ninguém tem vontade de
# registrar. Fica nomeado para o painel de cobertura poder medir se ele está
# sendo registrado na mesma proporção que o bom.
DESFAVORAVEIS = (RECUSADA, ATRASO_31_90, ATRASO_MAIS_90, RENEGOCIADA)


class DesfechoInvalido(ValueError):
    """Erro de vocabulário — não de banco."""


def validar(etapa: str, situacao: str) -> tuple[str, str]:
    etapa = str(etapa or '').strip().lower()
    situacao = str(situacao or '').strip().lower()
    if etapa not in ETAPAS:
        raise DesfechoInvalido(
            f"Etapa inválida: {etapa or '(vazia)'}. Use {' ou '.join(ETAPAS)}.")
    if situacao not in SITUACOES[etapa]:
        raise DesfechoInvalido(
            f"Situação '{situacao}' não existe na etapa {etapa}. "
            f"Use: {', '.join(SITUACOES[etapa])}.")
    return etapa, situacao


def validar_condicoes(situacao: str, condicoes: dict | None) -> dict:
    """As condições CONTRATADAS, que costumam divergir das pedidas.

    A divergência é informação: o banco que aprova metade do valor pedido, ou
    corta o prazo, está dizendo o que achou da operação.
    """
    condicoes = {k: v for k, v in (condicoes or {}).items() if v not in (None, '')}
    if not condicoes:
        return {}
    if situacao not in GEROU_OPERACAO:
        raise DesfechoInvalido(
            'Condições contratadas só valem quando a operação foi contratada.')

    limpas: dict[str, float | str] = {}
    for campo in ('valor_contratado', 'prazo_contratado', 'juros_contratado'):
        if campo not in condicoes:
            continue
        try:
            numero = float(condicoes[campo])
        except (TypeError, ValueError) as erro:
            raise DesfechoInvalido(f'{campo} precisa ser número.') from erro
        if numero < 0:
            raise DesfechoInvalido(f'{campo} não pode ser negativo.')
        limpas[campo] = numero

    if 'juros_contratado' in limpas and limpas['juros_contratado'] >= 1:
        # Mesma convenção do resto da API: fração, não porcentagem.
        raise DesfechoInvalido(
            'juros_contratado é fração ao ano: use 0.105 para 10,5% a.a.')

    sistema = str(condicoes.get('sistema_contratado') or '').strip().lower()
    if sistema:
        if sistema not in ('price', 'sac'):
            raise DesfechoInvalido("sistema_contratado deve ser 'price' ou 'sac'.")
        limpas['sistema_contratado'] = sistema
    return limpas


def cobertura(total_pareceres: int, registros: list[dict]) -> dict:
    """Três estados, nunca dois: respondido, não sei, e sem registro.

    Um painel que só mostrasse "X% respondidos" trataria "não sei" como
    resposta útil. Aqui os três aparecem separados, porque é a comparação
    entre eles que denuncia viés de coleta.
    """
    por_parecer: dict[int, set] = {}
    for registro in registros or []:
        parecer_id = registro.get('parecer_id')
        if parecer_id is None:
            continue
        por_parecer.setdefault(parecer_id, set()).add(registro.get('situacao'))

    respondidos = sum(1 for situacoes in por_parecer.values()
                      if situacoes - {NAO_SEI})
    so_nao_sei = len(por_parecer) - respondidos
    total = max(int(total_pareceres or 0), len(por_parecer))
    sem_registro = total - len(por_parecer)

    desfavoraveis = sum(1 for situacoes in por_parecer.values()
                        if situacoes & set(DESFAVORAVEIS))
    return {
        'pareceres': total,
        'respondidos': respondidos,
        'so_nao_sei': so_nao_sei,
        'sem_registro': sem_registro,
        'taxa_resposta_pct': round(respondidos / total * 100, 1) if total else 0.0,
        'com_desfecho_desfavoravel': desfavoraveis,
    }
