"""Coortes reais no ciclo completo — não mais um pool 0–24m misturado.

`femeas_024`/`machos_024` cobriam dois anos de idade num número só. Qualquer
fêmea retida — tivesse ela um mês ou vinte e três — virava matriz reprodutiva
no ano seguinte via `fem_repor`, porque a função não tinha como saber que ela
não estava perto dos 36 meses. Numa cria de 190 fêmeas jovens recém-nascidas
isso promovia ~38 delas a matriz no ano 1 — impossível: idade média à
primeira parição de 36,3 meses (Embrapa, 468 matrizes Nelore).

Machos tinham o mesmo problema do lado da terminação: metade de QUALQUER
pool 0–24m graduava para boi todo ano, gradue o animal tivesse nascido ontem
ou há quase dois anos.

A correção separa em coortes reais que envelhecem uma etapa por ano:
0–12 (c0) → 13–24 (c1) → 25–36/"prestes" (c2) → matriz.
"""
import pytest

from ml_engine import calcular_ano, simular_cenario
from services.engine.contracts import HerdState
from services.production_engine.ciclo_completo import project_full_cycle


def _params(**extra):
    base = dict(matrizes=100, c0_femeas=190, c1_femeas=0,
                c0_machos=190, c1_machos=0, bois=50,
                nat_pct=0.70, desc_mat_pct=0.10, prop_boi=30,
                renov_boi_pct=0.2, venda_bez_pct=0.75, mort_pct=0.03,
                preco_arroba=320, custo_arroba=57)
    base.update(extra)
    return base


# ── O defeito original ───────────────────────────────────────────────────────
def test_femea_recem_nascida_nao_vira_matriz_em_um_ano():
    """O caso que expôs o bug: 190 fêmeas inteiramente em c0 (0–12m)."""
    r = calcular_ano(**_params())

    assert r['aumento_matrizes'] <= 0, (
        f"aumento_matrizes={r['aumento_matrizes']} — fêmeas de 0–12m entraram "
        f"na base reprodutiva num ano só. Sem ninguém em c1/prestes, o único "
        f"movimento possível é descarte (negativo)."
    )
    assert r['matrizes_prox'] < 100, (
        'matrizes só pode cair aqui (descarte), nunca subir — nada estava '
        'perto dos 36 meses para promover'
    )


def test_macho_recem_nascido_nao_gradua_em_um_ano():
    """Espelha o teste acima do lado macho: sem ninguém em c1, zero gradua."""
    r = calcular_ano(**_params())

    assert r['machos_graduados'] == 0, (
        f"machos_graduados={r['machos_graduados']} — animal de 0–12m não "
        f"completa 25 meses no mesmo ano."
    )


# ── A progressão correta ────────────────────────────────────────────────────
def test_fêmea_precisa_de_tres_anos_para_virar_matriz():
    """c0 → c1 (ano 1) → prestes (ano 2) → matriz (ano 3). Nunca antes."""
    r = simular_cenario(
        [190, 0, 0, 0, 0, 0, 0, 0, 100, 20], 'conservador',
        ciclo='CICLO_COMPLETO', preco_arroba=320, custo_arroba=57, anos=4)
    base = 100
    # Ano 1: nada em c1/prestes ainda — só descarte pode mexer em matrizes.
    assert r['anos'][0]['matrizes'] <= base
    # Ano 2: a coorte de 0–12m amadureceu para c1 no ano 1, mas ainda não
    # para prestes — matrizes segue sem ganho de quem entrou como bezerra.
    assert r['anos'][1]['matrizes'] <= base
    # Ano 3: agora sim — quem entrou com 0–12m completou o percurso e pode
    # aparecer como aumento em matrizes.
    assert r['anos'][2]['aumento_matrizes'] > 0 or r['anos'][2]['matrizes'] > base


def test_macho_gradua_no_ano_certo_nao_antes():
    """c1_machos > 0 é obrigatório para graduar — c0 sozinho não basta."""
    zero_c1 = calcular_ano(**_params(c0_machos=200, c1_machos=0))
    com_c1  = calcular_ano(**_params(c0_machos=100, c1_machos=100))

    assert zero_c1['machos_graduados'] == 0
    assert com_c1['machos_graduados'] > 0


# ── Conservação de massa ────────────────────────────────────────────────────
def test_conserva_massa_com_coortes_desbalanceadas():
    """início + nascimentos − vendas − mortes = fim, dentro da tolerância de
    arredondamento já usada pela suíte de conservação (2%)."""
    matrizes, c0_f, c1_f, c0_m, c1_m, bois, prestes = 310, 100, 90, 100, 90, 100, 60
    r = calcular_ano(matrizes=matrizes, c0_femeas=c0_f, c1_femeas=c1_f,
                     c0_machos=c0_m, c1_machos=c1_m, bois=bois,
                     nat_pct=0.665, desc_mat_pct=0.08, prop_boi=30,
                     renov_boi_pct=0.2, venda_bez_pct=0.75, mort_pct=0.03,
                     preco_arroba=304, custo_arroba=122, prestes_matrizes=prestes)

    inicio = matrizes + prestes + c0_f + c1_f + c0_m + c1_m + bois
    fim = (r['matrizes_prox'] + r['prestes_matrizes_prox'] + r['c0_femeas_prox']
           + r['c1_femeas_prox'] + r['c0_machos_prox'] + r['c1_machos_prox']
           + r['bois_prox'])
    esperado = inicio + r['bezerros_produzidos'] - r['total_vendido'] - r['mortes']

    tolerancia = max(3, inicio * 0.02)
    assert abs(fim - esperado) <= tolerancia, (
        f'fim={fim:.1f} contra esperado={esperado:.1f} — {fim-esperado:.1f} '
        f'animais não contabilizados'
    )


# ── O pipeline de terminação não esvazia (garantia pré-existente) ──────────
def test_terminacao_continua_alimentada_pelas_coortes():
    """A garantia que test_conservacao_rebanho.py já cobre — DSCR não pode
    colapsar do ano 1 para o ano 2 por falta de boi para vender."""
    r = simular_cenario(
        [40, 40, 40, 40, 50, 50, 80, 35, 275, 50], 'conservador',
        ciclo='CICLO_COMPLETO', preco_arroba=320, custo_arroba=119, anos=3)
    vendidos = [a['bois_vendidos'] for a in r['anos']]
    assert all(v >= 0 for v in vendidos)
    # Nenhum ano fica sem boi para vender depois que o pipeline se estabiliza.
    assert vendidos[1] > 0 and vendidos[2] > 0


# ── Os dois motores concordam ───────────────────────────────────────────────
def test_producao_engine_espelha_o_motor_do_parecer():
    """project_full_cycle (API v1) e calcular_ano (parecer) usam a mesma
    lógica de coortes — verificado pela mesma propriedade central."""
    state = HerdState(values=[190, 0, 0, 0, 0, 0, 0, 0, 100, 20],
                      source='MANUAL', farm_id=None, metadata={})
    r = project_full_cycle(state, {}, years=1)
    assert r['anos'][0]['aumento_matrizes'] <= 0, (
        'production_engine também não pode promover fêmea de 0–12m a matriz '
        'em um ano — mesma regra do motor do parecer'
    )
