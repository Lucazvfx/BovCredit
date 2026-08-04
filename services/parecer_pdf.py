"""Geração de PDF do parecer de crédito — documento profissional para anexar
a um processo de crédito (não o tema escuro do dashboard).

Módulo puro: recebe o dict do parecer (mesma estrutura de
`services.parecer_credito.montar_parecer`), devolve os bytes do PDF. Sem
dependência de sistema (reportlab é puro Python/wheels), funciona igual em
qualquer alvo de deploy.
"""
from __future__ import annotations
import io
import base64
import logging
from datetime import datetime

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, Image,
)

_logger = logging.getLogger(__name__)

_COR_RECOMENDACAO = {
    'aprovar': colors.HexColor('#2E7D32'),
    'ressalva': colors.HexColor('#B8860B'),
    'negar': colors.HexColor('#C62828'),
}
_LABEL_RECOMENDACAO = {
    'aprovar': 'APROVAR', 'ressalva': 'APROVAR COM RESSALVA', 'negar': 'NEGAR',
}


def _styles():
    ss = getSampleStyleSheet()
    ss.add(ParagraphStyle('Titulo', parent=ss['Heading1'], fontSize=16, spaceAfter=4))
    ss.add(ParagraphStyle('Subtitulo', parent=ss['Normal'], fontSize=9, textColor=colors.grey))
    ss.add(ParagraphStyle('SecaoTitulo', parent=ss['Heading2'], fontSize=12, spaceBefore=14, spaceAfter=6))
    ss.add(ParagraphStyle('Corpo', parent=ss['Normal'], fontSize=10, leading=14))
    return ss


def _fmt_moeda(v) -> str:
    try:
        return f"R$ {float(v):,.2f}".replace(',', '_').replace('.', ',').replace('_', '.')
    except (TypeError, ValueError):
        return '—'


def _logo_flowable(logo_base64: str):
    """Decodifica o logo em base64 para uma Image do reportlab. None se inválido."""
    if not logo_base64:
        return None
    try:
        raw = base64.b64decode(logo_base64, validate=False)
        img = Image(io.BytesIO(raw))
        largura_max = 4 * cm
        if img.imageWidth > 0:
            escala = largura_max / img.imageWidth
            img.drawWidth = largura_max
            img.drawHeight = img.imageHeight * escala
        return img
    except Exception:
        _logger.warning('Logo inválido no PDF do parecer — gerando sem logo.', exc_info=True)
        return None


