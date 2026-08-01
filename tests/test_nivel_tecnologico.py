"""
Nível tecnológico — e a razão de ele NÃO ser por tamanho de rebanho.

O sistema tinha dois perfis de custo por modalidade (`média` e `top
rentáveis`) e nenhum critério para escolher entre eles: aplicava sempre
`media` e deixava o `top` num botão que o analista clicava no olho. Numa cria
isso vale 23% no custo, e custo errado em 23% desloca DSCR e parecer na mesma
proporção.

A chave escolhida foi lotação e produtividade, não cabeças. O que sustenta
isso, e que estes testes protegem de ser desfeito por intuição:

  · nos três painéis de cria da nossa base o rebanho cresce 46× e o custo SOBE
    (Pelotas 100 matrizes R$ 166,35 → Pantanal 4.657 cab R$ 223,21)
  · o estudo Embrapa/Cepea/CNA de escala em Corumbá achou relação em U —
    menor e maior com bom retorno, INTERMEDIÁRIAS com margem líquida negativa
  · o que explica os painéis é intensificação: o Pantanal é caro a 0,30 UA/ha

Âncoras nacionais (Rally da Pecuária): 0,7 UA/ha e 4,77 @/ha/ano de média;
alta tecnologia acima de 1,6 UA/ha e 12 @/ha/ano.
"""
import pytest

from services.nivel_tecnologico import (
    PRODUTIVIDADE_MEDIA_BR,
    avaliar, classificar, conferir_produtividade, unidades_animais,
    EXTENSIVO, MEDIO, INTENSIVO, INDEFINIDO,
    LOTACAO_MEDIA_BR, LOTACAO_INTENSIVO, PRODUTIVIDADE_INTENSIVO,
    KG_POR_UA, PESO_VIVO_FAIXA_KG,
)
from services.custos_desembolso import (
    preset_modalidade, perfil_do_nivel, custo_arroba_padrao, FATOR_EXTENSIVO,
)
from services.proveniencia import REFERENCIA

# Rebanho de recria real do projeto, 700 cabeças.
FICHA_RECRIA = [22, 219, 0, 0, 105, 234, 45, 16, 59, 0]


# ── Unidade Animal ──────────────────────────────────────────────────────────
def test_ua_usa_peso_vivo_e_nao_contagem_de_cabecas():
    """
    Mil bezerros não são mil UA. UA é 450 kg vivos, e é o que torna rebanhos de
    composições diferentes comparáveis — que é justamente o que contagem de
    cabeças não faz.
    """
    mil_bezerras = [1000] + [0] * 9
    mil_bois     = [0] * 9 + [1000]
    assert unidades_animais(mil_bezerras) < unidades_animais(mil_bois)
    assert unidades_animais(mil_bois) == pytest.approx(
        1000 * PESO_VIVO_FAIXA_KG[9] / KG_POR_UA)


def test_ua_tolera_vetor_curto_ou_vazio():
    assert unidades_animais([]) == 0.0
    assert unidades_animais(None) == 0.0
    assert unidades_animais([10, 10]) > 0


# ── Classificação ───────────────────────────────────────────────────────────
@pytest.mark.parametrize('ua_ha,esperado', [
    (0.30, EXTENSIVO),    # a lotação do painel do Pantanal
    (0.69, EXTENSIVO),
    (0.70, MEDIO),        # média nacional
    (1.40, MEDIO),        # o sistema Embrapa Brasil Central
    (1.60, INTENSIVO),
    (3.00, INTENSIVO),
])
def test_a_lotacao_define_o_nivel(ua_ha, esperado):
    assert classificar(ua_ha) == esperado


def test_sem_area_nao_se_chuta_nivel():
    """
    Sem área não há lotação, e sem lotação não há classificação. Devolver
    'médio' calado seria pior: o parecer diria um nível que ninguém apurou.
    """
    assert classificar(None) == INDEFINIDO
    assert classificar(0) == INDEFINIDO
    assert avaliar(FICHA_RECRIA, None)['nivel'] == INDEFINIDO
    assert avaliar(FICHA_RECRIA, 0)['ua_ha'] is None


