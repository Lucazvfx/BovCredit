"""
Um painel não é um benchmark nacional.

Até aqui havia UM painel Campo Futuro por modalidade, os três do Pará, e o
sistema comparava a fazenda contra aquele ponto — fosse ela de Rondônia ou do
Rio Grande do Sul. Com um segundo painel por modalidade aparece o que o ponto
escondia: a mesma metodologia, no mesmo sistema, dá números e composições bem
diferentes conforme a praça.

    CRIA             Altamira/PA          R$ 189,76/@   mão de obra 18,2%
                     Pelotas/RS           R$ 166,35/@   mão de obra 42,9%
    RECRIA_ENGORDA   Paragominas/PA       R$ 183,50/@   reposição   62,2%
                     Colorado d'Oeste/RO  R$ 171,88/@   aquisição   51,6%

O total varia ~7%; a COMPOSIÇÃO varia muito mais. Quem lê só o total não vê.

O que estes testes prendem:

  1. a comparação é contra a FAIXA, não contra um ponto — quem está entre dois
     painéis reais não é apontado
  2. o teto é que conta: só o excesso sobre o painel mais caro vira aviso
  3. a praça escolhe o painel — UF, depois região
  4. as fichas reais que motivaram o aviso CONTINUAM sinalizadas; a faixa não
     serve para encobrir custo alto de verdade
  5. o perímetro é COE contra COE, e isso está declarado no retorno

Fonte dos painéis novos: Campo Futuro/CNA — Colorado d'Oeste/RO (recria e
engorda em semiconfinamento, 100 cab abatidas/ano, R$ 171,88/@) e Pelotas/RS
(cria, 250 ha, 100 matrizes, R$ 166,35/@).
"""
import pytest

from services.benchmarks_nacionais import (
    COE_PAINEIS, COE_CAMPO_FUTURO, avaliar_coe, paineis_coe,
)
from services.parecer_credito import COE_DIVERGENCIA_AVISO, montar_parecer


# ── A faixa ──────────────────────────────────────────────────────────────────
def test_entre_dois_paineis_nao_e_desvio():
    """
    R$ 178/@ na cria fica entre Pelotas (166,35) e Altamira (189,76). Contra o
    ponto de Pelotas seria +7,0%; contra o de Altamira, −6,2%. Nenhum dos dois
    é "o" custo da cria brasileira — a fazenda está entre duas realidades
    igualmente medidas, e apontar desvio aqui é ruído.
    """
    r = avaliar_coe('CRIA', 178.00)
    assert r['delta_pct'] == 0.0
    assert r['nivel'] == 'dentro'


def test_o_delta_mede_o_excesso_sobre_o_teto():
    """Não sobre a média nem sobre o painel mais barato."""
    lo, hi = 171.88, 183.50
    r = avaliar_coe('RECRIA_ENGORDA', hi * 1.5)
    assert r['faixa_paineis'] == (lo, hi)
    assert r['delta_pct'] == pytest.approx(50.0, abs=0.1)


def test_abaixo_do_piso_da_faixa_e_custo_bom():
    r = avaliar_coe('CRIA', 166.35 * 0.85)
    assert r['nivel'] == 'excelente'
    assert r['delta_pct'] == 0.0, 'custo baixo não é desvio'


def test_faixa_de_modalidade_com_um_painel_so_e_declarada():
    """
    Ciclo completo tem um painel só. A faixa degenera no ponto, o que é o
    comportamento certo — mas `n_paineis` precisa dizer isso, senão o parecer
    promete uma dispersão que não foi medida.
    """
    r = avaliar_coe('CICLO_COMPLETO', 200.0)
    assert r['n_paineis'] == 1
    assert r['faixa_paineis'][0] == r['faixa_paineis'][1] == 164.61


# ── A praça ──────────────────────────────────────────────────────────────────
def test_a_uf_escolhe_o_painel():
    assert avaliar_coe('CRIA', 178.0, uf='RS')['local_ref'] == 'Pelotas, RS'
    assert avaliar_coe('CRIA', 178.0, uf='PA')['local_ref'] == 'Altamira, PA'


def test_sem_painel_na_uf_cai_na_regiao():
    """
    Não há painel de cria no Amapá, mas há no Pará — mesma região Norte, mesmo
    arco de fronteira agrícola. É comparação mais honesta que Pelotas/RS.

    A garantia é a REGIÃO, não uma UF específica: para o Acre, tanto Pará
    quanto Rondônia servem, e escolher entre eles exigiria uma noção de
    distância que não temos medida.
    """
    from services.benchmarks_nacionais import _UF_REGIAO
    for uf in ('AP', 'AC', 'AM', 'RR'):
        for mod in ('CRIA', 'RECRIA'):
            escolhido = avaliar_coe(mod, 180.0, uf=uf)['uf_ref']
            assert _UF_REGIAO[escolhido] == _UF_REGIAO[uf] == 'N', (uf, mod, escolhido)

    # Sul e Norte não se misturam quando há painel na região.
    assert avaliar_coe('CRIA', 180.0, uf='SC')['uf_ref'] == 'RS'


