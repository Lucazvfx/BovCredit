"""
Avaliação da garantia pecuária: deságio por categoria e LTV.

O sistema já sabia quanto o rebanho vale a mercado. Isso não é o que o comitê
pergunta — a pergunta é quanto ele vale numa execução, que é outra coisa.

Rebanho em penhor não se realiza pela cotação do dia. Entre a inadimplência e o
dinheiro em caixa há apreensão, transporte, risco sanitário, mortalidade no
período e venda forçada, que por definição não escolhe o momento do mercado.
Bancos cobrem isso com deságio sobre o valor de mercado, e o deságio não é
uniforme: depende de quão rápido cada categoria vira dinheiro.

Módulo puro — não importa Flask nem DB.
"""
from __future__ import annotations

from services.proveniencia import politica

# ── Política de crédito, não zootecnia ──────────────────────────────────────
# Estes números são parâmetros de política, no mesmo sentido de DSCR_APROVAR em
# parecer_credito.py: são ajustáveis pela instituição e não descrevem fato
# biológico nenhum. A ordenação entre eles, essa sim, tem razão de ser:
#
#   boi (25m+)        25%  pronto para abate, cotação pública diária, vende na
#                          semana — o ativo mais líquido do rebanho
#   garrote (13-24m)  35%  falta terminação; vende para confinamento, mercado
#                          menor e preço negociado
#   matriz            35%  líquida, mas o valor depende da vida reprodutiva
#                          restante, que não está nos dados do rebanho — vaca
#                          velha vale carne, não vale matriz
#   novilha (13-24m)  40%  ainda não pariu; o valor é expectativa reprodutiva
#   bezerro/a (0-12m) 50%  dois anos até a terminação, maior mortalidade da
#                          escala e preço por cabeça, regional e negociado
#
# Jovens agregados (0-24m) ficam em 45%, média ponderada das duas faixas, e só
# aparecem quando a valoração vem do simulador, que não separa cria de recria.
def _des(v, cat, motivo):
    return politica(v, 'Política de deságio da instituição',
                    rotulo=f'Deságio — {cat}', nota=motivo)


DESAGIO_PADRAO = {
    'bois':      _des(0.25, 'boi (25m+)',        'Cotação pública diária; vende na semana.'),
    'garrotes':  _des(0.35, 'garrote (13-24m)',  'Falta terminação; mercado menor.'),
    'matrizes':  _des(0.35, 'matriz',            'Valor depende da vida reprodutiva restante.'),
    'novilhas':  _des(0.40, 'novilha (13-24m)',  'Ainda não pariu; valor é expectativa.'),
    'bezerras':  _des(0.50, 'bezerra (0-12m)',   'Dois anos até terminação; maior mortalidade.'),
    'bezerros':  _des(0.50, 'bezerro (0-12m)',   'Dois anos até terminação; maior mortalidade.'),
    'jovens_f':  _des(0.45, 'jovem fêmea 0-24m', 'Média ponderada das duas faixas.'),
    'jovens_m':  _des(0.45, 'jovem macho 0-24m', 'Média ponderada das duas faixas.'),
}

# Teto de LTV sobre o valor JÁ deságiado.
LTV_APROVAR  = politica(0.60, 'Política de crédito da instituição',
                        rotulo='LTV folgado', nota='Até aqui, garantia folgada.')
LTV_RESSALVA = politica(0.80, 'Política de crédito da instituição',
                        rotulo='LTV ajustado',
                        nota='Entre 60% e 80% cobre, mas sem margem para queda de preço.')

_ROTULOS = {
    'bois':     'Bois (25m+)',
    'garrotes': 'Garrotes (13-24m)',
    'matrizes': 'Matrizes',
    'novilhas': 'Novilhas (13-24m)',
    'bezerras': 'Bezerras (0-12m)',
    'bezerros': 'Bezerros (0-12m)',
    'jovens_f': 'Jovens fêmeas (0-24m)',
    'jovens_m': 'Jovens machos (0-24m)',
}


def _fmt_rs(v) -> str:
    return f'R$ {v:,.0f}'.replace(',', '.')


