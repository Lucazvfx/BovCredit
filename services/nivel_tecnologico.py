"""
Nível tecnológico da fazenda — e por que ele NÃO se mede por cabeças.

O PROBLEMA

O sistema tem dois perfis de custo por modalidade (`média` e `top rentáveis`,
em custos_desembolso.py) e sempre aplica `média`. O botão "Top" existe, mas
quem decide é o analista, no olho, sem critério. Numa cria isso vale 23% de
diferença no custo — e custo errado em 23% desloca DSCR, margem e parecer na
mesma proporção.

POR QUE NÃO POR TAMANHO DE REBANHO

A intuição é que rebanho maior significa mais tecnologia e custo menor. Os
dados dizem outra coisa. Nos três painéis de cria da nossa própria base:

    Pelotas/RS        100 matrizes    R$ 166,35/@   ← o mais BARATO
    Altamira/PA       150 matrizes    R$ 189,76/@
    Pantanal/MS     4.657 cabeças     R$ 223,21/@   ← o mais CARO

O rebanho cresce 46 vezes e o custo SOBE. O Pantanal é caro porque é
extensivo (0,30 UA/ha), não porque é grande.

E a relação nem sequer é monotônica. O estudo Embrapa/Cepea/CNA de ganhos de
escala em Corumbá/MS comparou quatro propriedades modais — 3.600, 9.000,
14.400 e 30.000 ha: a MENOR teve o melhor retorno sobre o COE, a MAIOR veio em
segundo, e as INTERMEDIÁRIAS tiveram margem líquida negativa. É um U, não uma
ladeira. Uma regra por cabeças erraria justamente no rebanho médio.

O QUE SEPARA DE VERDADE

Intensificação: quanto animal a terra sustenta e quanta arroba ela produz.
São as duas variáveis com que a literatura nacional classifica, e são as que
explicam os nossos painéis.

    lotação          média Brasil 0,7 UA/ha    ·  semi-intensivo > 1,6 UA/ha
    produtividade    média Brasil 4,77 @/ha/ano ·  alta tecnologia 12,88

O grupo de alta produtividade é ~18% dos produtores e ocupa 8,5% da área.

Fontes: Rally da Pecuária (produtividade nacional 2023: 4,77 @/ha/ano; público
amostrado: 12,88); Embrapa Pantanal CT 126 (2024); Embrapa/Cepea/CNA, "Os
ganhos de escala dos sistemas modais de produção de pecuária de corte em
Corumbá, MS".

Módulo puro — sem Flask, sem banco.
"""
from __future__ import annotations

from services.fluxo_caixa_gep import CATEGORIAS_GEP
from services.proveniencia import referencia

# ── Unidade Animal ───────────────────────────────────────────────────────────
# UA = 450 kg de peso VIVO (padrão Embrapa Gado de Corte). Converte um rebanho
# de composição qualquer num número comparável entre fazendas.
KG_POR_UA = 450.0

# Peso vivo por faixa etária, na ordem canônica do vetor de rebanho. Reaproveita
# os pesos do GEP Araguaia onde a faixa coincide com uma categoria; as faixas
# intermediárias saem por interpolação entre as vizinhas, que é o que o próprio
# motor já faz em PESO_JOVEM_F_ARR / PESO_JOVEM_M_ARR.
_KG = {k: v['peso_kg'] for k, v in CATEGORIAS_GEP.items()}
PESO_VIVO_FAIXA_KG = [
    _KG['bezerra'] * 0.5,   # f00_F  fêmeas 0–4m   ~90 kg
    _KG['bezerro'] * 0.5,   # f00_M  machos 0–4m   ~100 kg
    _KG['bezerra'],         # f05_F  fêmeas 5–12m  180 kg
    _KG['bezerro'],         # f05_M  machos 5–12m  200 kg
    _KG['novilha'],         # f13_F  fêmeas 13–24m 280 kg
    _KG['garrote'],         # f13_M  machos 13–24m 320 kg
    _KG['vaca'],            # f25_F  fêmeas 25–36m 460 kg
    _KG['boi'],             # f25_M  machos 25–36m 560 kg
    _KG['vaca'],            # fac_F  fêmeas 36m+   460 kg
    _KG['boi'],             # fac_M  machos 36m+   560 kg
]