def test_uf_sem_painel_e_sem_regiao_nao_quebra():
    r = avaliar_coe('CRIA', 178.0, uf='ZZ')
    assert r is not None and r['local_ref']


def test_a_faixa_nao_muda_com_a_praca():
    """
    A praça escolhe QUEM é citado, não contra o que se compara. Se a faixa
    mudasse com a UF, o mesmo custo daria avisos diferentes por município — e
    o aviso deixaria de ser sobre custo.
    """
    a = avaliar_coe('CRIA', 300.0, uf='RS')
    b = avaliar_coe('CRIA', 300.0, uf='PA')
    assert a['faixa_paineis'] == b['faixa_paineis']
    assert a['delta_pct'] == b['delta_pct']
    assert a['local_ref'] != b['local_ref']


# ── A faixa não encobre custo alto de verdade ───────────────────────────────
def test_a_recria_real_continua_sinalizada():
    """
    O risco de trocar ponto por faixa é afrouxar o aviso até ele nunca
    disparar. A ficha real de recria de 700 cabeças roda a R$ 387,02/@ — mais
    que o DOBRO do painel mais caro da modalidade. Nenhuma faixa plausível a
    resgata, e é isso que este teste prende.
    """
    r = avaliar_coe('RECRIA', 387.02)
    assert r['delta_pct'] >= 100.0
    assert r['nivel'] == 'alto'


def test_a_cria_real_deixou_de_ser_desvio_quando_a_base_cresceu():
    """
    Este teste registra uma MUDANÇA DE CLASSIFICAÇÃO deliberada, não um
    afrouxamento acidental — a versão anterior dele falhou quando o terceiro
    painel entrou, e foi assim que a mudança apareceu.

    A cria real de 1.705 cabeças roda a R$ 249,60/@:

        contra Altamira/PA sozinha (189,76) ......... +31,5%  → avisava
        contra a faixa de 3 painéis (166,35–223,21) . +11,8%  → não avisa

    O que mudou não foi a fazenda: foi o que sabemos. O painel do Pantanal de
    Corumbá (Embrapa CT 126) mede uma cria extensiva modal a R$ 223,21/@, com
    lotação de 0,30 UA/ha. Uma fazenda 11,8% acima do sistema mais caro que já
    medimos não é anomalia — é variação de sistema, e apontá-la seria o ruído
    que o limiar de 25% existe para evitar.

    Se um quarto painel mostrar cria acima de R$ 249, este número cai mais. Se
    aparecer evidência de que R$ 223 é fora da curva, sobe. É para isso que a
    faixa é derivada dos painéis e não escrita à mão.
    """
    r = avaliar_coe('CRIA', 249.60)
    assert r['delta_pct'] == pytest.approx(11.8, abs=0.1)
    assert r['delta_pct'] < COE_DIVERGENCIA_AVISO
    assert r['nivel'] == 'atencao', 'deixou de avisar, mas não virou custo normal'

    # E a fazenda que motivou tudo isso continua acima do teto — o aviso ficou
    # mais exigente, não desligado.
    assert avaliar_coe('CRIA', 223.21 * 1.30)['delta_pct'] >= COE_DIVERGENCIA_AVISO


# ── O perímetro do custo ────────────────────────────────────────────────────
def test_a_base_de_comparacao_esta_declarada():
    """
    COE é desembolso: inclui compra de animais, exclui depreciação e
    remuneração do capital (isso é COT e CT). Nosso numerador é o custo de
    caixa do fluxo GEP, mesmo perímetro. Declarar isso no retorno é o que
    impede alguém de "completar" o numerador com depreciação depois — nenhum
    teste de número falharia, e a comparação viraria COT contra COE.
    """
    base = avaliar_coe('CRIA', 178.0)['base'].lower()
    assert 'desembolso' in base
    assert 'anima' in base, 'a compra de animais precisa estar explícita'


def test_a_composicao_do_painel_volta_junto():
    """
    O total esconde a diferença: mão de obra é 18,2% da cria paraense e 42,9%
    da gaúcha. Sem a composição, o analista não tem como saber onde procurar.
    """
    rs = avaliar_coe('CRIA', 178.0, uf='RS')['maiores_itens_pct']
    pa = avaliar_coe('CRIA', 178.0, uf='PA')['maiores_itens_pct']
    assert rs['Mao de obra'] == 42.9
    assert pa['Mao de obra'] == 18.2


