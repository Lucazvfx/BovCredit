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


@pytest.mark.parametrize('mod', ['CRIA', 'RECRIA', 'ENGORDA', 'CICLO_COMPLETO'])
def test_o_custo_cresce_do_intensivo_para_o_extensivo(mod):
    c = {n: custo_arroba_padrao(mod, 9.8, nivel=n)
         for n in (INTENSIVO, MEDIO, EXTENSIVO)}
    assert c[INTENSIVO] < c[MEDIO] < c[EXTENSIVO], (mod, c)


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
