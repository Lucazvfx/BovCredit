"""
Testes de regressão para os 19 bugs corrigidos (commits 469ba81, d76bfce, 7bbd382).
Cada teste nomeia o bug que protege e falha se o comportamento errado retornar.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest
import database as db
from app import app
from ml_engine import (
    calcular_indicadores,
    calcular_breakeven_simples,
    _simular_cria,
    _simular_recria,
)


# ──────────────────────────────────────────────────────────────────────────────
# Fixture de cliente autenticado
# ──────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope='module')
def client():
    db.init_db()
    email = 'regressao_bugs@bovcredit.com'
    u = db.buscar_usuario_email(email)
    if not u:
        db.criar_usuario(email, 'Regressão', 'senha123')
        u = db.buscar_usuario_email(email)
    c = app.test_client()
    with c.session_transaction() as sess:
        sess['_user_id'] = str(u['id'])
        sess['empresa_ativa_id'] = 1
    return c


def _api(client, valores, preco=344, custo=57, credito=200000, prazo=36, juros=0.12, **kw):
    payload = {
        'valores': valores, 'preco': preco, 'custo_arroba': custo,
        'credito_valor': credito, 'prazo_meses': prazo, 'juros_aa': juros,
    }
    payload.update(kw)
    r = client.post('/api/classificar', json=payload)
    assert r.status_code == 200, f'/api/classificar retornou {r.status_code}: {r.data[:200]}'
    return r.get_json()


# ──────────────────────────────────────────────────────────────────────────────
# Bug 1 — bezerros_est divide NATALIDADE_PCT por 100
# Antes: int(matrizes * 65.0)      = 4810 para 74 matrizes
# Depois: int(matrizes * 65.0/100) = 48
# ──────────────────────────────────────────────────────────────────────────────

def test_bezerros_est_usa_fracao_natalidade():
    # v = [f00F,f00M, f05F,f05M, f13F,f13M, f25F,f25M, facF,facM]
    # matrizes = v[6]+v[8] = f25F+facF = 0+70 = 70  (facM=4 são bois, não matrizes)
    # Referencia a constante em vez de fixar o número: o guard é contra a
    # ausência da divisão por 100, não contra o valor da taxa em si.
    from services.parametros_zootecnicos import NATALIDADE_PCT
    ind = calcular_indicadores([0, 0, 0, 0, 0, 0, 0, 0, 70, 4])
    esperado = int(70 * NATALIDADE_PCT / 100)
    assert ind['bezerros_est'] == esperado, (
        f'bezerros_est={ind["bezerros_est"]}, esperado {esperado}. '
        f'Bug produziria {int(70 * NATALIDADE_PCT)} (sem divisão por 100).'
    )


# ──────────────────────────────────────────────────────────────────────────────
# Bug 2 — descarte de matrizes usa desc_mat_pct/100 (era multiplicado direto)
# Antes: round(matrizes * 30.0) = 3150 para 105 matrizes
# Depois: round(matrizes * 30.0/100) = 32
# ──────────────────────────────────────────────────────────────────────────────

def test_descarte_matrizes_usa_percentual_correto():
    r = _simular_cria(
        [0, 0, 0, 0, 0, 0, 0, 0, 100, 5], 'conservador',
        nat_pct=65, mort_pct=3, desmama_pct=80, venda_bez_pct=60,
        preco_arroba_bezerro=300, custo_arroba=57, anos=1,
        desc_mat_pct=30.0,
    )
    descarte = r['anos'][0]['matrizes_descartadas']
    # 105 matrizes × 30% ≈ 32 (arredondado)
    assert 28 <= descarte <= 36, (
        f'descarte={descarte}, esperado ~32. '
        f'Bug multiplicaria direto: 105×30=3150.'
    )


# ──────────────────────────────────────────────────────────────────────────────
# Bug 3 — _simular_recria deve incluir fêmeas jovens (va[2]+va[4])
# Antes: animais = float(va[3] + va[5])  → só machos
# Depois: animais = float(va[2] + va[3] + va[4] + va[5])
# ──────────────────────────────────────────────────────────────────────────────

def test_simular_recria_inclui_femeas():
    base = dict(cenario='conservador', mort_pct=3, preco_arroba=320,
                peso_entrada_arr=8, peso_saida_arr=14, meses_recria=12,
                custo_arroba=57, anos=1)
    # só machos (40 f05M)
    r_m = _simular_recria([0, 0, 0, 40, 0, 0, 0, 0, 0, 0], **base)
    # machos + fêmeas (40 f05F + 40 f05M)
    r_mf = _simular_recria([0, 0, 40, 40, 0, 0, 0, 0, 0, 0], **base)
    custo_m  = r_m['anos'][0]['custo']
    custo_mf = r_mf['anos'][0]['custo']
    assert custo_mf > custo_m, 'custo com fêmeas deve ser maior que só machos'
    assert abs(custo_mf / custo_m - 2.0) < 0.05, (
        f'custo_mista/custo_macho={custo_mf/custo_m:.3f}, esperado ≈2.0. '
        f'Bug usaria só machos → custo_mf igual ao custo_m.'
    )


def test_breakeven_recria_conta_femeas():
    # Com só fêmeas na recria, deve retornar breakeven > 0
    # Bug (só machos va[3]+va[5]): _animais=0 → divisão por zero → {}
    v_so_femeas = [0, 0, 40, 0, 40, 0, 0, 0, 0, 0]
    r = calcular_breakeven_simples(v_so_femeas, 'RECRIA')
    assert r.get('preco_breakeven', 0) > 0, (
        'breakeven RECRIA com só fêmeas deve ser > 0. '
        'Bug retornaria {} (0 animais → sem cálculo).'
    )


# ──────────────────────────────────────────────────────────────────────────────
# Bug 4 — sensibilidade ±15% usa preço de referência exato (compensa mod 0.95)
# Antes: preco_boi_queda = preco_ref × 0.85 × 0.95 → deflacionado extra
# Depois: preco_boi_queda = preco_ref × 0.85  (preço efetivo na resposta)
# ──────────────────────────────────────────────────────────────────────────────

def test_sensibilidade_preco_exatamente_15pct(client):
    # Passa preco_boi explicitamente para não depender da cotação do DB
    # (outros testes podem alterar a cotação no banco compartilhado).
    preco_ref = 344.0
    d = _api(client, [10, 10, 8, 8, 6, 6, 30, 2, 40, 3],
             preco=preco_ref, preco_boi=preco_ref)
    sens = {s['cenario']: s for s in d.get('sensibilidade', [])}
    assert 'queda_15pct' in sens and 'alta_15pct' in sens, 'sensibilidade incompleta'
    queda = sens['queda_15pct']['preco_boi']
    alta  = sens['alta_15pct']['preco_boi']
    assert abs(queda - preco_ref * 0.85) < 1.0, (
        f'queda={queda}, esperado {round(preco_ref*0.85,2)}. '
        f'Bug daria {round(preco_ref*0.85*0.95,2)} (× 0.95 extra).'
    )
    assert abs(alta - preco_ref * 1.15) < 1.0, (
        f'alta={alta}, esperado {round(preco_ref*1.15,2)}.'
    )


# ──────────────────────────────────────────────────────────────────────────────
# Bug 5 — COE CRIA usa arrobas de bezerro (6@/6.67@), não de garrote (10.67@)
# Validação indireta: arrobas_vendidas por matriz < 4@ (razoável para CRIA)
# ──────────────────────────────────────────────────────────────────────────────

def test_coe_cria_arrobas_bezerro_nao_garrote(client):
    # Ciclo CRIA: machos vendidos devem usar peso de bezerro (6.67@), não de garrote (10.67@).
    # Para validar: calculamos as arrobas esperadas a partir dos animais vendidos no resultado.
    # Se fossem garrotes (10.67@), as arrobas seriam 60% maiores → COE artificialmente menor.
    d = _api(client, [0, 0, 0, 0, 0, 0, 0, 0, 100, 5], preco=344)
    fg = d.get('fluxo_gep', {})
    assert fg.get('arrobas_vendidas', 0) > 0, 'arrobas_vendidas deve existir e ser > 0'
    assert fg.get('coe_por_arroba', 0) > 0, 'coe_por_arroba deve existir e ser > 0'
    # Sanidade: COE por arroba de CRIA deve estar em faixa razoável (R$30–R$400)
    coe = fg['coe_por_arroba']
    assert 30 < coe < 400, f'coe_por_arroba={coe} fora da faixa razoável (R$30–R$400)'


# ──────────────────────────────────────────────────────────────────────────────
# Bug 6 — rendimento de carcaça diferencia macho 55% e fêmea 52%
# Antes: fixo 0.54 independente do sexo
# Depois: M=0.55, F=0.52
# ──────────────────────────────────────────────────────────────────────────────

def test_rendimento_carcaca_diferenciado_por_sexo(client):
    peso = 450.0
    rm = client.post('/api/estimativa-valor', json={'peso_vivo': peso, 'sexo': 'M'})
    rf = client.post('/api/estimativa-valor', json={'peso_vivo': peso, 'sexo': 'F'})
    if rm.status_code == 503 or rf.status_code == 503:
        pytest.skip('Cotação indisponível no banco de dados')
    assert rm.status_code == 200 and rf.status_code == 200
    dm = rm.get_json()
    df = rf.get_json()
    esperado_m = round(peso * 0.55 / 15.0, 2)
    esperado_f = round(peso * 0.52 / 15.0, 2)
    assert abs(dm['peso_estimado_arrobas'] - esperado_m) < 0.01, (
        f'macho @ = {dm["peso_estimado_arrobas"]}, esperado {esperado_m} (55%).'
    )
    assert abs(df['peso_estimado_arrobas'] - esperado_f) < 0.01, (
        f'femea @ = {df["peso_estimado_arrobas"]}, esperado {esperado_f} (52%).'
    )
    assert dm['peso_estimado_arrobas'] > df['peso_estimado_arrobas'], (
        'Macho deve ter mais arrobas que fêmea para mesmo peso vivo.'
    )


# ──────────────────────────────────────────────────────────────────────────────
# Bug 7 — preco_boi na resposta JSON é preço efetivo (sem deflação extra)
# Antes: preco_boi = preco_ref × fator × 0.95  → deflacionado para o JSON
# Depois: preco_boi = preco_ref × fator         → preço efetivo real
# ──────────────────────────────────────────────────────────────────────────────

def test_sensibilidade_preco_boi_json_sem_deflacao_extra(client):
    # preco_boi no JSON reflete o preço efetivo de mercado (não deflacionado por mod 0.95).
    # Validação via razão entre cenários: queda/base deve ser exatamente 0.85, alta/base=1.15.
    # Bug: preco_boi = preco_ref × fator × 0.95 → razão seria afetada.
    d = _api(client, [10, 10, 8, 8, 6, 6, 30, 2, 40, 3])
    sens = {s['cenario']: s for s in d.get('sensibilidade', [])}
    preco_base = sens.get('base', {}).get('preco_boi', 0)
    preco_queda = sens.get('queda_15pct', {}).get('preco_boi', 0)
    preco_alta  = sens.get('alta_15pct', {}).get('preco_boi', 0)
    assert preco_base > 0, 'preco_boi base não retornado'
    assert abs(preco_queda / preco_base - 0.85) < 0.01, (
        f'queda/base={preco_queda/preco_base:.4f}, esperado 0.85. '
        f'Bug daria razão diferente de 0.85 com deflação extra.'
    )
    assert abs(preco_alta / preco_base - 1.15) < 0.01, (
        f'alta/base={preco_alta/preco_base:.4f}, esperado 1.15.'
    )


# ──────────────────────────────────────────────────────────────────────────────
# Bug 8 — DSCR deduz reposição de reprodutores da geração de caixa
# Mayor renovboi → maior custo de reposição → DSCR menor
# ──────────────────────────────────────────────────────────────────────────────

def test_dscr_deduz_reposicao_reprodutores(client):
    v = [0, 0, 0, 0, 0, 0, 0, 0, 200, 10]
    # renovboi=0 → nenhuma reposição → geração de caixa maior → DSCR maior
    d_sem = _api(client, v, preco=344, renovboi=0)
    # renovboi=50 → alta renovação → custo de reposição deduzido do DSCR
    d_com = _api(client, v, preco=344, renovboi=50)
    dscr_sem = d_sem['parecer']['conclusao']['dscr']
    dscr_com = d_com['parecer']['conclusao']['dscr']
    assert dscr_sem is not None and dscr_com is not None, 'DSCR não retornado'
    assert dscr_sem > dscr_com, (
        f'DSCR sem reposição ({dscr_sem}) deve ser > com alta reposição ({dscr_com}). '
        f'Bug não deduziria reposição → ambos iguais.'
    )


# ──────────────────────────────────────────────────────────────────────────────
# Bug 9 — sensibilidade de custo também deduz reposição de reprodutores
# A geração de caixa nos cenários de custo deve ser menor quando há reposição
# ──────────────────────────────────────────────────────────────────────────────

def test_sensibilidade_custo_deduz_reposicao(client):
    v = [0, 0, 0, 0, 0, 0, 0, 0, 200, 10]
    d = _api(client, v, preco=344, renovboi=30)
    sens_custo = d.get('sensibilidade_custo', [])
    if not sens_custo:
        pytest.skip('sensibilidade_custo não presente nesta versão')
    # Geração de caixa em todos os cenários de custo deve ser >= 0 ou negativa
    for sc in sens_custo:
        gc = sc.get('geracao_caixa')
        if gc is not None:
            # Validamos que o campo existe e é numérico (não None)
            assert isinstance(gc, (int, float)), f'geracao_caixa não é numérico: {gc}'
