"""
Assistente de crédito: o que ele responde e o que ele recusa.

A referência é o Tai, da Tarken: um assistente de crédito no WhatsApp sobre
ChatGPT. A diferença que este módulo implementa está em duas decisões.

1. CONCEITO SE RESPONDE DA NOSSA METODOLOGIA, NÃO DO MODELO

   Um modelo explica "deságio" em geral. Nós explicamos o deságio QUE O
   PARECER APLICA — 25% em boi, 35% em matriz — porque é a nossa conta que
   produz o número que o comitê vai ler. Explicação que não bate com o
   cálculo é pior que nenhuma.

   Por isso os textos são montados das CONSTANTES VIVAS: mudar a política
   muda a explicação no mesmo commit. Um teste garante que os números
   citados são os que o sistema usa, e não cópias que envelhecem.

2. NORMATIVO SE RECUSA, E A RECUSA É DETERMINÍSTICA

   Taxa de Pronaf, prazo de Moderfrota, exigência do MCR: o modelo responde
   com confiança e erra. Num produto que vai a banco, informação errada
   sobre condição de crédito custa o cliente e a credibilidade.

   A recusa NÃO é delegada ao modelo via prompt — prompt é pedido, não
   garantia. A pergunta é classificada antes de qualquer chamada, e
   normativa não chega ao modelo. É o que torna a recusa propriedade do
   sistema em vez de esperança sobre o modelo.
"""
import pytest

from services.assistente import (
    responder, assunto_sem_fonte, conceito_da_pergunta, explicar, RECUSA,
)


# ── A recusa ────────────────────────────────────────────────────────────────
@pytest.mark.parametrize('pergunta', [
    'qual a taxa de juros do Pronaf?',
    'Quanto tempo o MODERFROTA financia?',
    'o Pronamp exige o quê?',
    'qual o limite do Plano Safra esse ano',
    'o que diz o MCR sobre custeio pecuário?',
    'resolução 4966 exige o quê exatamente',
    'a Selic afeta a minha linha?',
    'qual taxa de juros ao ano vocês usam do banco',
    'tem subvenção pra essa operação?',
])
def test_normativo_e_recusado(pergunta):
    r = responder(pergunta)
    assert r is not None and r['tipo'] == 'sem_fonte', (
        f'{pergunta!r} passou — o modelo responderia e poderia errar'
    )


def test_a_recusa_diz_onde_procurar():
    """Recusa sem alternativa é só uma porta fechada."""
    r = responder('qual a taxa do Pronaf?')
    assert 'Banco Central' in r['texto'] or 'MCR' in r['texto']
    assert 'DSCR' in r['texto'], 'a recusa precisa dizer com o que ele PODE ajudar'


def test_recusa_vence_conceito_na_pergunta_hibrida():
    """
    "Qual a taxa do Pronaf para quem tem DSCR bom?" cita DSCR e casaria com o
    conceito — mas o que está sendo perguntado é a taxa. A ordem importa.
    """
    r = responder('qual a taxa do Pronaf para quem tem DSCR bom?')
    assert r['tipo'] == 'sem_fonte'


# ── O conceito ──────────────────────────────────────────────────────────────
@pytest.mark.parametrize('pergunta,chave', [
    ('o que é DSCR?',                        'dscr'),
    ('como funciona a cobertura da dívida',  'dscr'),
    ('como vocês calculam o deságio?',       'garantia'),
    ('o que é LTV',                          'garantia'),
    ('como entra o endividamento?',          'endividamento'),
    ('o que é desfrute real?',               'desfrute'),
    ('por que a carência muda a parcela?',   'carencia'),
    ('como é feita a classificação?',        'classificacao'),
    ('de onde vem esse número?',             'proveniencia'),
    ('que natalidade vocês usam?',           'natalidade'),
    ('o custo por arroba sai de onde?',      'custo'),
])
def test_conceito_e_reconhecido(pergunta, chave):
    assert conceito_da_pergunta(pergunta) == chave


def test_pergunta_fora_do_escopo_segue_para_o_parecer():
    """Nem tudo é conceito ou recusa — o resto continua com quem tem o parecer."""
    assert responder('quanto custa uma vaca hoje?') is None
    assert responder('e aí, tudo bem?') is None


# ── Os números não podem divergir do sistema ────────────────────────────────
def test_dscr_citado_e_o_que_o_sistema_usa():
    from services.parecer_credito import DSCR_APROVAR, DSCR_RESSALVA
    t = explicar('dscr')
    assert f'{float(DSCR_APROVAR):.2f}' in t
    assert f'{float(DSCR_RESSALVA):.2f}' in t


def test_desagio_citado_e_o_que_a_garantia_aplica():
    from services.garantia import DESAGIO_PADRAO
    t = explicar('garantia')
    for categoria, valor in DESAGIO_PADRAO.items():
        assert f'{categoria} {float(valor)*100:.0f}%' in t, (
            f'{categoria} explicado diferente do que a garantia aplica'
        )


