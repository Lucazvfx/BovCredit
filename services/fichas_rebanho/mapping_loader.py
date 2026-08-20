"""Tabela de-para (estado, sexo, faixa etária) → classificação do rebanho.

A tabela vive em data/mapeamento_classificacao.csv: as faixas são as
publicadas pelos próprios órgãos estaduais (INDEA, IDARON, IAGRO, AGED,
AGRODEFESA, ADAPEC, ADEPARÁ) e a classificação é a nomenclatura zootécnica
correspondente. CSV em vez de planilha porque é o formato que o git versiona
linha a linha — uma mudança de regra aparece no diff.
"""
from __future__ import annotations

import csv
import unicodedata
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class MappingRule:
    ordem: int
    especie: str
    estratificacao: str
    sexo: str
    estado: str
    classificacao: str
    chave: str
    ativo: bool


def _texto(value) -> str:
    return str(value or '').strip()


def _normalizar(value: str) -> str:
    text = unicodedata.normalize('NFKD', _texto(value))
    return ''.join(c for c in text if not unicodedata.combining(c)).upper()


ARQUIVO_MAPEAMENTO = (
    Path(__file__).resolve().parents[2] / 'data' / 'mapeamento_classificacao.csv'
)


class MappingCatalog:
    def __init__(self, rules: list[MappingRule]):
        self.rules = tuple(rules)
        self._by_key = {
            self._key(r.estado, r.sexo, r.estratificacao): r
            for r in self.rules if r.ativo
        }

    @staticmethod
    def _key(estado, sexo, estratificacao) -> str:
        return '|'.join((
            _normalizar(estado),
            _normalizar(sexo),
            _normalizar(estratificacao),
        ))

    def lookup(self, estado, sexo, estratificacao) -> MappingRule | None:
        estado = {
            'GO_DEC_WEB': 'GO_DECLARACAO',
            'AGRODEFESA_GO': 'GO_DECLARACAO',
            # O relatório "Rebanho por Fazenda" não informa a sigla no
            # cabeçalho, mas o layout/faixas e os municípios deste modelo são
            # os mesmos do resumo de declaração de Goiás.
            'RESUMO_FAZENDAS': 'GO_DECLARACAO',
        }.get(_normalizar(estado), estado)
        return self._by_key.get(self._key(estado, sexo, estratificacao))

    def __len__(self):
        return len(self.rules)


def load_mapping(source=None) -> MappingCatalog:
    caminho = Path(source) if source else ARQUIVO_MAPEAMENTO
    with open(caminho, newline='', encoding='utf-8') as arquivo:
        linhas = list(csv.DictReader(arquivo))

    if not linhas:
        raise ValueError('Tabela de mapeamento vazia.')
    colunas = {_normalizar(nome) for nome in (linhas[0].keys())}
    required = {
        'ORDEM', 'ESPECIE', 'ESTRATIFICACAO', 'SEXO',
        'ESTADO', 'CLASSIFICACAO', 'CHAVE', 'ATIVO',
    }
    missing = required - colunas
    if missing:
        raise ValueError(f'Colunas ausentes no MAPEAMENTO: {sorted(missing)}')

    rules = []
    for linha in linhas:
        get = linha.get
        ativo = _normalizar(get('ATIVO')) in {'SIM', 'S', 'TRUE', '1'}
        rules.append(MappingRule(
            ordem=int(get('ORDEM') or 0),
            especie=_texto(get('ESPECIE')).upper(),
            estratificacao=_texto(get('ESTRATIFICACAO')).upper(),
            sexo=_texto(get('SEXO')).upper(),
            estado=_texto(get('ESTADO')).upper(),
            classificacao=_texto(get('CLASSIFICACAO')),
            chave=_texto(get('CHAVE')),
            ativo=ativo,
        ))
    return MappingCatalog(rules)
