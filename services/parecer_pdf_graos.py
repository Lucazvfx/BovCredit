"""Geração do PDF oficial do parecer técnico de crédito para culturas anuais, grãos e Barter/CPR.

Produz relatório executivo e auditável de 2 a 4 páginas contendo:
1. Identificação da propriedade e produtor
2. Plano de Safra (Culturas 1ª Safra Verão e 2ª Safra Safrinha)
3. Estrutura de Custos (COE/COT), DRE da safra e Pontos de Equilíbrio (sc/ha)
4. Capacidade de Pagamento, DSCR do contrato e amortização (SAC/Price)
5. Projeção Plurianual e Testes de Estresse
6. Operação de Barter e Termômetro de Risco de Penhor (quando simulada)
7. Minuta da Cédula de Produto Rural — CPR Física (Lei 8.929/94) pronta para assinatura
8. Parecer técnico e recomendações do comitê
"""
from __future__ import annotations

import io
from datetime import datetime
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.platypus import (
    HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle, PageBreak,
)

from services.parecer_pdf import _fmt_moeda, _logo_flowable, _styles

_CABECALHO = TableStyle([
    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#E8DCC7')),
    ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#203127')),
    ('GRID', (0, 0), (-1, -1), 0.35, colors.HexColor('#D8C9B3')),
    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
    ('FONTSIZE', (0, 0), (-1, -1), 8),
    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ('TOPPADDING', (0, 0), (-1, -1), 4),
    ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
])


def _numero(valor, casas=0) -> str:
    try:
        texto = f'{float(valor):,.{casas}f}'
    except (TypeError, ValueError):
        return '—'
    return texto.replace(',', '_').replace('.', ',').replace('_', '.')


def _secao(story, ss, titulo: str) -> None:
    story.append(Paragraph(titulo, ss['SecaoTitulo']))
    story.append(HRFlowable(width='100%', thickness=0.6, color=colors.HexColor('#D8C9B3')))
    story.append(Spacer(1, 5))


def _tabela(story, dados: list[list], larguras: list[float]) -> None:
    tabela = Table(dados, colWidths=larguras, repeatRows=1)
    tabela.setStyle(_CABECALHO)
    story.append(tabela)


def _identificacao(story, ss, ident: dict, nome_consultoria: str) -> None:
    titulo = (f'{nome_consultoria} — Parecer de Crédito Agrícola'
              if nome_consultoria else
              'Parecer Técnico de Crédito Agrícola — Grãos & Safra')
    story.append(Paragraph(titulo, ss['Titulo']))
    story.append(Paragraph(
        f"{ident.get('fazenda') or 'Fazenda Modelo'} · {ident.get('municipio') or 'Região Centro-Oeste'} · "
        f"{ident.get('proprietario') or 'Produtor Rural'} — emitido em "
        f"{datetime.now().strftime('%d/%m/%Y às %H:%M')}", ss['Subtitulo']))
    story.append(Spacer(1, 5))
    story.append(Paragraph(
        '<b>Natureza da análise:</b> parecer técnico-financeiro de suporte à tomada de decisão de '
        'crédito rural (custeio, investimento ou barter). A capacidade de pagamento e os índices de '
        'breakeven refletem os dados de safra e custos declarados e/ou calibrados com benchmarks oficiais '
        '(Conab/IMEA/Cepea).', ss['Subtitulo']))
    story.append(Spacer(1, 10))


def _plano_safra(story, ss, economico: dict) -> None:
    culturas = economico.get('culturas') or []
    if not culturas:
        return
    _secao(story, ss, 'Plano de Safra e Produção Esperada')

    dados = [['Cultura / Safra', 'Área (ha)', 'Produtividade', 'Produção Total', 'Preço Unitário', 'Receita Bruta']]
    for c in culturas:
        dados.append([
            c.get('identificacao') or c.get('cultura') or '—',
            f"{_numero(c.get('area_ha'), 0)} ha",
            f"{_numero(c.get('produtividade_ha'), 1)} {c.get('unidade','sc')}/ha",
            f"{_numero(c.get('producao_total'), 0)} {c.get('unidade','sc')}",
            _fmt_moeda(c.get('preco_unitario')),
            _fmt_moeda(c.get('receita_bruta')),
        ])
    _tabela(story, dados, [3.6 * cm, 2.2 * cm, 2.8 * cm, 2.8 * cm, 2.5 * cm, 3.1 * cm])

    story.append(Spacer(1, 6))
    area_fisica = economico.get('area_fisica_ha') or 0
    area_plantada = economico.get('area_plantada_total_ha') or 0
    story.append(Paragraph(
        f"Área física estimada da fazenda: <b>{_numero(area_fisica, 0)} ha</b> · "
        f"Área plantada total (safra + safrinha): <b>{_numero(area_plantada, 0)} ha</b> · "
        f"Receita bruta consolidada: <b>{_fmt_moeda(economico.get('receita_total'))}</b>",
        ss['Corpo']))
    story.append(Spacer(1, 8))