def gerar_pdf_parecer(parecer: dict, branding: dict | None = None) -> bytes:
    ss = _styles()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            topMargin=2*cm, bottomMargin=2*cm,
                            leftMargin=2*cm, rightMargin=2*cm)
    story = []

    branding = branding or {}
    nome_consultoria = (branding.get('nome_consultoria') or '').strip()
    logo = _logo_flowable(branding.get('logo_base64') or '')
    if logo is not None:
        story.append(logo)
        story.append(Spacer(1, 6))

    ident = parecer.get('identificacao') or {}
    titulo = (f"{nome_consultoria} — Parecer de Crédito" if nome_consultoria
              else 'Parecer de Crédito — Análise Técnico-Financeira')
    story.append(Paragraph(titulo, ss['Titulo']))
    fazenda = ident.get('fazenda') or '—'
    municipio = ident.get('municipio') or '—'
    proprietario = ident.get('proprietario') or '—'
    story.append(Paragraph(
        f"{fazenda} · {municipio} · {proprietario} — emitido em "
        f"{datetime.now().strftime('%d/%m/%Y')}", ss['Subtitulo']))
    story.append(Spacer(1, 5))
    story.append(Paragraph(
        '<b>Natureza da análise:</b> pré-análise técnico-financeira de apoio à '
        'consultoria. Este documento não substitui a conferência documental, '
        'a visita à propriedade ou a decisão final do agente de crédito.',
        ss['Subtitulo']))
    story.append(HRFlowable(width='100%', color=colors.HexColor('#CCCCCC'), spaceBefore=8, spaceAfter=4))

    composicao = parecer.get('composicao') or {}
    story.append(Paragraph('Composição do Rebanho', ss['SecaoTitulo']))
    story.append(Paragraph(f"Total de animais: {composicao.get('total', '—')}", ss['Corpo']))

    qualidade = parecer.get('qualidade_dados') or {}
    if qualidade:
        story.append(Paragraph('Qualidade e origem dos dados', ss['SecaoTitulo']))
        story.append(Paragraph(
            f"Confiança: <b>{qualidade.get('nivel_confianca', '—')}</b> · "
            f"Origem principal: {qualidade.get('origem_principal', '—')}",
            ss['Corpo']))
        for aviso in (qualidade.get('avisos') or []):
            story.append(Paragraph(f"• {aviso}", ss['Corpo']))

    indicadores = parecer.get('indicadores') or {}
    benchmarks = indicadores.get('benchmarks') or []
    if benchmarks:
        story.append(Paragraph('Indicadores Técnicos vs. Benchmark', ss['SecaoTitulo']))
        linhas = [['Indicador', 'Faixa']]
        for b in benchmarks:
            linhas.append([b.get('label', '—'), str(b.get('faixa', '—')).capitalize()])
        t = Table(linhas, colWidths=[10*cm, 6*cm])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#EEEEEE')),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#DDDDDD')),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
        ]))
        story.append(t)

    consistencia = parecer.get('consistencia') or {}
    story.append(Paragraph('Consistência do Rebanho Declarado', ss['SecaoTitulo']))
    score = consistencia.get('score_consistencia', '—')
    resumo = consistencia.get('resumo') or {}
    story.append(Paragraph(
        f"Score: {score} — {resumo.get('erros', 0)} erro(s), "
        f"{resumo.get('alertas', 0)} alerta(s), {resumo.get('ok', 0)} ok", ss['Corpo']))
    for f in (consistencia.get('flags') or []):
        story.append(Paragraph(
            f"• <b>{f.get('titulo', '')}</b>: {f.get('mensagem', '')}", ss['Corpo']))

    financeiro = parecer.get('financeiro') or {}
    if financeiro:
        story.append(Paragraph('Situação Financeira', ss['SecaoTitulo']))
        be = financeiro.get('preco_breakeven')
        if be is not None:
            story.append(Paragraph(
                f"Preço de equilíbrio (breakeven): {_fmt_moeda(be)} "
                f"{financeiro.get('unidade', '')}", ss['Corpo']))

    fluxo_gep = parecer.get('fluxo_gep')
    if fluxo_gep and fluxo_gep.get('receita_vendas', 0) > 0:
        story.append(Paragraph('Fluxo de Caixa', ss['SecaoTitulo']))
        linhas_fc = [['Componente', 'R$ (Ano 1)']]
        linhas_fc.append(['(+) Receita de vendas', _fmt_moeda(fluxo_gep.get('receita_vendas'))])
        linhas_fc.append(['(−) Custo operacional', _fmt_moeda(fluxo_gep.get('custo_operacional'))])
        linhas_fc.append(['(=) Resultado operacional (caixa)', _fmt_moeda(fluxo_gep.get('resultado_operacional'))])
        linhas_fc.append(['(±) Variação de estoque do rebanho', _fmt_moeda(fluxo_gep.get('variacao_estoque'))])
        linhas_fc.append(['(=) Resultado econômico total', _fmt_moeda(fluxo_gep.get('resultado_economico'))])
        if fluxo_gep.get('servico_divida_anual', 0) > 0:
            linhas_fc.append(['(−) Serviço da dívida (anual)', _fmt_moeda(fluxo_gep.get('servico_divida_anual'))])
            linhas_fc.append(['(=) Fluxo livre', _fmt_moeda(fluxo_gep.get('fluxo_livre'))])
        linhas_fc.append(['Valor do rebanho — início do período', _fmt_moeda(fluxo_gep.get('valor_rebanho_ini'))])
        linhas_fc.append(['Valor do rebanho — fim do período', _fmt_moeda(fluxo_gep.get('valor_rebanho_fim'))])
        tf = Table(linhas_fc, colWidths=[10*cm, 6*cm])
        _destaques = {3, 5}  # linhas de resultado (índice 0 = header)
        _estilo_fc = [
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#EEEEEE')),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#DDDDDD')),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ]
        for i in _destaques:
            if i < len(linhas_fc):
                _estilo_fc.append(('BACKGROUND', (0, i), (-1, i), colors.HexColor('#E8F5E9')))
                _estilo_fc.append(('FONTNAME', (0, i), (-1, i), 'Helvetica-Bold'))
        tf.setStyle(TableStyle(_estilo_fc))
        story.append(tf)
        story.append(Spacer(1, 4))
        # A legenda tem de seguir o SINAL do número que ela explica. Era fixa em
        # "riqueza criada pelo crescimento do rebanho" e aparecia embaixo de uma
        # variação de −R$ 1,7 milhão num parecer real: a legenda dizia riqueza
        # criada onde o rebanho tinha encolhido em um quarto do próprio valor.
        #
        # É a mesma classe de defeito do ano 1 na sensibilidade — texto estático
        # ao lado de número que mudou de sinal, e quem lê acredita no texto.
        _var_est = float(fluxo_gep.get('variacao_estoque') or 0)
        story.append(Paragraph(
            ('<i>Variação de estoque: riqueza criada pelo crescimento do rebanho '
             '— não é caixa, mas é valor real do ativo.</i>'
             if _var_est >= 0 else
             '<i>Variação de estoque NEGATIVA: o rebanho encolheu no período. '
             'Não é saída de caixa, mas é perda de ativo — a fazenda financiou '
             'parte do resultado consumindo o próprio plantel. Confira se é '
             'realização planejada ou descapitalização.</i>'), ss['Subtitulo']))
        _cd = fluxo_gep.get('compra_desmama_estimada', 0)
        if _cd:
            _repoe = fluxo_gep.get('repoe_compra_desmama')
            story.append(Paragraph(
                f"<b>Suposição — compra de desmama:</b> a coorte de 0–12 meses "
                f"excede a produção própria em <b>{_cd} animais</b>, que só podem "
                f"ter sido comprados. "
                + (f"A projeção MANTÉM essa compra todo ano "
                   f"({_fmt_moeda(fluxo_gep.get('custo_compra_desmama'))} no ano 1), "
                   f"preservando a estrutura do rebanho."
                   if _repoe else
                   "A projeção assume que o produtor DEIXA de comprar: não há custo "
                   "de aquisição, mas o rebanho converge para a produção própria — "
                   "e é isso que explica a variação de estoque negativa.")
                + " As duas leituras são legítimas e dão pareceres diferentes.",
                ss['Corpo']))

    # ── Praça de referência dos preços ───────────────────────────────────────
    # Sem isto o parecer não diz sobre qual preço os números foram feitos, e
    # quem lê não tem como conferir nada que dependa de cotação.
    reg = parecer.get('precos_regional')
    if reg:
        story.append(Paragraph('Praça de Referência dos Preços', ss['SecaoTitulo']))
        if reg.get('ajustado'):
            linhas_p = [['Categoria', 'Indicador nacional', f"Praça {reg.get('uf')}"]]
            for c in reg.get('categorias', []):
                linhas_p.append([
                    c['categoria'].replace('preco_', '').capitalize(),
                    _fmt_moeda(c['nacional']),
                    _fmt_moeda(c['regional']),
                ])
            tp = Table(linhas_p, colWidths=[6*cm, 5*cm, 5*cm])
            tp.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#EEEEEE')),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#DDDDDD')),
                ('FONTSIZE', (0, 0), (-1, -1), 8.5),
                ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
            ]))
            story.append(tp)
            story.append(Spacer(1, 4))
        story.append(Paragraph(reg.get('resumo', ''), ss['Corpo']))
        story.append(Paragraph(
            f"<i>Origem: {reg.get('origem', '')}. O indicador CEPEA/ESALQ é "
            f"praça de {reg.get('uf_referencia', 'SP')}; o diferencial regional "
            f"aqui aplicado é calibração de referência, a ser recalibrada com "
            f"série própria.</i>", ss['Subtitulo']))
        story.append(Spacer(1, 6))

    # ── Garantia: valor de execução, não valor de mercado ────────────────────
    garantia = parecer.get('garantia')
    if garantia and garantia.get('valor_mercado', 0) > 0:
        story.append(Paragraph('Garantia — Valor de Execução', ss['SecaoTitulo']))
        linhas_g = [['Categoria', 'Valor de mercado', 'Deságio', 'Valor de execução']]
        for linha in garantia.get('composicao', []):
            linhas_g.append([
                linha['rotulo'],
                _fmt_moeda(linha['valor_mercado']),
                f"{linha['desagio_pct']:.0f}%".replace('.', ','),
                _fmt_moeda(linha['valor_garantia']),
            ])
        linhas_g.append([
            'Total',
            _fmt_moeda(garantia.get('valor_mercado')),
            f"{garantia.get('desagio_medio_pct', 0):.1f}%".replace('.', ','),
            _fmt_moeda(garantia.get('valor_garantia')),
        ])
        tg = Table(linhas_g, colWidths=[6*cm, 4*cm, 2.2*cm, 4*cm])
        tg.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#EEEEEE')),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#DDDDDD')),
            ('FONTSIZE', (0, 0), (-1, -1), 8.5),
            ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
            ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#E8F5E9')),
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ]))
        story.append(tg)
        story.append(Spacer(1, 4))
        if garantia.get('ltv') is not None:
            _cor_ltv = {'suficiente': '#2E7D32', 'ajustada': '#F9A825',
                        'insuficiente': '#C62828'}.get(garantia.get('veredito'), '#333333')
            story.append(Paragraph(
                f"<b>LTV {garantia['ltv']:.1f}%</b> sobre o valor de execução — "
                f"<font color='{_cor_ltv}'><b>{(garantia.get('veredito') or '').upper()}</b></font>. "
                f"Crédito máximo pela garantia: {_fmt_moeda(garantia.get('credito_maximo_garantia'))}.",
                ss['Corpo']))
        story.append(Paragraph(
            '<i>Rebanho em penhor não se realiza pela cotação do dia: entre a '
            'inadimplência e o caixa há apreensão, transporte, risco sanitário e '
            'venda forçada. O deságio por categoria reflete quão rápido cada uma '
            'vira dinheiro.</i>', ss['Subtitulo']))
        story.append(Spacer(1, 6))

    # ── Endividamento total ──────────────────────────────────────────────────
    endiv = parecer.get('endividamento')
    if endiv and (endiv.get('itens') or endiv.get('alerta') is None):
        story.append(Paragraph('Endividamento do Proponente', ss['SecaoTitulo']))
        if endiv.get('itens'):
            linhas_e = [['Credor', 'Saldo devedor', 'Parcela mensal']]
            for it in endiv['itens']:
                linhas_e.append([
                    it['instituicao'],
                    _fmt_moeda(it['saldo_devedor']) if it['saldo_devedor'] else '—',
                    _fmt_moeda(it['parcela_mensal']),
                ])
            linhas_e.append(['Total existente',
                             _fmt_moeda(endiv.get('saldo_devedor_total')) if endiv.get('saldo_devedor_total') else '—',
                             _fmt_moeda(endiv.get('parcela_existente_mensal'))])
            if endiv.get('parcela_nova_mensal', 0) > 0:
                linhas_e.append(['(+) Crédito em análise', '—',
                                 _fmt_moeda(endiv['parcela_nova_mensal'])])
                linhas_e.append(['(=) Serviço total mensal', '—',
                                 _fmt_moeda(endiv.get('parcela_total_mensal'))])
            te = Table(linhas_e, colWidths=[7.2*cm, 4.4*cm, 4.4*cm])
            te.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#EEEEEE')),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#DDDDDD')),
                ('FONTSIZE', (0, 0), (-1, -1), 8.5),
                ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
                ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#E8F5E9')),
                ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
            ]))
            story.append(te)
            story.append(Spacer(1, 4))
        _cor_e = '#C62828' if endiv.get('alerta') == 'critico' else '#333333'
        story.append(Paragraph(
            f"<font color='{_cor_e}'>{endiv.get('justificativa', '')}</font>",
            ss['Subtitulo']))
        story.append(Paragraph(
            f"<i>Origem: {endiv.get('origem', 'declarado')}. Endividamento "
            f"declarado pelo proponente não substitui consulta ao SCR do Banco "
            f"Central.</i>", ss['Subtitulo']))
        story.append(Spacer(1, 6))

    sensibilidade = parecer.get('sensibilidade') or []
    if sensibilidade:
        story.append(Paragraph('Sensibilidade de Preço', ss['SecaoTitulo']))
        _SLBL = {'aprovar': 'APROVAR', 'ressalva': 'RESSALVA', 'negar': 'NEGAR'}
        linhas_s = [['Cenário', 'Preço R$/@', 'Geração de Caixa', 'DSCR', 'Resultado']]
        for s in sensibilidade:
            vp = s.get('variacao_pct', 0)
            prefix = f'+{vp}%' if vp > 0 else f'{vp}%'
            linhas_s.append([
                prefix,
                _fmt_moeda(s.get('preco_boi')),
                _fmt_moeda(s.get('geracao_caixa')),
                str(s.get('dscr') or '—'),
                _SLBL.get(s.get('recomendacao'), '—'),
            ])
        ts = Table(linhas_s, colWidths=[2.5*cm, 3.5*cm, 4*cm, 2*cm, 4*cm])
        _base_idx = next((i+1 for i, s in enumerate(sensibilidade) if s.get('variacao_pct', 0) == 0), None)
        _s_style = [
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#EEEEEE')),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#DDDDDD')),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
        ]
        if _base_idx:
            _s_style.append(('BACKGROUND', (0, _base_idx), (-1, _base_idx), colors.HexColor('#F5F5F5')))
            _s_style.append(('FONTNAME', (0, _base_idx), (-1, _base_idx), 'Helvetica-Bold'))
        ts.setStyle(TableStyle(_s_style))
        story.append(ts)
        story.append(Spacer(1, 4))

    shap = parecer.get('shap_explicacao') or {}
    fatores = shap.get('fatores') or []
    if fatores:
        story.append(Paragraph('Explicabilidade da Classificação (SHAP)', ss['SecaoTitulo']))
        story.append(Paragraph(
            f"Classe classificada: <b>{shap.get('classe', '—')}</b> · "
            f"{shap.get('metodo', '')}",
            ss['Subtitulo']))
        story.append(Spacer(1, 4))
        linhas_shap = [['Característica do Rebanho', 'Contribuição', 'Impacto']]
        for f in fatores:
            sinal = '▲' if f.get('direcao') == 'positivo' else '▼'
            cor_txt = '+' if f.get('direcao') == 'positivo' else '−'
            linhas_shap.append([
                f.get('feature', '—'),
                f"{cor_txt}{abs(f.get('shap', 0)):.4f}",
                f"{sinal} {f.get('importancia_pct', 0):.1f}%",
            ])
        ts = Table(linhas_shap, colWidths=[9*cm, 3.5*cm, 3.5*cm])
        _shap_style = [
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#EEEEEE')),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#DDDDDD')),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
        ]
        for i, f in enumerate(fatores, start=1):
            bg = colors.HexColor('#E8F5E9') if f.get('direcao') == 'positivo' else colors.HexColor('#FFEBEE')
            _shap_style.append(('BACKGROUND', (0, i), (-1, i), bg))
        ts.setStyle(TableStyle(_shap_style))
        story.append(ts)
        story.append(Spacer(1, 4))
        story.append(Paragraph(
            f'<i>Conformidade: {shap.get("conformidade", "")}. '
            'Valores positivos aumentam e negativos reduzem a probabilidade da classe.</i>',
            ss['Subtitulo']))

    conclusao = parecer.get('conclusao') or {}
    # ── Proveniência dos parâmetros ──────────────────────────────────────────
    prov = parecer.get('proveniencia') or {}
    _params = prov.get('parametros') or []
    if _params:
        res = prov.get('resumo') or {}
        cont = res.get('contagem') or {}
        story.append(Paragraph('Origem dos Parâmetros', ss['SecaoTitulo']))
        story.append(Paragraph(
            f"{res.get('total', 0)} parâmetros sustentam este parecer: "
            f"<b>{cont.get('medido', 0)} medidos</b>, "
            f"{cont.get('referencia', 0)} de referência, "
            f"{cont.get('politica', 0)} de política e "
            f"{cont.get('declarado', 0)} declarados.", ss['Corpo']))
        linhas_pv = [['Parâmetro', 'Valor', 'Origem', 'Fonte']]
        for d in _params:
            linhas_pv.append([
                d['rotulo'] or '—',
                f"{d['valor']:g}",
                d['origem_rotulo'],
                d['fonte'] or '—',
            ])
        tpv = Table(linhas_pv, colWidths=[5.4*cm, 1.8*cm, 2.2*cm, 6.6*cm],
                    repeatRows=1)
        tpv.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#EEEEEE')),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#DDDDDD')),
            ('FONTSIZE', (0, 0), (-1, -1), 7.5),
            ('ALIGN', (1, 1), (1, -1), 'RIGHT'),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ]))
        story.append(tpv)
        story.append(Spacer(1, 4))
        story.append(Paragraph(
            '<i>Medição se cita — série apurada por terceiro. Política se discute '
            '— é escolha da instituição, não descreve fato. Referência se '
            'questiona — calibração de bibliografia, não apurada nesta fazenda. '
            'Declaração se confere — informada, não verificada.</i>',
            ss['Subtitulo']))
        story.append(Spacer(1, 6))

    story.append(Paragraph('Conclusão — Capacidade de Pagamento', ss['SecaoTitulo']))
    rec = conclusao.get('recomendacao')
    if rec:
        cor = _COR_RECOMENDACAO.get(rec, colors.grey)
        label = _LABEL_RECOMENDACAO.get(rec, rec.upper())
        t = Table([[Paragraph(f"<b>{label}</b>", ParagraphStyle('r', parent=ss['Corpo'], textColor=colors.white, fontSize=12))]],
                  colWidths=[16*cm])
        t.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), cor),
                               ('TOPPADDING', (0, 0), (-1, -1), 8),
                               ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                               ('LEFTPADDING', (0, 0), (-1, -1), 10)]))
        story.append(t)
        story.append(Spacer(1, 6))
        # O DSCR do ano 1 sozinho engana: o primeiro ano liquida o estoque de
        # animais prontos declarado na ficha. O documento que vai ao comitê
        # precisa mostrar o ano crítico, que é o que define a recomendação.
        _dmin = conclusao.get('dscr_minimo')
        _dano1 = conclusao.get('dscr_ano1', conclusao.get('dscr'))
        if _dmin is not None and _dmin != _dano1:
            story.append(Paragraph(
                f"DSCR no ano crítico (ano {conclusao.get('ano_critico')}): <b>{_dmin}</b> "
                f"· no ano 1: {_dano1} · Parcela mensal: "
                f"{_fmt_moeda(conclusao.get('parcela_mensal'))}", ss['Corpo']))
        else:
            story.append(Paragraph(
                f"DSCR: {conclusao.get('dscr')} · Parcela mensal: "
                f"{_fmt_moeda(conclusao.get('parcela_mensal'))}", ss['Corpo']))
        if conclusao.get('capacidade_maxima', 0) > 0:
            story.append(Paragraph(
                f"Crédito máximo (DSCR ≥ 1,30): <b>{_fmt_moeda(conclusao.get('capacidade_maxima'))}</b>",
                ss['Corpo']))
        story.append(Paragraph(conclusao.get('justificativa', ''), ss['Corpo']))

        # Memória de cálculo — o comitê precisa auditar o raciocínio, não só
        # receber o veredicto. Exigência prática sob CMN 4.966/2021.
        memoria = conclusao.get('memoria') or []
        if memoria:
            story.append(Spacer(1, 8))
            story.append(Paragraph('Memória de cálculo', ss['SecaoTitulo']))
            linhas_m = [['#', 'Passo', 'Valor', 'Justificativa']]
            for i, m in enumerate(memoria, 1):
                linhas_m.append([
                    str(i),
                    Paragraph(f"<b>{m.get('passo','')}</b>", ss['Corpo']),
                    Paragraph(str(m.get('valor', '')), ss['Corpo']),
                    Paragraph(m.get('detalhe', ''), ss['Corpo']),
                ])
            tm = Table(linhas_m, colWidths=[0.8*cm, 4.2*cm, 3.4*cm, 7.6*cm])
            tm.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1E2535')),
                ('TEXTCOLOR',  (0, 0), (-1, 0), colors.white),
                ('FONTSIZE',   (0, 0), (-1, -1), 7),
                ('VALIGN',     (0, 0), (-1, -1), 'TOP'),
                ('GRID',       (0, 0), (-1, -1), 0.25, colors.HexColor('#CCCCCC')),
                ('TOPPADDING', (0, 0), (-1, -1), 4),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ]))
            story.append(tm)
    else:
        story.append(Paragraph(
            conclusao.get('justificativa') or 'Sem solicitação de crédito informada.', ss['Corpo']))

    doc.build(story)
    return buf.getvalue()

