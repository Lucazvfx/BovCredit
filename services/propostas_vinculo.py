"""Parâmetros técnicos de uma proposta a partir de um parecer salvo.

Quando a proposta cita um parecer, o servidor lê caixa, prazo, juros, carência,
dívidas, revisão humana e atipicidade do próprio registro. Nada disso vem do
cliente: o cliente só escolhe o parecer e, se quiser, o valor pretendido.
Não há fórmula nova — os números seguem para `simular_proposta`, que já existe.
"""
from services import politica_alcada as _alcada


def parametros_do_parecer(parecer_salvo: dict,
                          valor_pretendido=None) -> tuple[dict | None, str | None]:
    """(params para `simular_proposta`, erro). `parecer_salvo` vem de
    `database.buscar_parecer_empresa`."""
    sol = parecer_salvo.get('solicitacao') or {}
    corpo = parecer_salvo.get('parecer') or {}
    conclusao = corpo.get('conclusao') or {}
    classificacao = corpo.get('explicacao_classificacao')

    # Pareceres gravados antes de `atipicidade_nivel` existir não dizem se o
    # rebanho era atípico: só o bloco completo vale como registro da revisão.
    if isinstance(classificacao, dict) and 'atipicidade_nivel' in classificacao:
        revisao = bool(classificacao.get('revisao_humana'))
        motivos = [m for m in classificacao.get('motivos_revisao') or []
                   if m in _alcada.MOTIVOS_REVISAO_VALIDOS]
        nivel = classificacao.get('atipicidade_nivel')
        if nivel not in _alcada.NIVEIS_ATIPICIDADE:
            nivel = None
    else:
        # Parecer sem o registro completo da classificação: não dá para afirmar
        # que dispensa revisão. Na dúvida, trata como dados incompletos.
        revisao, motivos, nivel = True, ['dados_incompletos'], None

    valor = valor_pretendido if valor_pretendido is not None else sol.get('credito_valor')
    params, erro = _alcada.validar_simulacao({
        'valor_pretendido': valor,
        'prazo_meses': sol.get('prazo_meses'),
        'carencia_meses': sol.get('carencia_meses') or 0,
        'juros_aa': sol.get('juros_aa'),
        'dividas_mensais': sol.get('dividas_mensais') or 0,
        'geracao_caixa_anual': conclusao.get('geracao_caixa_anual'),
        'revisao_humana': revisao,
        'motivos_revisao': motivos,
        'atipicidade_nivel': nivel,
    })
    if erro:
        return None, 'Parecer sem dados suficientes para a proposta: ' + erro
    return params, None


def origem_do_parecer(parecer_salvo: dict) -> dict:
    """Identificação do parecer guardada no snapshot da proposta."""
    return {'parecer_id': parecer_salvo['id'],
            'fazenda_id': parecer_salvo['fazenda_id'],
            'emitido_em': parecer_salvo['emitido_em'][:19],
            # O vínculo herda caixa do ano 1 e Price: a recomendação do parecer
            # fica registrada para o aprovador ver o que a alçada não considera.
            'recomendacao': (parecer_salvo.get('parecer') or {})
            .get('conclusao', {}).get('recomendacao')}