# ── Faixas de classificação ──────────────────────────────────────────────────
# REFERÊNCIA, não medição: são âncoras nacionais publicadas, não apuração
# nossa nem do proponente. A camada de proveniência registra isso.
LOTACAO_MEDIA_BR = referencia(
    0.7, 'Rally da Pecuária — lotação média nacional', rotulo='Lotação média Brasil')
LOTACAO_INTENSIVO = referencia(
    1.6, 'Sistemas semi-intensivos — acima de 1,6 UA/ha', rotulo='Lotação semi-intensiva')
PRODUTIVIDADE_MEDIA_BR = referencia(
    4.77, 'Rally da Pecuária 2023 — produtividade média nacional',
    rotulo='Produtividade média Brasil (@/ha/ano)')
# O limiar de 12 @/ha/ano vinha só do Rally (público amostrado: 12,88). Ganhou
# uma segunda confirmação, e desta vez de um PAINEL, não de matéria: Campo
# Futuro/CNA em Naviraí/MS — 1.250 ha em integração lavoura-pecuária, mais de
# 1.600 cabeças manejadas por ano, 884 comercializadas, semiconfinamento na
# terminação — mede 13 @/ha/ano. É uma operação inequivocamente intensiva, e
# cai logo acima do limiar. Duas fontes independentes, mesmo patamar.
PRODUTIVIDADE_INTENSIVO = referencia(
    12.0,
    'Rally da Pecuária (público amostrado 12,88 @/ha/ano) e painel Campo '
    'Futuro/CNA em Naviraí/MS, ILP com semiconfinamento (13 @/ha/ano)',
    rotulo='Produtividade alta tecnologia (@/ha/ano)')

EXTENSIVO   = 'extensivo'
MEDIO       = 'medio'
INTENSIVO   = 'intensivo'
INDEFINIDO  = 'indefinido'   # sem área declarada: não se classifica

_ROTULO = {
    EXTENSIVO:  'Extensivo',
    MEDIO:      'Médio',
    INTENSIVO:  'Intensivo',
    INDEFINIDO: 'Não determinado',
}


def unidades_animais(valores: list) -> float:
    """Converte o vetor de 10 faixas em Unidades Animais (450 kg vivos)."""
    if not valores:
        return 0.0
    v = [float(x or 0) for x in (list(valores) + [0] * 10)[:10]]
    return sum(v[i] * PESO_VIVO_FAIXA_KG[i] for i in range(10)) / KG_POR_UA


_ORDEM = {EXTENSIVO: 0, MEDIO: 1, INTENSIVO: 2}

# Arrobas por UA por ano acima das quais a conta não fecha fisicamente: um boi
# terminado sai com ~20@ e nem o confinamento gira mais que ~1,2 vez por ano.
# Acima disto a área declarada está errada, não a fazenda é excepcional.
ARROBAS_POR_UA_IMPLAUSIVEL = 25.0


def nivel_por_lotacao(ua_ha: float) -> str:
    """Nível pelo estoque de animais que a área sustenta."""
    if ua_ha < float(LOTACAO_MEDIA_BR):
        return EXTENSIVO
    if ua_ha >= float(LOTACAO_INTENSIVO):
        return INTENSIVO
    return MEDIO


def nivel_por_produtividade(arrobas_ha_ano: float) -> str:
    """Nível pela arroba que a área entrega no ano."""
    if arrobas_ha_ano < float(PRODUTIVIDADE_MEDIA_BR):
        return EXTENSIVO
    if arrobas_ha_ano >= float(PRODUTIVIDADE_INTENSIVO):
        return INTENSIVO
    return MEDIO


