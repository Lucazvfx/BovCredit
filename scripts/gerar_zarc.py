"""Gera os arquivos de ZARC que o app consulta, a partir da tábua de risco do MAPA.

Fonte: MAPA — "Tábua de risco - Zoneamento Agrícola de Risco Climático",
dados.agricultura.gov.br (licença CC-BY). Os códigos de ciclo, solo e manejo
seguem o dicionário de dados publicado junto (dicionario-de-dados-tabua-de-risco-2026.pdf).

O CSV oficial tem ~200 MB e ~1 milhão de linhas. Aqui ficam só as culturas de
grãos que a análise usa, sem os níveis de manejo experimentais (Cod_NM 1–4), e
cada linha vira:

    geocodigo;cod_solo;cod_ciclo;cod_manejo;riscos;portaria

`riscos` são 36 caracteres, um por decêndio do ano: '0' fora do zoneamento,
'2'/'3'/'4' para 20/30/40% de risco. Um arquivo por cultura, para que a consulta
leia só o que precisa sem carregar a tábua inteira na memória.

Rode: python scripts/gerar_zarc.py dados-abertos-tabua-de-risco-safra-2026-2027.csv 2026-2027
"""
import csv
import gzip
import sys
from pathlib import Path

DESTINO = Path(__file__).resolve().parent.parent / 'data' / 'zarc'

# Nome_cultura no CSV oficial → arquivo
CULTURAS = {
    'Soja': 'soja',
    'Milho 1ª Safra': 'milho_1_safra',
    'Milho 2ª Safra': 'milho_2_safra',
    'Feijão': 'feijao',
    'Feijão 2ª Safra': 'feijao_2_safra',
    'Algodão Herbáceo': 'algodao',
    'Arroz': 'arroz',
    'Sorgo Granífero': 'sorgo',
    'Sorgo Granífero 2ª Safra': 'sorgo_2_safra',
}
_RISCO = {'0': '0', '20': '2', '30': '3', '40': '4'}


def gerar(origem: Path, safra: str) -> None:
    pasta = DESTINO / safra
    pasta.mkdir(parents=True, exist_ok=True)
    linhas = {arq: [] for arq in CULTURAS.values()}
    municipios = {}

    with open(origem, encoding='utf-8-sig', newline='') as f:
        for row in csv.DictReader(f, delimiter=';'):
            arq = CULTURAS.get(row['Nome_cultura'])
            if arq is None or row['Cod_NM'] not in ('', '0'):
                continue
            riscos = ''.join(_RISCO[row[f'dec{i}']] for i in range(1, 37))
            linhas[arq].append(';'.join((
                row['geocodigo'], row['Cod_Solo'], row['Cod_Ciclo'],
                row['Cod_Outros_Manejos'], riscos, row['Portaria'])))
            municipios[row['geocodigo']] = (row['UF'], row['municipio'])

    for arq, conteudo in linhas.items():
        _gravar(pasta / f'{arq}.csv.gz', sorted(conteudo))
        print(f'{arq}: {len(conteudo)} linhas')

    _gravar(pasta / 'municipios.csv.gz',
            [f'{geo};{uf};{nome}' for geo, (uf, nome) in sorted(municipios.items())])
    print(f'municipios: {len(municipios)}')


def _gravar(caminho: Path, linhas: list[str]) -> None:
    # mtime=0: regerar a mesma tábua produz o mesmo arquivo, e o git não vê diff.
    with gzip.GzipFile(caminho, 'wb', mtime=0) as g:
        g.write(('\n'.join(linhas) + '\n').encode('utf-8'))


if __name__ == '__main__':
    gerar(Path(sys.argv[1]), sys.argv[2])
