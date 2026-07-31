"""
Preço por praça: aplica o diferencial regional sobre o indicador nacional.

O sistema usava UM preço para o Brasil inteiro. A mesma arroba valia igual em
Araçatuba-SP e em Ariquemes-RO, e isso não é detalhe: o indicador CEPEA/ESALQ
é praça de São Paulo, e o produtor de Rondônia vende com desconto relevante
sobre ele. Um LTV calculado com preço paulista numa fazenda rondoniense está
errado por construção — e é justamente o LTV que decide se a garantia cobre.

O QUE ESTES NÚMEROS SÃO, E O QUE NÃO SÃO

`BASIS_UF` são diferenciais de REFERÊNCIA, na mesma categoria dos deságios de
garantia e das faixas de DSCR: parâmetros de calibração, ajustáveis, que
descrevem a ordem de grandeza dos spreads regionais publicados. **Não são
medição nossa.** Nenhum deles foi apurado contra série própria, porque a série
própria ainda não existe.

Ela vai existir: todo parecer emitido registra município e o preço que o
analista usou ou sobrescreveu. Acumulados, esses pares (praça, data, preço)
são a base para recalibrar esta tabela com dado real — o mesmo desenho do
botão de confirmação de ciclo. Até lá, o parecer diz de onde veio o número,
e o analista pode sobrescrever.

A ordenação, essa sim, tem razão de ser: distância dos centros de abate e
consumo, custo de frete e histórico sanitário empurram o preço para baixo à
medida que se sobe pelo arco norte.

Módulo puro — não importa Flask nem DB.
"""
from __future__ import annotations

import re

# Praça de referência do indicador nacional (CEPEA/ESALQ boi gordo).
UF_REFERENCIA = 'SP'

# Diferencial sobre o indicador nacional, por UF. Negativo = abaixo da praça
# de referência. Ver o aviso no topo: calibração, não medição.
BASIS_UF = {
    'SP': 0.00,
    'RS': 0.00,
    'SC': 0.01,
    'PR': -0.01,
    'MG': -0.02,
    'RJ': -0.02,
    'ES': -0.03,
    'GO': -0.04,
    'MS': -0.04,
    'DF': -0.04,
    'BA': -0.06,
    'MT': -0.07,
    'TO': -0.08,
    'PI': -0.08,
    'MA': -0.09,
    'PE': -0.09,
    'CE': -0.09,
    'RO': -0.10,
    'PA': -0.10,
    'AL': -0.10,
    'SE': -0.10,
    'PB': -0.10,
    'RN': -0.10,
    'AC': -0.13,
    'AM': -0.14,
    'RR': -0.14,
    'AP': -0.14,
}

_UFS = set(BASIS_UF)

# Categorias que recebem o diferencial. Bezerro é o caso mais frágil: o mercado
# de reposição é bem mais segmentado regionalmente que o de boi gordo, e o
# diferencial verdadeiro costuma ser MAIOR que o do boi. Aplicamos o mesmo
# fator por ora — inventar um segundo nível de precisão sem série própria seria
# passar por medição o que é chute. Fica registrado como limitação conhecida.
CATEGORIAS = ('preco_boi', 'preco_vaca', 'preco_bezerro', 'preco_bezerra')


def extrair_uf(texto: str) -> str | None:
    """
    Extrai a UF de um campo livre de município.

    O formulário pede "Município / Estado" e o analista escreve como quiser:
    'Juara - MT', 'Juara/MT', 'JUARA MT', 'Ariquemes - RO'. Devolve None quando
    não dá para afirmar, que é melhor que adivinhar errado — sem UF o sistema
    usa o preço nacional e diz que usou.
    """
    if not texto:
        return None
    up = re.sub(r'[^A-Za-zÀ-ÿ\s/\-]', ' ', str(texto)).upper()
    # Procura de trás para frente: a UF quase sempre encerra a string.
    candidatos = re.findall(r'\b([A-Z]{2})\b', up)
    for c in reversed(candidatos):
        if c in _UFS:
            return c
    return None


