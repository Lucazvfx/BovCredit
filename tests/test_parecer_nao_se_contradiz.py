"""
Defeitos achados lendo um parecer emitido, não o código.

O Lucas mandou um PDF de produção — Fazenda Bela Vista, 1.775 cabeças. Três
coisas estavam erradas no documento, e nenhuma tinha teste:

  1. "Reposição de 33% das matrizes — adequada", quando a taxa é 13%. As
     mesmas 150 fêmeas de 25–36 meses eram contadas como plantel a repor E
     como a reposição dele.

  2. "Variação de estoque: riqueza criada pelo crescimento do rebanho" logo
     abaixo de −R$ 1.723.075,98. O rebanho tinha encolhido um quarto do
     próprio valor e a legenda dizia riqueza criada.

  3. A seção "Praça de Referência dos Preços" saía DUAS VEZES, com o mesmo
     conteúdo, por bloco duplicado literal no gerador.

As três são a mesma família do que já corrigimos nesta semana: texto ou
número estático ao lado de outro que mudou, e quem lê acredita no primeiro.
"""
import pytest

from services.consistencia_rebanho import analisar_consistencia
from services.parametros_zootecnicos import avaliar_reposicao

# A ficha do parecer que motivou este arquivo.
BELA_VISTA = [300, 280, 200, 80, 100, 40, 150, 10, 600, 15]


def _flag(v, codigo):
    return next(f for f in analisar_consistencia(v)['flags']
                if f['codigo'] == codigo)


# ── 1. A mesma novilha não repõe a si mesma ─────────────────────────────────
def test_a_faixa_25_36m_nao_conta_dos_dois_lados():
    """
    `matrizes = v[6] + v[8]` e `novilhas_repo = v[4] + v[6]` compartilhavam
    v[6]. Com 150 futuras matrizes numa base de 750, isso inflava a reposição
    de 13% para 33% — e 33% passa folgado em qualquer limiar, então o alerta
    nunca disparava.
    """
    msg = _flag(BELA_VISTA, 'reposicao_femeas')['mensagem']
    assert '33%' not in msg, f'a dupla contagem voltou: {msg}'
    assert '13%' in msg, msg


def test_a_consistencia_e_a_avaliacao_de_reposicao_concordam():
    """
    Dois módulos calculam reposição de fêmeas por caminhos diferentes:
    `consistencia_rebanho` (checagem da ficha) e `avaliar_reposicao`
    (requisito da Embrapa-CPATSA). Se divergirem, o mesmo parecer publica
    dois números para a mesma coisa — que é exatamente o defeito que a
    sensibilidade e o benchmark de custo tinham.
    """
    msg = _flag(BELA_VISTA, 'reposicao_femeas')['mensagem']
    aval = avaliar_reposicao(matrizes=BELA_VISTA[6] + BELA_VISTA[8],
                             novilhas=BELA_VISTA[4], descarte_pct=10.0)
    assert f"{aval['reposicao_sustentada_pct']:.0f}%" in msg, (
        f"consistência diz '{msg}' e avaliar_reposicao diz "
        f"{aval['reposicao_sustentada_pct']}%"
    )


def test_reposicao_realmente_baixa_dispara_alerta():
    """Com a dupla contagem, uma ficha sem novilha passava como adequada."""
    magra = [300, 280, 200, 80, 5, 40, 150, 10, 600, 15]
    f = _flag(magra, 'reposicao_femeas')
    assert f['severidade'] == 'alerta', f


# ── 2. A legenda segue o sinal do número ────────────────────────────────────
@pytest.mark.parametrize('variacao,esperado,proibido', [
    ( 1_000_000.0, 'riqueza criada', 'encolheu'),
    (-1_723_075.98, 'encolheu',      'riqueza criada'),
])
def test_a_legenda_da_variacao_de_estoque_segue_o_sinal(variacao, esperado,
                                                        proibido, tmp_path):
    """
    O caso real: −R$ 1,7 milhão com a legenda "riqueza criada pelo crescimento
    do rebanho". Um analista que confia na legenda lê o oposto do que houve.
    """
    from services.parecer_pdf import gerar_pdf_parecer
    import re

    parecer = {
        'identificacao': {'fazenda': 'Teste', 'municipio': 'X', 'proprietario': ''},
        'composicao': {'total': 1775, 'valores': BELA_VISTA},
        'fluxo_gep': {
            'receita_vendas': 2_006_596.11,
            'custo_operacional': 2_289_727.21,
            'resultado_operacional': -332_755.70,
            'variacao_estoque': variacao,
            'resultado_economico': -2_055_831.68,
            'valor_rebanho_inicio': 6_020_960.87,
            'valor_rebanho_fim': 6_020_960.87 + variacao,
        },
        'conclusao': {'texto': 'Sem crédito a avaliar.'},
    }
    caminho = tmp_path / 'p.pdf'
    caminho.write_bytes(gerar_pdf_parecer(parecer))

    import subprocess
    txt = subprocess.run(['pdftotext', '-layout', str(caminho), '-'],
                         capture_output=True, text=True).stdout
    assert esperado in txt, f'legenda não menciona "{esperado}"'
    assert proibido not in txt, (
        f'legenda diz "{proibido}" com variação de {variacao:,.2f}'
    )


