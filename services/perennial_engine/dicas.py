"""Dicas calculadas sobre a análise — não texto genérico de tooltip.

"DSCR é caixa dividido por serviço da dívida" o analista lê uma vez e nunca
mais. O que muda o trabalho dele é a frase que olha o dado DELE: a carência
que vence antes da lavoura produzir, os talhões todos na mesma carga, o
cenário que descobre a operação.

Vive no backend, e não na tela, pelo mesmo motivo de services/origem_rebanho.py:
tela e PDF divergirem sobre a leitura da mesma análise seria pior que nenhum
dos dois dizer nada.
"""
from __future__ import annotations

from typing import Any

ATENCAO = 'atencao'
INFORMACAO = 'informacao'


def _int(valor, padrao=0) -> int:
    try:
        return int(float(valor))
    except (TypeError, ValueError):
        return padrao


def _primeiro_ano_produtivo(producao: dict) -> int | None:
    for linha in producao.get('anos') or []:
        if float(linha.get('producao_total') or 0) > 0:
            return _int(linha.get('ano'))
    return None


def _dica(tipo: str, titulo: str, texto: str) -> dict[str, str]:
    return {'tipo': tipo, 'titulo': titulo, 'texto': texto}


def _carencia_curta(analise: dict, credito: dict) -> dict | None:
    """A dica mais acionável da perene: carência que vence antes da produção.

    Financiar formação de lavoura com carência curta é o erro clássico — o
    contrato começa a cobrar num ano em que o talhão ainda não devolveu nada.
    """
    carencia_anos = _int(credito.get('carencia_meses')) / 12
    primeiro = _primeiro_ano_produtivo(analise.get('producao') or {})
    if not primeiro or primeiro <= 1:
        return None
    if carencia_anos >= primeiro - 1:
        return None
    sugerida = (primeiro - 1) * 12
    return _dica(
        ATENCAO, 'A carência vence antes da lavoura produzir',
        f'A primeira produção sai no ano {primeiro}, e a carência de '
        f'{_int(credito.get("carencia_meses"))} meses termina antes disso. '
        f'O contrato passa a cobrar num período sem receita da lavoura. '
        f'Carência de {sugerida} meses alcança a primeira colheita.')


def _anos_negativos(analise: dict) -> dict | None:
    negativos = (analise.get('economico') or {}).get('anos_negativos') or ()
    if not negativos:
        return None
    lista = ', '.join(str(n) for n in negativos)
    return _dica(
        INFORMACAO, 'Resultado negativo não é motivo de recusa aqui',
        f'O resultado operacional é negativo no(s) ano(s) {lista}. Em lavoura '
        'perene isso é o comportamento esperado do talhão em formação, que '
        'consome caixa antes de produzir. O que a análise pede não é recusa: '
        'é carência que cubra esse período, ou receita de outra fonte.')


def _ano_critico(analise: dict) -> dict | None:
    pior = ((analise.get('credito') or {}).get('analysis') or {}).get('pior_periodo') or {}
    ano = _int(pior.get('ano'))
    if ano <= 1:
        return None
    return _dica(
        ATENCAO, f'Avalie pelo ano {ano}, não pelo primeiro',
        f'O DSCR mínimo do contrato cai no ano {ano}. Em perene o aperto '
        'raramente é no ano 1: o café alterna carga alta e baixa, e a soqueira '
        'da cana decai a cada corte. Olhar só o primeiro ano mede o melhor ano '
        'do contrato.')


def _cenarios_descobertos(analise: dict) -> dict | None:
    cenarios = (analise.get('stress') or {}).get('scenarios') or []
    descobertos = [c for c in cenarios if c.get('uncovered')]
    if not descobertos:
        return None
    nomes = ', '.join(str(c.get('nome', '')).replace('_', ' ') for c in descobertos)
    return _dica(
        ATENCAO,
        f'{len(descobertos)} de {len(cenarios)} cenários descobrem a operação',
        f'Em {nomes} o DSCR cai abaixo de 1 — a geração de caixa não cobre o '
        'serviço da dívida. Vale discutir garantia adicional, prazo maior ou '
        'valor menor antes de levar a comitê.')


def _carga_alinhada(analise: dict) -> dict | None:
    producao = analise.get('producao') or {}
    if not any('mesma fase de carga' in aviso for aviso in producao.get('avisos') or []):
        return None
    return _dica(
        INFORMACAO, 'A lavoura inteira oscila junta',
        'Todos os talhões estão na mesma fase de carga, então o ano de carga '
        'baixa aperta o caixa de uma vez. Escalonar a poda entre talhões não '
        'muda a produção total do período — muda o fundo do poço, que é o que '
        'o DSCR mínimo mede.')


def _curva_sem_fonte(analise: dict) -> dict | None:
    sem_fonte = sorted(
        nome for nome, curva in (analise.get('curvas') or {}).items()
        if not (curva.get('fonte') or '').strip())
    if not sem_fonte:
        return None
    return _dica(
        ATENCAO, 'A curva de produtividade não tem fonte',
        f'A curva de {", ".join(sem_fonte)} está sem fonte declarada. Toda a '
        'projeção depende dela, e no parecer ela aparece como declaração do '
        'analista. Preencher a coluna Fonte na ficha — Embrapa, IAC, Conab ou '
        'laudo — muda o peso do documento em comitê.')


def _dados_faltando(analise: dict) -> dict | None:
    if analise.get('valido'):
        return None
    sem_curva = (analise.get('producao') or {}).get('sem_curva') or ()
    detalhe = (f' Sem curva declarada: {", ".join(sem_curva)}.' if sem_curva else '')
    return _dica(
        ATENCAO, 'A análise está incompleta',
        'Faltam dados declarados na ficha, então os números cobrem apenas as '
        'culturas com curva, preço e custo informados.' + detalhe)


def gerar_dicas(analise: dict, credito: dict | None = None) -> list[dict[str, str]]:
    """Lê a análise pronta e devolve o que vale dizer sobre ela."""
    credito = credito or {}
    candidatas = (
        _dados_faltando(analise),
        _carencia_curta(analise, credito),
        _cenarios_descobertos(analise),
        _ano_critico(analise),
        _anos_negativos(analise),
        _carga_alinhada(analise),
        _curva_sem_fonte(analise),
    )
    return [dica for dica in candidatas if dica]
