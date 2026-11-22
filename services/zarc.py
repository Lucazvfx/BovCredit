"""ZARC — Zoneamento Agrícola de Risco Climático (MAPA) na análise de grãos.

Responde, para cada cultura do plano de safra: plantar nesta data, neste
município, com este solo e este ciclo, cai dentro do zoneamento? Com que risco
de perda (20, 30 ou 40%)? Fora do ZARC não há Proagro nem seguro rural
subvencionado — para o crédito oficial, é impeditivo.

A tábua vem de data/zarc/<safra>/, gerada por scripts/gerar_zarc.py a partir
dos dados abertos do MAPA. A consulta lê só o arquivo da cultura pedida, linha
a linha, em vez de manter a tábua na memória: com preload_app no gunicorn, cada
megabyte residente pesa em todos os workers.
"""
from __future__ import annotations

import calendar
import gzip
import re
import unicodedata
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping, Sequence

PASTA_ZARC = Path(__file__).resolve().parent.parent / 'data' / 'zarc'
FONTE = 'MAPA — Tábua de Risco do Zoneamento Agrícola de Risco Climático (dados abertos, CC-BY)'

# (palavra-chave da cultura, é 2ª safra?) → (arquivo, nome oficial no ZARC)
_CULTURAS = {
    ('SOJA', False): ('soja', 'Soja'),
    ('MILHO', False): ('milho_1_safra', 'Milho 1ª Safra'),
    ('MILHO', True): ('milho_2_safra', 'Milho 2ª Safra'),
    ('FEIJAO', False): ('feijao', 'Feijão'),
    ('FEIJAO', True): ('feijao_2_safra', 'Feijão 2ª Safra'),
    ('ALGODAO', False): ('algodao', 'Algodão Herbáceo'),
    ('ARROZ', False): ('arroz', 'Arroz'),
    ('SORGO', False): ('sorgo', 'Sorgo Granífero'),
    ('SORGO', True): ('sorgo_2_safra', 'Sorgo Granífero 2ª Safra'),
}

SOLOS = {1: 'Arenoso', 2: 'Textura Média', 3: 'Argiloso',
         11: 'AD1', 12: 'AD2', 13: 'AD3', 14: 'AD4', 15: 'AD5', 16: 'AD6'}
CICLOS = {20: 'Grupo I', 21: 'Grupo II', 22: 'Grupo III', 24: 'Grupo IV'}


def _normalizar(texto: str) -> str:
    sem_acento = unicodedata.normalize('NFKD', str(texto or '')).encode('ascii', 'ignore').decode()
    return ' '.join(re.sub(r'[^A-Za-z0-9]+', ' ', sem_acento).upper().split())


