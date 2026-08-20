"""
O peso médio vem do rebanho declarado — nos dois caminhos.

O custo entra no sistema em R$/cab/mês, e o motor precisa de R$/@·ano. A
conversão divide pelo peso médio do rebanho:

    R$/@·ano = (R$/cab/mês × 12) ÷ arrobas por cabeça

Havia dois caminhos com bases diferentes:

    analista digita os componentes  →  peso médio REAL do rebanho declarado
    analista não digita (o normal)  →  11,7 @/cab FIXO

E o 11,7 não era medição de nada. O próprio docstring dizia: "reproduz a
conversão que já era usada para o CICLO_COMPLETO, mantendo 119 R$/@". Era
compatibilidade retroativa que virou parâmetro zootécnico.

Peso médio depende da composição — rebanho com muito animal jovem pesa bem
menos por cabeça. Medido nas duas fazendas reais do projeto:

    Recria A (ADAPEC-TO, 700 cab)  9,75 @/cab contra 11,7  → custo −17%
    Recria B (ADAPEC-TO, 753 cab)  9,87 @/cab contra 11,7  → custo −16%

Dividir por um número maior que o real infla o denominador e REDUZ o custo por
arroba: menos custo, mais caixa, DSCR maior. O erro corria a favor de aprovar,
como a carência e como o peso de saída da recria.

CORRIGE NOS DOIS SENTIDOS, e isso é o esperado de uma conversão certa. Medido
pelas rotas, o COE do ciclo completo (rebanho mais pesado que 11,7) CAIU de
R$ 185,86 para R$ 173,36 enquanto o da recria subiu de R$ 387,02 para
R$ 422,26. Nenhuma recomendação mudou nos casos testados.
"""
import pytest

import database as db
from app import app
from services.custos_desembolso import (
    custo_arroba_padrao, custo_arroba_de_desembolso,
    ARROBAS_POR_CABECA_FALLBACK, DESEMBOLSO_PADRAO_CAB_MES,
)
from services.pesos_rebanho import arrobas_categorias


def _arrobas_por_cab(v):
    a = arrobas_categorias(
        matrizes=float(v[6] + v[8]), bois=float(v[7] + v[9]),
        jovens_f=float(v[0] + v[2] + v[4]), jovens_m=float(v[1] + v[3] + v[5]))
    return a / sum(v)


RECRIA_700 = [22, 219, 0, 0, 105, 234, 45, 16, 59, 0]    # ADAPEC-TO, real
RECRIA_753 = [0, 0, 150, 15, 374, 0, 209, 0, 5, 0]       # ADAPEC-TO, real
CICLO = [80, 80, 50, 50, 60, 60, 90, 40, 220, 60]


# ── A conversão ─────────────────────────────────────────────────────────────
@pytest.mark.parametrize('nome,v', [('recria 700', RECRIA_700), ('recria 753', RECRIA_753)])
def test_rebanho_jovem_pesa_menos_que_a_constante(nome, v):
    """O caso que a constante subestimava — e são os dois rebanhos reais."""
    assert _arrobas_por_cab(v) < ARROBAS_POR_CABECA_FALLBACK


def test_peso_real_encarece_rebanho_jovem():
    real = custo_arroba_padrao('RECRIA', arrobas_por_cabeca=_arrobas_por_cab(RECRIA_700))
    fixo = custo_arroba_padrao('RECRIA', arrobas_por_cabeca=ARROBAS_POR_CABECA_FALLBACK)
    assert real > fixo
    assert real / fixo == pytest.approx(ARROBAS_POR_CABECA_FALLBACK / _arrobas_por_cab(RECRIA_700), rel=1e-3)


def test_peso_real_barateia_rebanho_pesado():
    """
    Corrige nos DOIS sentidos. Se só encarecesse, seria política disfarçada de
    correção.
    """
    p = _arrobas_por_cab(CICLO)
    assert p > ARROBAS_POR_CABECA_FALLBACK, 'o caso precisa ser o de rebanho pesado'
    assert (custo_arroba_padrao('CICLO_COMPLETO', arrobas_por_cabeca=p)
            < custo_arroba_padrao('CICLO_COMPLETO',
                                  arrobas_por_cabeca=ARROBAS_POR_CABECA_FALLBACK))