def avaliar_garantia(valoracao: dict, credito_valor: float,
                     desagios: dict | None = None) -> dict:
    """
    Aplica deságio por categoria e mede o LTV do crédito pedido.

    `valoracao` é o retorno de fluxo_caixa_gep.valor_rebanho_gep — usa as
    chaves `valor_<categoria>`, então o split por categoria vem de lá e não é
    recalculado aqui.

    Devolve None em `ltv` quando não há crédito a avaliar; a avaliação da
    garantia em si continua sendo feita, porque o valor de execução interessa
    mesmo sem pedido em análise.
    """
    d = dict(DESAGIO_PADRAO)
    if desagios:
        d.update({k: float(v) for k, v in desagios.items() if k in DESAGIO_PADRAO})

    composicao = []
    valor_mercado = 0.0
    valor_garantia = 0.0
    for cat, desagio in d.items():
        vm = float(valoracao.get(f'valor_{cat}', 0.0) or 0.0)
        if vm <= 0:
            continue
        vg = vm * (1 - desagio)
        valor_mercado += vm
        valor_garantia += vg
        composicao.append({
            'categoria':      cat,
            'rotulo':         _ROTULOS.get(cat, cat),
            'valor_mercado':  round(vm, 2),
            'desagio_pct':    round(desagio * 100, 1),
            'valor_garantia': round(vg, 2),
        })
    composicao.sort(key=lambda r: -r['valor_garantia'])

    credito = max(float(credito_valor or 0.0), 0.0)
    desagio_medio = (1 - valor_garantia / valor_mercado) if valor_mercado > 0 else 0.0
    ltv = (credito / valor_garantia) if (valor_garantia > 0 and credito > 0) else None

    # Arredonda antes de comparar: no limite exato da política (crédito igual ao
    # teto) o LTV sai 0.6000000000000001 e o veredito virava 'ajustada' por
    # ruído de ponto flutuante, não por decisão de crédito.
    if ltv is not None:
        ltv = round(ltv, 6)

    if ltv is None:
        veredito, justificativa = None, 'Sem crédito a avaliar contra a garantia.'
    elif ltv <= LTV_APROVAR:
        veredito = 'suficiente'
        justificativa = (f'LTV {ltv*100:.1f}% sobre o valor de execução — garantia '
                         f'folgada para o crédito pedido.')
    elif ltv <= LTV_RESSALVA:
        veredito = 'ajustada'
        justificativa = (f'LTV {ltv*100:.1f}% sobre o valor de execução — a garantia '
                         f'cobre o crédito, mas sem margem para queda de preço.')
    else:
        veredito = 'insuficiente'
        justificativa = (f'LTV {ltv*100:.1f}% sobre o valor de execução — a garantia '
                         f'não cobre o crédito pedido com o deságio aplicado.')

    memoria = [
        {'passo': 'Valor de mercado do rebanho',
         'valor': _fmt_rs(valor_mercado),
         'detalhe': 'Soma das categorias pela cotação corrente, sem deságio.'},
        {'passo': 'Deságio médio ponderado',
         'valor': f'{desagio_medio*100:.1f}%',
         'detalhe': 'Média resultante dos deságios por categoria, ponderada pela '
                    'composição do rebanho. Um plantel de bois deságio menos que '
                    'um de bezerros.'},
        {'passo': 'Valor de execução da garantia',
         'valor': _fmt_rs(valor_garantia),
         'detalhe': 'O que se espera realizar numa venda forçada, já descontado '
                    'transporte, risco sanitário e ausência de escolha do momento '
                    'de mercado.'},
    ]
    if ltv is not None:
        memoria.append({
            'passo': 'LTV (crédito ÷ valor de execução)',
            'valor': f'{ltv*100:.1f}%',
            'detalhe': f'{_fmt_rs(credito)} ÷ {_fmt_rs(valor_garantia)}. '
                       f'Política: até {LTV_APROVAR*100:.0f}% folgada, até '
                       f'{LTV_RESSALVA*100:.0f}% ajustada, acima disso insuficiente.'})
        memoria.append({
            'passo': 'Crédito máximo pela garantia',
            'valor': _fmt_rs(valor_garantia * LTV_APROVAR),
            'detalhe': 'Teto que mantém o LTV na faixa folgada. É o limite pela '
                       'garantia — o limite pela capacidade de pagamento é outro, '
                       'e vale o menor dos dois.'})

    return {
        'valor_mercado':          round(valor_mercado, 2),
        'valor_garantia':         round(valor_garantia, 2),
        'desagio_medio_pct':      round(desagio_medio * 100, 1),
        'credito_valor':          round(credito, 2),
        'ltv':                    round(ltv * 100, 1) if ltv is not None else None,
        'ltv_aprovar_pct':        LTV_APROVAR * 100,
        'ltv_ressalva_pct':       LTV_RESSALVA * 100,
        'credito_maximo_garantia': round(valor_garantia * LTV_APROVAR, 2),
        'veredito':               veredito,
        'justificativa':          justificativa,
        'composicao':             composicao,
        'memoria':                memoria,
    }