def _economico_breakeven(story, ss, economico: dict) -> None:
    culturas = economico.get('culturas') or []
    if not culturas:
        return
    _secao(story, ss, 'Custos Operacionais & Ponto de Equilíbrio (Breakeven)')

    dados = [['Cultura', 'COE (Insumos/ha)', 'COT Total/ha', 'Breakeven sc/ha', 'Breakeven Preço', 'Margem Segurança']]
    for c in culturas:
        dados.append([
            c.get('identificacao') or c.get('cultura') or '—',
            f"{_fmt_moeda(c.get('coe_ha'))}/ha",
            f"{_fmt_moeda(c.get('cot_ha'))}/ha",
            f"{_numero(c.get('breakeven_sc_ha'), 1)} {c.get('unidade','sc')}/ha",
            _fmt_moeda(c.get('breakeven_preco')),
            f"{_numero(c.get('margem_seguranca_sc_ha'), 1)} {c.get('unidade','sc')}/ha",
        ])
    _tabela(story, dados, [3.6 * cm, 2.9 * cm, 2.8 * cm, 2.7 * cm, 2.5 * cm, 2.5 * cm])

    story.append(Spacer(1, 6))
    story.append(Paragraph(
        f"COE Total (Desembolso direto): <b>{_fmt_moeda(economico.get('coe_total'))}</b> · "
        f"Margem de Contribuição: <b>{_fmt_moeda(economico.get('margem_contribuicao_total'))}</b> · "
        f"Resultado Operacional Líquido: <b>{_fmt_moeda(economico.get('resultado_operacional'))}</b>",
        ss['Corpo']))
    story.append(Spacer(1, 8))


def _capacidade(story, ss, analise: dict) -> None:
    credito = (analise.get('credito') or {}).get('analysis') or {}
    if not credito:
        return
    _secao(story, ss, 'Capacidade de Pagamento & Dimensionamento do Crédito')

    pior = credito.get('pior_periodo') or {}
    resumo = [
        ['DSCR médio do contrato', f"{_numero(credito.get('dscr_medio'), 2)}x"],
        ['DSCR mínimo do contrato', f"{_numero(credito.get('dscr_minimo'), 2)}x"],
        ['Ano mais crítico / apertado', f"Ano {pior.get('ano') or '1'}"],
        ['Serviço da dívida anual no ano crítico', _fmt_moeda(pior.get('servico_divida_anual'))],
        ['Geração de caixa operacional anual', _fmt_moeda(credito.get('geracao_caixa_anual'))],
        ['Capacidade máxima estimada de endividamento', _fmt_moeda(credito.get('capacidade_maxima_estimativa'))],
    ]
    _tabela(story, [['Indicador de Risco de Crédito', 'Valor / Projeção']] + resumo, [9.0 * cm, 8.0 * cm])
    story.append(Spacer(1, 8))


def _projecao_estresse(story, ss, analise: dict) -> None:
    scenarios = (analise.get('stress') or {}).get('scenarios') or []
    if not scenarios:
        return
    _secao(story, ss, 'Testes de Estresse na Safra e Sensibilidade')

    dados = [['Cenário de Estresse', 'Choque Simulado', 'DSCR Resultante', 'Status de Cobertura']]
    for s in scenarios:
        dados.append([
            str(s.get('nome') or '').replace('_', ' ').title(),
            ', '.join(s.get('applied_changes') or ['—']),
            f"{_numero(s.get('dscr_minimo'), 2)}x",
            'Descoberto (Risco)' if s.get('uncovered') else 'Coberto (Caixa Positivo)',
        ])
    _tabela(story, dados, [5.5 * cm, 5.5 * cm, 2.8 * cm, 3.2 * cm])
    story.append(Spacer(1, 8))


