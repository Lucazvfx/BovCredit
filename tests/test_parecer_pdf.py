from services.parecer_pdf import gerar_pdf_parecer

PARECER_COMPLETO = {
    'secoes': ['identificacao', 'composicao', 'indicadores', 'consistencia', 'financeiro', 'conclusao'],
    'identificacao': {'fazenda': 'Fazenda Teste', 'municipio': 'Juara - MT', 'proprietario': 'João da Silva'},
    'composicao': {'total': 200, 'valores': [10, 10, 8, 8, 6, 6, 30, 2, 40, 3]},
    'indicadores': {'valores': {'total': 200, 'total_femeas': 120}, 'benchmarks': [
        {'label': 'Taxa de Natalidade', 'faixa': 'bom'}]},
    'consistencia': {'score_consistencia': 90, 'resumo': {'erros': 0, 'alertas': 1, 'ok': 5},
                     'flags': [{'severidade': 'alerta', 'titulo': 'Relação touro:matriz',
                                'mensagem': 'Levemente fora do padrão'}]},
    'financeiro': {'preco_breakeven': 170.88, 'unidade': 'R$/arroba'},
    'conclusao': {'dscr': 1.45, 'parcela_mensal': 12345.67, 'servico_divida_anual': 148148.0,
                  'geracao_caixa_anual': 214814.6, 'recomendacao': 'aprovar', 'faixa': 'aprovar',
                  'justificativa': 'Cobertura 1.45 — folga confortável sobre o serviço da dívida.'},
}

PARECER_SEM_CREDITO = {
    **PARECER_COMPLETO,
    'conclusao': {'dscr': None, 'parcela_mensal': 0.0, 'servico_divida_anual': 0.0,
                  'geracao_caixa_anual': 214814.6, 'recomendacao': None, 'faixa': None,
                  'justificativa': 'Sem crédito a avaliar.'},
}

PARECER_SEM_FLAGS = {
    **PARECER_COMPLETO,
    'consistencia': {'score_consistencia': 100, 'resumo': {'erros': 0, 'alertas': 0, 'ok': 6}, 'flags': []},
}


def test_gerar_pdf_devolve_bytes_pdf_valido():
    pdf = gerar_pdf_parecer(PARECER_COMPLETO)
    assert isinstance(pdf, bytes)
    assert pdf.startswith(b'%PDF')


def test_gerar_pdf_sem_conclusao_de_credito_nao_lanca():
    pdf = gerar_pdf_parecer(PARECER_SEM_CREDITO)
    assert pdf.startswith(b'%PDF')


def test_gerar_pdf_sem_flags_de_consistencia_nao_lanca():
    pdf = gerar_pdf_parecer(PARECER_SEM_FLAGS)
    assert pdf.startswith(b'%PDF')


def test_gerar_pdf_com_nome_consultoria():
    pdf = gerar_pdf_parecer(PARECER_COMPLETO, branding={'nome_consultoria': 'Consultoria X'})
    assert pdf.startswith(b'%PDF')


def test_gerar_pdf_com_logo_base64_invalido_nao_lanca():
    pdf = gerar_pdf_parecer(PARECER_COMPLETO, branding={'logo_base64': 'não-é-base64-válido!!'})
    assert pdf.startswith(b'%PDF')


def test_gerar_pdf_sem_branding_identico_ao_atual():
    pdf = gerar_pdf_parecer(PARECER_COMPLETO, branding=None)
    assert pdf.startswith(b'%PDF')


def test_pdf_leva_a_memoria_de_calculo_ao_comite():
    """
    O PDF é o que chega ao comitê de crédito. Mostrava o DSCR do ano 1 — que
    liquida o estoque e não se repete — e omitia o raciocínio. Sob CMN
    4.966/2021 a decisão precisa ser auditável no documento, não só na tela.
    """
    from services.parecer_pdf import gerar_pdf_parecer
    memoria = [
        {'passo': 'Prazo do crédito', 'valor': '36 meses', 'detalhe': 'Avalia 3 anos.'},
        {'passo': 'Ano crítico', 'valor': 'ano 2 · DSCR -0.53', 'detalhe': 'Define a recomendação.'},
        {'passo': 'Rebaixamento', 'valor': 'APROVAR → NEGAR', 'detalhe': 'O ano 1 não se repete.'},
    ]
    base = {
        'identificacao': {'fazenda': 'F', 'municipio': 'M', 'proprietario': 'P'},
        'composicao': {'total': 790, 'valores': [80, 80, 50, 50, 60, 60, 90, 40, 220, 60]},
        'conclusao': {
            'recomendacao': 'negar', 'dscr': 6.08, 'dscr_ano1': 6.08,
            'dscr_minimo': -0.53, 'ano_critico': 2, 'parcela_mensal': 9748.0,
            'justificativa': 'Cobertura cai no ano 2.', 'memoria': memoria,
        },
    }
    com = gerar_pdf_parecer(base)
    sem = gerar_pdf_parecer({**base, 'conclusao': {k: v for k, v in base['conclusao'].items()
                                                   if k != 'memoria'}})
    assert com[:4] == b'%PDF'
    assert len(com) > len(sem), 'a memória precisa aparecer no documento'


def test_pdf_de_parecer_antigo_nao_quebra():
    """Pareceres salvos antes dos campos novos precisam continuar gerando PDF."""
    from services.parecer_pdf import gerar_pdf_parecer
    antigo = {
        'identificacao': {'fazenda': 'F', 'municipio': 'M', 'proprietario': 'P'},
        'composicao': {'total': 100, 'valores': [0] * 8 + [100, 5]},
        'conclusao': {'recomendacao': 'aprovar', 'dscr': 2.1,
                      'parcela_mensal': 1000.0, 'justificativa': 'ok'},
    }
    assert gerar_pdf_parecer(antigo)[:4] == b'%PDF'