def decendio(dia: date) -> int:
    """Decêndio do ano (1–36): dias 1–10, 11–20 e 21–fim de cada mês."""
    return (dia.month - 1) * 3 + min((dia.day - 1) // 10, 2) + 1


def _inicio_fim(dec: int) -> tuple[str, str]:
    mes, parte = (dec - 1) // 3 + 1, (dec - 1) % 3
    fim = (10, 20, calendar.monthrange(2027, mes)[1])[parte]
    return f'{parte * 10 + 1:02d}/{mes:02d}', f'{fim:02d}/{mes:02d}'


def _melhor_janela(riscos: str, perto_de: int | None) -> dict | None:
    """Trecho contínuo de menor risco; com data de plantio, o mais próximo dela.

    A janela pode atravessar a virada do ano (soja no MT: outubro a janeiro),
    por isso a busca roda sobre os 36 decêndios em círculo.
    """
    zoneados = [int(r) for r in riscos if r != '0']
    if not zoneados:
        return None
    menor = str(min(zoneados))
    if riscos.count(menor) == 36:
        return {'risco_pct': int(menor) * 10, 'inicio': '01/01', 'fim': '31/12'}

    # Começa logo depois de um decêndio de outro risco, para não partir uma janela ao meio.
    inicio_busca = next(i for i in range(36) if riscos[i - 1] != menor)
    janelas, atual = [], []
    for k in range(36):
        i = (inicio_busca + k) % 36
        if riscos[i] == menor:
            atual.append(i + 1)
        elif atual:
            janelas.append(atual)
            atual = []
    if atual:
        janelas.append(atual)

    def distancia(janela):
        if perto_de is None:
            return 0
        return min(min(abs(d - perto_de), 36 - abs(d - perto_de)) for d in janela)

    escolhida = min(janelas, key=distancia)
    return {'risco_pct': int(menor) * 10,
            'inicio': _inicio_fim(escolhida[0])[0],
            'fim': _inicio_fim(escolhida[-1])[1]}


def _pasta_safra(ano_agricola: str) -> tuple[Path, str]:
    """'2026/27' → (data/zarc/2026-2027, '2026/2027')."""
    m = re.match(r'\s*(\d{4})', str(ano_agricola or ''))
    inicio = int(m.group(1)) if m else date.today().year
    return PASTA_ZARC / f'{inicio}-{inicio + 1}', f'{inicio}/{inicio + 1}'


@lru_cache(maxsize=4)
def _municipios(pasta: Path) -> dict[tuple[str, str], tuple[str, str]]:
    """(UF, nome normalizado) → (geocódigo, nome oficial). ~5.570 entradas."""
    indice = {}
    with gzip.open(pasta / 'municipios.csv.gz', 'rt', encoding='utf-8') as f:
        for linha in f:
            geo, uf, nome = linha.rstrip('\n').split(';', 2)
            indice[(uf, _normalizar(nome))] = (geo, nome)
    return indice


def _linha_tabua(pasta: Path, arquivo: str, geo: str, solo: int, ciclo: int,
                 manejo: int) -> tuple[str, str] | None:
    prefixo = f'{geo};{solo};{ciclo};{manejo};'
    with gzip.open(pasta / f'{arquivo}.csv.gz', 'rt', encoding='utf-8') as f:
        for linha in f:
            if linha.startswith(prefixo):
                riscos, portaria = linha.rstrip('\n')[len(prefixo):].split(';', 1)
                return riscos, portaria
    return None


def _int(valor: Any) -> int | None:
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None


def _avaliar_cultura(c: Mapping[str, Any], pasta: Path, safra: str, geo: str | None,
                     erro_local: str, solo: int | None, manejo: int) -> dict[str, Any]:
    cultura = str(c.get('cultura') or '').strip().upper()
    safra_tipo = str(c.get('safra_tipo') or '').upper()
    nome = _normalizar(cultura)
    segunda = safra_tipo == '2_SAFRA' or 'SAFRINHA' in nome
    dados = dict(c.get('zarc') or {})
    ciclo = _int(dados.get('cod_ciclo'))
    saida: dict[str, Any] = {
        'cultura': cultura, 'safra_tipo': safra_tipo, 'cultura_zarc': None,
        'status': 'nao_avaliado', 'motivo': '', 'risco_pct': None, 'decendio': None,
        'data_plantio': str(dados.get('data_plantio') or ''), 'cod_ciclo': ciclo,
        'ciclo': CICLOS.get(ciclo, ''), 'melhor_janela': None, 'portaria': '',
    }

    chave = next(((arq, oficial) for (palavra, seg), (arq, oficial) in _CULTURAS.items()
                  if seg == segunda and palavra in nome.split()), None)
    if chave is None:
        saida['motivo'] = f'Sem tábua ZARC para a cultura {cultura} no Orkavyn.'
        return saida
    arquivo, saida['cultura_zarc'] = chave

    if not (pasta / f'{arquivo}.csv.gz').exists():
        saida['motivo'] = f'Tábua ZARC da safra {safra} não carregada.'
        return saida
    if geo is None:
        saida['motivo'] = erro_local
        return saida
    if solo is None or ciclo is None:
        saida['motivo'] = 'Informe o tipo de solo e o grupo (ciclo) da cultivar.'
        return saida

    achado = _linha_tabua(pasta, arquivo, geo, solo, ciclo, manejo)
    if achado is None:
        saida['motivo'] = (f'{saida["cultura_zarc"]} não é zoneada neste município para o solo '
                           f'{SOLOS.get(solo, solo)}, {CICLOS.get(ciclo, ciclo)}'
                           f'{" irrigado" if manejo == 2 else ""}.')
        return saida
    riscos, saida['portaria'] = achado

    try:
        dia = date.fromisoformat(saida['data_plantio'])
    except ValueError:
        dia = None
    dec = decendio(dia) if dia else None
    saida['melhor_janela'] = _melhor_janela(riscos, dec)
    if dec is None:
        saida['motivo'] = 'Informe a data prevista de plantio para avaliar o risco.'
        return saida

    saida['decendio'] = dec
    if riscos[dec - 1] == '0':
        saida['status'] = 'fora'
    else:
        saida['status'] = 'dentro'
        saida['risco_pct'] = int(riscos[dec - 1]) * 10
    return saida


def avaliar_zarc(zarc: Mapping[str, Any], culturas: Sequence[Mapping[str, Any]],
                 ano_agricola: str) -> dict[str, Any]:
    """Consulta o ZARC de cada cultura do plano.

    `zarc` traz o que vale para a fazenda: município, UF (ou geocódigo IBGE),
    cod_solo e irrigado. Cada cultura traz em `zarc` a data_plantio (AAAA-MM-DD)
    e o cod_ciclo (20 = Grupo I, 21 = II, 22 = III).
    """
    pasta, safra = _pasta_safra(ano_agricola)
    geo, municipio, uf = None, str(zarc.get('municipio') or '').strip(), str(zarc.get('uf') or '').strip().upper()
    geo_informado = str(zarc.get('geocodigo') or '').strip()
    if (pasta / 'municipios.csv.gz').exists():
        indice = _municipios(pasta)
        if geo_informado:
            achado = next(((g, n, u) for (u, _), (g, n) in indice.items() if g == geo_informado), None)
        else:
            g_n = indice.get((uf, _normalizar(municipio)))
            achado = (g_n[0], g_n[1], uf) if g_n else None
        if achado:
            geo, municipio, uf = achado
    if geo_informado or municipio:
        erro_local = f'Município {geo_informado or municipio + "/" + uf} não encontrado na tábua ZARC.'
    else:
        erro_local = 'Informe o município e a UF para consultar o ZARC.'

    solo = _int(zarc.get('cod_solo'))
    manejo = 2 if zarc.get('irrigado') else 1
    resultado = [_avaliar_cultura(c, pasta, safra, geo, erro_local, solo, manejo) for c in culturas]
    return {
        'safra': safra, 'municipio': municipio, 'uf': uf, 'geocodigo': geo,
        'cod_solo': solo, 'solo': SOLOS.get(solo, ''), 'irrigado': manejo == 2,
        'fonte': FONTE, 'culturas': resultado,
    }


def avisos_zarc(resultado: Mapping[str, Any] | None) -> list[str]:
    """Avisos para o parecer: fora do zoneamento e risco de 40%."""
    avisos = []
    for c in (resultado or {}).get('culturas') or []:
        janela = c.get('melhor_janela')
        sugestao = (f' Melhor janela: {janela["inicio"]} a {janela["fim"]} '
                    f'({janela["risco_pct"]}% de risco).') if janela else ''
        local = f'{resultado.get("municipio")}/{resultado.get("uf")}'
        if c['status'] == 'fora':
            avisos.append(
                f'ZARC: plantio de {c["cultura"]} em {c["data_plantio"]} fora do zoneamento '
                f'em {local} — sem Proagro nem seguro rural subvencionado.{sugestao}')
        elif c['status'] == 'dentro' and c['risco_pct'] == 40:
            avisos.append(
                f'ZARC: plantio de {c["cultura"]} em {c["data_plantio"]} com risco climático '
                f'de 40% em {local}.{sugestao}')
    return avisos
