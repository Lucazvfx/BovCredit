"""Gerador de PDF de alta fidelidade para o Dossiê Executivo do Comitê de Crédito B2B."""
from __future__ import annotations

import io
from datetime import datetime
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from services.dossie_comite.models import DossieComite
from services.parecer_pdf import _fmt_moeda, _logo_flowable, _styles

_COR_PRIMARIA = colors.HexColor('#1E3A2F')
_COR_SECUNDARIA = colors.HexColor('#2D5A46')
_COR_BEGE = colors.HexColor('#F3EFE6')
_COR_BORDA = colors.HexColor('#D8C9B3')
_COR_DESTAQUE = colors.HexColor('#8C7355')
_COR_TEXTO = colors.HexColor('#203127')
_COR_SUAVE = colors.HexColor('#555555')


def _numero(valor: Any, casas: int = 0) -> str:
    try:
        texto = f"{float(valor):,.{casas}f}"
    except (TypeError, ValueError):
        return '—'
    return texto.replace(',', '_').replace('.', ',').replace('_', '.')


def _secao(story: list, ss: dict, titulo: str) -> None:
    story.append(Paragraph(titulo, ss['SecaoTitulo']))
    story.append(HRFlowable(width='100%', thickness=0.6, color=_COR_BORDA))
    story.append(Spacer(1, 4))


def _tabela(story: list, dados: list[list], larguras: list[float], header_bg: str = '#E8DCC7') -> None:
    estilo = TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor(header_bg)),
        ('TEXTCOLOR', (0, 0), (-1, -1), _COR_TEXTO),
        ('GRID', (0, 0), (-1, -1), 0.35, _COR_BORDA),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 7.5),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ])
    tab = Table(dados, colWidths=larguras, style=estilo)
    story.append(tab)
    story.append(Spacer(1, 6))