def test_lotacao_alta_com_producao_baixa_nao_e_intensivo():
    """
    Rebanho parado ocupa pasto sem gerar arroba. Se a produtividade estiver
    disponível na hora de classificar, ela impede a promoção — porque o perfil
    intensivo é o de custo MAIS BAIXO dos três, e o erro correria a favor de
    aprovar.
    """
    assert classificar(2.5, arrobas_ha_ano=3.0) == MEDIO
    assert classificar(2.5, arrobas_ha_ano=15.0) == INTENSIVO
    # produtividade ausente não bloqueia: é conferência, não requisito
    assert classificar(2.5, arrobas_ha_ano=None) == INTENSIVO


def test_produtividade_nunca_promove_sozinha():
    """Produzir muito num pasto vazio não faz do sistema um intensivo."""
    assert classificar(0.4, arrobas_ha_ano=30.0) == EXTENSIVO


# ── A conferência que vem depois da simulação ───────────────────────────────
def test_a_produtividade_confere_mas_nao_reescreve():
    """
    A produtividade depende das arrobas vendidas, que dependem da simulação,
    que precisou do custo — que é o que o nível decidiu. Se a conferência
    reclassificasse, o parecer exibiria um nível diferente do que foi usado no
    custo, e ninguém acharia o erro.
    """
    info = avaliar(FICHA_RECRIA, 150)          # lotação alta → intensivo
    assert info['nivel'] == INTENSIVO
    conferido = conferir_produtividade(info, arrobas_vendidas_ano=100)
    assert conferido['nivel'] == INTENSIVO, 'a conferência reescreveu o nível'
    assert conferido['divergencia']['motivo'] == 'lotacao_alta_produtividade_baixa'
    assert 'mais baixo dos três' in conferido['divergencia']['texto']


def test_produtividade_coerente_nao_gera_aviso():
    info = avaliar(FICHA_RECRIA, 150)
    conferido = conferir_produtividade(
        info, arrobas_vendidas_ano=150 * float(PRODUTIVIDADE_INTENSIVO) * 1.2)
    assert 'divergencia' not in conferido
    assert conferido['arrobas_ha_ano'] > float(PRODUTIVIDADE_INTENSIVO)


def test_conferencia_sem_area_e_inocua():
    info = avaliar(FICHA_RECRIA, None)
    assert conferir_produtividade(info, 5000) == info


# ── O elo com o custo ───────────────────────────────────────────────────────
def test_cada_nivel_puxa_um_perfil_diferente():
    assert perfil_do_nivel(EXTENSIVO) == 'extensivo'
    assert perfil_do_nivel(MEDIO)     == 'media'
    assert perfil_do_nivel(INTENSIVO) == 'top'


def test_sem_nivel_o_custo_e_o_de_antes():
    """
    Compatibilidade: quem não informa área tem exatamente o custo que tinha
    antes desta mudança. Um recurso novo que altera o número de todo mundo
    silenciosamente é um recurso que ninguém consegue auditar.
    """
    for mod in ('CRIA', 'RECRIA', 'ENGORDA', 'CICLO_COMPLETO'):
        assert (custo_arroba_padrao(mod, 9.8)
                == custo_arroba_padrao(mod, 9.8, nivel=INDEFINIDO)
                == custo_arroba_padrao(mod, 9.8, nivel=MEDIO))


@pytest.mark.parametrize('mod', ['CRIA', 'RECRIA', 'CICLO_COMPLETO'])
def test_o_custo_cresce_do_intensivo_para_o_extensivo(mod):
    """
    Nos ciclos que criam ou fazem crescer animal, intensificar é ficar mais
    eficiente por cabeça: o extensivo custa mais.
    """
    c = {n: custo_arroba_padrao(mod, 9.8, nivel=n)
         for n in (INTENSIVO, MEDIO, EXTENSIVO)}
    assert c[INTENSIVO] < c[MEDIO] < c[EXTENSIVO], (mod, c)