# ── 3. Nenhuma seção sai duas vezes ─────────────────────────────────────────
def test_o_gerador_nao_repete_secao():
    """
    A praça de referência saía duplicada por bloco copiado literalmente. Este
    teste varre o gerador inteiro: qualquer título de seção que apareça duas
    vezes é copy-paste, não intenção.
    """
    import re
    import services.parecer_pdf as pp

    fonte = open(pp.__file__, encoding='utf-8').read()
    titulos = re.findall(r"Paragraph\('([^']+)', ss\['SecaoTitulo'\]\)", fonte)
    repetidos = {t for t in titulos if titulos.count(t) > 1}
    assert not repetidos, f'seções emitidas mais de uma vez: {repetidos}'


# ── 4. O parecer não afirma sobre o que não foi declarado ───────────────────
def test_nao_se_chama_implausivel_uma_declaracao_inexistente():
    """
    A mensagem de touros dizia "Prenhez declarada implausível sem IATF" numa
    ficha com ZERO parâmetros declarados. Afirmar que uma declaração é
    implausível quando ela não existe é afirmar sobre o nada — e o rodapé de
    proveniência do mesmo PDF contava "0 declarados".
    """
    msg = _flag(BELA_VISTA, 'touro_matriz')['mensagem']
    assert 'declarada implausível' not in msg, msg
    assert 'IATF' in msg, 'o alerta perdeu a orientação prática'


# ── 5. O catálogo de proveniência se monta sozinho ──────────────────────────
def test_toda_medicao_registrada_chega_ao_parecer():
    """
    O parecer de produção publicava CINCO parâmetros medidos quando o módulo
    já tinha TREZE. A lista do `catalogo()` era escrita à mão em
    parecer_credito.py, e tudo registrado depois dela ficava invisível — as
    quatro do painel do Pantanal e as quatro da cadeia reprodutiva de Vieira
    et al. nunca chegaram ao documento.

    O rodapé de proveniência é o que separa este parecer de uma planilha com
    opinião. Uma medição que não aparece nele é, para o comitê, uma medição
    que não existe. E o defeito era silencioso: nada quebrava, o número só
    ficava menor que a verdade.
    """
    import services.parametros_zootecnicos as pz
    from services.proveniencia import Parametro, MEDIDO, catalogo, do_modulo

    no_modulo = {n for n, v in vars(pz).items()
                 if isinstance(v, Parametro) and v.origem == MEDIDO}
    no_catalogo = {p['rotulo'] for p in catalogo(do_modulo(pz))
                   if p['origem'] == MEDIDO}

    assert len(no_catalogo) >= len(no_modulo), (
        f'{len(no_modulo)} medições no módulo, {len(no_catalogo)} no catálogo — '
        f'a lista voltou a ser escrita à mão'
    )
    assert len(no_modulo) >= 13, (
        'o módulo perdeu medições — se alguma foi removida, confirme que foi '
        'de propósito'
    )


def test_o_parecer_publica_as_medicoes_novas():
    """As quatro da cadeia reprodutiva têm de aparecer pelo nome no parecer."""
    import database as db
    from app import app
    db.init_db()
    email = 'provdeploy@example.com'
    u = db.buscar_usuario_email(email)
    if not u:
        db.criar_usuario(email, 'Prov', 'senha123')
        u = db.buscar_usuario_email(email)
    app.config['TESTING'] = True
    c = app.test_client()
    with c.session_transaction() as s:
        s['_user_id'] = str(u['id'])

    r = c.post('/api/classificar', json={
        'valores': BELA_VISTA, 'preco': 330,
        'credito_valor': sum(BELA_VISTA) * 1200,
        'prazo_meses': 36, 'juros_aa': 0.125}).get_json()

    prov = r['parecer']['proveniencia']
    medidos = {p['rotulo'] for p in prov['parametros'] if p['origem'] == 'medido'}
    assert prov['resumo']['contagem']['medido'] >= 13, prov['resumo']['contagem']
    for esperado in ('Prenhez, média de 4 safras',
                     'Natalidade sobre prenhez',
                     'Desmama sobre vacas expostas, 4 safras',
                     'Mortalidade pré-desmama medida'):
        assert esperado in medidos, f'{esperado!r} não chegou ao parecer'
