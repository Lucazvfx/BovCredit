"""
Endividamento total do proponente.

Todo o DSCR se apoiava num único número digitado — "dívidas mensais" — sem
origem e sem verificação. Produtor com operação em outros quatro bancos que
informasse zero fechava um parecer bonito e errado, e nada denunciaria.

O inventário por credor não verifica nada sozinho. O que ele muda é que a
dívida passa a ter credor, saldo e parcela item a item: vira declaração
assinável, confrontável com o SCR, e visível no parecer.
"""
import pytest

from services.endividamento import consolidar, COMPROMETIMENTO_ALERTA


def test_soma_as_parcelas_dos_credores_declarados():
    e = consolidar(dividas=[
        {'instituicao': 'Banco do Brasil', 'saldo_devedor': 800_000, 'parcela_mensal': 22_000},
        {'instituicao': 'Sicredi',          'saldo_devedor': 300_000, 'parcela_mensal': 9_000},
    ], geracao_caixa_anual=1_200_000)
    assert e['parcela_existente_mensal'] == 31_000
    assert e['saldo_devedor_total'] == 1_100_000
    assert len(e['itens']) == 2
    assert e['tudo_discriminado'] is True


def test_campo_antigo_continua_funcionando_e_se_declara_nao_discriminado():
    """
    Compatibilidade: a conta tem que dar o mesmo de antes. O que muda é o
    parecer passar a dizer que a origem do número é desconhecida.
    """
    e = consolidar(dividas_mensais_legado=15_000, geracao_caixa_anual=1_200_000)
    assert e['parcela_existente_mensal'] == 15_000
    assert e['tudo_discriminado'] is False
    assert 'não foi discriminada' in e['justificativa'].lower()


def test_inventario_tem_precedencia_sobre_o_campo_antigo():
    """Se o analista discriminou, o número solto não pode somar em duplicidade."""
    e = consolidar(dividas=[{'instituicao': 'Banco X', 'parcela_mensal': 10_000}],
                   dividas_mensais_legado=99_000,
                   geracao_caixa_anual=1_200_000)
    assert e['parcela_existente_mensal'] == 10_000


def test_parcela_nova_entra_no_comprometimento():
    """A decisão é sobre a situação DEPOIS da operação, não antes."""
    sem = consolidar(dividas=[{'instituicao': 'X', 'parcela_mensal': 10_000}],
                     geracao_caixa_anual=1_200_000)
    com = consolidar(dividas=[{'instituicao': 'X', 'parcela_mensal': 10_000}],
                     geracao_caixa_anual=1_200_000, parcela_nova=20_000)
    assert com['comprometimento_pct'] > sem['comprometimento_pct']
    assert com['parcela_total_mensal'] == 30_000


def test_comprometimento_acima_do_limite_vira_alerta_critico():
    caixa = 1_200_000
    parcela = (caixa * (COMPROMETIMENTO_ALERTA + 0.15)) / 12
    e = consolidar(dividas=[{'instituicao': 'X', 'parcela_mensal': parcela}],
                   geracao_caixa_anual=caixa)
    assert e['alerta'] == 'critico'
    assert e['comprometimento_pct'] > COMPROMETIMENTO_ALERTA * 100


def test_comprometimento_dentro_do_limite_fica_ok():
    caixa = 1_200_000
    parcela = (caixa * 0.30) / 12
    e = consolidar(dividas=[{'instituicao': 'X', 'parcela_mensal': parcela}],
                   geracao_caixa_anual=caixa)
    assert e['alerta'] == 'ok'


def test_sem_divida_declarada_o_parecer_avisa_para_conferir_o_scr():
    """
    O caso mais perigoso: zero declarado pode ser verdade ou omissão, e o
    parecer não pode tratar os dois como a mesma coisa.
    """
    e = consolidar(geracao_caixa_anual=1_200_000)
    assert e['itens'] == []
    assert e['alerta'] is None
    assert 'SCR' in e['justificativa'], (
        'o analista precisa ser lembrado de que ausência declarada não é '
        'ausência verificada'
    )


def test_caixa_negativo_e_incompativel_com_qualquer_divida():
    e = consolidar(dividas=[{'instituicao': 'X', 'parcela_mensal': 5_000}],
                   geracao_caixa_anual=-50_000)
    assert e['alerta'] == 'critico'
    assert e['comprometimento_pct'] is None


def test_entradas_sujas_nao_quebram():
    e = consolidar(dividas=[
        {'instituicao': 'Válido', 'parcela_mensal': 5_000},
        {'instituicao': 'Zerado', 'parcela_mensal': 0, 'saldo_devedor': 0},
        {'parcela_mensal': 'abc'},
        'nem é dict',
        None,
    ], geracao_caixa_anual=1_200_000)
    assert e['parcela_existente_mensal'] == 5_000
    assert len(e['itens']) == 1


def test_credor_sem_nome_nao_vira_string_vazia():
    e = consolidar(dividas=[{'parcela_mensal': 5_000}], geracao_caixa_anual=1_200_000)
    assert e['itens'][0]['instituicao'] == 'Não informada'


def test_origem_e_declarada_ate_haver_convenio_com_o_scr():
    """Rastreabilidade: o parecer precisa dizer de onde veio o número."""
    e = consolidar(dividas=[{'instituicao': 'X', 'parcela_mensal': 5_000}],
                   geracao_caixa_anual=1_200_000)
    assert e['origem'] == 'declarado'


def test_memoria_de_calculo_mostra_a_conta():
    e = consolidar(dividas=[{'instituicao': 'X', 'parcela_mensal': 10_000}],
                   geracao_caixa_anual=1_200_000, parcela_nova=20_000)
    passos = ' '.join(m['passo'] for m in e['memoria']).lower()
    assert 'existente' in passos
    assert 'análise' in passos or 'analise' in passos
    assert 'comprometimento' in passos