def test_na_engorda_intensificar_custa_MAIS_por_cabeca():
    """
    A engorda é a exceção, e ela aparece nos próprios dados da fonte: o perfil
    "top rentáveis" gasta MAIS insumo que o médio (R$ 102,80 contra R$ 85,20
    por cabeça/mês), porque intensificar terminação é suplementar mais.

    Isso ficava escondido enquanto as rubricas de investimento entravam na
    conta — elas eram maiores no perfil médio e mascaravam a inversão. Separar
    custeio de investimento expôs a propriedade real do dado.

    Não é contradição: na engorda o intensivo custa mais POR CABEÇA e menos
    POR ARROBA, porque produz mais arroba na mesma cabeça. O parecer compara
    por arroba; este teste prende o que a fonte diz por cabeça, para ninguém
    "corrigir" a tabela achando que há erro de digitação.
    """
    from services.custos_desembolso import PERFIL_DESEMBOLSO, desembolso_operacional, preset_modalidade
    assert PERFIL_DESEMBOLSO['ENGORDA']['insumos'][1] > PERFIL_DESEMBOLSO['ENGORDA']['insumos'][0]
    oper = {p: desembolso_operacional(preset_modalidade('ENGORDA', p))
            for p in ('extensivo', 'media', 'top')}
    assert oper['top'] > oper['media'], oper
    assert oper['extensivo'] > oper['top'], oper


def test_o_perfil_extensivo_e_derivado_do_medio_e_nao_inventado():
    """
    `media` e `top` são medidos componente a componente (GEP Araguaia). O
    extensivo é a coluna média × FATOR_EXTENSIVO, e o fator tem derivação
    escrita: painel do Pantanal (R$ 223,21/@) ÷ média dos outros dois painéis
    de cria (R$ 178,06/@) = 1,254.

    Inventar oito valores de componente que ninguém mediu seria passar por
    apuração o que é aritmética.
    """
    media = preset_modalidade('CRIA', 'media')
    ext   = preset_modalidade('CRIA', 'extensivo')
    assert set(media) == set(ext)
    for k in media:
        assert ext[k] == pytest.approx(media[k] * FATOR_EXTENSIVO, abs=0.01)

    from services.benchmarks_nacionais import COE_PAINEIS
    cria = COE_PAINEIS['CRIA']
    pantanal = [p['coe_arroba'] for p in cria if p['uf'] == 'MS'][0]
    outros = [p['coe_arroba'] for p in cria if p['uf'] != 'MS']
    fator_medido = pantanal / (sum(outros) / len(outros))
    assert abs(FATOR_EXTENSIVO - fator_medido) < 0.02, (
        f'FATOR_EXTENSIVO ({FATOR_EXTENSIVO}) descolou da derivação '
        f'({fator_medido:.3f}) — se um painel mudou, o fator precisa mudar junto'
    )


def test_perfil_desconhecido_cai_no_medio():
    assert preset_modalidade('CRIA', 'nao_existe') == preset_modalidade('CRIA', 'media')
    assert perfil_do_nivel('nao_existe') == 'media'


# ── As âncoras são referência, não medição ──────────────────────────────────
@pytest.mark.parametrize('p', [LOTACAO_MEDIA_BR, LOTACAO_INTENSIVO,
                               PRODUTIVIDADE_INTENSIVO],
                         ids=lambda p: p.rotulo)
def test_as_ancoras_estao_rotuladas_como_referencia(p):
    """
    São números nacionais publicados, não apuração nossa nem do proponente.
    Marcá-los como medição seria exatamente o que a camada de proveniência
    existe para impedir.
    """
    assert p.origem == REFERENCIA
    assert p.fonte


# ── O que o rebanho da nossa ficha real diz ─────────────────────────────────
def test_a_ficha_real_muda_de_nivel_conforme_a_area():
    """
    A mesma ficha de 700 cabeças é extensiva em 3.000 ha e intensiva em 150 —
    e é por isso que a área precisou virar campo. Sem ela, as duas fazendas
    recebiam o mesmo custo.
    """
    niveis = [avaliar(FICHA_RECRIA, ha)['nivel'] for ha in (3000, 900, 300, 150)]
    assert niveis == [EXTENSIVO, EXTENSIVO, MEDIO, INTENSIVO]


