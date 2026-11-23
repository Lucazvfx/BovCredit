"""PDF do parecer: valores None/ausentes, fallback limpo e texto sem colagens.

Prova só a RENDERIZAÇÃO (nenhum cálculo de crédito é exercitado): um parecer
com chaves presentes porém nulas — o que `.get(chave, '—')` não cobre — não
pode imprimir `None`/`nan` nem derrubar a geração do documento.
"""
import copy
import io
import re

import pdfplumber
import pytest

from services.parecer_pdf import gerar_pdf_parecer


def _texto(pdf: bytes, quebras: bool = False) -> str:
    with pdfplumber.open(io.BytesIO(pdf)) as doc:
        bruto = '\n'.join(p.extract_text() or '' for p in doc.pages)
    return bruto if quebras else ' '.join(bruto.split())


def _cru(texto: str) -> list[str]:
    return [m.group(0) for m in re.finditer(r'\b(None|nan|inf|null)\b', texto)]


PARECER_NULO = {
    'identificacao': {'fazenda': None, 'municipio': None, 'proprietario': None},
    'composicao': {'total': None},
    'indicadores': {'total_femeas': None, 'femeas': None, 'total_machos': None,
                    'cria': None, 'recria': None, 'adultos': None,
                    'benchmarks': [{'label': None, 'faixa': None}]},
    'fluxo_gep': {'receita_vendas': 5e6, 'arrobas_vendidas': None,
                  'producao_sobre_venda_pct': None, 'custo_operacional': None,
                  'custo_manutencao': None, 'custo_reposicao': None,
                  'servico_divida_anual': 2e5, 'fluxo_livre': None,
                  'resultado_operacional': None, 'variacao_estoque': None,
                  'compra_desmama_estimada': 5, 'custo_compra_desmama': None},
    'conclusao': {
        'recomendacao': 'negar', 'dscr': None, 'dscr_minimo': None,
        'ano_critico': None, 'parcela_mensal': None, 'capacidade_maxima': None,
        'servico_divida_anual': None, 'justificativa': None,
        'memoria': [{'passo': None, 'valor': None, 'detalhe': None}]},
    'rating': {'faixa': None, 'score': None, 'rotulo': None, 'observacao': None},
    'qualidade_dados': {'nivel_confianca': None, 'origem_principal': None},
    'garantia': {'valor_mercado': 1e6, 'valor_garantia': None,
                 'desagio_medio_pct': None, 'ltv': None,
                 'composicao': [{'rotulo': None, 'valor_mercado': None,
                                 'desagio_pct': None, 'valor_garantia': None}]},
    'endividamento': {'itens': [{'instituicao': None, 'saldo_devedor': None,
                                 'parcela_mensal': None}],
                      'parcela_nova_mensal': None},
    'sensibilidade': [{'variacao_pct': None, 'preco_boi': None,
                       'geracao_caixa': None, 'dscr': None,
                       'recomendacao': None}],
    'comparacao_cenarios': {'cenarios': [{'id': None, 'acumulado': None,
                                          'dscr_minimo': None,
                                          'ano_critico': None}]},
    'ciclo_pecuario': {'disponivel': True, 'meses': [{'rotulo': None, 'mes': 1}],
                       'sistema': None, 'frequencia': None,
                       'ano_referencia': None, 'receita_anual': None,
                       'servico_divida_anual': None},
    'estresse_pecuario': {
        'disponivel': True, 'ano_referencia': None,
        'base': {'preco_arroba': None, 'servico_divida_anual': None},
        'cenarios': {'queda_arroba': {'dscr': None, 'classificacao': None,
                                      'margem_liquida': None}},
        'ponto_ruptura_arroba': {'aprovar': {'status': None, 'dscr_alvo': None,
                                             'preco_base': None}}},
    'proveniencia': {'parametros': [{'rotulo': None, 'valor': None,
                                     'origem_rotulo': None, 'fonte': None}]},
    'shap_explicacao': {'fatores': [{}], 'classe': None},
    'consistencia': {'score_consistencia': None, 'resumo': {},
                     'flags': [{'titulo': None, 'mensagem': None}]},
}


def test_payload_todo_nulo_gera_pdf_sem_none_cru():
    pdf = gerar_pdf_parecer(copy.deepcopy(PARECER_NULO))
    assert pdf[:4] == b'%PDF'
    assert _cru(_texto(pdf)) == []


def test_blocos_novos_com_valores_nulos_usam_fallback_consistente():
    t = _texto(gerar_pdf_parecer(copy.deepcopy(PARECER_NULO)))
    assert 'Ciclo de 12 meses' in t
    assert 'Sistema: — · Pagamento: — · Ano de referência: —' in t
    assert 'Estresse da arroba' in t and 'Ano crítico: — · Preço-base da arroba: —' in t
    assert 'Ponto de ruptura da arroba' in t


def test_stress_e_dscr_minimo_nulos_mostram_travessao():
    t = _texto(gerar_pdf_parecer(copy.deepcopy(PARECER_NULO)))
    assert '—: DSCR — · —' in t  # Stress: sensibilidade
    assert '—: DSCR mín. — · ano crítico —' in t  # Stress: cenários
    assert 'DSCR calculado: — · Ano crítico: —' in t


def test_rebanho_e_producao_sem_dado_nao_deixam_rotulo_solto():
    t = _texto(gerar_pdf_parecer(copy.deepcopy(PARECER_NULO)))
    assert 'Total de animais: — · Fêmeas: — · Machos: —' in t
    assert 'Cria: — · Recria: — · Adultos: —' in t
    assert 'Arrobas vendidas: — · Produz/vende: —' in t