def basis(uf: str | None) -> float | None:
    """Diferencial da UF, ou None quando a praça é desconhecida."""
    if not uf:
        return None
    return BASIS_UF.get(uf.strip().upper())


def _fmt_pct(f: float) -> str:
    return f'{f*100:+.0f}%'.replace('+0%', '0%')


def aplicar(precos: dict, municipio: str | None = None, uf: str | None = None,
            ajustaveis: set | None = None) -> dict:
    """
    Devolve os preços ajustados à praça, com a proveniência junto.

    `precos` é {preco_boi, preco_vaca, preco_bezerro, preco_bezerra} — valores
    podem ser None. `ajustaveis` limita quais categorias recebem o diferencial:
    um preço digitado pelo analista JÁ é o preço da praça dele, e aplicar o
    diferencial sobre ele seria descontar duas vezes.

    Devolve sempre `precos` (ajustados ou não) e `regional` com o que foi feito,
    para que o parecer possa dizer de onde veio cada número.
    """
    uf_final = (uf or '').strip().upper() or extrair_uf(municipio or '')
    dif = basis(uf_final)
    alvo = CATEGORIAS if ajustaveis is None else tuple(ajustaveis)

    ajustados = dict(precos or {})
    aplicados = []

    if dif is not None and dif != 0.0:
        for cat in alvo:
            v = ajustados.get(cat)
            if v:
                novo = round(float(v) * (1 + dif), 2)
                aplicados.append({'categoria': cat,
                                  'nacional': round(float(v), 2),
                                  'regional': novo})
                ajustados[cat] = novo

    if not uf_final:
        situacao = 'sem_uf'
        resumo = ('Praça não identificada — usando o indicador nacional. '
                  'Informe o estado no campo Município / Estado para o preço '
                  'ser ajustado à região.')
    elif dif is None:
        situacao = 'uf_desconhecida'
        resumo = (f'UF {uf_final} sem diferencial cadastrado — usando o '
                  f'indicador nacional.')
    elif dif == 0.0:
        situacao = 'praca_referencia'
        resumo = (f'{uf_final} é a praça de referência do indicador '
                  f'CEPEA/ESALQ — sem ajuste.')
    elif not aplicados:
        situacao = 'sem_precos_ajustaveis'
        resumo = (f'Preços informados manualmente — já são da praça do '
                  f'analista, sem ajuste adicional.')
    else:
        situacao = 'ajustado'
        resumo = (f'Preços ajustados para {uf_final}: {_fmt_pct(dif)} sobre o '
                  f'indicador nacional (praça de referência {UF_REFERENCIA}).')

    memoria = []
    if situacao == 'ajustado':
        memoria.append({
            'passo': f'Diferencial de praça ({uf_final})',
            'valor': _fmt_pct(dif),
            'detalhe': ('O indicador CEPEA/ESALQ é praça de São Paulo. '
                        'Distância dos centros de abate, frete e histórico '
                        'sanitário deslocam o preço regional. Diferencial de '
                        'referência — recalibrar com série própria.'),
        })
        for a in aplicados:
            rot = a['categoria'].replace('preco_', '').capitalize()
            memoria.append({
                'passo': f'{rot} — nacional → praça',
                'valor': f"R$ {a['nacional']:,.2f} → R$ {a['regional']:,.2f}".replace(',', '.'),
                'detalhe': f'Aplicado o diferencial de {uf_final}.',
            })

    return {
        'precos': ajustados,
        'regional': {
            'uf':             uf_final,
            'municipio':      municipio,
            'basis_pct':      round(dif * 100, 1) if dif is not None else None,
            'uf_referencia':  UF_REFERENCIA,
            'situacao':       situacao,
            'ajustado':       situacao == 'ajustado',
            'categorias':     aplicados,
            'resumo':         resumo,
            'origem':         'diferencial de referência (não medido)',
            'memoria':        memoria,
        },
    }
