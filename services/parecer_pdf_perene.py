"""PDF do parecer de lavoura perene.

Não é o parecer pecuário com outro título. O documento fala de talhão, idade e
estágio no lugar de rebanho, faixa etária e desfrute, e traz duas seções que só
existem aqui: a curva de produtividade que sustenta a projeção, com a fonte de
cada uma, e o ano crítico do contrato explicado pelo fenômeno agronômico que o
causa — carga baixa do café ou reforma do canavial.

Reaproveita estilo, moeda e logo de `parecer_pdf`: o documento tem de sair com
a mesma cara do parecer pecuário.
"""
from __future__ import annotations

import io
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.platypus import (
    HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

from services.parecer_pdf import _fmt_moeda, _logo_flowable, _styles

_ESTAGIO = {
    'formacao': 'Formação',
    'producao': 'Produção',
    'reforma': 'Reforma',
    'nao_plantado': 'Não plantado',
}

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
    story.append(HRFlowable(width='100%', thickness=0.6,
                            color=colors.HexColor('#D8C9B3')))
    story.append(Spacer(1, 5))


def _tabela(story, dados: list[list], larguras: list[float]) -> None:
    tabela = Table(dados, colWidths=larguras, repeatRows=1)
    tabela.setStyle(_CABECALHO)
    story.append(tabela)


def _identificacao(story, ss, analise: dict, ident: dict, nome_consultoria: str) -> None:
    titulo = (f'{nome_consultoria} — Parecer de Crédito Agrícola'
              if nome_consultoria else
              'Parecer de Crédito Agrícola — Lavoura Perene')
    story.append(Paragraph(titulo, ss['Titulo']))
    story.append(Paragraph(
        f"{ident.get('fazenda') or '—'} · {ident.get('municipio') or '—'} · "
        f"{ident.get('proprietario') or '—'} — emitido em "
        f"{datetime.now().strftime('%d/%m/%Y')}", ss['Subtitulo']))
    story.append(Spacer(1, 5))
    story.append(Paragraph(
        '<b>Natureza da análise:</b> pré-análise técnico-financeira de apoio à '
        'consultoria. A produção projetada depende da curva de produtividade '
        'declarada para cada cultura e da idade informada de cada talhão — não '
        'de medição em campo. Este documento não substitui a conferência '
        'documental, a visita à propriedade ou a decisão do agente de crédito.',
        ss['Subtitulo']))
    story.append(Spacer(1, 10))


def _composicao(story, ss, analise: dict) -> None:
    producao = analise.get('producao') or {}
    anos = producao.get('anos') or []
    if not anos:
        return
    _secao(story, ss, 'Composição da lavoura')

    dados = [['Talhão', 'Cultura', 'Área (ha)', 'Idade', 'Estágio', 'Carga']]
    for talhao in anos[0].get('talhoes') or []:
        dados.append([
            talhao.get('talhao') or '—',
            talhao.get('cultura') or '—',
            _numero(talhao.get('area_ha'), 2),
            str(talhao.get('idade') or '—'),
            _ESTAGIO.get(talhao.get('estagio'), talhao.get('estagio') or '—'),
            (talhao.get('fase_bienal') or '—').capitalize(),
        ])
    _tabela(story, dados, [3.2 * cm, 2.6 * cm, 2.4 * cm, 1.8 * cm, 3.0 * cm, 2.0 * cm])

    story.append(Spacer(1, 6))
    story.append(Paragraph(
        f"Área total: <b>{_numero(producao.get('area_total_ha'), 2)} ha</b> · "
        f"em produção no primeiro ano: "
        f"<b>{_numero(anos[0].get('area_produtiva_ha'), 2)} ha</b> · "
        f"em formação ou reforma: "
        f"<b>{_numero(anos[0].get('area_em_formacao_ha'), 2)} ha</b>",
        ss['Corpo']))


def _curvas(story, ss, analise: dict) -> None:
    curvas = analise.get('curvas') or {}
    if not curvas:
        return
    _secao(story, ss, 'Curva de produtividade e origem do dado')

    dados = [['Cultura', 'Plena', 'Unidade', 'Bienalidade', 'Ciclo', 'Fonte']]
    sem_fonte = []
    for cultura, curva in sorted(curvas.items()):
        fonte = (curva.get('fonte') or '').strip()
        if not fonte:
            sem_fonte.append(cultura)
        bienalidade = curva.get('bienalidade') or 0
        dados.append([
            cultura,
            _numero(curva.get('produtividade_plena'), 1),
            curva.get('unidade') or '—',
            f'±{_numero(float(bienalidade) * 100, 0)}%' if bienalidade else '—',
            f"{curva.get('ciclo_anos')} anos" if curva.get('ciclo_anos') else '—',
            fonte or 'Declarada pelo analista',
        ])
    _tabela(story, dados, [2.4 * cm, 1.8 * cm, 2.2 * cm, 2.2 * cm, 1.9 * cm, 4.5 * cm])

    story.append(Spacer(1, 6))
    if sem_fonte:
        story.append(Paragraph(
            '<b>Ressalva:</b> a curva de '
            f"{', '.join(sorted(sem_fonte))} não tem fonte declarada. Ela é "
            'declaração do analista e não foi apurada nesta lavoura — toda a '
            'projeção de produção depende dela.', ss['Corpo']))


def _projecao(story, ss, analise: dict) -> None:
    linhas = (analise.get('economico') or {}).get('anos') or []
    if not linhas:
        return
    _secao(story, ss, 'Produção e resultado projetados')

    unidades = (analise.get('producao') or {}).get('unidades') or {}
    unidade = ', '.join(sorted(set(unidades.values()))) or 'unidade'
    dados = [['Ano', 'Safra', f'Produção ({unidade})', 'Receita', 'Custo', 'Resultado']]
    for linha in linhas:
        dados.append([
            str(linha.get('ano')),
            str(linha.get('ano_calendario')),
            _numero(linha.get('producao_total'), 0),
            _fmt_moeda(linha.get('receita')),
            _fmt_moeda(linha.get('custo')),
            _fmt_moeda(linha.get('resultado')),
        ])
    _tabela(story, dados, [1.2 * cm, 1.6 * cm, 3.2 * cm, 3.3 * cm, 3.0 * cm, 3.3 * cm])

    negativos = (analise.get('economico') or {}).get('anos_negativos') or ()
    if negativos:
        story.append(Spacer(1, 6))
        story.append(Paragraph(
            'Resultado operacional negativo no(s) ano(s) '
            f"{', '.join(str(n) for n in negativos)}. Em lavoura perene isso é "
            'o comportamento esperado do talhão em formação, que consome caixa '
            'antes de produzir — e é o período que a carência precisa cobrir.',
            ss['Corpo']))


def _capacidade(story, ss, analise: dict) -> None:
    credito = (analise.get('credito') or {}).get('analysis') or {}
    if not credito:
        return
    _secao(story, ss, 'Capacidade de pagamento')

    pior = credito.get('pior_periodo') or {}
    resumo = [
        ['DSCR médio do prazo', _numero(credito.get('dscr_medio'), 2)],
        ['DSCR mínimo', _numero(credito.get('dscr_minimo'), 2)],
        ['Ano mais apertado', str(pior.get('ano') or '—')],
        ['Serviço da dívida no ano crítico', _fmt_moeda(pior.get('servico_divida_anual'))],
        ['Capacidade máxima estimada', _fmt_moeda(credito.get('capacidade_maxima_estimativa'))],
    ]
    tabela = Table(resumo, colWidths=[7.0 * cm, 8.6 * cm])
    tabela.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#E8DCC7')),
        ('BACKGROUND', (1, 0), (1, -1), colors.HexColor('#F6F0E6')),
        ('GRID', (0, 0), (-1, -1), 0.35, colors.HexColor('#D8C9B3')),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))
    story.append(tabela)

    if pior.get('ano') and int(pior['ano']) > 1:
        story.append(Spacer(1, 6))
        story.append(Paragraph(
            f"<b>O ano mais apertado do contrato é o {int(pior['ano'])}, não o "
            'primeiro.</b> Em lavoura perene o aperto raramente cai no primeiro '
            'ano: o café alterna carga alta e baixa, e a soqueira da cana decai '
            'a cada corte até a reforma. Avaliar esta operação pelo DSCR do ano '
            '1 mediria o melhor ano do contrato, não o pior.', ss['Corpo']))