def gerar_pdf_dossie_comite(dossie: DossieComite | dict[str, Any], branding: dict | None = None) -> bytes:
    """Gera o documento PDF do Dossiê do Comitê de Crédito."""
    if isinstance(dossie, DossieComite):
        d = dossie.to_dict()
    else:
        d = dossie

    proponente = d.get('proponente') or {}
    operacao = d.get('operacao') or {}
    atividades = d.get('atividades') or {}
    esg = d.get('esg') or {}
    garantias = d.get('garantias') or {}
    financeiro = d.get('financeiro') or {}
    deliberacao = d.get('deliberacao') or {}

    branding = branding or {}
    nome_consultoria = (branding.get('nome_consultoria') or '').strip()

    ss = _styles()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        topMargin=1.5 * cm,
        bottomMargin=1.5 * cm,
        leftMargin=1.5 * cm,
        rightMargin=1.5 * cm,
    )
    story: list = []

    # 1. Logotipo e Cabeçalho Superior
    logo = _logo_flowable(branding.get('logo_base64') or '')
    if logo is not None:
        story.append(logo)
        story.append(Spacer(1, 4))

    cod_dossie = deliberacao.get('codigo_dossie') or operacao.get('codigo_operacao') or 'ORK-COM-2026-0001'
    titulo = (f"{nome_consultoria} — Dossiê de Crédito B2B"
              if nome_consultoria else
              'Dossiê Executivo de Crédito — Comitê de Deliberação')
    story.append(Paragraph(titulo, ss['Titulo']))

    subtitulo_texto = (
        f"<b>Operação:</b> {cod_dossie} · <b>Proponente:</b> {proponente.get('nome')} "
        f"({proponente.get('cpf_cnpj')}) · <b>Fazenda:</b> {proponente.get('fazenda')} "
        f"({proponente.get('municipio')}/{proponente.get('uf')}) · <b>Emissão:</b> {deliberacao.get('data_emissao')}"
    )
    story.append(Paragraph(subtitulo_texto, ss['Subtitulo']))
    story.append(Spacer(1, 6))

    # 2. Fact Sheet Teaser Matrix
    rating_val = str(deliberacao.get('rating_final') or 'A1')
    recom_val = str(deliberacao.get('recomendacao') or 'FAVORAVEL').replace('_', ' ')
    dscr_med = f"{_numero(financeiro.get('dscr_medio'), 2)}x"
    ltv_val = f"{_numero(garantias.get('ltv_liquidacao_forcada_pct'), 1)}%"
    esg_status = str(esg.get('parecer_compliance') or 'APROVADO')

    cor_recom = '#1E3A2F'
    if 'DESFAVORAVEL' in recom_val:
        cor_recom = '#B3261E'
    elif 'RESSALVA' in recom_val:
        cor_recom = '#B26B00'

    teaser_dados = [
        ['RATING GLOBAL', 'RECOMENDAÇÃO TÉCNICA', 'DSCR MÉDIO', 'LTV LIQUIDAÇÃO', 'STATUS ESG'],
        [rating_val, recom_val, dscr_med, ltv_val, esg_status]
    ]
    tab_teaser = Table(teaser_dados, colWidths=[3.6 * cm, 3.8 * cm, 3.5 * cm, 3.5 * cm, 3.6 * cm])
    tab_teaser.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), _COR_BEGE),
        ('BACKGROUND', (0, 1), (-1, 1), colors.HexColor('#FFFFFF')),
        ('TEXTCOLOR', (0, 0), (-1, 0), _COR_SUAVE),
        ('TEXTCOLOR', (0, 1), (0, 1), _COR_PRIMARIA),
        ('TEXTCOLOR', (1, 1), (1, 1), colors.HexColor(cor_recom)),
        ('TEXTCOLOR', (2, 1), (-1, 1), _COR_PRIMARIA),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 7),
        ('FONTSIZE', (0, 1), (-1, 1), 9.5),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.5, _COR_BORDA),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    story.append(tab_teaser)
    story.append(Spacer(1, 8))

    # 3. Seção: Dados da Operação & Proponente
    _secao(story, ss, '1. Características da Operação de Crédito & Proponente')
    dados_op = [
        ['Valor Solicitado', _fmt_moeda(operacao.get('valor_solicitado') or 0.0),
         'Finalidade', operacao.get('finalidade') or 'Custeio Agropecuário'],
        ['Prazo da Operação', f"{operacao.get('prazo_meses')} meses",
         'Carência', f"{operacao.get('carencia_meses')} meses"],
        ['Taxa de Juros', f"{_numero(operacao.get('juros_aa'), 2)}% a.a.",
         'Amortização / Fluxo', f"{operacao.get('sistema_amortizacao')} / {operacao.get('periodicidade')}"],
        ['Área Total Propriedade', f"{_numero(proponente.get('area_total_ha'), 1)} ha",
         'Localização', f"{proponente.get('fazenda')} — {proponente.get('municipio')}/{proponente.get('uf')}"]
    ]
    _tabela(story, dados_op, [3.8 * cm, 4.8 * cm, 4.2 * cm, 5.2 * cm])

    # 4. Seção: Atividades Produtivas
    _secao(story, ss, '2. Atividades Agropecuárias & Base Produtiva')
    resumo_ativ_txt = atividades.get('resumo_texto') or 'Atividades produtivas da propriedade'
    story.append(Paragraph(f"<b>Diagnóstico de Produção:</b> {resumo_ativ_txt}", ss['Subtitulo']))
    story.append(Spacer(1, 3))

    dados_ativ = [
        ['Segmento', 'Dimensão / Efetivo', 'Parâmetro Chave', 'Receita Anual Estimada'],
    ]
    if atividades.get('tem_pecuaria'):
        dados_ativ.append([
            'Pecuária de Corte/Leite',
            f"{_numero(atividades.get('rebanho_total_cabecas'))} cabeças ({_numero(atividades.get('rebanho_uas'), 1)} UA)",
            f"Desfrute: {_numero(atividades.get('taxa_desfrute_pct'), 1)}%",
            _fmt_moeda(atividades.get('receita_pecuaria_anual') or 0.0)
        ])
    if atividades.get('tem_agricola'):
        cults_txt = ", ".join(atividades.get('culturas_principais') or []) or 'Grãos'
        dados_ativ.append([
            f"Agrícola ({cults_txt})",
            f"{_numero(atividades.get('area_plantada_ha'), 1)} ha cultivados",
            f"Produtiv: {_numero(atividades.get('produtividade_media_sc_ha'), 1)} sc/ha (BE: {_numero(atividades.get('breakeven_medio_sc_ha'), 1)})",
            _fmt_moeda(atividades.get('receita_agricola_anual') or 0.0)
        ])
    if len(dados_ativ) == 1:
        dados_ativ.append([
            'Agropecuária Integrada', 'Área total informada', 'Atividade consolidada',
            _fmt_moeda(financeiro.get('receita_bruta_anual') or 0.0)
        ])
    _tabela(story, dados_ativ, [4.5 * cm, 4.5 * cm, 4.5 * cm, 4.5 * cm])

    # 5. Seção: Diagnóstico Socioambiental (ESG - CMN 5.081/23 e MCR 2-1)
    _secao(story, ss, '3. Conformidade Socioambiental & CAR (CMN 5.081/23 e MCR 2-1)')
    dados_esg = [
        ['Inscrição SICAR (CAR)', esg.get('numero_car') or '—', 'Status no SICAR', esg.get('status_car') or 'ATIVO'],
        ['Bioma Referência', esg.get('bioma') or 'CERRADO', 'Reserva Legal (RL)', f"{_numero(esg.get('reserva_legal_ha'), 1)} ha ({_numero(esg.get('reserva_legal_pct'), 1)}% vs mín {_numero(esg.get('exigencia_reserva_legal_pct'), 0)}%)"],
        ['Área de Preservação (APP)', f"{_numero(esg.get('app_ha'), 1)} ha", 'Embargos IBAMA/ICMBio', f"{esg.get('status_ibama')} / {esg.get('status_icmbio')}"],
        ['Sobreposição Indígena/Quilombola', 'NÃO' if not esg.get('sobreposicao_indigena_quilombola') else 'SIM (IMPEDITIVO)', 'Parecer de Compliance', esg.get('parecer_compliance') or 'APROVADO']
    ]
    _tabela(story, dados_esg, [4.5 * cm, 4.5 * cm, 4.5 * cm, 4.5 * cm])
    for obs in (esg.get('observacoes') or [])[:2]:
        story.append(Paragraph(f"• <i>{obs}</i>", ss['Subtitulo']))
    story.append(Spacer(1, 4))

    # 6. Seção: Matriz de Garantias & LTV
    _secao(story, ss, '4. Matriz de Garantias, Deságios e Cobertura de LTV')
    itens_gar = garantias.get('detalhes_itens') or []
    dados_gar = [
        ['Garantia / Descrição', 'Tipo Gravame', 'Valor Mercado', 'Deságio Execução', 'Valor Liq. Forçada']
    ]
    for g in itens_gar[:5]:
        dados_gar.append([
            str(g.get('descricao') or g.get('tipo'))[:35],
            str(g.get('gravame') or 'ALIENACAO_FIDUCIARIA').replace('_', ' ')[:22],
            _fmt_moeda(g.get('valor_mercado_bruto') or 0.0),
            f"{_numero(g.get('desagio_aplicado_pct'), 0)}%",
            _fmt_moeda(g.get('valor_liquidacao_forcada') or 0.0)
        ])
    if len(dados_gar) == 1:
        dados_gar.append([
            'Garantia Real Imobiliária / Penhor', 'Alienação Fiduciária',
            _fmt_moeda(garantias.get('valor_mercado_total') or 0.0),
            '25%',
            _fmt_moeda(garantias.get('valor_liquidacao_forcada_total') or 0.0)
        ])
    # Linha totalizadora
    dados_gar.append([
        f"<b>TOTAL ({garantias.get('total_bens')} bens)</b>",
        f"<b>LTV Mercado: {_numero(garantias.get('ltv_mercado_pct'), 1)}%</b>",
        f"<b>{_fmt_moeda(garantias.get('valor_mercado_total') or 0.0)}</b>",
        f"<b>LTV Liq: {_numero(garantias.get('ltv_liquidacao_forcada_pct'), 1)}%</b>",
        f"<b>{_fmt_moeda(garantias.get('valor_liquidacao_forcada_total') or 0.0)}</b>"
    ])
    _tabela(story, dados_gar, [5.2 * cm, 3.8 * cm, 3.0 * cm, 2.8 * cm, 3.2 * cm])

    # 7. Seção: Fluxo de Caixa Consolidado & DSCR
    _secao(story, ss, '5. Projeção de Fluxo de Caixa Livre & Capacidade de Pagamento')
    dados_fluxo = [
        ['Ano', 'Receita Bruta', 'Custos / Despesas', 'EBITDA Operacional', 'Serviço Dívida', 'Caixa Livre', 'DSCR']
    ]
    for l in (financeiro.get('projecao_plurianual') or []):
        dados_fluxo.append([
            f"Ano {l.get('ano')}",
            _fmt_moeda(l.get('receita_bruta') or 0.0),
            _fmt_moeda(l.get('custos_despesas') or 0.0),
            _fmt_moeda(l.get('ebitda') or 0.0),
            _fmt_moeda(l.get('servico_divida') or 0.0),
            _fmt_moeda(l.get('fluxo_caixa_livre') or 0.0),
            f"{_numero(l.get('dscr'), 2)}x"
        ])
    _tabela(story, dados_fluxo, [1.8 * cm, 2.8 * cm, 2.8 * cm, 2.8 * cm, 2.7 * cm, 2.7 * cm, 2.4 * cm])
    
    txt_resumo_fin = (
        f"<b>EBITDA Anual Base:</b> {_fmt_moeda(financeiro.get('ebitda_anual') or 0.0)} "
        f"(Margem {_numero(financeiro.get('margem_ebitda_pct'), 1)}%) · "
        f"<b>DSCR Mínimo:</b> {_numero(financeiro.get('dscr_minimo'), 2)}x (Ano {financeiro.get('ano_critico')}) · "
        f"<b>DSCR Médio:</b> {_numero(financeiro.get('dscr_medio'), 2)}x"
    )
    story.append(Paragraph(txt_resumo_fin, ss['Subtitulo']))
    story.append(Spacer(1, 6))

    # 8. Seção: Covenants Obrigatórios
    _secao(story, ss, '6. Covenants e Condicionantes Contratuais para o Financiamento')
    for cov in deliberacao.get('covenants_obrigatorios') or []:
        story.append(Paragraph(f"• <b>Covenant:</b> {cov}", ss['Corpo']))
    story.append(Spacer(1, 8))

    # 9. Seção: Quadro de Deliberação e Assinaturas (KeepTogether para evitar quebra no final)
    assinaturas_bloco = []
    assinaturas_bloco.append(Paragraph('7. Homologação Final do Comitê de Crédito B2B', ss['SecaoTitulo']))
    assinaturas_bloco.append(HRFlowable(width='100%', thickness=0.6, color=_COR_BORDA))
    assinaturas_bloco.append(Spacer(1, 6))

    parecer_risco = deliberacao.get('parecer_risco_tecnico') or 'Análise técnica favorável.'
    parecer_ger = deliberacao.get('parecer_gerencia_b2b') or 'De acordo com a alçada proposta.'
    parecer_dir = deliberacao.get('parecer_diretoria') or 'Homologado pelo Comitê.'

    col1 = Paragraph(
        f"_______________________________<br/><b>Analista de Risco & Agronomia</b><br/>"
        f"<font size=6 color='#555555'>{parecer_risco}</font>",
        ss['Subtitulo']
    )
    col2 = Paragraph(
        f"_______________________________<br/><b>Gerente de Crédito B2B</b><br/>"
        f"<font size=6 color='#555555'>{parecer_ger}</font>",
        ss['Subtitulo']
    )
    col3 = Paragraph(
        f"_______________________________<br/><b>Diretor / Comitê de Crédito</b><br/>"
        f"<font size=6 color='#555555'>{parecer_dir}</font>",
        ss['Subtitulo']
    )

    tab_ass = Table([[col1, col2, col3]], colWidths=[6.0 * cm, 6.0 * cm, 6.0 * cm])
    tab_ass.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    assinaturas_bloco.append(tab_ass)
    assinaturas_bloco.append(Spacer(1, 10))

    hash_full = deliberacao.get('hash_sha256') or ''
    assinaturas_bloco.append(HRFlowable(width='100%', thickness=0.4, color=_COR_BORDA))
    assinaturas_bloco.append(Spacer(1, 3))
    texto_seguranca = (
        f"<b>INTEGRIDADE DO DOSSIÊ DIGITAL:</b> Identificador <b>{cod_dossie}</b> · "
        f"Hash Criptográfico SHA-256: <font name='Courier' size=6>{hash_full}</font><br/>"
        f"Dossiê auditável gerado pelo motor de inteligência de crédito Orkavyn. "
        f"Validação: <u>https://credito.orkavyn.tech/</u>"
    )
    assinaturas_bloco.append(Paragraph(texto_seguranca, ss['Subtitulo']))

    story.append(KeepTogether(assinaturas_bloco))

    doc.build(story)
    return buf.getvalue()
