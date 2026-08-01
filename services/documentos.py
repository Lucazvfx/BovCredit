"""
Acervo de documentos lidos — o ativo que o sistema estava jogando fora.

Até aqui `/api/ler-pdf` fazia o parse e apagava o arquivo (`os.unlink` no
`finally`). O documento vivia trinta segundos em disco e sumia.

POR QUE ISSO IMPORTA MAIS DO QUE PARECE

Três documentos reais entraram neste projeto e cada um achou uma classe de
defeito que 64 arquivos de teste sintético não acharam:

  ficha de recria (700 cab)  → o simulador vendia a coorte inteira; a receita
                               estava 41% superestimada
  parecer negativo real      → custo 31,5% acima da própria referência e DSCR
                               negativo invertendo a lógica do crédito
  PDF escaneado da ADAPEC-TO → OCR inalcançável, e o parser incompatível com
                               a saída do OCR (linha inteira vs um número por
                               linha)

Aproveitamento de três em três. Um acervo de fichas reais não é arquivo morto:
é o corpus de regressão das seis agências que hoje não têm nenhuma fixture, e
é o dado de calibração das perguntas que hoje só se responde por palpite —
quanto uma fazenda de ciclo completo de fato repõe, qual o desfrute observado.

O QUE SE GUARDA

Três coisas, e a terceira é a que vale mais:

  1. o documento              — para reprocessar quando o parser melhorar
  2. o que o parser extraiu   — para saber o que ele fazia na época
  3. o que o analista corrigiu — cada correção é um rótulo humano dizendo
                                 exatamente onde o parser errou

O par (2, 3) é o que transforma uso em melhoria. Sem ele o acervo é só um
depósito de PDFs.

Módulo puro: hash, comparação e classificação da divergência. A escrita fica
em `database.py`, e o gancho nas rotas em `app.py`.
"""
from __future__ import annotations

import hashlib

# Ordem canônica do vetor de rebanho, igual à do resto do sistema.
FAIXAS = [
    ('f00_F', 'Fêmeas 0–4m'),   ('f00_M', 'Machos 0–4m'),
    ('f05_F', 'Fêmeas 5–12m'),  ('f05_M', 'Machos 5–12m'),
    ('f13_F', 'Fêmeas 13–24m'), ('f13_M', 'Machos 13–24m'),
    ('f25_F', 'Fêmeas 25–36m'), ('f25_M', 'Machos 25–36m'),
    ('fac_F', 'Fêmeas 36m+'),   ('fac_M', 'Machos 36m+'),
]

# Divergência relativa a partir da qual a leitura é tratada como falha, e não
# como ajuste. Abaixo disso o analista está afinando; acima, o parser errou.
# Limiar de política, não de zootecnia.
TOLERANCIA_AJUSTE = 0.02

# Classificação da divergência entre o que o parser leu e o que foi usado.
CONFERE      = 'confere'        # analista aceitou o que o parser leu
AJUSTE       = 'ajuste'         # mexeu pouco — afinação
DIVERGENCIA  = 'divergencia'    # mexeu muito — o parser errou
PARSER_VAZIO = 'parser_vazio'   # parser não leu nada e o analista digitou tudo
SEM_PARSE    = 'sem_parse'      # não houve leitura de documento


def impressao(conteudo: bytes) -> str:
    """SHA-256 do arquivo — identidade estável para deduplicar reenvios.

    O mesmo produtor reenvia a mesma ficha várias vezes numa análise; guardar
    N cópias do mesmo PDF só encarece o banco sem acrescentar informação.
    """
    return hashlib.sha256(conteudo).hexdigest()


def comparar(lido: list | None, usado: list | None) -> dict:
    """Compara o vetor que o parser extraiu com o que o analista de fato usou.

    Devolve a classificação, o total de cada lado e as faixas que mudaram —
    é a lista de faixas que aponta em qual coluna o parser tropeça.
    """
    if not lido or not any(lido):
        if usado and any(usado):
            return {
                'situacao': PARSER_VAZIO,
                'total_lido': 0,
                'total_usado': int(sum(usado)),
                'faixas_alteradas': [f[0] for f in FAIXAS],
                'divergencia_pct': 100.0,
            }
        return {'situacao': SEM_PARSE, 'total_lido': 0, 'total_usado': 0,
                'faixas_alteradas': [], 'divergencia_pct': 0.0}

    lido  = [int(x or 0) for x in (list(lido)  + [0] * 10)[:10]]
    usado = [int(x or 0) for x in (list(usado or []) + [0] * 10)[:10]]

    alteradas = [FAIXAS[i][0] for i in range(10) if lido[i] != usado[i]]
    t_lido, t_usado = sum(lido), sum(usado)

    # A divergência é medida sobre a soma das diferenças por faixa, não sobre a
    # diferença dos totais: trocar 50 cabeças de uma faixa para outra mantém o
    # total e ainda assim é erro de leitura — e é justamente o erro que o OCR
    # comete quando engole um zero e desloca a coluna.
    desvio = sum(abs(lido[i] - usado[i]) for i in range(10))
    div_pct = desvio / max(t_lido, 1) * 100.0

    if not alteradas:
        situacao = CONFERE
    elif div_pct <= TOLERANCIA_AJUSTE * 100:
        situacao = AJUSTE
    else:
        situacao = DIVERGENCIA

    return {
        'situacao':         situacao,
        'total_lido':       t_lido,
        'total_usado':      t_usado,
        'faixas_alteradas': alteradas,
        'divergencia_pct':  round(div_pct, 1),
    }


def vale_revisao(comparacao: dict) -> bool:
    """Casos que merecem virar fixture de teste.

    Não é todo documento: um parse que conferiu não ensina nada. O que ensina
    é o parser ter errado — e é essa fila que vira cobertura das agências sem
    documento real.
    """
    return comparacao.get('situacao') in (DIVERGENCIA, PARSER_VAZIO)