def classificar(ua_ha: float | None,
                arrobas_ha_ano: float | None = None) -> str:
    """Nível tecnológico pela lotação e pela produtividade, o MAIOR dos dois.

    POR QUE O MAIOR, E NÃO A LOTAÇÃO MANDANDO

    A primeira versão fazia a lotação mandar e deixava a produtividade só
    desempatar para cima. O raciocínio era que rebanho parado não é sistema
    intensivo. Os 19 painéis do Campo Futuro 2022 mostraram que a regra erra em
    dois deles, e erra pelo motivo que importa:

        Pontes e Lacerda/MT  recria    1,20 UA/ha   19,81 @/ha  → dizia MÉDIO
        Feira de Santana/BA  engorda   0,68 UA/ha   12,71 @/ha  → dizia EXTENSIVO

    São o segundo e o terceiro mais produtivos dos dezenove. O de Feira de
    Santana levava o perfil de custo extensivo, 27% mais caro, sendo uma das
    engordas mais eficientes da amostra.

    A razão é conceitual: LOTAÇÃO mede estoque parado, PRODUTIVIDADE mede giro.
    Num sistema que compra e vende — recria, engorda — dá para ter pouco animal
    no pasto e muita arroba no ano, porque o animal passa e sai. Feira de
    Santana entrega 18,7 @ por UA por ano, que é exatamente um giro de boi
    terminado. Não é rebanho parado: é rebanho rápido.

    Então cada eixo classifica sozinho e vale o maior dos dois. O caso que a
    regra antiga queria evitar — lotação alta com produção baixa — continua
    coberto: ali a produtividade classifica como extensivo ou médio e não
    promove nada, e a divergência vira aviso em `conferir_produtividade`.

    Sem área declarada devolve INDEFINIDO: o sistema mantém o perfil médio e
    diz no parecer que não classificou, em vez de chutar.
    """
    if not ua_ha or ua_ha <= 0:
        return INDEFINIDO

    n_lot = nivel_por_lotacao(ua_ha)
    if not arrobas_ha_ano or arrobas_ha_ano <= 0:
        return n_lot

    # Produtividade implausível para a lotação declarada não classifica nada: é
    # sinal de área errada na ficha, e promover daria o perfil de custo mais
    # barato a uma fazenda cujo dado não fecha.
    if arrobas_ha_ano / ua_ha > ARROBAS_POR_UA_IMPLAUSIVEL:
        return n_lot

    n_prod = nivel_por_produtividade(arrobas_ha_ano)
    n = max(n_lot, n_prod, key=lambda x: _ORDEM[x])

    # A ASSIMETRIA, e a razão dela: produtividade PROMOVE sozinha, lotação NÃO.
    #
    # Produtividade mede o que saiu; se saiu arroba, saiu. Lotação mede o que
    # está parado no pasto, e muito animal parado produzindo pouco é o caso que
    # a versão anterior desta função existia para pegar — rebanho ocupando área
    # sem gerar arroba. Deixar a lotação promover ali daria o perfil intensivo,
    # que é o mais BARATO dos três, e o erro correria a favor de aprovar.
    if n_lot == INTENSIVO and n_prod == EXTENSIVO:
        n = MEDIO
    return n


def rotulo(nivel: str) -> str:
    """Nome do nível para exibição."""
    return _ROTULO.get(nivel, _ROTULO[INDEFINIDO])