def test_rebanho_usa_chave_alternativa_quando_a_primeira_e_nula():
    p = copy.deepcopy(PARECER_NULO)
    p['indicadores'].update({'total_femeas': None, 'femeas': 120, 'total_machos': 30})
    p['composicao']['total'] = 150
    t = _texto(gerar_pdf_parecer(p))
    assert 'Total de animais: 150 · Fêmeas: 120 · Machos: 30' in t


@pytest.mark.parametrize('ruim', [float('nan'), float('inf'), '', '   ', 'abc'])
def test_numero_invalido_nao_vira_texto_cru(ruim):
    p = copy.deepcopy(PARECER_NULO)
    p['conclusao'].update({'dscr': ruim, 'dscr_minimo': ruim,
                           'parcela_mensal': ruim, 'capacidade_maxima': ruim})
    p['fluxo_gep']['receita_vendas'] = ruim
    p['garantia']['valor_mercado'] = ruim
    t = _texto(gerar_pdf_parecer(p))
    assert _cru(t) == []


def test_fluxo_de_caixa_separa_total_operacional_de_seus_componentes():
    p = {'fluxo_gep': {'receita_vendas': 1_000_000.0, 'custo_operacional': 600_000.0,
                       'custo_manutencao': 400_000.0, 'custo_reposicao': 200_000.0,
                       'resultado_operacional': 400_000.0, 'variacao_estoque': 0.0,
                       'resultado_economico': 400_000.0, 'servico_divida_anual': 216_000.0,
                       'fluxo_livre': 184_000.0, 'valor_rebanho_ini': 1.0,
                       'valor_rebanho_fim': 1.0}}
    t = _texto(gerar_pdf_parecer(p), quebras=True)
    linhas = t.splitlines()
    i_total = next(i for i, l in enumerate(linhas) if 'Custo operacional total (Ano 1)' in l)
    assert 'R$ 600.000,00' in linhas[i_total]
    resto = '\n'.join(linhas[i_total + 1:i_total + 3])
    assert 'dos quais: manutenção do plantel R$ 400.000,00' in resto
    assert 'dos quais: compra de animais (reposição) R$ 200.000,00' in resto
    assert 'Serviço da dívida — total anual (Ano 1) R$ 216.000,00' in t
    # nada da tabela ficou na antiga forma ambígua, somável com o custo total
    assert '(-) Manutenção do plantel' not in t
    assert '(−) Custo operacional ' not in t


def test_conclusao_nao_cola_ano_critico_no_dscr():
    p = {'conclusao': {'recomendacao': 'negar', 'dscr': 6.08, 'dscr_ano1': 6.08,
                       'dscr_minimo': 4.16, 'ano_critico': 2,
                       'parcela_mensal': 9748.0, 'justificativa': 'ok'}}
    t = _texto(gerar_pdf_parecer(p), quebras=True)
    assert not re.search(r'ano \d+DSCR', t)
    assert 'DSCR no ano crítico (ano 2): 4,16' in t
    assert 'DSCR no ano 1: 6,08 · Parcela mensal: R$ 9.748,00' in t


def test_memoria_de_calculo_preserva_valor_em_uma_celula():
    p = {'conclusao': {'recomendacao': 'negar', 'dscr': 6.08, 'dscr_minimo': 4.16,
                       'ano_critico': 2, 'parcela_mensal': 1.0,
                       'justificativa': 'x < y & z',
                       'memoria': [{'passo': 'Ano crítico', 'valor': 'ano 2 · DSCR 4.16',
                                    'detalhe': 'Define a recomendação.'}]}}
    t = _texto(gerar_pdf_parecer(p), quebras=True)
    assert 'ano 2 · DSCR 4.16' in t
    assert not re.search(r'ano \d+DSCR', t)
    assert 'x < y & z' in t  # escapado: não vira tag nem quebra o Paragraph


def test_garantia_mantem_valores_grandes_inteiros_em_uma_linha():
    p = {'garantia': {'valor_mercado': 123_456_789.12, 'valor_garantia': 99_999_999.99,
                      'desagio_medio_pct': 18.5, 'ltv': 40.0, 'veredito': 'suficiente',
                      'composicao': [{'rotulo': 'Vacas de cria descarte e novilhas '
                                                'prenhes com garantia',
                                      'valor_mercado': 99_999_999.99, 'desagio_pct': 20,
                                      'valor_garantia': 79_999_999.99}]}}
    t = _texto(gerar_pdf_parecer(p), quebras=True)
    assert 'R$ 99.999.999,99' in t
    assert 'R$ 79.999.999,99' in t
    assert 'Total R$ 123.456.789,12 18,5% R$ 99.999.999,99' in t
    assert 'LTV 40,0%' in t


def test_fontes_e_origens_longas_quebram_linha_sem_truncar():
    fonte = 'Campo Futuro CNA/Senar boletim anual de custos de produção pecuária ' * 2
    p = {'proveniencia': {'resumo': {'total': 1, 'contagem': {}},
                          'parametros': [{'rotulo': 'Custo operacional efetivo por arroba',
                                          'valor': 245.5, 'origem_rotulo': 'Referência',
                                          'fonte': fonte.strip()}]}}
    t = _texto(gerar_pdf_parecer(p))
    assert 'boletim anual de custos de produção pecuária' in t
    assert 'Custo operacional efetivo por arroba' in t


def test_nao_muda_o_parecer_recebido():
    p = copy.deepcopy(PARECER_NULO)
    gerar_pdf_parecer(p)
    assert p == PARECER_NULO