def _cenarios(story, ss, analise: dict) -> None:
    cenarios = (analise.get('stress') or {}).get('scenarios') or []
    if not cenarios:
        return
    _secao(story, ss, 'Cenários de estresse')

    dados = [['Cenário', 'Choque aplicado', 'DSCR mínimo']]
    for cenario in cenarios:
        dados.append([
            str(cenario.get('nome') or '—').replace('_', ' ').capitalize(),
            ', '.join(cenario.get('applied_changes') or []) or '—',
            _numero(cenario.get('dscr_minimo'), 2),
        ])
    _tabela(story, dados, [4.0 * cm, 7.6 * cm, 4.0 * cm])


def _ressalvas(story, ss, analise: dict) -> None:
    avisos = list(analise.get('avisos') or [])
    producao = analise.get('producao') or {}
    if producao.get('sem_curva'):
        avisos.append(
            'Culturas sem curva declarada ficaram fora da projeção: '
            + ', '.join(producao['sem_curva']) + '.')
    if not analise.get('valido'):
        avisos.append(
            'Análise incompleta: faltam dados declarados. Os números acima '
            'cobrem apenas as culturas com curva, preço e custo informados.')
    if not avisos:
        return

    _secao(story, ss, 'Ressalvas')
    for aviso in avisos:
        story.append(Paragraph(f'— {aviso}', ss['Corpo']))
        story.append(Spacer(1, 3))


def gerar_pdf_parecer_perene(analise: dict, identificacao: dict | None = None,
                             branding: dict | None = None) -> bytes:
    """Recebe a saída de `analisar_lavoura_perene` e devolve os bytes do PDF."""
    ss = _styles()
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=2 * cm,
                            bottomMargin=2 * cm, leftMargin=2 * cm,
                            rightMargin=2 * cm)
    story = []

    branding = branding or {}
    logo = _logo_flowable(branding.get('logo_base64') or '')
    if logo is not None:
        story.append(logo)
        story.append(Spacer(1, 6))

    _identificacao(story, ss, analise, identificacao or {},
                   (branding.get('nome_consultoria') or '').strip())
    _composicao(story, ss, analise)
    _curvas(story, ss, analise)
    _projecao(story, ss, analise)
    _capacidade(story, ss, analise)
    _cenarios(story, ss, analise)
    _ressalvas(story, ss, analise)

    doc.build(story)
    return buffer.getvalue()