# ── O nível passa a mexer na PRODUÇÃO, não só no custo ───────────────────────
#
# Até aqui o nível escolhia o perfil de custo e parava aí. A simulação projetava
# as MESMAS arrobas nos três níveis, o que é falso na direção perigosa: um
# extensivo colhe menos arroba por cabeça, então o custo POR ARROBA dele ficava
# subestimado e o parecer o via mais barato do que ele é.
#
# Estava escrito neste módulo como pendência, dizendo que a correção exigia
# saber quanta arroba a menos um extensivo colhe. O número chegou.
#
# Tabela 2.3 do relatório de cenários para a pecuária — manejos de
# suplementação por idade de abate, em sistemas de ciclo completo a pasto:
#
#     idade ao abate   GMD (kg/dia)   manejo
#     32–36 meses      0,50–0,40      sem creep, mineral + pasto
#     22–26 meses      0,60–0,70      creep opcional, terminação na 2ª seca
#     17–18 meses      0,80–0,90      creep + suplemento múltiplo
#     13–15 meses      1,20–1,30      creep + confinamento
#
# *GMD medido da DESMAMA AO ABATE, que é exatamente o período que a nossa
# engorda simula.
#
# O DEFAULT ANTIGO ERA DE PRECOCE. `simular_cenario` usava 0,85 kg/dia para
# todo mundo — o valor do sistema de 17–18 meses, com creep feeding e
# suplemento múltiplo. Aplicado a uma fazenda extensiva, projetava o boi
# ganhando quase o dobro do que ele ganha, e a engorda terminando em metade do
# tempo. Como a duração manda nos giros por ano, isso inflava o desfrute e o
# DSCR — de novo do lado de aprovar.
#
# Confinamento não vira nível: ele não é um degrau de intensificação de pasto,
# é outro sistema, e o nosso perfil de custo de engorda descreve pasto com
# suplementação. Quem confina informa o GMD na ficha e vence este default.
_TABELA_2_3 = ('Tabela 2.3, relatório de cenários para a pecuária — manejos de '
               'suplementação por idade de abate em ciclo completo a pasto '
               '(GMD da desmama ao abate)')

GMD_POR_NIVEL = {
    EXTENSIVO:  referencia(0.45, _TABELA_2_3 + '; abate aos 32–36 meses '
                           '(0,40–0,50 kg/dia), sem creep, mineral e pasto',
                           rotulo='GMD · extensivo'),
    MEDIO:      referencia(0.65, _TABELA_2_3 + '; abate aos 22–26 meses '
                           '(0,60–0,70 kg/dia), terminação na 2ª seca',
                           rotulo='GMD · médio'),
    INTENSIVO:  referencia(0.85, _TABELA_2_3 + '; abate aos 17–18 meses '
                           '(0,80–0,90 kg/dia), creep e suplemento múltiplo',
                           rotulo='GMD · intensivo'),
}

# Sem área declarada não se classifica — e aí a pergunta é qual GMD supor de
# uma fazenda que não disse nada.
#
# O default histórico era 0,85, que a Tabela 2.3 identifica como abate aos
# 17–18 meses com creep feeding e suplemento múltiplo. Supor precoce de quem
# não declarou nada é a suposição mais otimista possível, e otimismo aqui vira
# arroba projetada, que vira DSCR, que vira aprovação.
#
# O meio da escala é a posição honesta do desconhecido, e ainda fica otimista
# perto da realidade nacional: 0,65 implica abate aos 22–26 meses, contra os
# ~30+ meses da média brasileira.
#
# DIREÇÃO DA MUDANÇA, declarada: para BAIXO. Uma engorda sem área declarada
# projeta 24% menos arroba do que projetava, e o DSCR cai junto — o lado de
# reprovar, que é o barato num produto de crédito. A troca do giro truncado
# pelo fracionário empurra na direção oposta; medido numa engorda de 780
# cabeças, as duas juntas saem de DSCR 2,93 para 2,46.
GMD_PADRAO_SEM_NIVEL = float(GMD_POR_NIVEL[MEDIO])


def gmd_do_nivel(nivel: str | None) -> float:
    """GMD em kg/dia coerente com o nível de intensificação (Tabela 2.3)."""
    if nivel is None:
        return GMD_PADRAO_SEM_NIVEL
    return float(GMD_POR_NIVEL.get(nivel, GMD_PADRAO_SEM_NIVEL))


