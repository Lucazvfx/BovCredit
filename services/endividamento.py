"""
Endividamento total do proponente.

Até aqui o sistema pedia um único número — "dívidas mensais" — digitado pelo
proponente, sem origem e sem verificação. Todo o DSCR se apoiava nele. Se o
produtor tem operação em outros quatro bancos e informa zero, a projeção fecha
bonito e está errada, e nada no parecer denunciaria isso.

Trocar o número solto por um inventário declarado não verifica nada sozinho.
O que muda é que a dívida passa a ter credor, saldo e parcela, item a item:
vira uma declaração assinável, confrontável com o SCR do Banco Central quando
houver convênio, e visível no parecer em vez de embutida numa conta.

Módulo puro — não importa Flask nem DB.
"""
from __future__ import annotations

# Fração da geração de caixa anual que o serviço da dívida TOTAL pode consumir
# antes de acender alerta. Política de crédito, ajustável.
COMPROMETIMENTO_ALERTA = 0.70


def _num(v, default=0.0) -> float:
    try:
        return max(float(v or default), 0.0)
    except (TypeError, ValueError):
        return default


def _fmt_rs(v) -> str:
    return f'R$ {v:,.0f}'.replace(',', '.')


def consolidar(dividas: list | None = None,
               dividas_mensais_legado: float = 0.0,
               geracao_caixa_anual: float = 0.0,
               parcela_nova: float = 0.0) -> dict:
    """
    Consolida o endividamento existente e mede o quanto ele já compromete.

    `dividas` é uma lista de {instituicao, saldo_devedor, parcela_mensal}.
    `dividas_mensais_legado` mantém compatibilidade com o campo único antigo:
    quando não há inventário, ele vira uma linha "não discriminado" — a conta
    continua idêntica à de antes, e o parecer passa a dizer que a origem do
    número é desconhecida, que é a informação que faltava.

    `parcela_nova` é a parcela do crédito em análise; entra no comprometimento
    porque o comitê decide sobre a situação depois da operação, não antes.
    """
    itens = []
    for d in (dividas or []):
        if not isinstance(d, dict):
            continue
        parcela = _num(d.get('parcela_mensal'))
        saldo   = _num(d.get('saldo_devedor'))
        if parcela <= 0 and saldo <= 0:
            continue
        itens.append({
            'instituicao':    (str(d.get('instituicao') or '').strip()
                               or 'Não informada'),
            'saldo_devedor':  round(saldo, 2),
            'parcela_mensal': round(parcela, 2),
            'discriminado':   True,
        })

    legado = _num(dividas_mensais_legado)
    if legado > 0 and not itens:
        itens.append({
            'instituicao':    'Não discriminado',
            'saldo_devedor':  0.0,
            'parcela_mensal': round(legado, 2),
            'discriminado':   False,
        })

    itens.sort(key=lambda i: -i['parcela_mensal'])
    parcela_existente = sum(i['parcela_mensal'] for i in itens)
    saldo_total       = sum(i['saldo_devedor'] for i in itens)
    tudo_discriminado = bool(itens) and all(i['discriminado'] for i in itens)

    parcela_total  = parcela_existente + _num(parcela_nova)
    servico_anual  = 12 * parcela_total
    caixa          = _num(geracao_caixa_anual)
    comprometimento = (servico_anual / caixa) if caixa > 0 else None

    if not itens:
        alerta = None
        justificativa = ('Nenhuma dívida declarada. O parecer assume ausência de '
                         'endividamento fora desta operação — confirme com o SCR '
                         'do Banco Central antes de decidir.')
    elif comprometimento is None:
        alerta = 'critico'
        justificativa = ('Sem geração de caixa positiva, qualquer endividamento é '
                         'incompatível.')
    elif comprometimento > COMPROMETIMENTO_ALERTA:
        alerta = 'critico'
        justificativa = (f'O serviço da dívida total consome {comprometimento*100:.0f}% '
                         f'da geração de caixa — acima do limite de '
                         f'{COMPROMETIMENTO_ALERTA*100:.0f}%.')
    else:
        alerta = 'ok'
        justificativa = (f'O serviço da dívida total consome {comprometimento*100:.0f}% '
                         f'da geração de caixa.')

    if itens and not tudo_discriminado:
        justificativa += (' Parte do endividamento não foi discriminada por credor, '
                          'então não é confrontável com o SCR.')

    memoria = []
    if itens:
        memoria.append({
            'passo': 'Endividamento existente (parcela mensal)',
            'valor': _fmt_rs(parcela_existente),
            'detalhe': (f'{len(itens)} operação(ões) declarada(s)'
                        + (f', saldo devedor {_fmt_rs(saldo_total)}' if saldo_total > 0 else '')
                        + ('.' if tudo_discriminado
                           else ' — origem não discriminada por credor.')),
        })
    if _num(parcela_nova) > 0:
        memoria.append({
            'passo': 'Parcela do crédito em análise',
            'valor': _fmt_rs(parcela_nova),
            'detalhe': 'Somada ao existente, porque a decisão é sobre a situação '
                       'depois da operação.'})
    if comprometimento is not None and parcela_total > 0:
        memoria.append({
            'passo': 'Comprometimento da geração de caixa',
            'valor': f'{comprometimento*100:.0f}%',
            'detalhe': f'{_fmt_rs(servico_anual)} de serviço anual ÷ '
                       f'{_fmt_rs(caixa)} de geração de caixa. Limite de política: '
                       f'{COMPROMETIMENTO_ALERTA*100:.0f}%.'})

    return {
        'itens':                    itens,
        'parcela_existente_mensal': round(parcela_existente, 2),
        'parcela_nova_mensal':      round(_num(parcela_nova), 2),
        'parcela_total_mensal':     round(parcela_total, 2),
        'saldo_devedor_total':      round(saldo_total, 2),
        'servico_divida_anual':     round(servico_anual, 2),
        'comprometimento_pct':      (round(comprometimento * 100, 1)
                                     if comprometimento is not None else None),
        'limite_alerta_pct':        COMPROMETIMENTO_ALERTA * 100,
        'tudo_discriminado':        tudo_discriminado,
        'origem':                   'declarado',
        'alerta':                   alerta,
        'justificativa':            justificativa,
        'memoria':                  memoria,
    }
