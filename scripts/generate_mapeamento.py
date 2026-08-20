"""Gera data/mapeamento_classificacao.csv a partir da regra que o define.

A tabela não é um trabalho de autoria: é o produto cartesiano entre as faixas
etárias que cada órgão estadual imprime no próprio formulário de declaração e
os dois sexos, rotulado por doze regras de nomenclatura zootécnica. Não há
julgamento por estado — a classificação depende só de (sexo, faixa), e as
mesmas doze regras já aparecem em services/importar_excel.py (_FEMALE_MAP /
_MALE_MAP) e em services/fichas_rebanho/consolidator.py.

Gerar em vez de manter à mão deixa isso explícito e verificável: o teste
test_ficha_sem_planilha_de_terceiro.py compara o CSV distribuído com a saída
deste script.

Rode: python scripts/generate_mapeamento.py
"""
import csv
from pathlib import Path

SAIDA = Path(__file__).resolve().parent.parent / 'data' / 'mapeamento_classificacao.csv'

COLUNAS = ('ORDEM', 'ESPECIE', 'ESTRATIFICACAO', 'SEXO',
           'ESTADO', 'CLASSIFICACAO', 'CHAVE', 'ATIVO')

# As faixas como aparecem no formulário de cada órgão.
QUATRO_FAIXAS = ('0 A 12 MESES', '13 A 24 MESES', '25 A 36 MESES',
                 'ACIMA DE 36 MESES')
CINCO_FAIXAS = ('00 A 04 MESES', '05 A 12 MESES', '13 A 24 MESES',
                '25 A 36 MESES', 'ACIMA DE 36 MESES')

# GO recebe dois documentos: a declaração detalhada (cinco faixas) e o resumo
# "Rebanho por Fazenda" (quatro), que o leitor trata como GO_DECLARACAO. Por
# isso esses modelos carregam as duas formas; MT só recebe a detalhada.
MODELOS = {
    'MT_DECLARACAO': CINCO_FAIXAS,
    'GO_DECLARACAO': ('0 A 12 MESES',) + CINCO_FAIXAS,
    'GO IR':         ('0 A 12 MESES',) + CINCO_FAIXAS,
    'MS':            QUATRO_FAIXAS,
    'MA':            QUATRO_FAIXAS,
    'TO_DECLARACAO': QUATRO_FAIXAS,
    'RO_DECLARACAO': QUATRO_FAIXAS,
    'PA_DECLARACAO': QUATRO_FAIXAS,
}

# Nomenclatura zootécnica: a idade e o sexo dizem o nome do animal.
CLASSIFICACAO = {
    ('FEMEA', '0 A 12 MESES'):      'Bezerra',
    ('FEMEA', '00 A 04 MESES'):     'Bezerra',
    ('FEMEA', '05 A 12 MESES'):     'Bezerra',
    ('FEMEA', '13 A 24 MESES'):     'Bezerra Desmama',
    ('FEMEA', '25 A 36 MESES'):     'Novilha',
    ('FEMEA', 'ACIMA DE 36 MESES'): 'Vaca',
    ('MACHO', '0 A 12 MESES'):      'Bezerro',
    ('MACHO', '00 A 04 MESES'):     'Bezerro',
    ('MACHO', '05 A 12 MESES'):     'Bezerro',
    ('MACHO', '13 A 24 MESES'):     'Bezerro Desmama',
    ('MACHO', '25 A 36 MESES'):     'Garrote',
    ('MACHO', 'ACIMA DE 36 MESES'): 'Boi Gordo',
}


def linhas() -> list[list[str]]:
    saida = []
    for estado, faixas in MODELOS.items():
        for faixa in faixas:
            for sexo in ('FEMEA', 'MACHO'):
                saida.append([
                    str(len(saida) + 1),
                    'BOVINO',
                    faixa,
                    sexo,
                    estado,
                    CLASSIFICACAO[(sexo, faixa)],
                    f'{estado}|{sexo}|{faixa}',
                    'SIM',
                ])
    return saida


def escrever(destino: Path = SAIDA) -> None:
    destino.parent.mkdir(parents=True, exist_ok=True)
    with open(destino, 'w', newline='', encoding='utf-8') as arquivo:
        escritor = csv.writer(arquivo)
        escritor.writerow(COLUNAS)
        escritor.writerows(linhas())


if __name__ == '__main__':
    escrever()
    print(f'Mapeamento gerado: {SAIDA} ({len(linhas())} regras)')