def _barter_cpr(story, ss, barter: dict | None, cpr: dict | None) -> None:
    if not barter and not cpr:
        return
    dados_b = barter or (cpr.get('barter') if cpr else {})
    if not dados_b:
        return

    story.append(PageBreak())
    _secao(story, ss, 'Operação de Barter & Penhor de Safra (CPR)')

    cor_risco = dados_b.get('classificacao_risco', 'BAIXO')
    resumo_barter = [
        ['Valor do pacote de insumos financiado', _fmt_moeda(dados_b.get('valor_insumos'))],
        ['Preço referencial travado da saca', f"{_fmt_moeda(dados_b.get('preco_saca_referencia'))} ({dados_b.get('praca_nome', 'Mercado')})"],
        ['Quantidade de grãos a entregar', f"{_numero(dados_b.get('sacas_a_entregar'), 1)} sc ({_numero(dados_b.get('toneladas_a_entregar'), 1)} t)"],
        ['Área física comprometida com o penhor', f"{_numero(dados_b.get('area_travada_ha'), 1)} hectares"],
        ['Percentual de comprometimento da safra', f"{_numero(dados_b.get('comprometimento_safra_pct'), 1)}% da produção total"],
        ['Classificação do Risco de Penhor', f"{cor_risco}"],
    ]
    _tabela(story, [['Condição da Operação de Barter', 'Especificação']] + resumo_barter, [8.5 * cm, 8.5 * cm])

    story.append(Spacer(1, 6))
    rec = dados_b.get('recomendacao_comite') or ''
    if rec:
        story.append(Paragraph(f"<b>Recomendação do Comitê de Crédito:</b> {rec}", ss['Corpo']))
        story.append(Spacer(1, 8))

    # Minuta anexa
    if cpr and cpr.get('texto_minuta'):
        _secao(story, ss, 'Anexo: Minuta Jurídica da Cédula de Produto Rural (Lei 8.929/94)')
        linhas = cpr['texto_minuta'].split('\n')
        for linha in linhas[:40]:  # primeiras 40 linhas resumidas para caber no parecer
            story.append(Paragraph(linha.replace(' ', '&nbsp;'), ss['Corpo']))
        story.append(Spacer(1, 6))
        story.append(Paragraph('<i>[Texto integral disponível no sistema para assinatura e registro na B3 / CERC]</i>', ss['Subtitulo']))


def _compliance_esg(story, ss, esg: dict | None) -> None:
    if not esg:
        return
    _secao(story, ss, 'Conformidade Socioambiental & ESG (Resoluções CMN 4.945 e 5.081)')
    car = esg.get('car') or {}
    checagens = esg.get('checagens') or {}
    selo = esg.get('selo_conformidade_cmn') or 'Em conformidade'

    rl_decl = float(car.get('percentual_rl_declarado') or 0.0) * 100
    rl_exig = float(car.get('percentual_rl_exigido') or 0.0) * 100
    rl_ha = float(car.get('area_reserva_legal_ha') or 0.0)
    app_ha = float(car.get('area_app_ha') or 0.0)

    tabela_esg = [
        ['Item de Verificação Socioambiental', 'Situação / Resultado'],
        ['Número do CAR (SICAR)', str(car.get('numero_car') or 'Não informado')],
        ['Status Cadastral do CAR', str(car.get('status') or 'ATIVO')],
        ['Bioma Referencial', str(car.get('bioma') or 'CERRADO').replace('_', ' ')],
        ['Reserva Legal (Declarada vs Exigida)', f"{rl_decl:.1f}% decl. vs {rl_exig:.0f}% exig. ({rl_ha:.1f} ha)"],
        ['Área de Preservação Permanente (APP)', f"{app_ha:.1f} ha"],
        ['Consulta de Embargos Ambientais (IBAMA)', 'EMBARGO ATIVO (IMPEDITIVO)' if checagens.get('embargo_ibama') else 'Nada Consta (Regular)'],
        ['Consulta Lista Suja Trabalho Escravo (MTE)', 'INSCRIÇÃO ATIVA (IMPEDITIVO)' if checagens.get('trabalho_escravo_mte') else 'Nada Consta (Regular)'],
        ['Sobreposição Terra Indígena / Unid. Conservação', 'Sobreposição Detectada' if (checagens.get('sobreposicao_terra_indigena') or checagens.get('sobreposicao_unidade_conservacao')) else 'Isento de Sobreposição'],
        ['Score ESG / Conformidade Bacen', f"{esg.get('score_esg', 100)} / 100 — {selo}"],
    ]
    _tabela(story, tabela_esg, [9.0 * cm, 8.0 * cm])
    story.append(Spacer(1, 6))
    if esg.get('recomendacoes_comite'):
        story.append(Paragraph(f"<b>Parecer Técnico ESG:</b> {esg.get('recomendacoes_comite')}", ss['Corpo']))
        story.append(Spacer(1, 8))