def test_ltv_citado_e_o_que_a_politica_define():
    from services.garantia import LTV_APROVAR, LTV_RESSALVA
    t = explicar('garantia')
    assert f'{float(LTV_APROVAR)*100:.0f}%' in t
    assert f'{float(LTV_RESSALVA)*100:.0f}%' in t


def test_desfrute_citado_e_o_de_referencia():
    from services.parametros_zootecnicos import DESFRUTE_PCT
    t = explicar('desfrute')
    for ciclo, valor in DESFRUTE_PCT.items():
        assert f'{ciclo} {float(valor):.0f}%' in t


def test_todo_conceito_tem_texto():
    from services.assistente import _GATILHOS
    for chave in _GATILHOS:
        t = explicar(chave)
        assert t and len(t) > 120, f'{chave} sem explicação útil'


# ── Independência do modelo ─────────────────────────────────────────────────
def test_responde_sem_ia_configurada(monkeypatch):
    """
    Conceito e recusa são do sistema, não do modelo. Se dependessem da IA,
    cairiam junto com ela — e a recusa é justamente a parte que não pode cair.
    """
    monkeypatch.delenv('GROQ_API_KEY', raising=False)
    assert responder('o que é DSCR?')['tipo'] == 'conceito'
    assert responder('taxa do Pronaf?')['tipo'] == 'sem_fonte'


# ── Pelas rotas: tela e WhatsApp seguem a mesma disciplina ──────────────────
def _cli():
    import database as db
    from app import app
    db.init_db()
    u = db.buscar_usuario_email('assist@example.com')
    if not u:
        db.criar_usuario('assist@example.com', 'A', 'senha123')
        u = db.buscar_usuario_email('assist@example.com')
    app.config['TESTING'] = True
    c = app.test_client()
    with c.session_transaction() as s:
        s['_user_id'] = str(u['id'])
    return c, u


@pytest.mark.parametrize('mensagem,tipo', [
    ('o que é DSCR?', 'conceito'),
    ('qual a taxa do Pronaf?', 'sem_fonte'),
])
def test_rota_de_chat_responde_sem_depender_da_ia(mensagem, tipo):
    """
    Sem GROQ_API_KEY a rota devolvia 503 para tudo. Conceito e recusa passam
    a funcionar mesmo assim — são a parte que não pode depender de terceiro.
    """
    c, _ = _cli()
    r = c.post('/api/chat', json={'mensagem': mensagem})
    assert r.status_code == 200
    assert r.get_json()['origem'] == tipo


def test_whatsapp_usa_a_mesma_disciplina():
    """
    O canal muda, a regra não. E vale mesmo sem parecer emitido: um analista
    que ainda não gerou nada continua podendo perguntar como a conta é feita.
    """
    import app as A
    fonte = open(A.__file__, encoding='utf-8').read()
    i_assist = fonte.index("_assistente.responder(texto)")
    i_parecer = fonte.index("db.ultimo_parecer_do_usuario(uid)")
    assert i_assist < i_parecer, (
        'o assistente precisa responder ANTES da exigência de parecer emitido'
    )


# ── Valor × conceito: a distinção que eu errei na primeira versão ───────────
# "Qual o DSCR?" e "o que é DSCR?" citam a mesma palavra e querem coisas
# opostas. A primeira versão deste módulo respondia a DEFINIÇÃO a quem pedia o
# NÚMERO — e dois testes de WhatsApp que já existiam pegaram isso na hora.
# É o pior dos dois erros: o analista já sabe o que é DSCR, ele quer saber
# quanto deu.

@pytest.mark.parametrize('pergunta', [
    'Qual o DSCR?',
    'quanto ficou o LTV?',
    'meu desfrute deu quanto?',
    'qual o custo por arroba desse parecer?',
    'quantos meses de carência ficou?',
])
def test_pergunta_por_valor_segue_para_o_parecer(pergunta):
    assert responder(pergunta) is None, (
        f'{pergunta!r} pede o número e recebeu a definição'
    )


@pytest.mark.parametrize('pergunta', [
    'qual a diferença entre recria e engorda?',
    'qual o critério de deságio?',
    'qual a metodologia do desfrute?',
])
def test_qual_nem_sempre_pede_valor(pergunta):
    """
    "Qual" abre pergunta conceitual também. Tratar a palavra como sinal
    absoluto mandaria explicação de metodologia para o caminho do parecer,
    que não sabe responder isso.
    """
    assert conceito_da_pergunta(pergunta) is not None


def test_recusa_vale_mesmo_quando_pede_valor():
    """
    Pedir o VALOR de algo normativo não é motivo para responder: "qual a taxa
    do Pronaf" é exatamente a pergunta de valor que não podemos responder.
    """
    assert responder('qual a taxa do Pronaf?')['tipo'] == 'sem_fonte'
    assert responder('quanto é o limite do Pronamp?')['tipo'] == 'sem_fonte'
