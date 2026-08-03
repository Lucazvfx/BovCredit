"""Gera fixtures INDEA sintéticos com o mesmo layout e as mesmas quantidades."""
import os, subprocess
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

DEST = os.path.dirname(os.path.abspath(__file__))

# (arquivo, propriedade, exploracao, pga, linhas[(estratificacao, sexo, qtd)])
CASOS = [
    ('fazenda_alfa.pdf', 'FAZENDA ALFA', '5100000001', '510000000010001',
     [('5 A 12 MESES', 'MACHO', 120), ('13 A 24 MESES', 'MACHO', 483)]),
    ('fazenda_bravo.pdf', 'FAZENDA BRAVO', '5100000002', '510000000020001',
     [('5 A 12 MESES', 'FEMEA', 225), ('5 A 12 MESES', 'MACHO', 55),
      ('13 A 24 MESES', 'FEMEA', 175), ('25 A 36 MESES', 'FEMEA', 5)]),
    ('fazenda_charlie.pdf', 'FAZENDA CHARLIE', '5100000003', '510000000030001',
     [('5 A 12 MESES', 'MACHO', 25), ('13 A 24 MESES', 'FEMEA', 210),
      ('13 A 24 MESES', 'MACHO', 100), ('25 A 36 MESES', 'FEMEA', 113),
      ('25 A 36 MESES', 'MACHO', 30)]),
    # Regressão do bug de 1 dígito: '9' isolado.
    ('fazenda_delta.pdf', 'FAZENDA DELTA', '5100000004', '510000000040001',
     [('5 A 12 MESES', 'MACHO', 15), ('13 A 24 MESES', 'MACHO', 9),
      ('ACIMA DE 36 MESES', 'FEMEA', 53)]),
    ('fazenda_echo.pdf', 'FAZENDA ECHO', '5100000005', '510000000050001',
     [('0 A 4 MESES', 'FEMEA', 340), ('0 A 4 MESES', 'MACHO', 325),
      ('5 A 12 MESES', 'FEMEA', 102), ('13 A 24 MESES', 'FEMEA', 308),
      ('ACIMA DE 36 MESES', 'FEMEA', 2200), ('ACIMA DE 36 MESES', 'MACHO', 17)]),
    # Regressão do bug: ÚNICA linha, quantidade de 1 dígito.
    ('fazenda_foxtrot.pdf', 'FAZENDA FOXTROT', '5100000006', '510000000060001',
     [('25 A 36 MESES', 'FEMEA', 2)]),
]

# Identidade FICTÍCIA. CPF com dígitos verificadores inválidos de propósito,
# para que nem por acidente corresponda a alguém.
CPF_FICTICIO = '00000000000'
NOME_FICTICIO = 'PRODUTOR DE TESTE SINTETICO'

def gerar(nome, propriedade, exploracao, pga, linhas):
    # RETRATO de propósito. O teste de OCR rasteriza e regrava em A4
    # retrato; um fixture em paisagem seria esmagado na horizontal e o
    # tesseract passava a ler '13 A 24' como '13424'. O layout do INDEA
    # é paisagem, mas o que os testes exercitam é o PARSER, não a
    # orientação da folha.
    c = canvas.Canvas(os.path.join(DEST, nome), pagesize=A4)
    L, y = 36, 780
    def p(txt, x=L, dy=20, fonte='Helvetica', tam=12):
        nonlocal y
        c.setFont(fonte, tam); c.drawString(x, y, txt); y -= dy
    p('Sistema de Controle de Animais'); p('Saldo Atual da Exploração')
    y -= 8
    p('SALDO ATUAL DA EXPLORACAO', x=180)
    p(f'EXPLORAÇÃO: {exploracao} - Cód. PGA: {pga} - CADASTRO ATIVO')
    p(f'PROPRIEDADE: {pga[:11]} - {propriedade}')
    p('MUNICÍPIO: MUNICIPIO DE TESTE - MT')
    p('SIT. FUNDIÁRIA: PROPRIETÁRIO')
    y -= 10
    p('PRODUTORES:')
    p('CPF               NOME')
    p(f'{CPF_FICTICIO}      {NOME_FICTICIO}')
    y -= 20
    p('SALDO NORMAL', x=220)
    y -= 6
    p('ESPECIE          ESTRATIFICACAO          SEXO          QUANTIDADE')
    y -= 4
    total = 0
    for estrat, sexo, qtd in linhas:
        total += qtd
        c.setFont('Helvetica', 12)
        c.drawString(L, y, 'BOVINO')
        c.drawString(L + 110, y, estrat)
        c.drawString(L + 300, y, sexo)
        c.drawString(L + 420, y, str(qtd))
        y -= 20
    c.setFont('Helvetica', 12)
    c.drawString(L + 240, y, 'TOTAL DA ESPECIE:'); c.drawString(L + 420, y, str(total)); y -= 24
    c.drawString(L + 340, y, 'Total:'); c.drawString(L + 420, y, str(total)); y -= 30
    p('OBS.:')
    p('A informacao quanto ao numero de animais e declarada de forma voluntaria.')
    c.save()
    return total

for caso in CASOS:
    t = gerar(*caso)
    print(f'{caso[0]:26} total {t}')
