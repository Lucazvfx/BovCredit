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
PRODUTIVIDADE_INTENSIVO = referencia(
    12.0, 'Sistemas semi-intensivos — acima de 12 @/ha/ano; público do Rally: 12,88',
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


def classificar(ua_ha: float | None,
                arrobas_ha_ano: float | None = None) -> str:
    """Nível tecnológico a partir de lotação e, quando houver, produtividade.

    A lotação manda; a produtividade só desempata para cima. Uma fazenda pode
    ter lotação alta e produzir pouco (rebanho parado, desfrute baixo), e nesse
    caso não é intensiva coisa nenhuma — por isso exigir os DOIS para subir a
    intensivo, e bastar um para cair a extensivo.

    Sem área declarada (`ua_ha` ausente ou não positiva) devolve INDEFINIDO. O
    sistema então mantém o perfil médio e diz no parecer que não classificou —
    é preferível a chutar um nível.
    """
    if not ua_ha or ua_ha <= 0:
        return INDEFINIDO

    if ua_ha < float(LOTACAO_MEDIA_BR):
        return EXTENSIVO

    if ua_ha >= float(LOTACAO_INTENSIVO):
        if arrobas_ha_ano is None:
            return INTENSIVO
        return (INTENSIVO if arrobas_ha_ano >= float(PRODUTIVIDADE_INTENSIVO)
                else MEDIO)

    return MEDIO


def rotulo(nivel: str) -> str:
    """Nome do nível para exibição."""
    return _ROTULO.get(nivel, _ROTULO[INDEFINIDO])


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
