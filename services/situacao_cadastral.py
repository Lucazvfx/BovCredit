"""Consulta gratuita de situação cadastral — CNPJ apenas, fonte oficial.

NÃO é score de crédito. NÃO é o Serasa. É a mesma informação pública que
qualquer pessoa consegue no site da Receita Federal: a empresa está ativa,
baixada, suspensa, inapta ou nula. Sem valor, sem pendência financeira, sem
histórico de pagamento — só existência e regularidade cadastral.

POR QUE SÓ CNPJ

A Receita Federal expõe dados de CNPJ de forma consultável e as fontes
espelho (como a BrasilAPI, usada aqui) automatizam isso de graça. CPF não:
a consulta oficial (servicos.receita.fazenda.gov.br) é protegida por
captcha, feita para uso humano manual — não existe API gratuita e legítima
para automatizar, e produtor rural pessoa física é CPF, não CNPJ. Por isso
`consultar_cpf` não tenta nada — devolve, de forma explícita, que não há
fonte gratuita, em vez de ficar em silêncio ou fingir que consultou.

SOBRE FALHAR ALTO

Uma falha de rede ou um formato de resposta inesperado nunca pode virar
"situação regular" por omissão — isso transformaria indisponibilidade da
BrasilAPI em aprovação de crédito por acidente. O motor devolve
`encontrado=None` (não `False`) quando não consegue responder à pergunta,
e quem chama precisa tratar os três estados: True (existe), False (não
existe/CNPJ inválido) e None (não foi possível verificar).

ESTE MÓDULO NUNCA FOI EXERCITADO CONTRA A API REAL — o ambiente de
desenvolvimento bloqueia saída para hosts fora da lista permitida. O parsing
foi escrito a partir da documentação pública da BrasilAPI (schema estável,
amplamente usado) e testado com fixtures. A primeira chamada em produção é a
validação de verdade.
"""
from __future__ import annotations

import logging
import re

import requests

logger = logging.getLogger(__name__)

BASE_URL = 'https://brasilapi.com.br/api/cnpj/v1'
TIMEOUT = 10  # dispara dentro do request síncrono do analista — sem retry


def _somente_digitos(doc: str) -> str:
    return re.sub(r'\D', '', doc or '')


def validar_cnpj(cnpj: str) -> bool:
    """Checksum oficial (módulo 11) — barra entrada inválida antes da API."""
    d = _somente_digitos(cnpj)
    if len(d) != 14 or d == d[0] * 14:
        return False

    def _dv(base: str, pesos: list[int]) -> int:
        soma = sum(int(n) * p for n, p in zip(base, pesos))
        resto = soma % 11
        return 0 if resto < 2 else 11 - resto

    p1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    p2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    dv1 = _dv(d[:12], p1)
    dv2 = _dv(d[:12] + str(dv1), p2)
    return d[-2:] == f'{dv1}{dv2}'


def validar_cpf(cpf: str) -> bool:
    """Checksum oficial — usado só para identificar o tipo de documento e
    devolver a mensagem certa; nenhuma consulta é feita para CPF."""
    d = _somente_digitos(cpf)
    if len(d) != 11 or d == d[0] * 11:
        return False

    def _dv(base: str, tam: int) -> int:
        soma = sum(int(n) * (tam + 1 - i) for i, n in enumerate(base))
        resto = (soma * 10) % 11
        return 0 if resto == 10 else resto

    dv1 = _dv(d[:9], 9)
    dv2 = _dv(d[:9] + str(dv1), 10)
    return d[-2:] == f'{dv1}{dv2}'


_SEM_FONTE_CPF = (
    'Não existe fonte gratuita e automatizável para consulta de CPF. A '
    'consulta oficial da Receita Federal exige captcha e uso manual — '
    'automatizá-la violaria os termos de uso do serviço. Para verificar '
    'CPF é necessário contratar um bureau de crédito (Serasa, Boa Vista, '
    'Quod) ou um revendedor de dados.'
)


def consultar_cpf(cpf: str) -> dict:
    """Sempre devolve `disponivel=False` — nunca tenta consultar."""
    return {
        'documento': _somente_digitos(cpf),
        'tipo': 'CPF',
        'disponivel': False,
        'motivo': _SEM_FONTE_CPF,
    }


# Códigos da Receita Federal para situação cadastral de CNPJ.
_SITUACOES = {
    1: 'NULA', 2: 'ATIVA', 3: 'SUSPENSA', 4: 'INAPTA', 8: 'BAIXADA',
}


def consultar_cnpj(cnpj: str) -> dict:
    """Consulta situação cadastral na Receita Federal via BrasilAPI.

    Returns:
        dict com `documento`, `tipo`, `disponivel` (True) e, dentro dela:
        `encontrado` (True/False/None — None significa "não foi possível
        verificar", nunca tratar como regular), `situacao`, `data_situacao`,
        `razao_social`, `fonte`, e `erro` quando `encontrado` for None.
    """
    doc = _somente_digitos(cnpj)
    base = {'documento': doc, 'tipo': 'CNPJ', 'disponivel': True,
            'fonte': 'Receita Federal (via BrasilAPI)'}

    if not validar_cnpj(doc):
        return {**base, 'encontrado': False, 'erro': 'CNPJ inválido — dígito verificador não confere.'}

    try:
        resp = requests.get(f'{BASE_URL}/{doc}', timeout=TIMEOUT)
    except requests.RequestException as exc:
        logger.warning('[situacao_cadastral] falha de rede consultando %s: %s', doc, exc)
        return {**base, 'encontrado': None, 'erro': f'Falha de rede: {exc}'}

    if resp.status_code == 404:
        return {**base, 'encontrado': False, 'erro': 'CNPJ não encontrado na base da Receita Federal.'}
    if resp.status_code != 200:
        logger.warning('[situacao_cadastral] BrasilAPI devolveu %s para %s', resp.status_code, doc)
        return {**base, 'encontrado': None, 'erro': f'Serviço indisponível (HTTP {resp.status_code}).'}

    try:
        payload = resp.json()
        situacao = payload.get('descricao_situacao_cadastral') or _SITUACOES.get(
            payload.get('situacao_cadastral'), 'DESCONHECIDA')
    except (ValueError, AttributeError) as exc:
        logger.error('[situacao_cadastral] resposta em formato inesperado para %s: %s', doc, exc)
        return {**base, 'encontrado': None, 'erro': f'Resposta em formato inesperado: {exc}'}

    return {
        **base,
        'encontrado': True,
        'situacao': situacao,
        'regular': situacao == 'ATIVA',
        'data_situacao': payload.get('data_situacao_cadastral'),
        'motivo_situacao': payload.get('motivo_situacao_cadastral') or None,
        'razao_social': payload.get('razao_social'),
        'municipio': payload.get('municipio'),
        'uf': payload.get('uf'),
    }


def consultar(documento: str) -> dict:
    """Detecta CPF (11 dígitos) ou CNPJ (14) e roteia para a função certa."""
    doc = _somente_digitos(documento)
    if len(doc) == 11:
        return consultar_cpf(doc)
    if len(doc) == 14:
        return consultar_cnpj(doc)
    return {
        'documento': doc, 'tipo': None, 'disponivel': False,
        'encontrado': False,
        'erro': f'Documento com {len(doc)} dígitos — CPF tem 11, CNPJ tem 14.',
    }
