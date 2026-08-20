"""Fonte única das regras de classificação (data/mapeamento_classificacao.csv)."""
from __future__ import annotations

import csv
from functools import lru_cache
from pathlib import Path
import unicodedata


_ARQUIVO_PADRAO = Path(__file__).resolve().parents[1] / 'data' / 'mapeamento_classificacao.csv'
_COLUNAS = ('ORDEM', 'ESPECIE', 'ESTRATIFICACAO', 'SEXO', 'ESTADO', 'CLASSIFICACAO', 'CHAVE', 'ATIVO')


def _normalizar(valor) -> str:
    texto = str(valor or '').strip().upper()
    return ''.join(
        c for c in unicodedata.normalize('NFKD', texto)
        if not unicodedata.combining(c)
    )


def _estado_mapeamento(estado: str) -> str:
    origem = _normalizar(estado).replace('-', '_').replace(' ', '_')
    return {
        'MT': 'MT_DECLARACAO',
        'RO': 'RO_DECLARACAO',
        'PA': 'PA_DECLARACAO',
        'TO': 'TO_DECLARACAO',
        'GO': 'GO_DECLARACAO',
        'GO_DEC_WEB': 'GO_DECLARACAO',
        'AGRODEFESA_GO': 'GO_DECLARACAO',
        'GO_IR': 'GO IR',
    }.get(origem, origem)


@lru_cache(maxsize=4)
def load_mapeamento(source: str | Path | None = None) -> dict[str, dict]:
    """Carrega as regras ativas da tabela de classificação do projeto."""
    caminho = Path(source) if source else _ARQUIVO_PADRAO
    with open(caminho, newline='', encoding='utf-8') as arquivo:
        linhas = list(csv.DictReader(arquivo))

    if not linhas:
        raise ValueError('Tabela de mapeamento vazia')
    faltando = [c for c in _COLUNAS if c not in linhas[0]]
    if faltando:
        raise ValueError(f'Colunas ausentes no mapeamento: {faltando}')

    regras = {}
    for regra in linhas:
        if _normalizar(regra['ATIVO']) != 'SIM':
            continue
        chave = regra['CHAVE'].strip()
        if not chave:
            chave = f"{regra['ESTADO']}|{regra['SEXO']}|{regra['ESTRATIFICACAO']}"
        regras[chave] = {
            'ordem': int(regra['ORDEM']),
            'especie': regra['ESPECIE'].strip(),
            'estratificacao': regra['ESTRATIFICACAO'].strip(),
            'sexo': regra['SEXO'].strip(),
            'estado': regra['ESTADO'].strip(),
            'classificacao': regra['CLASSIFICACAO'].strip(),
            'chave': chave,
            'ativo': regra['ATIVO'].strip(),
        }
    return regras


def buscar_mapeamento(estado: str, sexo: str, estratificacao: str) -> dict:
    """Busca uma regra por estado, sexo e estratificação, como a macro."""
    estado_excel = _estado_mapeamento(estado)
    sexo_excel = _normalizar(sexo)
    faixa_excel = _normalizar(estratificacao)
    regras = load_mapeamento()
    for regra in regras.values():
        if (
            _normalizar(regra['estado']) == _normalizar(estado_excel)
            and _normalizar(regra['sexo']) == sexo_excel
            and _normalizar(regra['estratificacao']) == faixa_excel
        ):
            return regra
    raise KeyError(f'Mapeamento não encontrado: {estado}|{sexo}|{estratificacao}')


def mapear_animais(animais: dict, estado: str) -> list[dict]:
    """Distribui o rebanho nas classificações definidas no mapeamento."""
    resultado = []
    estado_excel = _estado_mapeamento(estado)
    origem = _normalizar(estado).replace('-', '_').replace(' ', '_')
    # GO/MT possuem regras de 0-4 e 5-12 no modelo INDEA. As linhas
    # agregadas de 0-12 tambem existem na planilha para outros modelos,
    # mas nao podem ser somadas junto com as faixas divididas.
    faixas_divididas = origem in {'MT', 'GO', 'GO_DEC_WEB', 'GO_IR'}
    regras = load_mapeamento()
    for regra in regras.values():
        if _normalizar(regra['estado']) != _normalizar(estado_excel):
            continue
        sexo_key = 'F' if _normalizar(regra['sexo']) == 'FEMEA' else 'M'
        faixa = _normalizar(regra['estratificacao'])
        if faixas_divididas and faixa == '0 A 12 MESES':
            continue
        if faixa == '0 A 12 MESES':
            quantidade = animais.get(f'f00_{sexo_key}', 0) + animais.get(f'f05_{sexo_key}', 0)
        elif faixa == '00 A 04 MESES':
            quantidade = animais.get(f'f00_{sexo_key}', 0)
        elif faixa == '05 A 12 MESES':
            quantidade = animais.get(f'f05_{sexo_key}', 0)
        elif faixa == '13 A 24 MESES':
            quantidade = animais.get(f'f13_{sexo_key}', 0)
        elif faixa == '25 A 36 MESES':
            quantidade = animais.get(f'f25_{sexo_key}', 0)
        elif faixa == 'ACIMA DE 36 MESES':
            quantidade = animais.get(f'fac_{sexo_key}', 0)
        else:
            quantidade = 0
        if quantidade:
            resultado.append({**regra, 'quantidade': int(quantidade)})
    return resultado