def _matriz_garantias(story, ss, garantias: dict | None) -> None:
    if not garantias or not garantias.get('itens'):
        return
    _secao(story, ss, 'Matriz de Garantias & Dimensionamento de LTV (Garantias Reais e Fiduciárias)')

    itens = garantias.get('itens') or []
    linhas = [['Garantia Ofertada', 'Modalidade / Gravame', 'Valor Mercado', 'Deságio', 'Valor Líquido']]
    for it in itens:
        linhas.append([
            f"{it.get('descricao') or 'Garantia'}\n({it.get('identificador_registro') or 'S/N'})",
            str(it.get('gravame') or '').replace('_', ' ').title(),
            _fmt_moeda(it.get('valor_mercado_bruto')),
            f"-{it.get('desagio_aplicado_pct', 0):.0f}%",
            _fmt_moeda(it.get('valor_liquidacao_forcada')),
        ])
    _tabela(story, linhas, [6.0 * cm, 4.0 * cm, 2.5 * cm, 1.8 * cm, 2.7 * cm])
    story.append(Spacer(1, 6))

    kpis = [
        ['Indicador de Risco da Garantia', 'Métrica Apurada'],
        ['Valor Total de Mercado das Garantias', _fmt_moeda(garantias.get('valor_mercado_total'))],
        ['Valor Total de Liquidação Forçada (Pós-Deságio)', _fmt_moeda(garantias.get('valor_liquidacao_total'))],
        ['Crédito Solicitado no Contrato', _fmt_moeda(garantias.get('credito_solicitado'))],
        ['LTV Consolidado (Loan-to-Value)', f"{garantias.get('ltv_pct', 0):.1f}%"],
        ['Índice de Cobertura de Garantias (ICG)', f"{garantias.get('indice_cobertura_pct', 0):.1f}%"],
        ['Classificação de Risco da Garantia', f"{garantias.get('classificacao_risco') or 'ADEQUADA'}"],
    ]
    _tabela(story, kpis, [9.0 * cm, 8.0 * cm])
    story.append(Spacer(1, 6))
    if garantias.get('recomendacao_comite'):
        story.append(Paragraph(f"<b>Parecer do Comitê de Garantias:</b> {garantias.get('recomendacao_comite')}", ss['Corpo']))
        story.append(Spacer(1, 8))


def _dicas_parecer(story, ss, analise: dict) -> None:
    dicas = analise.get('dicas') or []
    if not dicas:
        return
    _secao(story, ss, 'Diagnóstico & Recomendações Técnicas')
    for d in dicas:
        story.append(Paragraph(f"<b>• {d.get('titulo')}:</b> {d.get('texto')}", ss['Corpo']))
        story.append(Spacer(1, 4))


def gerar_pdf_parecer_graos(
    analise: dict,
    identificacao: dict | None = None,
    barter: dict | None = None,
    cpr: dict | None = None,
    branding: dict | None = None,
    esg: dict | None = None,
    garantias: dict | None = None,
) -> bytes:
    """Recebe o resultado de `analisar_culturas_anuais` e devolve os bytes do PDF."""
    ss = _styles()
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
    )
    story = []

    branding = branding or {}
    logo = _logo_flowable(branding.get('logo_base64') or '')
    if logo is not None:
        story.append(logo)
        story.append(Spacer(1, 6))

    _identificacao(story, ss, identificacao or {}, (branding.get('nome_consultoria') or '').strip())
    _plano_safra(story, ss, analise.get('economico') or {})
    _economico_breakeven(story, ss, analise.get('economico') or {})
    _capacidade(story, ss, analise)
    _projecao_estresse(story, ss, analise)
    _compliance_esg(story, ss, esg)
    _matriz_garantias(story, ss, garantias)
    _barter_cpr(story, ss, barter, cpr)
    _dicas_parecer(story, ss, analise)

    doc.build(story)
    return buffer.getvalue()