def avaliar(valores: list, area_pasto_ha: float | None,
            arrobas_vendidas_ano: float | None = None) -> dict:
    """Classifica a fazenda e devolve os números que sustentam a classificação.

    Args:
        valores: vetor de 10 faixas do rebanho.
        area_pasto_ha: área de pastagem em hectares; None ou 0 → INDEFINIDO.
        arrobas_vendidas_ano: arrobas comercializadas no ano, para a
            produtividade por hectare. Opcional.

    Returns:
        `{nivel, rotulo, ua, ua_ha, arrobas_ha_ano, area_pasto_ha, referencias}`.
        `ua_ha` e `arrobas_ha_ano` vêm None quando não há área.
    """
    ua = unidades_animais(valores)
    area = float(area_pasto_ha or 0)

    ua_ha = (ua / area) if area > 0 else None
    prod  = ((float(arrobas_vendidas_ano) / area)
             if area > 0 and arrobas_vendidas_ano else None)

    nivel = classificar(ua_ha, prod)
    return {
        'nivel':          nivel,
        'rotulo':         rotulo(nivel),
        'ua':             round(ua, 1),
        'ua_ha':          round(ua_ha, 2) if ua_ha is not None else None,
        'arrobas_ha_ano': round(prod, 2) if prod is not None else None,
        'area_pasto_ha':  area or None,
        'referencias': {
            'lotacao_media_br':       float(LOTACAO_MEDIA_BR),
            'lotacao_intensivo':      float(LOTACAO_INTENSIVO),
            'produtividade_media_br': float(PRODUTIVIDADE_MEDIA_BR),
            'produtividade_intensivo': float(PRODUTIVIDADE_INTENSIVO),
        },
    }


def conferir_produtividade(info: dict, arrobas_vendidas_ano: float | None) -> dict:
    """Acrescenta a produtividade medida à classificação já feita.

    ORDEM DAS COISAS, e por que ela obriga a isto: a produtividade em @/ha/ano
    depende das arrobas vendidas, que vêm da simulação, que precisa do custo,
    que é o que o nível decide. O nível, portanto, é classificado ANTES, só
    pela lotação — e a produtividade entra depois como CONFERÊNCIA.

    Ela não reescreve o nível nem o custo. Reescrever em silêncio produziria um
    parecer cujo custo não corresponde ao nível exibido, e ninguém acharia o
    erro. Quando a produtividade contradiz a lotação — muita UA por hectare e
    pouca arroba produzida, que é o rebanho parado — isso vira um aviso
    explícito, para o analista olhar.
    """
    info = dict(info)
    area = info.get('area_pasto_ha')
    if not area or not arrobas_vendidas_ano:
        return info

    prod = float(arrobas_vendidas_ano) / float(area)
    info['arrobas_ha_ano'] = round(prod, 2)

    # O caso que interessa: classificado como intensivo pela lotação, mas
    # produzindo menos que o limiar de produtividade. Rebanho parado ocupa
    # pasto sem gerar arroba, e o custo do perfil intensivo é o mais baixo dos
    # três — seria o erro correndo a favor de aprovar, de novo.
    if (info.get('nivel') == INTENSIVO
            and prod < float(PRODUTIVIDADE_INTENSIVO)):
        info['divergencia'] = {
            'motivo': 'lotacao_alta_produtividade_baixa',
            'texto': (f'A lotação de {info.get("ua_ha")} UA/ha classifica como '
                      f'intensivo, mas a produção é de {prod:.2f} @/ha/ano, '
                      f'abaixo das {float(PRODUTIVIDADE_INTENSIVO):.0f} @/ha/ano '
                      f'do nível. Rebanho ocupando pasto sem gerar arroba: o '
                      f'custo aplicado foi o do perfil intensivo, que é o mais '
                      f'baixo dos três. Confira antes de aceitar o resultado.'),
        }
    return info