# ── Por que COE, e não o custo "completo" ───────────────────────────────────
def test_o_painel_do_pantanal_guarda_os_tres_niveis():
    """
    Comparar custo em CT parece mais rigoroso e seria erro de crédito grave.
    O painel do Pantanal de Corumbá publica os três níveis para a MESMA
    fazenda modal, e a conta muda de sinal entre eles:

        receita R$ 275,32/@   COE R$ 223,21/@  → margem bruta   positiva
                              COT R$ 260,76/@  → margem líquida positiva
                              CT  R$ 431,09/@  → prejuízo de R$ 1,66 mi/ano

    Santos et al. (2014), sobre 193 propriedades modais em 13 estados que
    concentram 90% do rebanho nacional: em mais de 90% delas a receita não
    remunera o custo de oportunidade do capital — porque o ativo principal é a
    TERRA, cuja valorização não entra na receita do ano.

    Um analista que comparasse em CT reprovaria nove em cada dez fazendas
    brasileiras. Crédito rural se paga com caixa, e COE é o nível do caixa.

    Guardar os três aqui é o que torna essa escolha auditável em vez de
    arbitrária — e o que impede alguém de "completar" o benchmark depois.
    """
    pantanal = [p for p in COE_PAINEIS['CRIA'] if p['uf'] == 'MS'][0]
    assert pantanal['coe_arroba'] < pantanal['cot_arroba'] < pantanal['ct_arroba']
    assert pantanal['coe_arroba'] == 223.21
    assert pantanal['ct_arroba'] == 431.09

    # A receita da fazenda cobre COE e COT, e não cobre CT. É esse cruzamento
    # que decide qual nível serve de referência de crédito.
    receita_arroba = 275.32
    assert pantanal['coe_arroba'] < receita_arroba
    assert pantanal['cot_arroba'] < receita_arroba
    assert pantanal['ct_arroba']  > receita_arroba


def test_a_comparacao_usa_o_nivel_coe_dos_paineis():
    """
    O teto da faixa da cria tem de ser o COE do Pantanal (223,21), nunca o COT
    nem o CT. Se alguém trocar a chave lida, a faixa saltaria para 431,09 e o
    aviso de custo praticamente nunca mais dispararia.
    """
    _, hi = avaliar_coe('CRIA', 200.0)['faixa_paineis']
    assert hi == 223.21, 'a faixa deixou de ser medida em COE'


# ── Integridade dos painéis ─────────────────────────────────────────────────
def test_todo_painel_tem_praca_valor_e_composicao():
    for modalidade, paineis in COE_PAINEIS.items():
        assert paineis, modalidade
        for p in paineis:
            assert p['coe_arroba'] > 0, (modalidade, p['local'])
            assert len(p['uf']) == 2, (modalidade, p['local'])
            assert p['uf'] in p['local'], 'o local precisa nomear a UF'
            assert p['maiores_itens_pct'], (modalidade, p['local'])
            assert sum(p['maiores_itens_pct'].values()) <= 100.0


def test_o_ponto_antigo_continua_disponivel():
    """Compatibilidade: código que lia um ponto por modalidade não quebrou."""
    assert set(COE_CAMPO_FUTURO) == set(COE_PAINEIS)
    for mod, ref in COE_CAMPO_FUTURO.items():
        assert ref is COE_PAINEIS[mod][0]


def test_recria_e_engorda_isoladas_usam_o_painel_conjunto():
    """Os painéis publicados tratam as duas fases juntas."""
    assert paineis_coe('RECRIA') == paineis_coe('ENGORDA') == COE_PAINEIS['RECRIA_ENGORDA']
    assert paineis_coe('MODALIDADE_INEXISTENTE') == []
    assert avaliar_coe('MODALIDADE_INEXISTENTE', 200.0) is None
    assert avaliar_coe('CRIA', 0) is None


# ── O que o parecer diz ─────────────────────────────────────────────────────
def _parecer_com(coe_benchmark):
    return montar_parecer(
        identificacao={}, composicao={}, indicadores={}, benchmarks={},
        consistencia={}, financeiro={}, geracao_caixa_anual=500_000,
        credito={'credito_valor': 500_000, 'prazo_meses': 36, 'juros_aa': 0.1},
        fluxo_gep={'coe_benchmark': coe_benchmark},
    )


def test_o_aviso_fala_em_faixa_quando_ha_faixa():
    p = _parecer_com(avaliar_coe('RECRIA', 387.02))
    passo = [m for m in p['conclusao']['memoria']
             if 'Custo acima' in str(m.get('passo'))][0]
    assert 'painéis' in passo['detalhe']
    assert 'teto' in passo['valor']
    assert 'COE contra COE' in passo['detalhe'], (
        'o perímetro do custo precisa aparecer para quem lê o parecer'
    )


def test_com_um_painel_so_o_aviso_nao_promete_faixa():
    p = _parecer_com(avaliar_coe('CICLO_COMPLETO', 300.0))
    passo = [m for m in p['conclusao']['memoria']
             if 'Custo acima' in str(m.get('passo'))][0]
    assert 'painéis' not in passo['detalhe']
    assert p['conclusao']['custo_fora_da_referencia']['n_paineis'] == 1


def test_dentro_da_faixa_nao_gera_aviso_no_parecer():
    """Delta zero está abaixo do limiar — silêncio, e não um aviso de 0%."""
    p = _parecer_com(avaliar_coe('CRIA', 178.0))
    assert 'custo_fora_da_referencia' not in p['conclusao']