def test_o_limiar_de_produtividade_tem_duas_fontes():
    """
    O limiar de 12 @/ha/ano vinha só do Rally da Pecuária, que é matéria de
    imprensa sobre um levantamento. Ganhou confirmação de um PAINEL: Campo
    Futuro/CNA em Naviraí/MS — 1.250 ha em integração lavoura-pecuária, mais de
    1.600 cabeças manejadas/ano, semiconfinamento na terminação — mede
    13 @/ha/ano.

    Uma operação inequivocamente intensiva caindo logo acima do limiar é a
    checagem que se pode fazer sem ter a série própria: se Naviraí caísse
    ABAIXO de 12, o limiar estaria alto demais e classificaria como médio quem
    é intensivo.
    """
    NAVIRAI_ARROBAS_HA = 13.0
    assert NAVIRAI_ARROBAS_HA >= float(PRODUTIVIDADE_INTENSIVO), (
        'o limiar passou de 13 @/ha e deixaria de reconhecer um ILP com '
        'semiconfinamento como intensivo'
    )
    assert float(PRODUTIVIDADE_INTENSIVO) >= NAVIRAI_ARROBAS_HA * 0.85, (
        'o limiar caiu demais e passaria a chamar de intensivo quem não é'
    )
    fonte = PRODUTIVIDADE_INTENSIVO.fonte
    assert 'Rally' in fonte and 'Naviraí' in fonte, 'as duas fontes precisam estar citadas'


# ── A regra validada contra os 19 painéis do Campo Futuro 2022 ──────────────
def test_os_paineis_mais_produtivos_sao_classificados_como_intensivos():
    """
    A primeira versão de `classificar` fazia a lotação mandar e deixava a
    produtividade só desempatar para cima. Os 19 painéis mostraram que a regra
    errava em dois, e errava no que importa:

        Pontes e Lacerda/MT  recria    1,20 UA/ha  19,81 @/ha  → dizia MÉDIO
        Feira de Santana/BA  engorda   0,68 UA/ha  12,71 @/ha  → dizia EXTENSIVO

    São o segundo e o terceiro mais produtivos da amostra. O de Feira de Santana
    levava o perfil de custo EXTENSIVO, 27% mais caro, sendo uma das engordas
    mais eficientes medidas.

    A causa é conceitual: lotação mede estoque parado, produtividade mede giro.
    Num sistema que compra e vende dá para ter pouco animal no pasto e muita
    arroba no ano — Feira de Santana entrega 18,7 @ por UA por ano, que é
    exatamente um giro de boi terminado.
    """
    from services.benchmarks_nacionais import PAINEIS_DESFRUTE_2022
    top3 = sorted(PAINEIS_DESFRUTE_2022, key=lambda p: -p[4])[:3]
    for mun, uf, _sist, _d, arrobas_ha, ua_ha in top3:
        assert classificar(ua_ha, arrobas_ha) == INTENSIVO, (
            f'{mun}/{uf}: {arrobas_ha} @/ha e {ua_ha} UA/ha não classificou '
            f'como intensivo'
        )


def test_nenhum_painel_medido_cai_em_extensivo_produzindo_acima_da_media():
    """
    Extensivo é o perfil de custo mais CARO (+27%). Aplicá-lo a quem produz
    acima da média nacional é penalizar eficiência.
    """
    from services.benchmarks_nacionais import PAINEIS_DESFRUTE_2022
    erros = [
        f'{mun}/{uf}: {arr} @/ha com {ua} UA/ha → extensivo'
        for mun, uf, _s, _d, arr, ua in PAINEIS_DESFRUTE_2022
        if arr >= float(PRODUTIVIDADE_MEDIA_BR) * 1.5
        and classificar(ua, arr) == EXTENSIVO
    ]
    assert not erros, 'painéis produtivos classificados como extensivos:\n  ' + '\n  '.join(erros)


def test_a_natalidade_de_referencia_bate_com_a_mediana_medida():
    """
    NATALIDADE_PCT = 70% vinha de faixa bibliográfica. A mediana dos 12 painéis
    de cria e ciclo completo do Campo Futuro 2022 é 70,12%.

    É a confirmação mais limpa que apareceu: um parâmetro de referência caindo
    em cima da mediana medida, sem ajuste.
    """
    import statistics
    from services.parametros_zootecnicos import NATALIDADE_PCT
    medidas = [70.14, 60.20, 58.94, 65.18, 66.44, 70.11, 70.71, 66.50, 70.46,
               76.48, 81.20, 77.68]
    assert abs(float(NATALIDADE_PCT) - statistics.median(medidas)) < 1.0