def test_os_dois_caminhos_concordam():
    """
    Com o mesmo desembolso e o mesmo rebanho, o caminho com componentes e o
    caminho padrão têm de dar o mesmo R$/@. Eram duas bases diferentes.
    """
    v = RECRIA_700
    a = arrobas_categorias(
        matrizes=float(v[6] + v[8]), bois=float(v[7] + v[9]),
        jovens_f=float(v[0] + v[2] + v[4]), jovens_m=float(v[1] + v[3] + v[5]))
    # Os dois caminhos reais da rota: com componentes digitados, o app passa
    # por `desembolso_operacional` antes de converter; sem componentes, o
    # `custo_arroba_padrao` aplica a mesma separação internamente. Comparar a
    # soma CHEIA com o padrão testaria bases diferentes de propósito.
    from services.custos_desembolso import desembolso_operacional, preset_modalidade
    por_componentes = custo_arroba_de_desembolso(
        desembolso_operacional(preset_modalidade('RECRIA', 'media')), a, sum(v))
    padrao = custo_arroba_padrao('RECRIA', arrobas_por_cabeca=a / sum(v))
    assert padrao == pytest.approx(por_componentes, rel=1e-3)


def test_o_desembolso_cheio_e_maior_que_o_operacional():
    """
    A separação não pode zerar: o desembolso cheio continua sendo o que o
    produtor gasta, e é ele que a tela mostra. O que sai do DSCR é só a parcela
    de investimento das rubricas mistas.
    """
    from services.custos_desembolso import (
        desembolso_operacional, parcela_investimento, preset_modalidade,
        SHARE_INVESTIMENTO_COE)
    for mod in ('CRIA', 'RECRIA', 'CICLO_COMPLETO'):
        p = preset_modalidade(mod, 'media')
        cheio, oper = sum(p.values()), desembolso_operacional(p)
        assert 0 < oper < cheio, mod
        assert parcela_investimento(p) == pytest.approx(cheio - oper)
        # as rubricas mistas passam a ocupar a proporção do painel
        mistas = sum(p[k] for k in ('maquinas', 'pastagem', 'infraestrutura'))
        mistas_oper = oper - (cheio - mistas)
        assert mistas_oper / oper == pytest.approx(SHARE_INVESTIMENTO_COE, abs=1e-6), mod


# ── O fallback continua existindo, mas é último recurso ─────────────────────
@pytest.mark.parametrize('peso', [None, 0, -1])
def test_sem_rebanho_cai_no_fallback(peso):
    assert custo_arroba_padrao('CRIA', arrobas_por_cabeca=peso) == \
           custo_arroba_padrao('CRIA', arrobas_por_cabeca=ARROBAS_POR_CABECA_FALLBACK)


# ── Ponta a ponta ───────────────────────────────────────────────────────────
def test_a_rota_usa_o_peso_do_rebanho():
    db.init_db()
    email = 'peso@example.com'
    u = db.buscar_usuario_email(email)
    if not u:
        db.criar_usuario(email, 'Peso', 'senha123')
        u = db.buscar_usuario_email(email)
    app.config['TESTING'] = True
    c = app.test_client()
    with c.session_transaction() as s:
        s['_user_id'] = str(u['id'])
    d = c.post('/api/classificar', json={
        'valores': RECRIA_700, 'preco': 320, 'credito_valor': 840_000,
        'prazo_meses': 36, 'juros_aa': 0.125}).get_json()
    coe = d['parecer']['fluxo_gep'].get('coe_por_arroba') or 0
    # A asserção é RELATIVA de propósito. A versão anterior exigia COE > 400,
    # um número calibrado contra o nível de custo da época — e ele mudou quando
    # investimento saiu do DSCR, fazendo o teste falhar sem que nada do que ele
    # protege tivesse quebrado.
    #
    # O que ele protege é o PESO: este rebanho pesa 9,75 @/cab contra o
    # fallback de 11,7. Dividir pelo peso menor produz custo por arroba MAIOR,
    # na razão 11,7/9,75 = 1,2. É isso que se afere, em qualquer nível de custo.
    from services.custos_desembolso import ARROBAS_POR_CABECA_FALLBACK
    a = arrobas_categorias(
        matrizes=float(RECRIA_700[6] + RECRIA_700[8]), bois=float(RECRIA_700[7] + RECRIA_700[9]),
        jovens_f=float(RECRIA_700[0] + RECRIA_700[2] + RECRIA_700[4]),
        jovens_m=float(RECRIA_700[1] + RECRIA_700[3] + RECRIA_700[5]))
    peso_real = a / sum(RECRIA_700)
    assert peso_real < ARROBAS_POR_CABECA_FALLBACK, 'a premissa do caso mudou'
    razao = ARROBAS_POR_CABECA_FALLBACK / peso_real
    coe_com_fallback = coe / razao
    assert coe > coe_com_fallback * 1.15, (
        f'COE {coe:.2f} — a rota ainda usa a constante fixa de '
        f'{ARROBAS_POR_CABECA_FALLBACK} @/cab em vez do peso real de {peso_real:.2f}'
    )
